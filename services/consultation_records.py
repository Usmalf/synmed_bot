import json
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from database import get_connection


UTC = timezone.utc


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def start_consultation_record(consultation_id: str, *, patient_record: dict, doctor_id: int, summary: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO consultations (
                consultation_id, patient_id, doctor_id, status, notes,
                created_at, closed_at, patient_telegram_id, doctor_telegram_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                consultation_id,
                patient_record["hospital_number"],
                str(doctor_id),
                "active",
                summary,
                _now_iso(),
                None,
                patient_record.get("telegram_id"),
                doctor_id,
            ),
        )
        conn.commit()
    log_consultation_event(
        consultation_id,
        event_type="consultation_started",
        actor_id=str(doctor_id),
        details=summary,
    )


def close_consultation_record(consultation_id: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE consultations
            SET status = 'closed', closed_at = ?
            WHERE consultation_id = ?
            """,
            (_now_iso(), consultation_id),
        )
        conn.commit()
    log_consultation_event(
        consultation_id,
        event_type="consultation_closed",
        details="Consultation ended",
    )


def get_consultation_diagnosis(consultation_id: str) -> str:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT diagnosis
            FROM consultations
            WHERE consultation_id = ?
            """,
            (consultation_id,),
        )
        row = cursor.fetchone()
    if not row or not row["diagnosis"]:
        return ""
    return row["diagnosis"].strip()


def set_consultation_diagnosis(consultation_id: str, diagnosis: str):
    diagnosis = diagnosis.strip()
    if not diagnosis:
        return
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE consultations
            SET diagnosis = ?
            WHERE consultation_id = ?
            """,
            (diagnosis, consultation_id),
        )
        conn.commit()
    log_consultation_event(
        consultation_id,
        event_type="consultation_diagnosis_saved",
        details=diagnosis,
    )


def set_doctor_private_notes(consultation_id: str, notes: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE consultations
            SET doctor_private_notes = ?
            WHERE consultation_id = ?
            """,
            (notes, consultation_id),
        )
        conn.commit()
    log_consultation_event(
        consultation_id,
        event_type="doctor_note_saved",
        details=notes,
    )


def save_consultation_snapshot(consultation_id: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE consultations
            SET saved_at = ?
            WHERE consultation_id = ?
            """,
            (_now_iso(), consultation_id),
        )
        conn.commit()

        cursor.execute(
            "SELECT COUNT(*) AS total FROM consultation_messages WHERE consultation_id = ?",
            (consultation_id,),
        )
        message_total = (cursor.fetchone() or {"total": 0})["total"]

        cursor.execute(
            "SELECT COUNT(*) AS total FROM prescriptions WHERE consultation_id = ?",
            (consultation_id,),
        )
        prescription_total = (cursor.fetchone() or {"total": 0})["total"]

        cursor.execute(
            "SELECT COUNT(*) AS total FROM investigation_requests WHERE consultation_id = ?",
            (consultation_id,),
        )
        investigation_total = (cursor.fetchone() or {"total": 0})["total"]

        cursor.execute(
            "SELECT COUNT(*) AS total FROM clinical_letters WHERE consultation_id = ?",
            (consultation_id,),
        )
        letter_total = (cursor.fetchone() or {"total": 0})["total"]

    log_consultation_event(
        consultation_id,
        event_type="consultation_saved",
        details=(
            f"messages={message_total}, prescriptions={prescription_total}, "
            f"investigations={investigation_total}, letters={letter_total}"
        ),
    )


def _find_latest_consultation(cursor, identifier: str):
    cursor.execute(
        """
        SELECT consultation_id, patient_id, doctor_id, status, notes,
               created_at, closed_at, doctor_private_notes, diagnosis, saved_at,
               patient_telegram_id, doctor_telegram_id
        FROM consultations
        WHERE consultation_id = ?
           OR patient_id = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (identifier, identifier.upper()),
    )
    return cursor.fetchone()


def _resolve_asset_path(asset_path: str | None) -> Path | None:
    if not asset_path:
        return None
    path = Path(asset_path)
    if not path.is_absolute():
        path = Path(__file__).resolve().parent.parent / asset_path
    return path if path.exists() else None


def get_latest_consultation_bundle(identifier: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        consultation = _find_latest_consultation(cursor, identifier)
        if not consultation:
            return None

        cursor.execute(
            """
            SELECT patient_id, telegram_id, name, age, gender, phone, email, address, allergy, medical_conditions
            FROM patients
            WHERE patient_id = ?
            """,
            (consultation["patient_id"],),
        )
        patient = cursor.fetchone()

        cursor.execute(
            """
            SELECT sender_role, sender_id, message_text, asset_path, asset_type, created_at
            FROM consultation_messages
            WHERE consultation_id = ?
            ORDER BY id ASC
            """,
            (consultation["consultation_id"],),
        )
        messages = cursor.fetchall()

        cursor.execute(
            """
            SELECT rx_id AS document_id, consultation_id, doctor_id, patient_id, medication_json,
                   notes, created_at, asset_path, asset_type
            FROM prescriptions
            WHERE consultation_id = ?
            ORDER BY created_at DESC
            """,
            (consultation["consultation_id"],),
        )
        prescriptions = cursor.fetchall()

        cursor.execute(
            """
            SELECT request_id AS document_id, consultation_id, doctor_id, patient_id, diagnosis,
                   tests_text, notes, created_at, asset_path, asset_type
            FROM investigation_requests
            WHERE consultation_id = ?
            ORDER BY created_at DESC
            """,
            (consultation["consultation_id"],),
        )
        investigations = cursor.fetchall()

        cursor.execute(
            """
            SELECT letter_id AS document_id, consultation_id, doctor_id, patient_id, document_type,
                   diagnosis, body_text, target_hospital, created_at, asset_path, asset_type
            FROM clinical_letters
            WHERE consultation_id = ?
            ORDER BY created_at DESC
            """,
            (consultation["consultation_id"],),
        )
        letters = cursor.fetchall()

    return {
        "consultation": consultation,
        "patient": patient,
        "messages": messages,
        "prescriptions": prescriptions,
        "investigations": investigations,
        "letters": letters,
    }


def get_consultation_document_records(identifier: str):
    bundle = get_latest_consultation_bundle(identifier)
    if not bundle:
        return None

    documents = []
    for row in bundle["prescriptions"]:
        documents.append(
            {
                "kind": "prescription",
                "document_id": row["document_id"],
                "consultation_id": row["consultation_id"],
                "created_at": row["created_at"],
                "asset_path": row["asset_path"],
                "asset_type": row["asset_type"],
                "row": row,
            }
        )
    for row in bundle["investigations"]:
        documents.append(
            {
                "kind": "investigation",
                "document_id": row["document_id"],
                "consultation_id": row["consultation_id"],
                "created_at": row["created_at"],
                "asset_path": row["asset_path"],
                "asset_type": row["asset_type"],
                "row": row,
            }
        )
    for row in bundle["letters"]:
        documents.append(
            {
                "kind": row["document_type"],
                "document_id": row["document_id"],
                "consultation_id": row["consultation_id"],
                "created_at": row["created_at"],
                "asset_path": row["asset_path"],
                "asset_type": row["asset_type"],
                "row": row,
            }
        )

    documents.sort(key=lambda item: item["created_at"], reverse=True)
    return {
        "consultation_id": bundle["consultation"]["consultation_id"],
        "patient": bundle["patient"],
        "documents": documents,
    }


def log_consultation_event(consultation_id: str, *, event_type: str, actor_id: str | None = None, details: str = ""):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO consultation_timeline (
                consultation_id, event_type, actor_id, details, created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (consultation_id, event_type, actor_id, details, _now_iso()),
        )
        conn.commit()


def get_consultation_timeline(identifier: str, limit: int = 30):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT consultation_id
            FROM consultations
            WHERE consultation_id = ?
               OR patient_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (identifier, identifier.upper()),
        )
        consultation = cursor.fetchone()
        if not consultation:
            return None

        consultation_id = consultation["consultation_id"]
        cursor.execute(
            """
            SELECT event_type, actor_id, details, created_at
            FROM consultation_timeline
            WHERE consultation_id = ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (consultation_id, limit),
        )
        events = cursor.fetchall()

    return {"consultation_id": consultation_id, "events": events}


def get_latest_consultation_for_feedback(patient_telegram_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT consultation_id, doctor_id, status, created_at, closed_at
            FROM consultations
            WHERE patient_telegram_id = ?
            ORDER BY COALESCE(closed_at, created_at) DESC
            LIMIT 1
            """,
            (patient_telegram_id,),
        )
        consultation = cursor.fetchone()

    if not consultation:
        return None

    return {
        "consultation_id": consultation["consultation_id"],
        "doctor_id": int(consultation["doctor_id"]),
        "status": consultation["status"],
        "created_at": consultation["created_at"],
        "closed_at": consultation["closed_at"],
    }


def _build_patient_history(cursor, patient_id: str, name: str, limit: int = 5):
    cursor.execute(
        """
        SELECT consultation_id, doctor_id, status, notes, created_at, closed_at, doctor_private_notes
        FROM consultations
        WHERE patient_id = ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (patient_id, limit),
    )
    consultations = cursor.fetchall()

    cursor.execute(
        """
        SELECT consultation_id, medication_json, notes, created_at
        FROM prescriptions
        WHERE patient_id = ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (patient_id, limit),
    )
    raw_prescriptions = cursor.fetchall()

    prescriptions = []
    for item in raw_prescriptions:
        diagnosis = "N/A"
        try:
            payload = json.loads(item["medication_json"] or "{}")
            diagnosis = payload.get("diagnosis") or "N/A"
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
        prescriptions.append(
            {
                "consultation_id": item["consultation_id"],
                "diagnosis": diagnosis,
                "notes": item["notes"],
                "created_at": item["created_at"],
            }
        )

    cursor.execute(
        """
        SELECT consultation_id, diagnosis, tests_text, notes, created_at
        FROM investigation_requests
        WHERE patient_id = ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (patient_id, limit),
    )
    investigations = cursor.fetchall()

    return {
        "patient_id": patient_id,
        "name": name,
        "consultations": consultations,
        "prescriptions": prescriptions,
        "investigations": investigations,
    }


def get_patient_history(telegram_id: int, limit: int = 5):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT patient_id, name
            FROM patients
            WHERE telegram_id = ?
            """,
            (telegram_id,),
        )
        patient = cursor.fetchone()
        if not patient:
            return None

        return _build_patient_history(cursor, patient["patient_id"], patient["name"], limit)


def get_patient_history_by_identifier(identifier: str, limit: int = 5):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT patient_id, name
            FROM patients
            WHERE UPPER(patient_id) = UPPER(?)
               OR phone = ?
            """,
            (identifier.strip(), identifier.strip()),
        )
        patient = cursor.fetchone()
        if not patient:
            return None

        return _build_patient_history(cursor, patient["patient_id"], patient["name"], limit)


def log_consultation_message(
    consultation_id: str,
    *,
    sender_id: int,
    sender_role: str,
    message_text: str,
    asset_path: str | None = None,
    asset_type: str | None = None,
):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO consultation_messages (
                consultation_id, sender_id, sender_role, message_text, asset_path, asset_type, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                consultation_id,
                sender_id,
                sender_role,
                message_text,
                asset_path,
                asset_type,
                _now_iso(),
            ),
        )
        conn.commit()


def export_consultation_file(identifier: str):
    bundle = get_latest_consultation_bundle(identifier)
    if not bundle:
        return None

    consultation = bundle["consultation"]
    patient = bundle["patient"]
    messages = bundle["messages"]

    lines = [
        "SynMed Telehealth Consultation Export",
        "",
        f"Consultation ID: {consultation['consultation_id']}",
        f"Hospital Number: {consultation['patient_id']}",
        f"Doctor ID: {consultation['doctor_id']}",
        f"Status: {consultation['status']}",
        f"Created At: {consultation['created_at']}",
        f"Closed At: {consultation['closed_at'] or 'Active'}",
        f"Saved At: {consultation['saved_at'] or 'Not explicitly saved'}",
        f"Diagnosis: {consultation['diagnosis'] or 'Not recorded'}",
        "",
    ]

    if patient:
        lines.extend([
            "Patient Biodata",
            f"Name: {patient['name']}",
            f"Age: {patient['age']}",
            f"Gender: {patient['gender']}",
            f"Phone: {patient['phone']}",
            f"Email: {patient['email'] or 'N/A'}",
            f"Address: {patient['address'] or 'N/A'}",
            f"Allergy: {patient['allergy'] or 'None recorded'}",
            f"Medical Conditions: {patient['medical_conditions'] or 'None recorded'}",
            "",
        ])

    lines.extend([
        "Initial Consultation Summary",
        consultation["notes"] or "N/A",
        "",
        "Doctor Private Notes",
        consultation["doctor_private_notes"] or "None recorded",
        "",
        "Transcript",
    ])

    if messages:
        for message in messages:
            lines.append(
                f"[{message['created_at']}] {message['sender_role']} ({message['sender_id']}): {message['message_text']}"
            )
    else:
        lines.append("No chat transcript recorded.")

    if bundle["prescriptions"]:
        lines.extend(["", "Prescriptions"])
        for item in bundle["prescriptions"]:
            diagnosis = "N/A"
            try:
                payload = json.loads(item["medication_json"] or "{}")
                diagnosis = payload.get("diagnosis") or "N/A"
            except (TypeError, ValueError, json.JSONDecodeError):
                pass
            lines.append(
                f"{item['created_at']} | {item['document_id']} | Diagnosis: {diagnosis} | Asset: {item['asset_path'] or 'N/A'}"
            )

    if bundle["investigations"]:
        lines.extend(["", "Investigations"])
        for item in bundle["investigations"]:
            lines.append(
                f"{item['created_at']} | {item['document_id']} | Diagnosis: {item['diagnosis'] or 'N/A'} | Asset: {item['asset_path'] or 'N/A'}"
            )

    if bundle["letters"]:
        lines.extend(["", "Referral Notes / Medical Reports"])
        for item in bundle["letters"]:
            extra = f" | Target: {item['target_hospital']}" if item["target_hospital"] else ""
            lines.append(
                f"{item['created_at']} | {item['document_type']} | {item['document_id']} | Diagnosis: {item['diagnosis']}{extra}"
            )

    content = "\n".join(lines) + "\n"
    buffer = BytesIO(content.encode("utf-8"))
    buffer.name = f"consultation_{consultation['consultation_id'][:8]}.txt"
    buffer.seek(0)
    return {
        "consultation_id": consultation["consultation_id"],
        "file": buffer,
        "filename": buffer.name,
    }
