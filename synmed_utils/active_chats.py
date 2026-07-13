from datetime import datetime, timedelta, timezone
from uuid import uuid4

from database import get_connection
from services.consultation_records import (
    close_consultation_record,
    log_consultation_event,
    log_consultation_message,
    start_consultation_record,
)
from services.runtime_state import (
    load_active_consultations,
    remove_active_consultation_by_user,
    save_active_consultation,
)


# key = patient_id, value = doctor_id
active_chats = {}
last_consultation = {}  # patient_id -> consultation metadata
last_activity = {}  # user_id -> last activity timestamp
UTC = timezone.utc


def _now():
    return datetime.now(UTC)


def _runtime_id(user_id):
    try:
        return int(user_id)
    except (TypeError, ValueError):
        return user_id


def start_chat(patient_id: int, doctor_id: int, patient_details: dict | None = None):
    """
    Start a chat between patient and doctor.
    This is the single source of truth.
    """
    patient_id = _runtime_id(patient_id)
    doctor_id = _runtime_id(doctor_id)
    active_chats[patient_id] = doctor_id
    active_chats[doctor_id] = patient_id

    consultation = {
        "consultation_id": uuid4().hex,
        "doctor_id": doctor_id,
        "patient_id": patient_id,
        "patient_details": patient_details or {},
        "started_at": _now(),
    }
    last_consultation[patient_id] = consultation
    last_consultation[doctor_id] = consultation
    now = _now()
    last_activity[patient_id] = now
    last_activity[doctor_id] = now

    if patient_details and patient_details.get("hospital_number"):
        summary = (
            f"Symptoms / History: {patient_details.get('history', 'N/A')}\n"
            f"Address: {patient_details.get('address', 'N/A')}\n"
            f"Allergy: {patient_details.get('allergy', 'None recorded')}"
        )
        start_consultation_record(
            consultation["consultation_id"],
            patient_record=patient_details,
            doctor_id=doctor_id,
            summary=summary,
        )
        if patient_details.get("source") == "web" and patient_details.get("history"):
            log_consultation_message(
                consultation["consultation_id"],
                sender_id=patient_id,
                sender_role="patient",
                message_text=patient_details["history"],
            )
    save_active_consultation(
        consultation_id=consultation["consultation_id"],
        patient_id=patient_id,
        doctor_id=doctor_id,
        patient_details=patient_details or {},
    )
    return consultation["consultation_id"]


def is_in_chat(user_id: int) -> bool:
    user_id = _runtime_id(user_id)
    return user_id in active_chats


def get_partner(user_id: int):
    user_id = _runtime_id(user_id)
    return active_chats.get(user_id)


def end_chat(user_id: int):
    user_id = _runtime_id(user_id)
    consultation = last_consultation.get(user_id)
    partner_id = active_chats.pop(user_id, None)

    if partner_id:
        active_chats.pop(partner_id, None)
        if consultation:
            close_consultation_record(
                consultation["consultation_id"],
                (consultation.get("patient_details") or {}).get("reference"),
            )
        last_consultation.pop(user_id, None)
        last_consultation.pop(partner_id, None)
        last_activity.pop(user_id, None)
        last_activity.pop(partner_id, None)
        remove_active_consultation_by_user(user_id)
        return partner_id

    return None


def get_last_doctor(patient_id: int):
    patient_id = _runtime_id(patient_id)
    consultation = last_consultation.get(patient_id)
    if not consultation:
        return None
    return consultation["doctor_id"]


def get_last_consultation(user_id: int):
    user_id = _runtime_id(user_id)
    return last_consultation.get(user_id)


def transfer_chat_to_doctor(from_doctor_id: int, to_doctor_id: int, handover_note: str = ""):
    from_doctor_id = _runtime_id(from_doctor_id)
    to_doctor_id = _runtime_id(to_doctor_id)
    consultation = last_consultation.get(from_doctor_id)
    if not consultation or active_chats.get(from_doctor_id) != consultation.get("patient_id"):
        return None

    patient_id = consultation["patient_id"]
    consultation["doctor_id"] = to_doctor_id
    active_chats.pop(from_doctor_id, None)
    active_chats[patient_id] = to_doctor_id
    active_chats[to_doctor_id] = patient_id
    last_consultation.pop(from_doctor_id, None)
    last_consultation[patient_id] = consultation
    last_consultation[to_doctor_id] = consultation
    last_activity.pop(from_doctor_id, None)
    now = _now()
    last_activity[patient_id] = now
    last_activity[to_doctor_id] = now

    save_active_consultation(
        consultation_id=consultation["consultation_id"],
        patient_id=patient_id,
        doctor_id=to_doctor_id,
        patient_details=consultation.get("patient_details") or {},
    )
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE consultations
            SET doctor_id = ?, doctor_telegram_id = ?
            WHERE consultation_id = ?
            """,
            (str(to_doctor_id), to_doctor_id, consultation["consultation_id"]),
        )
        conn.commit()

    if handover_note.strip():
        log_consultation_event(
            consultation["consultation_id"],
            event_type="consultation_transferred",
            actor_id=str(from_doctor_id),
            details=handover_note.strip(),
        )
    return consultation


def touch_chat_activity(user_id: int):
    user_id = _runtime_id(user_id)
    consultation = last_consultation.get(user_id)
    if not consultation:
        return
    now = _now()
    patient_id = consultation["patient_id"]
    doctor_id = consultation["doctor_id"]
    last_activity[patient_id] = now
    last_activity[doctor_id] = now


def get_idle_consultations(max_idle: timedelta):
    now = _now()
    consultations = {}
    for consultation in last_consultation.values():
        consultations[consultation["consultation_id"]] = consultation

    idle = []
    for consultation in consultations.values():
        patient_id = consultation["patient_id"]
        doctor_id = consultation["doctor_id"]
        last_seen = max(
            last_activity.get(patient_id, consultation.get("started_at", now)),
            last_activity.get(doctor_id, consultation.get("started_at", now)),
        )
        if now - last_seen >= max_idle:
            idle.append(consultation)
    return idle


def clear_runtime_state():
    active_chats.clear()
    last_consultation.clear()
    last_activity.clear()


def restore_runtime_state():
    restored_consultations = load_active_consultations()
    if restored_consultations is None:
        return

    clear_runtime_state()
    for item in restored_consultations:
        patient_id = _runtime_id(item["patient_id"])
        doctor_id = _runtime_id(item["doctor_id"])
        consultation = {
            "consultation_id": item["consultation_id"],
            "doctor_id": doctor_id,
            "patient_id": patient_id,
            "patient_details": item["patient_details"],
            "started_at": _now(),
        }
        active_chats[patient_id] = doctor_id
        active_chats[doctor_id] = patient_id
        last_consultation[patient_id] = consultation
        last_consultation[doctor_id] = consultation
        last_activity[patient_id] = _now()
        last_activity[doctor_id] = _now()


restore_runtime_state()
