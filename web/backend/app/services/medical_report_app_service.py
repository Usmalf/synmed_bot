from datetime import datetime, timezone
from uuid import uuid4

from database import get_connection
from services.patient_records import get_patient_by_identifier, update_patient_record
from services.paystack import (
    build_frontend_callback_url,
    create_payment_reference,
    get_payment_by_reference,
    initialize_transaction,
    mark_payment_status,
    mark_payment_verified,
    verify_transaction,
)
from .settings_service import get_payment_settings


UTC = timezone.utc


def _medical_report_payment_config() -> dict:
    settings = get_payment_settings()
    return {
        "amount": settings["medical_report_fee"],
        "currency": settings["currency"],
        "label": settings["medical_report_label"],
    }


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _request_payload(row) -> dict:
    return {
        "request_id": row["request_id"],
        "patient_id": row["patient_id"],
        "consultation_id": row["consultation_id"] or "",
        "doctor_id": row["doctor_id"] or "",
        "request_note": row["request_note"] or "",
        "delivery_email": row["delivery_email"] or "",
        "status": row["status"],
        "payment_status": row["payment_status"],
        "payment_reference": row["payment_reference"] or "",
        "payment_token": row["payment_token"] or "",
        "fulfilled_letter_id": row["fulfilled_letter_id"] or "",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _fetch_request(request_id: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT request_id, patient_id, consultation_id, doctor_id, request_note,
                   delivery_email, status, payment_status, payment_reference, payment_token,
                   fulfilled_letter_id, created_at, updated_at
            FROM medical_report_requests
            WHERE request_id = ?
            """,
            (request_id,),
        )
        return cursor.fetchone()


def _latest_consultation(patient_id: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT consultation_id, doctor_id
            FROM consultations
            WHERE patient_id = ?
            ORDER BY datetime(created_at) DESC, id DESC
            LIMIT 1
            """,
            (patient_id,),
        )
        return cursor.fetchone()


def list_patient_medical_report_requests(patient_identifier: str) -> dict:
    patient = get_patient_by_identifier(patient_identifier)
    if not patient:
        return {
            "found": False,
            "message": "Patient record could not be found.",
            "requests": [],
            "fee_amount": _medical_report_payment_config()["amount"],
        }

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT request_id, patient_id, consultation_id, doctor_id, request_note,
                   delivery_email, status, payment_status, payment_reference, payment_token,
                   fulfilled_letter_id, created_at, updated_at
            FROM medical_report_requests
            WHERE patient_id = ?
            ORDER BY datetime(created_at) DESC, id DESC
            """,
            (patient["hospital_number"],),
        )
        rows = cursor.fetchall()

    return {
        "found": True,
        "message": "Medical report requests loaded." if rows else "No medical report requests found yet.",
        "requests": [_request_payload(row) for row in rows],
        "fee_amount": _medical_report_payment_config()["amount"],
    }


def create_patient_medical_report_request(patient_identifier: str, payload: dict) -> dict:
    patient = get_patient_by_identifier(patient_identifier)
    if not patient:
        return {
            "created": False,
            "message": "Patient record could not be found.",
            "request": None,
            "fee_amount": _medical_report_payment_config()["amount"],
        }

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT request_id, patient_id, consultation_id, doctor_id, request_note,
                   delivery_email, status, payment_status, payment_reference, payment_token,
                   fulfilled_letter_id, created_at, updated_at
            FROM medical_report_requests
            WHERE patient_id = ?
              AND payment_status = 'paid'
              AND status != 'fulfilled'
              AND COALESCE(fulfilled_letter_id, '') = ''
            ORDER BY datetime(created_at) DESC, id DESC
            LIMIT 1
            """,
            (patient["hospital_number"],),
        )
        pending_paid = cursor.fetchone()

    if pending_paid:
        return {
            "created": False,
            "message": "You already have a paid medical report request waiting for your doctor. Please wait until it is completed before making another payment.",
            "request": _request_payload(pending_paid),
            "fee_amount": _medical_report_payment_config()["amount"],
        }

    latest = _latest_consultation(patient["hospital_number"])
    request_id = f"mr-{uuid4().hex[:12]}"
    doctor_id = (latest["doctor_id"] if latest and latest["doctor_id"] else "") or ""
    consultation_id = (latest["consultation_id"] if latest and latest["consultation_id"] else "") or ""
    note = (payload.get("request_note") or "").strip()
    delivery_email = (payload.get("delivery_email") or patient.get("email") or "").strip().lower()
    now = _now_iso()

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO medical_report_requests (
                request_id, patient_id, consultation_id, doctor_id, request_note, delivery_email,
                status, payment_status, payment_reference, payment_token,
                fulfilled_letter_id, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request_id,
                patient["hospital_number"],
                consultation_id,
                doctor_id,
                note,
                delivery_email,
                "requested",
                "unpaid",
                None,
                None,
                None,
                now,
                now,
            ),
        )
        conn.commit()

    request_row = _fetch_request(request_id)
    assigned_message = (
        "The last doctor has been assigned automatically."
        if doctor_id
        else "No previous doctor was found, so admin can assign a doctor manually."
    )
    return {
        "created": True,
        "message": f"Medical report request created. {assigned_message}",
        "request": _request_payload(request_row),
        "fee_amount": _medical_report_payment_config()["amount"],
    }


async def initialize_medical_report_payment(request_id: str, patient_identifier: str, payload: dict) -> dict:
    request = _fetch_request(request_id)
    if not request:
        return {
            "initialized": False,
            "message": "Medical report request could not be found.",
            "request": None,
        }

    if request["patient_id"] != patient_identifier:
        return {
            "initialized": False,
            "message": "This medical report request does not belong to the signed-in patient.",
            "request": None,
        }

    patient = get_patient_by_identifier(patient_identifier)
    if not patient:
        return {
            "initialized": False,
            "message": "Patient record linked to this request could not be found.",
            "request": None,
        }

    email = (payload.get("email") or patient.get("email") or "").strip()
    if not email:
        return {
            "initialized": False,
            "message": "An email address is required before payment can start.",
            "request": _request_payload(request),
        }

    if email != (patient.get("email") or ""):
        update_patient_record(patient["hospital_number"], "email", email)

    payment_config = _medical_report_payment_config()
    payment_reference = create_payment_reference(prefix="report")
    callback_url = build_frontend_callback_url(
        payload.get("callback_path") or "/patient/medical-report-request",
        {
            "request_id": request_id,
            "payment_reference": payment_reference,
            "reference": payment_reference,
            "status": "success",
        },
    )
    result = await initialize_transaction(
        email=email,
        amount_ngn=payment_config["amount"],
        currency=payment_config["currency"],
        reference=payment_reference,
        label=payment_config["label"],
        metadata={
            "patient_type": "returning",
            "patient_id": patient["hospital_number"],
            "source": "web_medical_report",
            "telegram_id": patient.get("telegram_id") or 0,
            "purpose": "medical_report",
            "medical_report_request_id": request_id,
        },
        callback_url=callback_url,
    )

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE medical_report_requests
            SET payment_reference = ?, updated_at = ?
            WHERE request_id = ?
            """,
            (payment_reference, _now_iso(), request_id),
        )
        conn.commit()

    updated = _fetch_request(request_id)
    return {
        "initialized": True,
        "message": "Medical report payment initialized successfully.",
        "request": _request_payload(updated),
        "reference": payment_reference,
        "authorization_url": result["authorization_url"],
        "access_code": result["access_code"],
        "amount": payment_config["amount"],
        "currency": payment_config["currency"],
        "label": payment_config["label"],
    }


async def verify_medical_report_payment(request_id: str, patient_identifier: str, payment_reference: str) -> dict:
    request = _fetch_request(request_id)
    if not request:
        return {
            "verified": False,
            "message": "Medical report request could not be found.",
            "request": None,
            "payment_reference": payment_reference,
            "paystack_status": None,
        }

    if request["patient_id"] != patient_identifier:
        return {
            "verified": False,
            "message": "This medical report request does not belong to the signed-in patient.",
            "request": None,
            "payment_reference": payment_reference,
            "paystack_status": None,
        }

    payment = get_payment_by_reference(payment_reference)
    if not payment:
        return {
            "verified": False,
            "message": "Payment reference was not found.",
            "request": _request_payload(request),
            "payment_reference": payment_reference,
            "paystack_status": None,
        }

    if payment["patient_id"] != patient_identifier:
        return {
            "verified": False,
            "message": "That payment does not belong to the signed-in patient.",
            "request": _request_payload(request),
            "payment_reference": payment_reference,
            "paystack_status": None,
        }

    verification = await verify_transaction(payment_reference)
    paystack_status = (verification.get("status") or "").lower()
    amount_ngn = int(verification.get("amount", 0)) // 100
    currency = verification.get("currency")

    if paystack_status != "success":
        mark_payment_status(
            payment_reference,
            status="pending_verification",
            paystack_status=paystack_status or "pending",
        )
        return {
            "verified": False,
            "message": "Payment is not confirmed yet.",
            "request": _request_payload(request),
            "payment_reference": payment_reference,
            "paystack_status": paystack_status or "pending",
        }

    if amount_ngn != payment["amount"] or currency != payment["currency"]:
        mark_payment_status(
            payment_reference,
            status="amount_mismatch",
            paystack_status=paystack_status,
        )
        return {
            "verified": False,
            "message": "Payment amount or currency did not match the expected values.",
            "request": _request_payload(request),
            "payment_reference": payment_reference,
            "paystack_status": paystack_status,
        }

    payment_token = mark_payment_verified(
        payment_reference,
        paystack_status=paystack_status,
        patient_id=patient_identifier,
    )

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE medical_report_requests
            SET payment_status = 'paid', payment_reference = ?, payment_token = ?, updated_at = ?
            WHERE request_id = ?
            """,
            (payment_reference, payment_token, _now_iso(), request_id),
        )
        conn.commit()

    updated = _fetch_request(request_id)
    return {
        "verified": True,
        "message": "Medical report payment verified successfully.",
        "request": _request_payload(updated),
        "payment_reference": payment_reference,
        "paystack_status": paystack_status,
    }


def list_admin_medical_report_requests() -> dict:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT request_id, patient_id, consultation_id, doctor_id, request_note,
                   delivery_email, status, payment_status, payment_reference, payment_token,
                   fulfilled_letter_id, created_at, updated_at
            FROM medical_report_requests
            ORDER BY datetime(created_at) DESC, id DESC
            """
        )
        rows = cursor.fetchall()

    return {
        "found": True,
        "message": "Medical report requests loaded." if rows else "No medical report requests found yet.",
        "requests": [_request_payload(row) for row in rows],
        "fee_amount": _medical_report_payment_config()["amount"],
    }


def assign_medical_report_request(request_id: str, doctor_id: str) -> dict:
    request = _fetch_request(request_id)
    if not request:
        return {
            "updated": False,
            "message": "Medical report request could not be found.",
            "request": None,
        }

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE medical_report_requests
            SET doctor_id = ?, updated_at = ?
            WHERE request_id = ?
            """,
            (doctor_id.strip(), _now_iso(), request_id),
        )
        conn.commit()

    updated = _fetch_request(request_id)
    return {
        "updated": True,
        "message": "Medical report request assigned successfully.",
        "request": _request_payload(updated),
    }


def list_doctor_medical_report_requests(doctor_id: int) -> list[dict]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT request_id, patient_id, consultation_id, doctor_id, request_note,
                   delivery_email, status, payment_status, payment_reference, payment_token,
                   fulfilled_letter_id, created_at, updated_at
            FROM medical_report_requests
            WHERE doctor_id = ?
            ORDER BY datetime(created_at) DESC, id DESC
            """,
            (str(doctor_id),),
        )
        rows = cursor.fetchall()
    return [_request_payload(row) for row in rows]
