from datetime import datetime, timedelta, timezone
from uuid import uuid4

from services.consultation_records import close_consultation_record, start_consultation_record
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


def start_chat(patient_id: int, doctor_id: int, patient_details: dict | None = None):
    """
    Start a chat between patient and doctor.
    This is the single source of truth.
    """
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
    save_active_consultation(
        consultation_id=consultation["consultation_id"],
        patient_id=patient_id,
        doctor_id=doctor_id,
        patient_details=patient_details or {},
    )
    return consultation["consultation_id"]


def is_in_chat(user_id: int) -> bool:
    return user_id in active_chats


def get_partner(user_id: int):
    return active_chats.get(user_id)


def end_chat(user_id: int):
    consultation = last_consultation.get(user_id)
    partner_id = active_chats.pop(user_id, None)

    if partner_id:
        active_chats.pop(partner_id, None)
        if consultation:
            close_consultation_record(consultation["consultation_id"])
        last_consultation.pop(user_id, None)
        last_consultation.pop(partner_id, None)
        last_activity.pop(user_id, None)
        last_activity.pop(partner_id, None)
        remove_active_consultation_by_user(user_id)
        return partner_id

    return None


def get_last_doctor(patient_id: int):
    consultation = last_consultation.get(patient_id)
    if not consultation:
        return None
    return consultation["doctor_id"]


def get_last_consultation(user_id: int):
    return last_consultation.get(user_id)


def touch_chat_activity(user_id: int):
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
    clear_runtime_state()
    for item in load_active_consultations():
        consultation = {
            "consultation_id": item["consultation_id"],
            "doctor_id": item["doctor_id"],
            "patient_id": item["patient_id"],
            "patient_details": item["patient_details"],
            "started_at": _now(),
        }
        active_chats[item["patient_id"]] = item["doctor_id"]
        active_chats[item["doctor_id"]] = item["patient_id"]
        last_consultation[item["patient_id"]] = consultation
        last_consultation[item["doctor_id"]] = consultation
        last_activity[item["patient_id"]] = _now()
        last_activity[item["doctor_id"]] = _now()


restore_runtime_state()
