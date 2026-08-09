from database import get_connection
from services.backups import get_backup_status
from services.followups import get_due_follow_up_reminders
from services.operational_errors import get_operational_error_summary
from services.patient_records import get_patient_by_identifier, get_registered_patient_count, register_patient
from services.paystack import (
    grant_manual_payment_override,
    is_payment_within_validity_window,
    list_payment_events,
    revoke_manual_payment_override,
)
from datetime import datetime, timezone
import hashlib
import json
from .medical_report_app_service import list_admin_medical_report_requests
from .partner_app_service import list_partner_facilities
from synmed_utils.doctor_profiles import create_or_update_profile, get_profile_by_identifier
from .auth_service import (
    _allocate_web_doctor_id,
    _save_doctor_license_upload,
    get_delivery_status,
    hash_patient_password,
    send_email_with_attachment,
    send_patient_web_access_setup,
    send_plain_email,
)
from .auth_service import _deliver_otp_checked as deliver_otp_checked
from .internal_mail_service import send_internal_message
from .settings_service import (
    get_email_branding_settings,
    get_payment_settings,
    get_paystack_readiness,
    update_email_branding_settings,
    update_payment_settings,
)
from pathlib import Path


UTC = timezone.utc


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def record_admin_audit(
    admin_id: int,
    action: str,
    target_type: str,
    target_id: str,
    details: dict | str | None = None,
) -> None:
    if isinstance(details, dict):
        serialized_details = json.dumps(details, ensure_ascii=True)
    else:
        serialized_details = details or ""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO admin_audit_logs (
                admin_id, action, target_type, target_id, details, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (admin_id, action, target_type, str(target_id), serialized_details, _now_iso()),
        )
        conn.commit()


def list_admin_audit_logs(limit: int = 100) -> list[dict]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, admin_id, action, target_type, target_id, details, created_at
            FROM admin_audit_logs
            ORDER BY id DESC
            LIMIT ?
            """,
            (max(1, min(limit, 250)),),
        )
        rows = cursor.fetchall()

    records = []
    for row in rows:
        details = row["details"] or ""
        try:
            details = json.loads(details) if details else {}
        except json.JSONDecodeError:
            pass
        records.append({**dict(row), "details": details})
    return records


def _alert_signature(alert: dict) -> str:
    content = json.dumps(
        {
            "id": alert["id"],
            "title": alert["title"],
            "message": alert["message"],
            "href": alert["href"],
        },
        ensure_ascii=True,
        sort_keys=True,
    )
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:24]


def _get_admin_alert_states(admin_id: int) -> dict[tuple[str, str], dict]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT alert_id, alert_signature, reviewed_at, dismissed_at
            FROM admin_alert_states
            WHERE admin_id = ?
            """,
            (admin_id,),
        )
        rows = cursor.fetchall()
    return {
        (row["alert_id"], row["alert_signature"]): dict(row)
        for row in rows
    }


def get_admin_alerts(admin_id: int | None = None) -> dict:
    from .support_ai_service import list_support_tickets

    summary = get_admin_summary()
    payment_records = list_admin_payments()["payments"]
    backup_status = get_backup_status()
    error_summary = get_operational_error_summary()
    support_tickets = list_support_tickets("open", 250)
    verified_doctors = summary["verified_doctor_records"]
    expired = [doctor for doctor in verified_doctors if (doctor["license_status"].get("days_left") or 0) < 0]
    expiring = [
        doctor
        for doctor in verified_doctors
        if doctor["license_status"].get("days_left") is not None
        and 0 <= doctor["license_status"]["days_left"] <= 14
    ]
    unassigned_reports = [
        request
        for request in list_admin_medical_report_requests()["requests"]
        if not request.get("doctor_id")
    ]
    delivery = get_admin_delivery_settings()
    alerts = []

    if summary["pending_doctors"]:
        alerts.append({
            "id": "pending-doctors",
            "tone": "warning",
            "title": "Doctor applications awaiting review",
            "message": f"{summary['pending_doctors']} application(s) need an admin decision.",
            "href": "/admin/doctors",
        })
    if summary.get("pending_customer_care_agents"):
        alerts.append({
            "id": "pending-customer-care-agents",
            "tone": "warning",
            "title": "Customer-care accounts awaiting approval",
            "message": f"{summary['pending_customer_care_agents']} customer-care account request(s) need review.",
            "href": "/customer-care?panel=accounts",
        })
    if support_tickets:
        alerts.append({
            "id": "open-support-tickets",
            "tone": "warning",
            "title": "Open customer support tickets",
            "message": f"{len(support_tickets)} support ticket(s) are still open.",
            "href": "/admin/ticket-log?filter=open",
        })
    recent_errors = error_summary.get("last_24h", {}).get("error", 0)
    if recent_errors:
        alerts.append({
            "id": "backend-errors",
            "tone": "danger",
            "title": "Backend errors recorded",
            "message": f"{recent_errors} backend error(s) were recorded in the last 24 hours.",
            "href": "/admin/errors?severity=error",
        })
    if not backup_status.get("latest_backup"):
        alerts.append({
            "id": "backup-missing",
            "tone": "danger",
            "title": "No backup has been created",
            "message": "Create and download a full backup from admin settings.",
            "href": "/admin/settings",
        })
    elif backup_status["latest_backup"].get("created_at"):
        try:
            latest_created = datetime.fromisoformat(backup_status["latest_backup"]["created_at"])
            age_hours = (datetime.now(UTC) - latest_created).total_seconds() / 3600
        except ValueError:
            age_hours = 0
        if age_hours > 72:
            alerts.append({
                "id": "backup-old",
                "tone": "warning",
                "title": "Latest backup is older than 72 hours",
                "message": "Download a fresh full backup before further production changes.",
                "href": "/admin/settings",
            })
    if not backup_status.get("storage_exists"):
        alerts.append({
            "id": "storage-missing",
            "tone": "danger",
            "title": "Persistent storage folder is missing",
            "message": "Stored documents, media, and licence uploads may not persist.",
            "href": "/admin/settings",
        })
    if expired:
        alerts.append({
            "id": "expired-licences",
            "tone": "danger",
            "title": "Expired doctor licences",
            "message": f"{len(expired)} verified doctor licence(s) have expired.",
            "href": "/admin/doctors?filter=expired",
        })
    if expiring:
        alerts.append({
            "id": "expiring-licences",
            "tone": "warning",
            "title": "Licences nearing expiry",
            "message": f"{len(expiring)} doctor licence(s) expire within 14 days.",
            "href": "/admin/doctors?filter=expiring",
        })
    if unassigned_reports:
        alerts.append({
            "id": "unassigned-reports",
            "tone": "warning",
            "title": "Unassigned medical reports",
            "message": f"{len(unassigned_reports)} medical report request(s) need a doctor.",
            "href": "/admin/reports?filter=unassigned",
        })
    pending_payments = [
        payment
        for payment in payment_records
        if payment.get("status") not in {"verified", "no_payment"}
        and not payment.get("patient_archived_at")
    ]
    patients_without_payment = [
        payment for payment in payment_records if payment.get("status") == "no_payment"
    ]
    if pending_payments:
        alerts.append({
            "id": "pending-payments",
            "tone": "warning",
            "title": "Payments awaiting completion",
            "message": f"{len(pending_payments)} payment record(s) are pending or incomplete.",
            "href": "/admin/payments?filter=pending",
        })
    if patients_without_payment:
        alerts.append({
            "id": "missing-payments",
            "tone": "warning",
            "title": "Patients without payment records",
            "message": f"{len(patients_without_payment)} patient(s) have no payment record.",
            "href": "/admin/payments?filter=no_payment",
        })
    unavailable_channels = [
        channel
        for channel in ("email", "telegram")
        if not delivery.get(channel, {}).get("ready")
    ]
    if unavailable_channels:
        alerts.append({
            "id": "delivery-setup",
            "tone": "danger",
            "title": "Delivery channel needs attention",
            "message": f"{', '.join(unavailable_channels).title()} delivery is not ready.",
            "href": "/admin/settings",
        })

    if admin_id is None:
        return {"alerts": alerts, "generated_at": _now_iso()}

    states = _get_admin_alert_states(admin_id)
    visible_alerts = []
    for alert in alerts:
        signature = _alert_signature(alert)
        state = states.get((alert["id"], signature), {})
        if state.get("dismissed_at"):
            continue
        visible_alerts.append(
            {
                **alert,
                "signature": signature,
                "reviewed": bool(state.get("reviewed_at")),
                "reviewed_at": state.get("reviewed_at"),
                "dismissible": alert["tone"] != "danger",
            }
        )
    return {"alerts": visible_alerts, "generated_at": _now_iso()}


def update_admin_alert_state(admin_id: int, alert_id: str, action: str) -> dict:
    alerts = get_admin_alerts()["alerts"]
    alert = next((item for item in alerts if item["id"] == alert_id), None)
    if not alert:
        return {"updated": False, "message": "This alert is no longer active."}

    normalized_action = (action or "").strip().lower()
    if normalized_action not in {"review", "dismiss"}:
        return {"updated": False, "message": "Unsupported alert action."}
    if normalized_action == "dismiss" and alert["tone"] == "danger":
        return {"updated": False, "message": "Critical alerts cannot be dismissed."}

    now = _now_iso()
    signature = _alert_signature(alert)
    reviewed_at = now
    dismissed_at = now if normalized_action == "dismiss" else None
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO admin_alert_states (
                admin_id, alert_id, alert_signature, reviewed_at, dismissed_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(admin_id, alert_id, alert_signature)
            DO UPDATE SET
                reviewed_at = excluded.reviewed_at,
                dismissed_at = COALESCE(excluded.dismissed_at, admin_alert_states.dismissed_at),
                updated_at = excluded.updated_at
            """,
            (admin_id, alert_id, signature, reviewed_at, dismissed_at, now),
        )
        conn.commit()

    return {
        "updated": True,
        "message": "Alert dismissed." if normalized_action == "dismiss" else "Alert marked as reviewed.",
        "alert_id": alert_id,
        "signature": signature,
        "reviewed_at": reviewed_at,
        "dismissed_at": dismissed_at,
    }


def _license_status(expiry_date: str) -> dict:
    if not expiry_date:
        return {"label": "No expiry set", "tone": "warning", "days_left": None}
    try:
        expiry = datetime.strptime(expiry_date, "%Y-%m-%d").date()
    except ValueError:
        return {"label": "Invalid expiry", "tone": "warning", "days_left": None}

    days_left = (expiry - datetime.now(UTC).date()).days
    if days_left < 0:
        return {"label": "Expired", "tone": "danger", "days_left": days_left}
    if days_left <= 14:
        return {"label": f"Expires in {days_left} day{'s' if days_left != 1 else ''}", "tone": "warning", "days_left": days_left}
    return {"label": "Current", "tone": "success", "days_left": days_left}


def _fetch_verified_doctors() -> list[dict]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                d.telegram_id,
                d.doctor_id,
                d.status,
                COALESCE(dp.name, 'Doctor') AS name,
                COALESCE(dp.specialty, 'N/A') AS specialty,
                COALESCE(dp.experience, 'N/A') AS experience,
                COALESCE(dp.email, '') AS email,
                COALESCE(dp.phone, '') AS phone,
                COALESCE(dp.license_id, '') AS license_id,
                COALESCE(dp.license_expiry_date, '') AS license_expiry_date,
                COALESCE(dp.license_file_id, '') AS license_file_id,
                COALESCE(dp.license_file_name, '') AS license_file_name,
                dp.license_file_size,
                COALESCE(drp.status, 'offline') AS runtime_status
            FROM doctors d
            INNER JOIN doctor_profiles dp ON dp.telegram_id = d.telegram_id
            LEFT JOIN doctor_runtime_presence drp ON drp.doctor_id = d.telegram_id
            WHERE d.status = 'verified' AND dp.verified = 1
            ORDER BY dp.name COLLATE NOCASE ASC, d.telegram_id ASC
            """
        )
        rows = cursor.fetchall()
    records = []
    for row in rows:
        license_file_id = row["license_file_id"] or ""
        records.append({
            "telegram_id": row["telegram_id"],
            "doctor_id": row["doctor_id"] or "",
            "name": row["name"],
            "specialty": row["specialty"],
            "experience": row["experience"],
            "email": row["email"],
            "phone": row["phone"],
            "license_id": row["license_id"],
            "license_expiry_date": row["license_expiry_date"],
            "license_status": _license_status(row["license_expiry_date"] or ""),
            "license_file_url": (
                f"/doctor-application-files/{license_file_id.replace('doctor_application_files/', '', 1)}"
                if license_file_id.startswith("doctor_application_files/")
                else ""
            ),
            "license_file_name": row["license_file_name"] or "",
            "license_file_size": row["license_file_size"] or None,
            "status": row["runtime_status"],
            "account_status": row["status"] or "verified",
        })
    return records


def _fetch_suspended_doctors() -> list[dict]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                dp.telegram_id,
                COALESCE(d.doctor_id, CAST(dp.telegram_id AS TEXT)) AS doctor_id,
                COALESCE(d.status, 'suspended') AS account_status,
                COALESCE(dp.name, 'Doctor') AS name,
                COALESCE(dp.specialty, 'N/A') AS specialty,
                COALESCE(dp.experience, 'N/A') AS experience,
                COALESCE(dp.email, '') AS email,
                COALESCE(dp.phone, '') AS phone,
                COALESCE(dp.license_id, '') AS license_id,
                COALESCE(dp.license_expiry_date, '') AS license_expiry_date,
                COALESCE(dp.license_file_id, '') AS license_file_id,
                COALESCE(dp.license_file_name, '') AS license_file_name,
                dp.license_file_size
            FROM doctor_profiles dp
            LEFT JOIN doctors d ON d.telegram_id = dp.telegram_id
            WHERE COALESCE(dp.verified, 0) = 0
              AND COALESCE(d.status, '') = 'suspended'
            ORDER BY dp.name COLLATE NOCASE ASC, dp.telegram_id ASC
            """
        )
        rows = cursor.fetchall()

    records = []
    for row in rows:
        license_file_id = row["license_file_id"] or ""
        records.append({
            "telegram_id": row["telegram_id"],
            "doctor_id": row["doctor_id"] or "",
            "name": row["name"],
            "specialty": row["specialty"],
            "experience": row["experience"],
            "email": row["email"],
            "phone": row["phone"],
            "license_id": row["license_id"],
            "license_expiry_date": row["license_expiry_date"],
            "license_status": _license_status(row["license_expiry_date"] or ""),
            "license_file_url": (
                f"/doctor-application-files/{license_file_id.replace('doctor_application_files/', '', 1)}"
                if license_file_id.startswith("doctor_application_files/")
                else ""
            ),
            "license_file_name": row["license_file_name"] or "",
            "license_file_size": row["license_file_size"] or None,
            "status": "suspended",
            "account_status": row["account_status"],
        })
    return records


def _active_consultation_count() -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) AS total FROM active_consultations_runtime")
        row = cursor.fetchone()
    return row["total"] if row else 0


def _customer_care_account_summary() -> dict:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT status, COUNT(*) AS total
            FROM customer_care_accounts
            GROUP BY status
            """
        )
        counts = {row["status"] or "unknown": int(row["total"]) for row in cursor.fetchall()}
        cursor.execute(
            """
            SELECT account_id, email, display_name, status, created_by_admin_id,
                   created_at, updated_at, last_login_at
            FROM customer_care_accounts
            ORDER BY
                CASE status
                    WHEN 'pending' THEN 0
                    WHEN 'active' THEN 1
                    WHEN 'suspended' THEN 2
                    WHEN 'rejected' THEN 3
                    ELSE 4
                END,
                display_name COLLATE NOCASE ASC
            LIMIT 20
            """
        )
        records = [dict(row) for row in cursor.fetchall()]
    return {
        "total": sum(counts.values()),
        "active": counts.get("active", 0),
        "pending": counts.get("pending", 0),
        "suspended": counts.get("suspended", 0),
        "rejected": counts.get("rejected", 0),
        "records": records,
    }


def get_admin_summary() -> dict:
    verified_doctors = _fetch_verified_doctors()
    suspended_doctors = _fetch_suspended_doctors()
    medical_report_requests = list_admin_medical_report_requests()["requests"]
    partner_summary = list_partner_facilities()["summary"]
    pending_doctor_applications = list_pending_doctor_applications()
    customer_care_summary = _customer_care_account_summary()
    return {
        "registered_patients": get_registered_patient_count(),
        "verified_doctors": len(verified_doctors),
        "suspended_doctors": len(suspended_doctors),
        "pending_doctors": len(pending_doctor_applications),
        "verified_doctor_records": verified_doctors,
        "suspended_doctor_records": suspended_doctors,
        "pending_doctor_applications": pending_doctor_applications,
        "active_consultations": _active_consultation_count(),
        "due_followups": len(get_due_follow_up_reminders()),
        "medical_report_requests": len(medical_report_requests),
        "partners": partner_summary["total"],
        "active_partners": partner_summary["active"],
        "pending_partners": partner_summary["pending"],
        "customer_care_agents": customer_care_summary["total"],
        "verified_customer_care_agents": customer_care_summary["active"],
        "pending_customer_care_agents": customer_care_summary["pending"],
        "suspended_customer_care_agents": customer_care_summary["suspended"],
        "rejected_customer_care_agents": customer_care_summary["rejected"],
        "customer_care_account_records": customer_care_summary["records"],
    }


def list_admin_patients(query: str = "", limit: int = 100, include_archived: bool = False) -> list[dict]:
    normalized = f"%{(query or '').strip()}%"
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                p.id, p.patient_id, p.telegram_id, p.name, p.age, p.gender,
                p.phone, p.email, p.email_verified_at, p.created_at,
                p.archived_at, p.archived_by_admin_id, p.archived_reason,
                COUNT(c.id) AS consultation_count,
                MAX(c.created_at) AS last_consultation_at
            FROM patients p
            LEFT JOIN consultations c ON c.patient_id = p.patient_id
            WHERE (? = 1 OR p.archived_at IS NULL)
              AND (
                ? = '%%'
                OR p.patient_id LIKE ?
                OR COALESCE(p.name, '') LIKE ?
                OR COALESCE(p.email, '') LIKE ?
                OR COALESCE(p.phone, '') LIKE ?
              )
            GROUP BY p.id
            ORDER BY COALESCE(p.archived_at, '') ASC, p.created_at DESC
            LIMIT ?
            """,
            (1 if include_archived else 0, normalized, normalized, normalized, normalized, normalized, max(1, min(limit, 250))),
        )
        rows = cursor.fetchall()
    return [dict(row) for row in rows]


def search_admin_records(query: str, limit: int = 12) -> dict:
    normalized = (query or "").strip()
    if len(normalized) < 2:
        return {"patients": [], "doctors": []}
    patients = list_admin_patients(normalized, limit)
    pattern = f"%{normalized}%"
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT telegram_id, name, specialty, email, license_id
            FROM doctor_profiles
            WHERE name LIKE ? OR specialty LIKE ? OR email LIKE ?
               OR license_id LIKE ? OR CAST(telegram_id AS TEXT) LIKE ?
            ORDER BY name COLLATE NOCASE
            LIMIT ?
            """,
            (pattern, pattern, pattern, pattern, pattern, max(1, min(limit, 50))),
        )
        doctors = [dict(row) for row in cursor.fetchall()]
    return {"patients": patients, "doctors": doctors}


def get_admin_patient_detail(patient_id: str) -> dict | None:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, patient_id, telegram_id, name, age, gender, phone, email,
                   email_verified_at, address, allergy, medical_conditions,
                   created_at, updated_at, archived_at, archived_by_admin_id, archived_reason
            FROM patients
            WHERE UPPER(patient_id) = UPPER(?)
            """,
            (patient_id,),
        )
        patient = cursor.fetchone()
        if not patient:
            return None

        document_queries = [
            (
                "prescription",
                """
                SELECT rx_id AS document_id, consultation_id, doctor_id, created_at,
                       asset_path, asset_type
                FROM prescriptions WHERE patient_id = ?
                """,
            ),
            (
                "investigation",
                """
                SELECT request_id AS document_id, consultation_id, doctor_id, created_at,
                       asset_path, asset_type
                FROM investigation_requests WHERE patient_id = ?
                """,
            ),
            (
                "report",
                """
                SELECT letter_id AS document_id, consultation_id, doctor_id, created_at,
                       asset_path, asset_type
                FROM clinical_letters
                WHERE patient_id = ? AND letter_type = 'medical_report'
                """,
            ),
        ]
        documents = []
        for kind, statement in document_queries:
            cursor.execute(statement, (patient_id,))
            for row in cursor.fetchall():
                filename = Path(row["asset_path"] or "").name
                documents.append({
                    **dict(row),
                    "kind": kind,
                    "title": kind.replace("_", " ").title(),
                    "filename": filename,
                    "asset_url": f"/generated-documents/{filename}" if filename else "",
                })
        documents.sort(key=lambda item: item["created_at"] or "", reverse=True)

    return {"patient": dict(patient), "documents": documents}


def archive_admin_patient_record(admin_id: int, patient_id: str, reason: str = "") -> dict:
    normalized_patient_id = (patient_id or "").strip()
    if not normalized_patient_id:
        return {"archived": False, "message": "Patient record was not selected.", "patient": None}
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, patient_id, name, archived_at
            FROM patients
            WHERE UPPER(patient_id) = UPPER(?)
            """,
            (normalized_patient_id,),
        )
        patient = cursor.fetchone()
        if not patient:
            return {"archived": False, "message": "Patient record could not be found.", "patient": None}
        if patient["archived_at"]:
            return {"archived": True, "message": "Patient record is already archived.", "patient": dict(patient)}
        cursor.execute(
            """
            UPDATE patients
            SET archived_at = ?, archived_by_admin_id = ?, archived_reason = ?, updated_at = ?
            WHERE UPPER(patient_id) = UPPER(?)
            """,
            (_now_iso(), admin_id, (reason or "").strip(), _now_iso(), normalized_patient_id),
        )
        conn.commit()
    return {
        "archived": True,
        "message": "Patient record archived. Clinical, payment, and audit history were preserved.",
        "patient": {"patient_id": normalized_patient_id, "name": patient["name"]},
    }


def send_admin_patient_document(
    *,
    admin_id: int,
    patient_id: str,
    document_kind: str,
    document_id: str,
    recipient_type: str,
    doctor_id: str = "",
    message: str = "",
) -> dict:
    detail = get_admin_patient_detail(patient_id)
    if not detail:
        return {"sent": False, "message": "Patient record could not be found."}
    document = next(
        (
            item for item in detail["documents"]
            if item["kind"] == document_kind and item["document_id"] == document_id
        ),
        None,
    )
    if not document or not document["asset_path"]:
        return {"sent": False, "message": "Document file could not be found."}

    path = Path(document["asset_path"])
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[4] / path
    if not path.exists():
        return {"sent": False, "message": "Document file is no longer available."}

    subject = f"SynMed {document['title']} for {detail['patient']['name']}"
    if recipient_type == "patient":
        email = (detail["patient"]["email"] or "").strip()
        if not email:
            return {"sent": False, "message": "Patient does not have an email address."}
        sent = send_email_with_attachment(
            email,
            subject,
            message or "Please find your SynMed clinical document attached.",
            document["filename"],
            path.read_bytes(),
            document["asset_type"] or "application/pdf",
        )
        return {
            "sent": sent,
            "message": "Document emailed to patient." if sent else "Document email could not be sent.",
        }
    if recipient_type == "doctor" and doctor_id:
        return send_internal_message(
            sender_role="admin",
            sender_id=admin_id,
            recipient_role="doctor",
            recipient_id=doctor_id,
            subject=subject,
            body=message or f"Clinical document for patient {patient_id}.",
            attachment_name=document["filename"],
            attachment_url=document["asset_url"],
            attachment_type=document["asset_type"] or "application/pdf",
        )
    return {"sent": False, "message": "Select a valid document recipient."}


def list_admin_payments() -> dict:
    with get_connection() as conn:
        cursor = conn.cursor()
        _ensure_payment_attention_table(cursor)
        cursor.execute(
            """
            SELECT
                pay.reference, pay.patient_id, pay.email, pay.amount, pay.currency,
                pay.patient_type, pay.label, pay.status, pay.paystack_status,
                pay.created_at, pay.verified_at, pay.access_expires_at,
                pay.grant_reason, pay.granted_by_admin_id,
                COALESCE(p.name, 'Unlinked patient') AS patient_name,
                p.archived_at AS patient_archived_at
            FROM payments pay
            LEFT JOIN patients p ON UPPER(p.patient_id) = UPPER(COALESCE(pay.patient_id, ''))
            ORDER BY datetime(pay.created_at) DESC, pay.id DESC
            """
        )
        payment_rows = cursor.fetchall()
        cursor.execute(
            """
            SELECT p.patient_id, p.name, p.email, p.created_at
            FROM patients p
            WHERE p.archived_at IS NULL
              AND NOT EXISTS (
                SELECT 1 FROM payments pay
                WHERE UPPER(COALESCE(pay.patient_id, '')) = UPPER(p.patient_id)
            )
              AND NOT EXISTS (
                SELECT 1 FROM dismissed_payment_attention dpa
                WHERE UPPER(dpa.patient_id) = UPPER(p.patient_id)
              )
            ORDER BY datetime(p.created_at) DESC, p.id DESC
            """
        )
        no_payment_rows = cursor.fetchall()

    payments = []
    for row in payment_rows:
        record = dict(row)
        record["access_active"] = row["status"] == "verified" and is_payment_within_validity_window(row)
        record["source"] = (
            "admin_grant"
            if row["paystack_status"] == "admin_access_grant"
            else "first_consultation_free"
            if row["paystack_status"] == "first_consultation_free"
            else "paystack"
        )
        payments.append(record)

    no_payment = [
        {
            "reference": "",
            "patient_id": row["patient_id"],
            "patient_name": row["name"],
            "email": row["email"] or "",
            "amount": None,
            "currency": "NGN",
            "patient_type": "returning",
            "label": "No payment record",
            "status": "no_payment",
            "paystack_status": "",
            "created_at": row["created_at"],
            "verified_at": None,
            "access_expires_at": None,
            "grant_reason": "",
            "granted_by_admin_id": None,
            "patient_archived_at": None,
            "access_active": False,
            "source": "none",
        }
        for row in no_payment_rows
    ]
    return {"payments": payments + no_payment, "payment_events": list_payment_events()}


def _ensure_payment_attention_table(cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS dismissed_payment_attention (
            patient_id TEXT PRIMARY KEY,
            dismissed_by_role TEXT,
            dismissed_by_id TEXT,
            dismissed_at TEXT NOT NULL
        )
        """
    )


def delete_attention_payment(reference: str = "", patient_id: str = "", *, actor_role: str = "admin", actor_id: str = "") -> dict:
    normalized_reference = (reference or "").strip()
    normalized_patient_id = (patient_id or "").strip()
    with get_connection() as conn:
        cursor = conn.cursor()
        _ensure_payment_attention_table(cursor)
        if normalized_reference:
            cursor.execute(
                """
                SELECT reference, status, paystack_status
                FROM payments
                WHERE reference = ?
                """,
                (normalized_reference,),
            )
            row = cursor.fetchone()
            if not row:
                return {"deleted": False, "message": "Payment record could not be found."}
            if row["status"] == "verified" or row["paystack_status"] == "admin_access_grant":
                return {"deleted": False, "message": "Verified payments and active access grants cannot be deleted here."}
            cursor.execute("DELETE FROM payments WHERE reference = ?", (normalized_reference,))
            conn.commit()
            return {"deleted": True, "message": "Payment attention row deleted."}

        if normalized_patient_id:
            cursor.execute(
                """
                INSERT INTO dismissed_payment_attention (patient_id, dismissed_by_role, dismissed_by_id, dismissed_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(patient_id) DO UPDATE SET
                    dismissed_by_role = excluded.dismissed_by_role,
                    dismissed_by_id = excluded.dismissed_by_id,
                    dismissed_at = excluded.dismissed_at
                """,
                (normalized_patient_id, actor_role, str(actor_id or ""), _now_iso()),
            )
            conn.commit()
            return {"deleted": True, "message": "No-payment attention row cleared."}

    return {"deleted": False, "message": "Select a payment reference or patient row to clear."}


def clear_attention_payments(*, actor_role: str = "admin", actor_id: str = "") -> dict:
    now = _now_iso()
    with get_connection() as conn:
        cursor = conn.cursor()
        _ensure_payment_attention_table(cursor)
        cursor.execute(
            """
            DELETE FROM payments
            WHERE status != 'verified'
              AND COALESCE(paystack_status, '') != 'admin_access_grant'
            """
        )
        deleted_payments = cursor.rowcount
        cursor.execute(
            """
            INSERT INTO dismissed_payment_attention (patient_id, dismissed_by_role, dismissed_by_id, dismissed_at)
            SELECT p.patient_id, ?, ?, ?
            FROM patients p
            WHERE p.archived_at IS NULL
              AND NOT EXISTS (
                SELECT 1 FROM payments pay
                WHERE UPPER(COALESCE(pay.patient_id, '')) = UPPER(p.patient_id)
            )
            ON CONFLICT(patient_id) DO UPDATE SET
                dismissed_by_role = excluded.dismissed_by_role,
                dismissed_by_id = excluded.dismissed_by_id,
                dismissed_at = excluded.dismissed_at
            """,
            (actor_role, str(actor_id or ""), now),
        )
        dismissed_rows = cursor.rowcount
        conn.commit()
    return {
        "cleared": True,
        "message": f"Cleared {deleted_payments + max(dismissed_rows, 0)} attention row(s).",
        "deleted_payments": deleted_payments,
        "dismissed_rows": max(dismissed_rows, 0),
    }


def grant_admin_consultation_access(admin_id: int, patient_id: str, reason: str, duration_hours: int) -> dict:
    detail = get_admin_patient_detail(patient_id)
    if not detail:
        return {"granted": False, "message": "Patient record could not be found."}
    patient = detail["patient"]
    grant = grant_manual_payment_override(
        telegram_id=patient["telegram_id"] or 0,
        patient_id=patient["patient_id"],
        email=patient["email"] or "",
        amount=0,
        label="Admin Consultation Access Grant",
        admin_id=admin_id,
        reason=reason,
        duration_hours=duration_hours,
    )
    return {
        "granted": True,
        "message": f"Consultation access granted for {duration_hours} hour(s).",
        **grant,
    }


def revoke_admin_consultation_access(reference: str) -> dict:
    revoked = revoke_manual_payment_override(reference)
    return {
        "revoked": revoked,
        "message": "Consultation access revoked." if revoked else "Active admin access grant could not be found.",
    }


def list_admin_consultations(limit: int = 100) -> list[dict]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                c.consultation_id, c.patient_id, c.doctor_id, c.status,
                c.diagnosis, c.created_at, c.closed_at,
                COALESCE(p.name, 'Patient') AS patient_name,
                COALESCE(dp.name, 'Doctor') AS doctor_name,
                (
                    SELECT COUNT(*)
                    FROM consultation_messages cm
                    WHERE cm.consultation_id = c.consultation_id
                ) AS message_count
            FROM consultations c
            LEFT JOIN patients p ON p.patient_id = c.patient_id
            LEFT JOIN doctor_profiles dp ON CAST(dp.telegram_id AS TEXT) = c.doctor_id
            ORDER BY c.created_at DESC
            LIMIT ?
            """,
            (max(1, min(limit, 250)),),
        )
        rows = cursor.fetchall()
    return [dict(row) for row in rows]


def get_admin_ratings() -> dict:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                dr.doctor_id,
                COALESCE(dp.name, d.name, 'Doctor') AS doctor_name,
                COALESCE(dp.specialty, 'N/A') AS specialty,
                COUNT(dr.id) AS rating_count,
                ROUND(AVG(dr.rating), 2) AS average_rating,
                MAX(dr.created_at) AS last_rating_at
            FROM doctor_ratings dr
            LEFT JOIN doctor_profiles dp ON dp.telegram_id = dr.doctor_id
            LEFT JOIN doctors d ON d.telegram_id = dr.doctor_id
            GROUP BY dr.doctor_id
            ORDER BY average_rating DESC, rating_count DESC, doctor_name COLLATE NOCASE
            """
        )
        doctor_summary_rows = cursor.fetchall()

        cursor.execute(
            """
            SELECT
                dr.id,
                dr.consultation_id,
                dr.doctor_id,
                dr.patient_id,
                dr.rating,
                dr.created_at,
                COALESCE(dp.name, d.name, 'Doctor') AS doctor_name,
                COALESCE(p.name, 'Patient') AS patient_name,
                COALESCE(rv.review, '') AS review
            FROM doctor_ratings dr
            LEFT JOIN doctor_reviews rv ON rv.consultation_id = dr.consultation_id
            LEFT JOIN doctor_profiles dp ON dp.telegram_id = dr.doctor_id
            LEFT JOIN doctors d ON d.telegram_id = dr.doctor_id
            LEFT JOIN patients p
                ON p.telegram_id = dr.patient_id
                OR p.patient_id = CAST(dr.patient_id AS TEXT)
            ORDER BY dr.created_at DESC
            LIMIT 250
            """
        )
        doctor_rating_rows = cursor.fetchall()

        cursor.execute(
            """
            SELECT
                stf.id,
                stf.ticket_id,
                stf.patient_id,
                stf.contact_email,
                stf.rating,
                stf.review,
                stf.skipped,
                stf.created_at,
                COALESCE(st.patient_name, 'Patient') AS patient_name,
                COALESCE(st.topic, '') AS topic,
                COALESCE(agents.agent_id, '') AS agent_id,
                COALESCE(cca.display_name, 'Unassigned customer care') AS agent_name
            FROM support_ticket_feedback stf
            LEFT JOIN support_tickets st ON st.ticket_id = stf.ticket_id
            LEFT JOIN (
                SELECT DISTINCT ticket_id, sender_id AS agent_id
                FROM support_ticket_messages
                WHERE sender_role = 'customer_care'
                  AND COALESCE(sender_id, '') != ''
            ) agents ON agents.ticket_id = stf.ticket_id
            LEFT JOIN customer_care_accounts cca ON CAST(cca.account_id AS TEXT) = agents.agent_id
            ORDER BY stf.created_at DESC
            LIMIT 250
            """
        )
        support_feedback_rows = cursor.fetchall()

    doctor_summaries = [dict(row) for row in doctor_summary_rows]
    doctor_ratings = [dict(row) for row in doctor_rating_rows]
    support_feedback = [dict(row) for row in support_feedback_rows]
    support_agent_groups: dict[str, dict] = {}
    for item in support_feedback:
        agent_id = str(item.get("agent_id") or "unassigned")
        if agent_id not in support_agent_groups:
            support_agent_groups[agent_id] = {
                "agent_id": agent_id,
                "agent_name": item.get("agent_name") or "Unassigned customer care",
                "feedback_count": 0,
                "rating_count": 0,
                "skipped_count": 0,
                "rating_total": 0,
                "last_feedback_at": item.get("created_at"),
            }
        group = support_agent_groups[agent_id]
        group["feedback_count"] += 1
        if item.get("skipped"):
            group["skipped_count"] += 1
        elif item.get("rating") is not None:
            group["rating_count"] += 1
            group["rating_total"] += int(item["rating"])
        if (item.get("created_at") or "") > (group.get("last_feedback_at") or ""):
            group["last_feedback_at"] = item.get("created_at")
    support_agent_summaries = []
    for group in support_agent_groups.values():
        rating_count = int(group["rating_count"] or 0)
        support_agent_summaries.append({
            "agent_id": group["agent_id"],
            "agent_name": group["agent_name"],
            "feedback_count": group["feedback_count"],
            "rating_count": rating_count,
            "skipped_count": group["skipped_count"],
            "average_rating": round(group["rating_total"] / rating_count, 2) if rating_count else 0,
            "last_feedback_at": group["last_feedback_at"],
        })
    support_agent_summaries.sort(
        key=lambda item: (item["average_rating"], item["rating_count"], item["agent_name"].lower()),
        reverse=True,
    )
    completed_support_feedback = [
        item for item in support_feedback
        if not item.get("skipped") and item.get("rating") is not None
    ]
    support_average = (
        round(
            sum(int(item["rating"]) for item in completed_support_feedback)
            / len(completed_support_feedback),
            2,
        )
        if completed_support_feedback
        else 0
    )
    doctor_average = (
        round(
            sum(float(item["average_rating"] or 0) * int(item["rating_count"] or 0) for item in doctor_summaries)
            / sum(int(item["rating_count"] or 0) for item in doctor_summaries),
            2,
        )
        if doctor_summaries
        else 0
    )
    return {
        "summary": {
            "doctor_average": doctor_average,
            "doctor_rating_count": len(doctor_ratings),
            "rated_doctors": len(doctor_summaries),
            "support_average": support_average,
            "support_feedback_count": len(completed_support_feedback),
            "support_skipped_count": len([item for item in support_feedback if item.get("skipped")]),
        },
        "doctor_summaries": doctor_summaries,
        "doctor_ratings": doctor_ratings,
        "support_agent_summaries": support_agent_summaries,
        "support_feedback": support_feedback,
    }


def get_admin_consultation(consultation_id: str) -> dict | None:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                c.consultation_id, c.patient_id, c.doctor_id, c.status,
                c.notes, c.doctor_private_notes, c.diagnosis,
                c.created_at, c.closed_at,
                COALESCE(p.name, 'Patient') AS patient_name,
                COALESCE(dp.name, 'Doctor') AS doctor_name
            FROM consultations c
            LEFT JOIN patients p ON p.patient_id = c.patient_id
            LEFT JOIN doctor_profiles dp ON CAST(dp.telegram_id AS TEXT) = c.doctor_id
            WHERE c.consultation_id = ?
            """,
            (consultation_id,),
        )
        consultation = cursor.fetchone()
        if not consultation:
            return None
        cursor.execute(
            """
            SELECT sender_role, message_text, asset_path, asset_type, created_at
            FROM consultation_messages
            WHERE consultation_id = ?
            ORDER BY id ASC
            """,
            (consultation_id,),
        )
        messages = cursor.fetchall()
    return {"consultation": dict(consultation), "messages": [dict(row) for row in messages]}


def send_doctor_license_reminder(doctor_id: int) -> dict:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT name, email, license_id, license_expiry_date
            FROM doctor_profiles
            WHERE telegram_id = ?
            """,
            (doctor_id,),
        )
        row = cursor.fetchone()
    if not row:
        return {"sent": False, "message": "Doctor account could not be found."}
    email = (row["email"] or "").strip().lower()
    if not email:
        return {"sent": False, "message": "Doctor does not have an email address."}

    expiry = row["license_expiry_date"] or "the recorded expiry date"
    sent = _send_doctor_review_email(
        email,
        "Reminder to renew your SynMed annual licence",
        (
            f"Hello Dr. {row['name'] or 'Doctor'},\n\n"
            f"This is a reminder that your annual licence ({row['license_id'] or 'number not recorded'}) expires on {expiry}.\n\n"
            "Please sign in to your SynMed doctor account and upload your renewed annual licence.\n\n"
            "Thank you,\nSynMed Telehealth"
        ),
    )
    return {
        "sent": sent,
        "message": "Licence reminder email sent." if sent else "Licence reminder email could not be sent.",
    }


def get_admin_delivery_settings() -> dict:
    return {
        **get_delivery_status(),
        "payments": get_payment_settings(),
        "paystack": get_paystack_readiness(),
        "email_branding": get_email_branding_settings(),
    }


def update_admin_payment_settings(payload: dict) -> dict:
    return update_payment_settings(payload)


def update_admin_email_branding_settings(payload: dict) -> dict:
    return update_email_branding_settings(payload)


def send_admin_delivery_test(channel: str, target: str) -> dict:
    normalized_channel = (channel or "").strip().lower()
    normalized_target = (target or "").strip()
    if normalized_channel not in {"email", "telegram"}:
        return {"sent": False, "message": "Unsupported delivery channel."}
    if not normalized_target:
        return {"sent": False, "message": "A delivery target is required."}

    test_code = "123456"
    try:
        deliver_otp_checked(normalized_channel, normalized_target, test_code)
    except Exception as exc:
        detail = getattr(exc, "detail", None)
        return {"sent": False, "message": detail or "Delivery test failed."}
    return {"sent": True, "message": f"Test OTP sent via {normalized_channel}."}


def list_pending_doctor_applications() -> list[dict]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT telegram_id, name, specialty, experience, license_id, username,
                   email, phone, license_expiry_date, file_id, file_type,
                   license_file_name, license_file_size, created_at, submitted_at
            FROM pending_doctor_requests
            WHERE COALESCE(review_status, 'pending_review') = 'pending_review'
            ORDER BY COALESCE(submitted_at, created_at) ASC, telegram_id ASC
            """
        )
        rows = cursor.fetchall()

    return [
        {
            "telegram_id": row["telegram_id"],
            "name": row["name"] or "Doctor",
            "specialty": row["specialty"] or "N/A",
            "experience": row["experience"] or "N/A",
            "license_id": row["license_id"] or "",
            "username": row["username"] or "",
            "email": row["email"] or "",
            "phone": row["phone"] or "",
            "license_expiry_date": row["license_expiry_date"] or "",
            "license_file_url": (
                f"/doctor-application-files/{(row['file_id'] or '').replace('doctor_application_files/', '', 1)}"
                if row["file_id"]
                else ""
            ),
            "license_file_name": row["license_file_name"] or "Latest annual licence",
            "license_file_size": row["license_file_size"] or None,
            "source": row["file_type"] or "telegram",
            "submitted_at": row["submitted_at"] or row["created_at"],
        }
        for row in rows
    ]


def create_manual_patient_registration(admin_id: int, payload: dict) -> dict:
    name = (payload.get("name") or "").strip()
    age = str(payload.get("age") or "").strip()
    gender = (payload.get("gender") or "").strip()
    phone = (payload.get("phone") or "").strip()
    email = (payload.get("email") or "").strip().lower()
    address = (payload.get("address") or "").strip()
    allergy = (payload.get("allergy") or "").strip()
    medical_conditions = (payload.get("medical_conditions") or "").strip()

    if not all([name, age, gender, phone, email]):
        return {"created": False, "message": "Name, age, gender, phone, and email are required."}
    try:
        int(age)
    except ValueError:
        return {"created": False, "message": "Age must be a number."}

    if get_patient_by_identifier(email):
        return {"created": False, "message": "A patient already exists with this email."}
    if get_patient_by_identifier(phone):
        return {"created": False, "message": "A patient already exists with this phone number."}

    patient = register_patient(
        telegram_id=None,
        name=name,
        age=age,
        gender=gender,
        phone=phone,
        email=email,
        address=address,
        allergy=allergy,
        medical_conditions=medical_conditions,
    )
    setup = send_patient_web_access_setup(hospital_number=patient["hospital_number"], email=email)

    return {
        "created": True,
        "message": (
            "Patient record created and setup email sent."
            if setup.get("delivered")
            else "Patient record created, but setup email could not be delivered right now."
        ),
        "patient": patient,
        "setup": setup,
        "created_by": admin_id,
    }


def create_manual_doctor_registration(admin_id: int, payload: dict) -> dict:
    name = (payload.get("name") or "").strip()
    email = (payload.get("email") or "").strip().lower()
    phone = (payload.get("phone") or "").strip()
    specialty = (payload.get("specialty") or "").strip()
    experience = (payload.get("experience") or "").strip()
    license_id = (payload.get("license_id") or "").strip()
    password = payload.get("password") or ""
    license_file_data = payload.get("license_file_data") or ""
    license_file_name = (payload.get("license_file_name") or "").strip() or "annual-licence"
    license_file_type = (payload.get("license_file_type") or "").strip() or "application/octet-stream"
    license_expiry_date = (payload.get("license_expiry_date") or "").strip()

    if not all([name, email, specialty, experience, license_id, password]):
        return {"created": False, "message": "Name, email, specialty, experience, licence ID, and temporary password are required."}
    if len(password.strip()) < 8:
        return {"created": False, "message": "Temporary password must be at least 8 characters long."}
    if not license_file_data:
        return {"created": False, "message": "Upload the doctor's latest annual licence."}

    existing_doctor_id, existing_profile = get_profile_by_identifier(email)
    if existing_doctor_id and existing_profile:
        return {"created": False, "message": "A doctor account already exists with this email."}

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT telegram_id
            FROM pending_doctor_requests
            WHERE LOWER(COALESCE(email, '')) = ?
              AND COALESCE(review_status, 'pending_review') = 'pending_review'
            LIMIT 1
            """,
            (email,),
        )
        if cursor.fetchone():
            return {"created": False, "message": "A pending doctor application already exists with this email."}

    license_file_id, stored_file_type, stored_file_name, stored_file_size = _save_doctor_license_upload(
        license_file_name,
        license_file_type,
        license_file_data,
    )
    doctor_id = _allocate_web_doctor_id()
    submitted_at = _now_iso()
    username = email.split("@", 1)[0]
    password_hash = hash_patient_password(password)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO pending_doctor_requests (
                telegram_id, name, specialty, experience, license_id, username,
                file_id, file_type, email, phone, password_hash, license_expiry_date,
                review_status, submitted_at, license_file_name, license_file_size, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending_review', ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                doctor_id,
                name,
                specialty,
                experience,
                license_id,
                username,
                license_file_id,
                stored_file_type,
                email,
                phone,
                password_hash,
                license_expiry_date,
                submitted_at,
                stored_file_name,
                stored_file_size,
            ),
        )
        conn.commit()

    return {
        "created": True,
        "message": "Doctor application created. Review and approve it from pending applications.",
        "doctor": {
            "telegram_id": doctor_id,
            "name": name,
            "email": email,
            "phone": phone,
            "specialty": specialty,
            "experience": experience,
            "license_id": license_id,
            "license_expiry_date": license_expiry_date,
            "license_file_name": stored_file_name,
            "submitted_at": submitted_at,
            "category": "pending",
        },
        "created_by": admin_id,
    }


def approve_doctor_application(doctor_id: int) -> dict:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT telegram_id, name, specialty, experience, license_id, username,
                   email, phone, password_hash, license_expiry_date, file_id, file_type,
                   license_file_name, license_file_size
            FROM pending_doctor_requests
            WHERE telegram_id = ?
              AND COALESCE(review_status, 'pending_review') = 'pending_review'
            """,
            (doctor_id,),
        )
        row = cursor.fetchone()

    if not row:
        return {"updated": False, "message": "Pending doctor application could not be found."}

    create_or_update_profile(
        doctor_id,
        {
            "name": row["name"],
            "specialty": row["specialty"],
            "experience": row["experience"],
            "license_id": row["license_id"],
            "license_file_id": row["file_id"],
            "license_file_type": row["file_type"],
            "license_file_name": row["license_file_name"],
            "license_file_size": row["license_file_size"],
            "username": row["username"],
            "email": (row["email"] or "").strip().lower(),
            "phone": row["phone"],
            "password_hash": row["password_hash"],
            "license_expiry_date": row["license_expiry_date"],
            "updated_at": _now_iso(),
            "verified": True,
        },
    )

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM pending_doctor_requests WHERE telegram_id = ?", (doctor_id,))
        conn.commit()

    notification_sent = _send_doctor_review_email(
        row["email"],
        "Your SynMed doctor application has been approved",
        (
            f"Hello Dr. {row['name'] or 'Doctor'},\n\n"
            "Your SynMed doctor application has been approved. You can now sign in to the doctor dashboard, go online, and connect to queued patients.\n\n"
            "Thank you,\nSynMed Telehealth"
        ),
    )

    return {
        "updated": True,
        "message": "Doctor application approved.",
        "notification_sent": notification_sent,
    }


def reject_doctor_application(doctor_id: int, reason: str = "") -> dict:
    review_note = (reason or "").strip() or "Your application could not be approved with the details submitted."
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT name, email
            FROM pending_doctor_requests
            WHERE telegram_id = ?
              AND COALESCE(review_status, 'pending_review') = 'pending_review'
            """,
            (doctor_id,),
        )
        row = cursor.fetchone()
        if not row:
            return {"updated": False, "message": "Pending doctor application could not be found."}

        cursor.execute(
            """
            UPDATE pending_doctor_requests
            SET review_status = 'rejected',
                reviewed_at = ?,
                review_note = ?
            WHERE telegram_id = ?
            """,
            (_now_iso(), review_note, doctor_id),
        )
        conn.commit()

    notification_sent = _send_doctor_review_email(
        row["email"],
        "Your SynMed doctor application needs attention",
        (
            f"Hello Dr. {row['name'] or 'Doctor'},\n\n"
            "Your SynMed doctor application was not approved at this time.\n\n"
            f"Reason: {review_note}\n\n"
            "You may submit a new application after correcting the issue.\n\n"
            "Thank you,\nSynMed Telehealth"
        ),
    )

    return {
        "updated": True,
        "message": "Doctor application rejected.",
        "notification_sent": notification_sent,
    }


def set_doctor_account_status(doctor_id: int, action: str, reason: str = "") -> dict:
    normalized_action = (action or "").strip().lower()
    if normalized_action not in {"suspend", "reactivate"}:
        return {"updated": False, "message": "Unsupported doctor account action."}

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT dp.telegram_id, dp.name, dp.email, dp.verified, COALESCE(d.status, '') AS account_status
            FROM doctor_profiles dp
            LEFT JOIN doctors d ON d.telegram_id = dp.telegram_id
            WHERE dp.telegram_id = ?
            """,
            (doctor_id,),
        )
        row = cursor.fetchone()
        if not row:
            return {"updated": False, "message": "Doctor account could not be found."}

        if normalized_action == "suspend":
            cursor.execute(
                """
                UPDATE doctor_profiles
                SET verified = 0, updated_at = ?
                WHERE telegram_id = ?
                """,
                (_now_iso(), doctor_id),
            )
            cursor.execute(
                """
                INSERT INTO doctors (telegram_id, doctor_id, name, status, created_at)
                VALUES (?, ?, ?, 'suspended', CURRENT_TIMESTAMP)
                ON CONFLICT(telegram_id) DO UPDATE SET status = 'suspended'
                """,
                (doctor_id, str(doctor_id), row["name"]),
            )
            cursor.execute("DELETE FROM doctor_runtime_presence WHERE doctor_id = ?", (doctor_id,))
            message = "Doctor account suspended."
        else:
            cursor.execute(
                """
                UPDATE doctor_profiles
                SET verified = 1, updated_at = ?
                WHERE telegram_id = ?
                """,
                (_now_iso(), doctor_id),
            )
            cursor.execute(
                """
                INSERT INTO doctors (telegram_id, doctor_id, name, status, created_at)
                VALUES (?, ?, ?, 'verified', CURRENT_TIMESTAMP)
                ON CONFLICT(telegram_id) DO UPDATE SET status = 'verified'
                """,
                (doctor_id, str(doctor_id), row["name"]),
            )
            message = "Doctor account reactivated."
        conn.commit()

    note = (reason or "").strip()
    if normalized_action == "suspend":
        body = (
            f"Hello Dr. {row['name'] or 'Doctor'},\n\n"
            "Your SynMed doctor account has been suspended by admin."
            + (f"\n\nReason: {note}" if note else "")
            + "\n\nPlease contact SynMed support if you believe this needs review.\n\nThank you,\nSynMed Telehealth"
        )
        subject = "Your SynMed doctor account has been suspended"
    else:
        body = (
            f"Hello Dr. {row['name'] or 'Doctor'},\n\n"
            "Your SynMed doctor account has been reactivated. You can now sign in and use the doctor dashboard again.\n\n"
            "Thank you,\nSynMed Telehealth"
        )
        subject = "Your SynMed doctor account has been reactivated"

    notification_sent = _send_doctor_review_email(row["email"], subject, body)
    return {"updated": True, "message": message, "notification_sent": notification_sent}


def _send_doctor_review_email(email: str, subject: str, body: str) -> bool:
    normalized_email = (email or "").strip().lower()
    if not normalized_email:
        return False
    try:
        return send_plain_email(normalized_email, subject, body)
    except Exception:
        return False


def list_health_tips(*, include_inactive: bool = False, audience: str | None = None) -> list[dict]:
    normalized_audience = (audience or "").strip().lower()
    audience_clause = ""
    parameters = []
    if normalized_audience in {"landing", "patient"}:
        audience_clause = " AND audience IN (?, 'both')"
        parameters.append(normalized_audience)
    with get_connection() as conn:
        cursor = conn.cursor()
        if include_inactive:
            cursor.execute(
                """
                SELECT id, eyebrow, title, body, sort_order, is_active, audience, created_at, updated_at
                FROM health_tips
                ORDER BY is_active DESC, sort_order ASC, id ASC
                """
            )
        else:
            cursor.execute(
                f"""
                SELECT id, eyebrow, title, body, sort_order, is_active, audience, created_at, updated_at
                FROM health_tips
                WHERE is_active = 1 {audience_clause}
                ORDER BY sort_order ASC, id ASC
                """,
                parameters,
            )
        rows = cursor.fetchall()

    return [
        {
            "id": row["id"],
            "eyebrow": row["eyebrow"],
            "title": row["title"],
            "body": row["body"],
            "sort_order": row["sort_order"],
            "is_active": bool(row["is_active"]),
            "audience": row["audience"] or "landing",
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]


def create_health_tip(payload: dict) -> dict:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO health_tips (eyebrow, title, body, sort_order, is_active, audience, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["eyebrow"].strip(),
                payload["title"].strip(),
                payload["body"].strip(),
                int(payload.get("sort_order", 0)),
                1 if payload.get("is_active", True) else 0,
                payload.get("audience", "landing"),
                _now_iso(),
                _now_iso(),
            ),
        )
        tip_id = cursor.lastrowid
        conn.commit()

    return get_health_tip_by_id(tip_id)


def get_health_tip_by_id(tip_id: int) -> dict | None:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, eyebrow, title, body, sort_order, is_active, audience, created_at, updated_at
            FROM health_tips
            WHERE id = ?
            """,
            (tip_id,),
        )
        row = cursor.fetchone()

    if not row:
        return None

    return {
        "id": row["id"],
        "eyebrow": row["eyebrow"],
        "title": row["title"],
        "body": row["body"],
        "sort_order": row["sort_order"],
        "is_active": bool(row["is_active"]),
        "audience": row["audience"] or "landing",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def update_health_tip(tip_id: int, payload: dict) -> dict | None:
    existing = get_health_tip_by_id(tip_id)
    if not existing:
        return None

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE health_tips
            SET eyebrow = ?, title = ?, body = ?, sort_order = ?, is_active = ?, audience = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                payload["eyebrow"].strip(),
                payload["title"].strip(),
                payload["body"].strip(),
                int(payload.get("sort_order", 0)),
                1 if payload.get("is_active", True) else 0,
                payload.get("audience", "landing"),
                _now_iso(),
                tip_id,
            ),
        )
        conn.commit()

    return get_health_tip_by_id(tip_id)


def delete_health_tip(tip_id: int) -> bool:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM health_tips WHERE id = ?", (tip_id,))
        deleted = cursor.rowcount > 0
        conn.commit()
    return deleted
