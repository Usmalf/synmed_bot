# synmed_utils/doctor_registry.py
from datetime import datetime, timedelta, timezone

from services.patient_records import get_patient_by_identifier
from services.paystack import get_payment_by_reference
from services.runtime_state import (
    load_doctor_presence,
    load_waiting_patients,
    remove_doctor_presence,
    remove_waiting_patient,
    save_doctor_presence,
    save_waiting_patient,
)

available_doctors = set()
busy_doctors = set()
waiting_patients = []
pending_patient_details = {}
UTC = timezone.utc
WEB_QUEUE_MAX_AGE = timedelta(hours=2)


def _parse_iso_datetime(value: str | None):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except ValueError:
        return None


def _is_assignable_waiting_patient(patient_id: int, details: dict) -> bool:
    source = (details or {}).get("source")
    if source != "web":
        return True

    submitted_at = _parse_iso_datetime((details or {}).get("submitted_at"))
    if submitted_at is None or datetime.now(UTC) - submitted_at > WEB_QUEUE_MAX_AGE:
        return False

    reference = (details or {}).get("reference")
    if not reference:
        return False

    payment = get_payment_by_reference(reference)
    if not payment or payment["status"] != "verified":
        return False

    patient = get_patient_by_identifier(payment["patient_id"] or "")
    if not patient:
        return False

    return patient["id"] == patient_id


def set_doctor_available(doctor_id: int):
    busy_doctors.discard(doctor_id)
    available_doctors.add(doctor_id)
    save_doctor_presence(doctor_id=doctor_id, status="available")


def set_doctor_busy(doctor_id: int):
    available_doctors.discard(doctor_id)
    busy_doctors.add(doctor_id)
    save_doctor_presence(doctor_id=doctor_id, status="busy")


def clear_doctor_runtime_state():
    available_doctors.clear()
    busy_doctors.clear()
    waiting_patients.clear()
    pending_patient_details.clear()


def queue_patient(patient_id: int, details: dict):
    if patient_id in waiting_patients:
        waiting_patients.remove(patient_id)

    if details.get("emergency_flag"):
        waiting_patients.insert(0, patient_id)
    else:
        waiting_patients.append(patient_id)
    pending_patient_details[patient_id] = details
    for index, queued_patient_id in enumerate(waiting_patients):
        save_waiting_patient(
            patient_id=queued_patient_id,
            queue_position=index,
            details=pending_patient_details.get(queued_patient_id, {}),
        )


def remove_patient_from_queue(patient_id: int):
    if patient_id in waiting_patients:
        waiting_patients.remove(patient_id)
    pending_patient_details.pop(patient_id, None)
    remove_waiting_patient(patient_id)
    for index, queued_patient_id in enumerate(waiting_patients):
        save_waiting_patient(
            patient_id=queued_patient_id,
            queue_position=index,
            details=pending_patient_details.get(queued_patient_id, {}),
        )


def prune_waiting_patients():
    stale_patient_ids = [
        patient_id
        for patient_id in list(waiting_patients)
        if not _is_assignable_waiting_patient(patient_id, pending_patient_details.get(patient_id, {}))
    ]
    for patient_id in stale_patient_ids:
        remove_patient_from_queue(patient_id)


def pop_waiting_patient():
    prune_waiting_patients()
    while waiting_patients:
        patient_id = waiting_patients.pop(0)
        details = pending_patient_details.pop(patient_id, {})
        remove_waiting_patient(patient_id)
        if _is_assignable_waiting_patient(patient_id, details):
            for index, queued_patient_id in enumerate(waiting_patients):
                save_waiting_patient(
                    patient_id=queued_patient_id,
                    queue_position=index,
                    details=pending_patient_details.get(queued_patient_id, {}),
                )
            return patient_id, details

    return None, None


def remove_doctor_from_runtime(doctor_id: int):
    available_doctors.discard(doctor_id)
    busy_doctors.discard(doctor_id)
    remove_doctor_presence(doctor_id)


def restore_runtime_state():
    clear_doctor_runtime_state()
    for row in load_doctor_presence():
        doctor_id = row["doctor_id"]
        if row["status"] == "busy":
            busy_doctors.add(doctor_id)
        else:
            available_doctors.add(doctor_id)

    restored_waiting = load_waiting_patients()
    for item in restored_waiting:
        waiting_patients.append(item["patient_id"])
        pending_patient_details[item["patient_id"]] = item["details"]
    prune_waiting_patients()


restore_runtime_state()
