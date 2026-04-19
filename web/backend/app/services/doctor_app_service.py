import os
from datetime import datetime, timezone

import httpx

import synmed_utils.doctor_registry as registry
from database import get_connection
from services.clinical_documents import (
    create_investigation_document,
    create_prescription_document,
)
from services.consultation_records import log_consultation_message
from synmed_utils.active_chats import end_chat, get_last_consultation, is_in_chat, start_chat
from synmed_utils.doctor_profiles import create_or_update_profile, doctor_profiles, get_rating_summary
from synmed_utils.doctor_profiles import format_doctor_intro
from synmed_utils.verified_doctors import is_verified
from .auth_service import hash_patient_password


UTC = timezone.utc


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


async def _send_telegram_message(chat_id: int, text: str):
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        return False

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
        )
    response.raise_for_status()
    return True


async def _send_telegram_document(chat_id: int, *, filename: str, content: bytes, caption: str):
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        return False

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"https://api.telegram.org/bot{token}/sendPhoto",
            data={
                "chat_id": str(chat_id),
                "caption": caption,
            },
            files={
                "photo": (filename, content, "image/png"),
            },
        )
    response.raise_for_status()
    return True


def _doctor_payload(doctor_id: int) -> dict:
    profile = doctor_profiles.get(doctor_id, {})
    return {
        "doctor_id": doctor_id,
        "name": profile.get("name") or "Doctor",
        "specialty": profile.get("specialty") or "N/A",
        "experience": profile.get("experience") or "N/A",
        "email": profile.get("email") or "",
        "license_id": profile.get("license_id") or "",
        "license_expiry_date": profile.get("license_expiry_date") or "",
        "rating_summary": get_rating_summary(doctor_id),
        "verified": is_verified(doctor_id),
        "status": (
            "busy"
            if doctor_id in registry.busy_doctors
            else "available"
            if doctor_id in registry.available_doctors
            else "offline"
        ),
    }


def _queue_payload() -> list[dict]:
    registry.prune_waiting_patients()
    items = []
    ordered_patient_ids = sorted(
        registry.waiting_patients,
        key=lambda patient_runtime_id: (
            0 if registry.pending_patient_details.get(patient_runtime_id, {}).get("emergency_flag") else 1,
            registry.waiting_patients.index(patient_runtime_id),
        ),
    )
    for patient_runtime_id in ordered_patient_ids:
        details = registry.pending_patient_details.get(patient_runtime_id, {})
        items.append(
            {
                "runtime_patient_id": patient_runtime_id,
                "hospital_number": details.get("hospital_number") or "N/A",
                "name": "Awaiting assignment",
                "summary": "Patient details will open after assignment.",
                "age": details.get("age") or "N/A",
                "emergency": bool(details.get("emergency_flag")),
                "source": details.get("source") or "telegram",
            }
        )
    return items


def _active_consultation_payload(doctor_id: int) -> dict | None:
    if not is_in_chat(doctor_id):
        return None

    consultation = get_last_consultation(doctor_id)
    if not consultation:
        return None

    details = consultation.get("patient_details") or {}
    return {
        "consultation_id": consultation["consultation_id"],
        "patient_runtime_id": consultation["patient_id"],
        "hospital_number": details.get("hospital_number") or "N/A",
        "patient_name": details.get("name") or "Unknown patient",
        "summary": details.get("history") or "No symptoms recorded",
        "source": details.get("source") or "telegram",
        "emergency": bool(details.get("emergency_flag")),
    }


def _doctor_notice_text(patient_details: dict) -> str:
    source_note = (
        "\nThis patient is consulting via SynMed Web. Reply here in the web doctor room and the patient will see your messages there."
        if patient_details.get("source") == "web"
        else ""
    )
    return (
        "New Patient Connected\n\n"
        f"Hospital Number: {patient_details.get('hospital_number', 'N/A')}\n"
        f"Name: {patient_details.get('name', 'N/A')}\n"
        f"Age: {patient_details.get('age', 'N/A')}\n"
        f"Gender: {patient_details.get('gender', 'N/A')}\n"
        f"Phone: {patient_details.get('phone', 'N/A')}\n"
        f"Address: {patient_details.get('address', 'N/A')}\n"
        f"Allergy: {patient_details.get('allergy', 'None recorded')}\n\n"
        "Medical History / Symptoms:\n"
        f"{patient_details.get('history', 'N/A')}\n\n"
        f"You may begin consultation.{source_note}"
    )


def _get_transcript_by_consultation_id(consultation_id: str) -> list[dict]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT sender_role, sender_id, message_text, created_at
            FROM consultation_messages
            WHERE consultation_id = ?
            ORDER BY id ASC
            """,
            (consultation_id,),
        )
        rows = cursor.fetchall()
    return [
        {
            "sender_role": row["sender_role"],
            "sender_id": row["sender_id"],
            "message_text": row["message_text"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def _current_consultation_for_doctor(doctor_id: int):
    consultation = get_last_consultation(doctor_id)
    if not consultation:
        return None, None
    return consultation, consultation.get("patient_details") or {}


def get_doctor_workspace(doctor_id: int) -> dict:
    if not is_verified(doctor_id):
        return {
            "found": False,
            "message": "Doctor is not verified on SynMed.",
            "doctor": None,
            "queue": [],
            "active_consultation": None,
        }

    return {
        "found": True,
        "message": "Doctor workspace loaded.",
        "doctor": _doctor_payload(doctor_id),
        "queue": _queue_payload(),
        "active_consultation": _active_consultation_payload(doctor_id),
    }


def update_doctor_presence(doctor_id: int, action: str) -> dict:
    if not is_verified(doctor_id):
        return {
            "found": False,
            "message": "Doctor is not verified on SynMed.",
            "doctor": None,
            "queue": [],
            "active_consultation": None,
        }

    normalized = action.strip().lower()
    if normalized == "offline":
        registry.remove_doctor_from_runtime(doctor_id)
        return get_doctor_workspace(doctor_id) | {"message": "Doctor is now offline."}

    if normalized != "online":
        return get_doctor_workspace(doctor_id) | {"message": "Unsupported presence action."}

    if doctor_id in registry.available_doctors or doctor_id in registry.busy_doctors:
        return get_doctor_workspace(doctor_id) | {"message": "Doctor presence already updated."}

    patient_id, patient_details = registry.pop_waiting_patient()
    if patient_id is None:
        registry.set_doctor_available(doctor_id)
        return get_doctor_workspace(doctor_id) | {"message": "Doctor is online and waiting for patients."}

    patient_details = {**patient_details, "doctor_channel": "web"}
    start_chat(patient_id, doctor_id, patient_details)
    registry.set_doctor_busy(doctor_id)
    return get_doctor_workspace(doctor_id) | {"message": "Doctor is online and connected to the next patient."}


def connect_doctor_to_selected_patient(doctor_id: int, runtime_patient_id: int) -> dict:
    if not is_verified(doctor_id):
        return get_doctor_workspace(doctor_id) | {"message": "Doctor is not verified on SynMed."}

    if doctor_id in registry.busy_doctors:
        return get_doctor_workspace(doctor_id) | {"message": "Finish the current consultation before selecting another patient."}

    details = registry.pending_patient_details.get(runtime_patient_id)
    if not details or runtime_patient_id not in registry.waiting_patients:
        return get_doctor_workspace(doctor_id) | {"message": "That patient is no longer in the waiting queue."}

    registry.remove_patient_from_queue(runtime_patient_id)
    patient_details = {**details, "doctor_channel": "web"}
    start_chat(runtime_patient_id, doctor_id, patient_details)
    registry.set_doctor_busy(doctor_id)
    return get_doctor_workspace(doctor_id) | {"message": "Doctor connected to the selected patient."}


def get_doctor_transcript(doctor_id: int) -> dict:
    consultation = get_last_consultation(doctor_id)
    if not consultation:
        return {
            "found": False,
            "message": "No active consultation found for this doctor.",
            "consultation_id": None,
            "transcript": [],
        }

    return {
        "found": True,
        "message": "Doctor transcript loaded.",
        "consultation_id": consultation["consultation_id"],
        "transcript": _get_transcript_by_consultation_id(consultation["consultation_id"]),
    }


async def send_doctor_message(doctor_id: int, message_text: str) -> dict:
    consultation = get_last_consultation(doctor_id)
    if not consultation:
        return {
            "sent": False,
            "message": "No active consultation found for this doctor.",
            "consultation_id": None,
            "transcript": [],
        }

    patient_details = consultation.get("patient_details") or {}
    patient_runtime_id = consultation["patient_id"]
    consultation_id = consultation["consultation_id"]

    log_consultation_message(
        consultation_id,
        sender_id=doctor_id,
        sender_role="doctor_web",
        message_text=message_text.strip(),
    )

    if patient_details.get("source") != "web":
        try:
            await _send_telegram_message(patient_runtime_id, message_text.strip())
        except Exception:
            pass

    return {
        "sent": True,
        "message": "Doctor message saved and delivered to the patient channel.",
        "consultation_id": consultation_id,
        "transcript": _get_transcript_by_consultation_id(consultation_id),
    }


async def end_doctor_chat(doctor_id: int) -> dict:
    consultation = get_last_consultation(doctor_id)
    if not consultation:
        return get_doctor_workspace(doctor_id) | {"message": "No active consultation to end."}

    patient_details = consultation.get("patient_details") or {}
    patient_id = consultation["patient_id"]
    end_chat(doctor_id)
    registry.remove_doctor_from_runtime(doctor_id)

    if patient_details.get("source") != "web":
        try:
            await _send_telegram_message(patient_id, "The consultation has ended.")
        except Exception:
            pass

    next_patient_id, next_patient_details = registry.pop_waiting_patient()
    if next_patient_id is None:
        registry.set_doctor_available(doctor_id)
        return get_doctor_workspace(doctor_id) | {"message": "Consultation ended. Doctor is now online and waiting."}

    next_patient_details = {**next_patient_details, "doctor_channel": "web"}
    start_chat(next_patient_id, doctor_id, next_patient_details)
    registry.set_doctor_busy(doctor_id)

    if next_patient_details.get("source") != "web":
        try:
            await _send_telegram_message(next_patient_id, format_doctor_intro(doctor_id))
        except Exception:
            pass

    return get_doctor_workspace(doctor_id) | {
        "message": "Consultation ended. Next patient has been assigned to the doctor workspace.",
    }


def get_doctor_account(doctor_id: int) -> dict:
    if not is_verified(doctor_id):
        return {
            "found": False,
            "message": "Doctor is not verified on SynMed.",
            "doctor": None,
        }
    return {
        "found": True,
        "message": "Doctor account loaded.",
        "doctor": _doctor_payload(doctor_id),
    }


def update_doctor_account(doctor_id: int, payload: dict) -> dict:
    if not is_verified(doctor_id):
        return {
            "found": False,
            "message": "Doctor is not verified on SynMed.",
            "doctor": None,
        }

    existing = doctor_profiles.get(doctor_id, {}) or {}
    create_or_update_profile(
        doctor_id,
        {
            **existing,
            "name": payload.get("name", "").strip(),
            "specialty": payload.get("specialty", "").strip(),
            "experience": payload.get("experience", "").strip(),
            "email": payload.get("email", "").strip().lower(),
            "license_id": payload.get("license_id", "").strip(),
            "license_expiry_date": payload.get("license_expiry_date", "").strip(),
            "updated_at": _now_iso(),
            "verified": True,
        },
    )
    refreshed = get_doctor_account(doctor_id)
    return refreshed | {"message": "Doctor account updated successfully."}


def change_doctor_password(doctor_id: int, current_password: str, new_password: str) -> dict:
    if not is_verified(doctor_id):
        return {
            "success": False,
            "message": "Doctor is not verified on SynMed.",
        }

    profile = doctor_profiles.get(doctor_id, {}) or {}
    stored_password_hash = profile.get("password_hash") or ""
    if not stored_password_hash or stored_password_hash != hash_patient_password(current_password):
        return {
            "success": False,
            "message": "Current password is incorrect.",
        }

    create_or_update_profile(
        doctor_id,
        {
            **profile,
            "password_hash": hash_patient_password(new_password),
            "updated_at": _now_iso(),
            "verified": True,
        },
    )
    return {
        "success": True,
        "message": "Password changed successfully.",
    }


async def create_doctor_prescription(
    doctor_id: int,
    *,
    diagnosis: str,
    medications_text: str,
    notes: str = "",
) -> dict:
    consultation, patient_details = _current_consultation_for_doctor(doctor_id)
    if not consultation:
        return {
            "created": False,
            "message": "No active consultation found for this doctor.",
            "consultation_id": None,
            "filename": None,
            "asset_url": None,
            "asset_type": None,
            "delivered_to_patient": False,
            "document_kind": "prescription",
            "preview_text": None,
        }

    document = create_prescription_document(
        consultation_id=consultation["consultation_id"],
        doctor_id=doctor_id,
        patient_id=consultation["patient_id"],
        patient_details=patient_details,
        diagnosis=diagnosis.strip(),
        medications_text=medications_text.strip(),
        notes=notes.strip(),
    )

    delivered = False
    if patient_details.get("source") != "web":
        try:
            delivered = await _send_telegram_document(
                consultation["patient_id"],
                filename=document["filename"],
                content=document["file"].getvalue(),
                caption="Prescription for your SynMed consultation.",
            )
        except Exception:
            delivered = False

    return {
        "created": True,
        "message": (
            "Prescription created and sent to the patient."
            if delivered
            else "Prescription created successfully."
        ),
        "consultation_id": consultation["consultation_id"],
        "filename": document["filename"],
        "asset_url": document["asset_url"],
        "asset_type": document["asset_type"],
        "delivered_to_patient": delivered,
        "document_kind": "prescription",
        "preview_text": document["content"],
    }


async def create_doctor_investigation(
    doctor_id: int,
    *,
    diagnosis: str,
    tests_text: str,
    notes: str = "",
) -> dict:
    consultation, patient_details = _current_consultation_for_doctor(doctor_id)
    if not consultation:
        return {
            "created": False,
            "message": "No active consultation found for this doctor.",
            "consultation_id": None,
            "filename": None,
            "asset_url": None,
            "asset_type": None,
            "delivered_to_patient": False,
            "document_kind": "investigation",
            "preview_text": None,
        }

    document = create_investigation_document(
        consultation_id=consultation["consultation_id"],
        doctor_id=doctor_id,
        patient_id=consultation["patient_id"],
        patient_details=patient_details,
        diagnosis=diagnosis.strip(),
        tests_text=tests_text.strip(),
        notes=notes.strip(),
    )

    delivered = False
    if patient_details.get("source") != "web":
        try:
            delivered = await _send_telegram_document(
                consultation["patient_id"],
                filename=document["filename"],
                content=document["file"].getvalue(),
                caption="Investigation request for your SynMed consultation.",
            )
        except Exception:
            delivered = False

    return {
        "created": True,
        "message": (
            "Investigation request created and sent to the patient."
            if delivered
            else "Investigation request created successfully."
        ),
        "consultation_id": consultation["consultation_id"],
        "filename": document["filename"],
        "asset_url": document["asset_url"],
        "asset_type": document["asset_type"],
        "delivered_to_patient": delivered,
        "document_kind": "investigation",
        "preview_text": document["content"],
    }
