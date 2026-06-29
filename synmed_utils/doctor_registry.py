# synmed_utils/doctor_registry.py
import json
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
available_doctors_by_channel = {"web": set(), "telegram": set()}
busy_doctors_by_channel = {"web": set(), "telegram": set()}
UTC = timezone.utc
WEB_QUEUE_MAX_AGE = timedelta(hours=2)


def normalize_channel(channel: str | None) -> str:
    return "web" if (channel or "").strip().lower() == "web" else "telegram"


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


def _rebuild_aggregate_presence():
    available_doctors.clear()
    busy_doctors.clear()
    for items in available_doctors_by_channel.values():
        available_doctors.update(items)
    for items in busy_doctors_by_channel.values():
        busy_doctors.update(items)


def is_doctor_available(doctor_id: int, channel: str | None = None) -> bool:
    return doctor_id in available_doctors_by_channel[normalize_channel(channel)]


def is_doctor_busy(doctor_id: int, channel: str | None = None) -> bool:
    if channel is None:
        return doctor_id in busy_doctors
    return doctor_id in busy_doctors_by_channel[normalize_channel(channel)]


def set_doctor_available(doctor_id: int, channel: str | None = None):
    channel_key = normalize_channel(channel)
    busy_doctors_by_channel[channel_key].discard(doctor_id)
    available_doctors_by_channel[channel_key].add(doctor_id)
    _rebuild_aggregate_presence()
    save_doctor_presence(doctor_id=doctor_id, status="available", channel=channel_key)


def set_doctor_busy(doctor_id: int, channel: str | None = None):
    channel_key = normalize_channel(channel)
    available_doctors_by_channel[channel_key].discard(doctor_id)
    busy_doctors_by_channel[channel_key].add(doctor_id)
    _rebuild_aggregate_presence()
    save_doctor_presence(doctor_id=doctor_id, status="busy", channel=channel_key)


def claim_available_doctor(channel: str | None = None):
    channel_key = normalize_channel(channel)
    if not available_doctors_by_channel[channel_key]:
        return None
    doctor_id = next(iter(available_doctors_by_channel[channel_key]))
    available_doctors_by_channel[channel_key].discard(doctor_id)
    _rebuild_aggregate_presence()
    return doctor_id


def clear_doctor_runtime_state():
    available_doctors.clear()
    busy_doctors.clear()
    for items in available_doctors_by_channel.values():
        items.clear()
    for items in busy_doctors_by_channel.values():
        items.clear()
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


def get_waiting_patients(channel: str | None = None) -> list[int]:
    prune_waiting_patients()
    channel_key = normalize_channel(channel) if channel else None
    if channel_key is None:
        return list(waiting_patients)
    return [
        patient_id
        for patient_id in waiting_patients
        if normalize_channel(pending_patient_details.get(patient_id, {}).get("source")) == channel_key
    ]


def pop_waiting_patient(channel: str | None = None):
    prune_waiting_patients()
    channel_key = normalize_channel(channel) if channel else None
    while waiting_patients:
        next_index = None
        for index, queued_patient_id in enumerate(waiting_patients):
            details = pending_patient_details.get(queued_patient_id, {})
            if channel_key and normalize_channel(details.get("source")) != channel_key:
                continue
            next_index = index
            break
        if next_index is None:
            return None, None

        patient_id = waiting_patients.pop(next_index)
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


def remove_doctor_from_runtime(doctor_id: int, channel: str | None = None):
    if channel is None:
        available_doctors.discard(doctor_id)
        busy_doctors.discard(doctor_id)
        for items in available_doctors_by_channel.values():
            items.discard(doctor_id)
        for items in busy_doctors_by_channel.values():
            items.discard(doctor_id)
        remove_doctor_presence(doctor_id)
        return

    channel_key = normalize_channel(channel)
    available_doctors_by_channel[channel_key].discard(doctor_id)
    busy_doctors_by_channel[channel_key].discard(doctor_id)
    _rebuild_aggregate_presence()
    remove_doctor_presence(doctor_id, channel=channel_key)


def restore_runtime_state():
    clear_doctor_runtime_state()
    for row in load_doctor_presence():
        doctor_id = row["doctor_id"]
        status_value = row["status"]
        status_map = {}
        if isinstance(status_value, str) and status_value.startswith("{"):
            try:
                status_map = {
                    normalize_channel(key): value
                    for key, value in json.loads(status_value).items()
                    if value
                }
            except Exception:
                status_map = {}
        if not status_map:
            status_map = {"telegram": status_value}

        for channel_key, status in status_map.items():
            normalized_channel = normalize_channel(channel_key)
            if status == "busy":
                busy_doctors_by_channel[normalized_channel].add(doctor_id)
            elif status == "available":
                available_doctors_by_channel[normalized_channel].add(doctor_id)
    _rebuild_aggregate_presence()

    restored_waiting = load_waiting_patients()
    for item in restored_waiting:
        waiting_patients.append(item["patient_id"])
        pending_patient_details[item["patient_id"]] = item["details"]
    prune_waiting_patients()


restore_runtime_state()
