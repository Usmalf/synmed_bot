import json
from datetime import datetime, timezone
from io import BytesIO

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
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT consultation_id, patient_id, doctor_id, status, notes,
                   created_at, closed_at, doctor_private_notes
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

        cursor.execute(
            """
            SELECT sender_role, sender_id, message_text, created_at
            FROM consultation_messages
            WHERE consultation_id = ?
            ORDER BY id ASC
            """,
            (consultation["consultation_id"],),
        )
        messages = cursor.fetchall()

        cursor.execute(
            """
            SELECT patient_id, name, age, gender, phone, address, allergy
            FROM patients
            WHERE patient_id = ?
            """,
            (consultation["patient_id"],),
        )
        patient = cursor.fetchone()

    lines = [
        "SynMed Telehealth Consultation Export",
        "",
        f"Consultation ID: {consultation['consultation_id']}",
        f"Hospital Number: {consultation['patient_id']}",
        f"Doctor ID: {consultation['doctor_id']}",
        f"Status: {consultation['status']}",
        f"Created At: {consultation['created_at']}",
        f"Closed At: {consultation['closed_at'] or 'Active'}",
        "",
    ]

    if patient:
        lines.extend([
            "Patient Biodata",
            f"Name: {patient['name']}",
            f"Age: {patient['age']}",
            f"Gender: {patient['gender']}",
            f"Phone: {patient['phone']}",
            f"Address: {patient['address'] or 'N/A'}",
            f"Allergy: {patient['allergy'] or 'None recorded'}",
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

    content = "\n".join(lines) + "\n"
    buffer = BytesIO(content.encode("utf-8"))
    buffer.name = f"consultation_{consultation['consultation_id'][:8]}.txt"
    buffer.seek(0)
    return {
        "consultation_id": consultation["consultation_id"],
        "file": buffer,
        "filename": buffer.name,
    }
