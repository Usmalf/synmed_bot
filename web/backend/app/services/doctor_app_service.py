import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import httpx

import synmed_utils.doctor_registry as registry
from database import get_connection
from services.clinical_documents import (
    create_investigation_document,
    create_medical_report_document,
    create_prescription_document,
)
from services import storage_service
from services.consultation_calls import (
    clear_consultation_call_state,
    get_consultation_call_state,
    update_consultation_call_state,
)
from services.consultation_records import log_consultation_message
from services.consultation_records import set_consultation_diagnosis
from services.consultation_records import set_consultation_notes
from services.operational_errors import log_exception, log_operational_error
from services.patient_records import get_patient_by_identifier
from .chat_realtime_service import realtime_hub
from synmed_utils.active_chats import (
    end_chat,
    get_last_consultation,
    is_in_chat,
    restore_runtime_state as restore_active_chat_state,
    start_chat,
)
from synmed_utils.doctor_profiles import create_or_update_profile, doctor_profiles, get_rating_summary
from synmed_utils.doctor_profiles import format_doctor_intro
from synmed_utils.verified_doctors import is_verified
from .auth_service import hash_patient_password, send_email_with_attachment, send_plain_email
from .medical_report_app_service import list_doctor_medical_report_requests
from .whatsapp_service import send_patient_document_notice, send_text_message, send_text_message_sync


UTC = timezone.utc


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _restore_runtime_state():
    registry.restore_runtime_state()
    restore_active_chat_state()


def _runtime_id(user_id):
    try:
        return int(user_id)
    except (TypeError, ValueError):
        return user_id


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


async def _send_whatsapp_document_notice(patient_details: dict, document_kind: str, document: dict | None = None) -> bool:
    try:
        return await send_patient_document_notice(
            patient_details,
            document_kind,
            (document or {}).get("asset_url") or "",
            (document or {}).get("filename") or "",
        )
    except Exception:
        return False


def _doctor_payload(doctor_id: int) -> dict:
    doctor_id = _runtime_id(doctor_id)
    profile = doctor_profiles.get(doctor_id, {})
    return {
        "doctor_id": doctor_id,
        "name": profile.get("name") or "Doctor",
        "specialty": profile.get("specialty") or "N/A",
        "experience": profile.get("experience") or "N/A",
        "email": profile.get("email") or "",
        "license_id": profile.get("license_id") or "",
        "license_expiry_date": profile.get("license_expiry_date") or "",
        "license_file_url": _doctor_license_url(profile),
        "license_file_name": profile.get("license_file_name") or "",
        "license_file_size": profile.get("license_file_size") or None,
        "rating_summary": get_rating_summary(doctor_id),
        "verified": is_verified(doctor_id),
        "status": (
            "busy"
            if registry.is_doctor_busy(doctor_id, "web")
            else "available"
            if registry.is_doctor_available(doctor_id, "web")
            else "offline"
        ),
    }


def _clear_stale_busy_state(doctor_id: int):
    doctor_id = _runtime_id(doctor_id)
    consultation = get_last_consultation(doctor_id)
    if consultation and is_in_chat(doctor_id):
        return
    if registry.is_doctor_busy(doctor_id, "web"):
        registry.remove_doctor_from_runtime(doctor_id, channel="web")


def _queue_payload() -> list[dict]:
    registry.prune_waiting_patients()
    items = []
    ordered_patient_ids = sorted(
        registry.get_waiting_patients("web"),
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
                "source": details.get("channel") or details.get("source") or "telegram",
            }
        )
    return items


def _active_consultation_payload(doctor_id: int) -> dict | None:
    doctor_id = _runtime_id(doctor_id)
    if not is_in_chat(doctor_id):
        return None

    consultation = get_last_consultation(doctor_id)
    if not consultation:
        return None

    details = consultation.get("patient_details") or {}
    if details.get("source") != "web":
        return None

    return {
        "consultation_id": consultation["consultation_id"],
        "patient_runtime_id": consultation["patient_id"],
        "hospital_number": details.get("hospital_number") or "N/A",
        "patient_name": details.get("name") or "Unknown patient",
        "age": details.get("age") or "N/A",
        "gender": details.get("gender") or "N/A",
        "allergy": details.get("allergy") or "None recorded",
        "medical_conditions": details.get("medical_conditions") or "None recorded",
        "summary": details.get("history") or "No symptoms recorded",
        "saved_history": details.get("history") or "No symptoms recorded",
        "source": details.get("channel") or details.get("source") or "telegram",
        "emergency": bool(details.get("emergency_flag")),
    }


def _active_consultation_payload_from_consultation(consultation: dict | None) -> dict | None:
    if not consultation:
        return None
    details = consultation.get("patient_details") or {}
    if details.get("source") != "web":
        return None
    return {
        "consultation_id": consultation["consultation_id"],
        "patient_runtime_id": consultation["patient_id"],
        "hospital_number": details.get("hospital_number") or "N/A",
        "patient_name": details.get("name") or "Unknown patient",
        "age": details.get("age") or "N/A",
        "gender": details.get("gender") or "N/A",
        "allergy": details.get("allergy") or "None recorded",
        "medical_conditions": details.get("medical_conditions") or "None recorded",
        "summary": details.get("history") or "No symptoms recorded",
        "saved_history": details.get("history") or "No symptoms recorded",
        "source": details.get("channel") or details.get("source") or "telegram",
        "emergency": bool(details.get("emergency_flag")),
    }


def _doctor_connect_response(doctor_id: int, active_consultation: dict | None, message: str) -> dict:
    return {
        "found": True,
        "message": message,
        "doctor": _doctor_payload(doctor_id),
        "queue": [],
        "active_consultation": active_consultation,
        "medical_report_requests": [],
        "call": None,
    }


def _doctor_connect_blocked_response(doctor_id: int, message: str, details: dict | None = None) -> dict:
    if details:
        log_operational_error(
            source="doctor_connect_blocked",
            severity="warning",
            message=message,
            user_role="doctor",
            user_id=str(doctor_id),
            details=details,
        )
    workspace = get_doctor_workspace(doctor_id)
    return {
        **workspace,
        "found": False,
        "message": message,
    }


def _doctor_notice_text(patient_details: dict) -> str:
    source_note = (
        "\nThis patient is consulting via WhatsApp. Reply here in the web doctor room and the patient will receive your messages on WhatsApp."
        if patient_details.get("channel") == "whatsapp"
        else "\nThis patient is consulting via SynMed Web. Reply here in the web doctor room and the patient will see your messages there."
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
            SELECT sender_role, sender_id, message_text, asset_path, asset_type, created_at
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
            "asset_url": (
                f"/consultation-media/{(row['asset_path'] or '').replace('consultation_media/', '', 1)}"
                if row["asset_path"]
                else None
            ),
            "asset_type": row["asset_type"],
            "asset_size": _chat_asset_size(row["asset_path"]),
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def _chat_asset_size(asset_path: str | None) -> int | None:
    return storage_service.file_size(asset_path)


def _doctor_license_url(profile: dict) -> str:
    file_id = profile.get("license_file_id") or ""
    if not file_id:
        return ""
    if file_id.startswith("doctor_application_files/"):
        return f"/doctor-application-files/{file_id.replace('doctor_application_files/', '', 1)}"
    return ""


def _save_chat_upload(filename: str, content_type: str, data: str, actor: str) -> tuple[str, str]:
    original_name = Path(filename or "attachment").name
    extension = Path(original_name).suffix[:16]
    stored_name = f"{actor}-{uuid4().hex}{extension}"
    asset_path, _decoded = storage_service.save_base64_upload("consultation_media/chat_uploads", stored_name, data)
    return asset_path, content_type or "application/octet-stream"


def _save_doctor_license_upload(filename: str, content_type: str, data: str) -> tuple[str, str, str, int]:
    original_name = Path(filename or "annual-licence").name
    extension = Path(original_name).suffix[:16] or ".bin"
    stored_name = f"annual-license-{uuid4().hex}{extension}"
    asset_path, decoded = storage_service.save_base64_upload("doctor_application_files", stored_name, data)
    return asset_path, content_type or "application/octet-stream", original_name, len(decoded)


def _call_payload_for_consultation(consultation_id: str | None) -> dict | None:
    if not consultation_id:
        return None

    state = get_consultation_call_state(consultation_id)
    return {
        "consultation_id": consultation_id,
        "status": state.get("status") or "idle",
        "call_type": state.get("call_type"),
        "initiated_by": state.get("initiated_by"),
        "offer_sdp": state.get("offer_sdp"),
        "answer_sdp": state.get("answer_sdp"),
        "patient_candidates": state.get("patient_candidates") or [],
        "doctor_candidates": state.get("doctor_candidates") or [],
        "started_at": state.get("started_at"),
        "connected_at": state.get("connected_at"),
        "updated_at": state.get("updated_at"),
    }


def _current_consultation_for_doctor(doctor_id: int):
    doctor_id = _runtime_id(doctor_id)
    _restore_runtime_state()
    consultation = get_last_consultation(doctor_id)
    if not consultation:
        return None, None
    details = consultation.get("patient_details") or {}
    if details.get("source") != "web":
        return None, None
    return consultation, details


def _medical_report_request_consultation(doctor_id: int, request_id: str):
    cleaned_request_id = (request_id or "").strip()
    if not cleaned_request_id:
        return None, None, None

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT request_id, patient_id, consultation_id, doctor_id, request_note,
                   delivery_email, status, payment_status, fulfilled_letter_id
            FROM medical_report_requests
            WHERE request_id = ?
            """,
            (cleaned_request_id,),
        )
        request = cursor.fetchone()
        if not request or str(request["doctor_id"] or "") != str(doctor_id):
            return None, None, request
        if request["payment_status"] != "paid":
            return None, None, request

        if request["consultation_id"]:
            cursor.execute(
                """
                SELECT consultation_id, patient_id, doctor_id, notes, diagnosis
                FROM consultations
                WHERE consultation_id = ?
                LIMIT 1
                """,
                (request["consultation_id"],),
            )
        else:
            cursor.execute(
                """
                SELECT consultation_id, patient_id, doctor_id, notes, diagnosis
                FROM consultations
                WHERE patient_id = ?
                ORDER BY datetime(created_at) DESC, id DESC
                LIMIT 1
                """,
                (request["patient_id"],),
            )
        consultation = cursor.fetchone()

    if not consultation:
        return None, None, request

    patient = get_patient_by_identifier(consultation["patient_id"]) or {}
    patient_details = {
        **patient,
        "patient_id": patient.get("hospital_number") or consultation["patient_id"],
        "email": request["delivery_email"] or patient.get("email") or "",
        "history": consultation["notes"] or request["request_note"] or "Not recorded",
        "source": "web",
    }
    return dict(consultation), patient_details, request


def _mark_medical_report_request_fulfilled(request_id: str, letter_id: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE medical_report_requests
            SET status = 'fulfilled',
                fulfilled_letter_id = ?,
                updated_at = ?
            WHERE request_id = ?
            """,
            (letter_id, _now_iso(), request_id),
        )
        conn.commit()


def _email_direct_medical_report(patient_details: dict, document: dict) -> bool:
    email = (patient_details.get("email") or "").strip().lower()
    if not email:
        return False
    patient_name = patient_details.get("name") or "there"
    subject = "Your SynMed medical report is ready"
    body = (
        f"Hello {patient_name},\n\n"
        "Your requested SynMed medical report has been completed by your doctor. "
        "The PDF is attached to this email, and it is also available from your patient dashboard under Documents.\n\n"
        "Thank you,\nSynMed Telehealth"
    )
    return send_email_with_attachment(
        email,
        subject,
        body,
        document["filename"],
        document["file"].getvalue(),
        document.get("asset_type") or "application/pdf",
    )


def get_doctor_workspace(doctor_id: int) -> dict:
    doctor_id = _runtime_id(doctor_id)
    _restore_runtime_state()
    if not is_verified(doctor_id):
        return {
            "found": False,
            "message": "Doctor is not verified on SynMed.",
            "doctor": None,
            "queue": [],
            "active_consultation": None,
            "call": None,
        }

    return {
        "found": True,
        "message": "Doctor workspace loaded.",
        "doctor": _doctor_payload(doctor_id),
        "queue": _queue_payload(),
        "active_consultation": _active_consultation_payload(doctor_id),
        "medical_report_requests": list_doctor_medical_report_requests(doctor_id),
        "call": _call_payload_for_consultation(
            (_active_consultation_payload(doctor_id) or {}).get("consultation_id")
        ),
    }


def update_doctor_presence(doctor_id: int, action: str) -> dict:
    doctor_id = _runtime_id(doctor_id)
    _restore_runtime_state()
    _clear_stale_busy_state(doctor_id)
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
        registry.remove_doctor_from_runtime(doctor_id, channel="web")
        return get_doctor_workspace(doctor_id) | {"message": "Doctor is now offline."}

    if normalized != "online":
        return get_doctor_workspace(doctor_id) | {"message": "Unsupported presence action."}

    if registry.is_doctor_available(doctor_id, "web") or registry.is_doctor_busy(doctor_id, "web"):
        return get_doctor_workspace(doctor_id) | {"message": "Doctor presence already updated."}

    registry.set_doctor_available(doctor_id, channel="web")
    return get_doctor_workspace(doctor_id) | {"message": "Doctor is online and waiting for web patients."}


def connect_doctor_to_selected_patient(doctor_id: int, runtime_patient_id: int) -> dict:
    doctor_id = _runtime_id(doctor_id)
    runtime_patient_id = _runtime_id(runtime_patient_id)
    _restore_runtime_state()
    _clear_stale_busy_state(doctor_id)
    if not is_verified(doctor_id):
        return _doctor_connect_blocked_response(
            doctor_id,
            "Doctor is not verified on SynMed.",
            {"reason": "doctor_not_verified", "runtime_patient_id": runtime_patient_id},
        )

    existing_consultation = get_last_consultation(doctor_id)
    if (
        existing_consultation
        and is_in_chat(doctor_id)
        and existing_consultation.get("patient_id") == runtime_patient_id
    ):
        active_consultation = _active_consultation_payload_from_consultation(existing_consultation)
        return _doctor_connect_response(doctor_id, active_consultation, "Doctor connected to the selected patient.")

    if registry.is_doctor_busy(doctor_id, "web"):
        return _doctor_connect_blocked_response(
            doctor_id,
            "Finish the current consultation before selecting another patient.",
            {
                "reason": "doctor_busy",
                "runtime_patient_id": runtime_patient_id,
                "existing_consultation_id": (existing_consultation or {}).get("consultation_id"),
                "existing_patient_id": (existing_consultation or {}).get("patient_id"),
            },
        )

    if not registry.is_doctor_available(doctor_id, "web"):
        return _doctor_connect_blocked_response(
            doctor_id,
            "Go online before connecting to a queued patient.",
            {"reason": "doctor_not_available", "runtime_patient_id": runtime_patient_id},
        )

    details = registry.pending_patient_details.get(runtime_patient_id)
    if (
        not details
        or runtime_patient_id not in registry.waiting_patients
        or registry.normalize_channel(details.get("source")) != "web"
    ):
        return _doctor_connect_blocked_response(
            doctor_id,
            "That patient is no longer in the waiting queue.",
            {
                "reason": "patient_not_waiting",
                "runtime_patient_id": runtime_patient_id,
                "queue_ids": list(registry.waiting_patients),
                "has_details": bool(details),
                "source": (details or {}).get("source"),
                "reference": (details or {}).get("reference"),
            },
        )

    patient_details = {**details, "doctor_channel": "web"}
    registry.set_doctor_busy(doctor_id, channel="web")
    try:
        consultation_id = start_chat(runtime_patient_id, doctor_id, patient_details)
    except Exception as exc:
        registry.set_doctor_available(doctor_id, channel="web")
        log_exception(
            exc,
            source="doctor_connect",
            user_role="doctor",
            user_id=str(doctor_id),
        )
        return _doctor_connect_blocked_response(
            doctor_id,
            "Unable to connect to this patient right now. Please try again.",
            {
                "reason": "start_chat_exception",
                "runtime_patient_id": runtime_patient_id,
                "exception": f"{exc.__class__.__name__}: {exc}",
            },
        )

    registry.remove_patient_from_queue(runtime_patient_id)
    if patient_details.get("channel") == "whatsapp" and patient_details.get("whatsapp_id"):
        try:
            send_text_message_sync(
                patient_details["whatsapp_id"],
                "A SynMed doctor has joined your consultation. You can now continue chatting here on WhatsApp.",
            )
        except Exception:
            pass
    active_consultation = _active_consultation_payload_from_consultation(
        {
            "consultation_id": consultation_id,
            "doctor_id": doctor_id,
            "patient_id": runtime_patient_id,
            "patient_details": patient_details,
        }
    )
    return _doctor_connect_response(doctor_id, active_consultation, "Doctor connected to the selected patient.")


def get_doctor_transcript(doctor_id: int) -> dict:
    doctor_id = _runtime_id(doctor_id)
    _restore_runtime_state()
    consultation, _patient_details = _current_consultation_for_doctor(doctor_id)
    if not consultation:
        return {
            "found": False,
            "message": "No active consultation found for this doctor.",
            "consultation_id": None,
            "transcript": [],
            "call": None,
        }

    return {
        "found": True,
        "message": "Doctor transcript loaded.",
        "consultation_id": consultation["consultation_id"],
        "transcript": _get_transcript_by_consultation_id(consultation["consultation_id"]),
        "call": _call_payload_for_consultation(consultation["consultation_id"]),
    }


async def send_doctor_message(doctor_id: int, message_text: str) -> dict:
    doctor_id = _runtime_id(doctor_id)
    _restore_runtime_state()
    consultation, patient_details = _current_consultation_for_doctor(doctor_id)
    if not consultation:
        return {
            "sent": False,
            "message": "No active consultation found for this doctor.",
            "consultation_id": None,
            "transcript": [],
            "call": None,
        }
    patient_runtime_id = consultation["patient_id"]
    consultation_id = consultation["consultation_id"]

    message = log_consultation_message(
        consultation_id,
        sender_id=doctor_id,
        sender_role="doctor_web",
        message_text=message_text.strip(),
    )
    await realtime_hub.broadcast_message(consultation_id, message)

    if patient_details.get("channel") == "whatsapp" and patient_details.get("whatsapp_id"):
        try:
            await send_text_message(patient_details["whatsapp_id"], message_text.strip())
        except Exception:
            pass
    elif patient_details.get("source") != "web":
        try:
            await _send_telegram_message(patient_runtime_id, message_text.strip())
        except Exception:
            pass

    return {
        "sent": True,
        "message": "Doctor message saved and delivered to the patient channel.",
        "consultation_id": consultation_id,
        "transcript": None,
        "call": None,
    }


async def send_doctor_attachment(doctor_id: int, filename: str, content_type: str, data: str) -> dict:
    doctor_id = _runtime_id(doctor_id)
    _restore_runtime_state()
    consultation, _patient_details = _current_consultation_for_doctor(doctor_id)
    if not consultation:
        return {
            "sent": False,
            "message": "No active consultation found for this doctor.",
            "consultation_id": None,
            "transcript": [],
            "call": None,
        }

    consultation_id = consultation["consultation_id"]
    asset_path, asset_type = _save_chat_upload(filename, content_type, data, "doctor")
    log_consultation_message(
        consultation_id,
        sender_id=doctor_id,
        sender_role="doctor_web",
        message_text="Voice message" if asset_type.startswith("audio/") else (filename or "Attachment"),
        asset_path=asset_path,
        asset_type=asset_type,
    )

    return {
        "sent": True,
        "message": "Attachment sent.",
        "consultation_id": consultation_id,
        "transcript": _get_transcript_by_consultation_id(consultation_id),
        "call": _call_payload_for_consultation(consultation_id),
    }


def start_doctor_call(doctor_id: int, call_type: str, offer_sdp: dict) -> dict:
    doctor_id = _runtime_id(doctor_id)
    consultation, _patient_details = _current_consultation_for_doctor(doctor_id)
    if not consultation:
        return {"ok": False, "message": "No active consultation found for this doctor.", "consultation_id": None, "call": None}

    consultation_id = consultation["consultation_id"]
    def set_ringing(current: dict) -> dict:
        preserved_patient_candidates = current.get("patient_candidates") if current.get("status") == "idle" else []
        preserved_doctor_candidates = current.get("doctor_candidates") if current.get("status") == "idle" else []
        return {
            **current,
            "status": "ringing",
            "call_type": call_type,
            "initiated_by": "doctor",
            "offer_sdp": offer_sdp,
            "answer_sdp": None,
            "patient_candidates": preserved_patient_candidates or [],
            "doctor_candidates": preserved_doctor_candidates or [],
            "connected_at": None,
        }

    next_state = update_consultation_call_state(consultation_id, set_ringing)
    return {
        "ok": True,
        "message": f"{call_type.title()} call is ringing.",
        "consultation_id": consultation_id,
        "call": next_state,
    }


def accept_doctor_call(doctor_id: int, answer_sdp: dict) -> dict:
    doctor_id = _runtime_id(doctor_id)
    consultation, _patient_details = _current_consultation_for_doctor(doctor_id)
    if not consultation:
        return {"ok": False, "message": "No active consultation found for this doctor.", "consultation_id": None, "call": None}

    consultation_id = consultation["consultation_id"]
    def set_accepted(current: dict) -> dict:
        return {
            **current,
            "status": "active",
            "answer_sdp": answer_sdp,
        }

    next_state = update_consultation_call_state(consultation_id, set_accepted)
    return {
        "ok": True,
        "message": "Call accepted.",
        "consultation_id": consultation_id,
        "call": next_state,
    }


def reject_doctor_call(doctor_id: int) -> dict:
    doctor_id = _runtime_id(doctor_id)
    consultation, _patient_details = _current_consultation_for_doctor(doctor_id)
    if not consultation:
        return {"ok": False, "message": "No active consultation found for this doctor.", "consultation_id": None, "call": None}

    consultation_id = consultation["consultation_id"]
    def set_rejected(current: dict) -> dict:
        return {
            **current,
            "status": "rejected",
            "answer_sdp": None,
            "patient_candidates": [],
            "doctor_candidates": [],
        }

    next_state = update_consultation_call_state(consultation_id, set_rejected)
    return {
        "ok": True,
        "message": "Call rejected.",
        "consultation_id": consultation_id,
        "call": next_state,
    }


def add_doctor_call_candidate(doctor_id: int, candidate: dict) -> dict:
    doctor_id = _runtime_id(doctor_id)
    consultation, _patient_details = _current_consultation_for_doctor(doctor_id)
    if not consultation:
        return {"ok": False, "message": "No active consultation found for this doctor.", "consultation_id": None, "call": None}

    consultation_id = consultation["consultation_id"]
    def append_candidate(current: dict) -> dict:
        next_candidates = [*(current.get("doctor_candidates") or []), candidate]
        return {
            **current,
            "doctor_candidates": next_candidates,
        }

    next_state = update_consultation_call_state(consultation_id, append_candidate)
    return {
        "ok": True,
        "message": "Candidate received.",
        "consultation_id": consultation_id,
        "call": next_state,
    }


def end_doctor_call_session(doctor_id: int) -> dict:
    doctor_id = _runtime_id(doctor_id)
    consultation, _patient_details = _current_consultation_for_doctor(doctor_id)
    if not consultation:
        return {"ok": False, "message": "No active consultation found for this doctor.", "consultation_id": None, "call": None}

    consultation_id = consultation["consultation_id"]
    def set_ended(current: dict) -> dict:
        return {
            **current,
            "status": "ended",
        }

    next_state = update_consultation_call_state(consultation_id, set_ended)
    return {
        "ok": True,
        "message": "Call ended.",
        "consultation_id": consultation_id,
        "call": next_state,
    }


async def end_doctor_chat(doctor_id: int) -> dict:
    doctor_id = _runtime_id(doctor_id)
    _restore_runtime_state()
    consultation, patient_details = _current_consultation_for_doctor(doctor_id)
    if not consultation:
        return get_doctor_workspace(doctor_id) | {"message": "No active consultation to end."}

    patient_id = consultation["patient_id"]
    clear_consultation_call_state(consultation["consultation_id"])
    end_chat(doctor_id)
    registry.remove_doctor_from_runtime(doctor_id, channel="web")

    if patient_details.get("channel") == "whatsapp" and patient_details.get("whatsapp_id"):
        try:
            await send_text_message(patient_details["whatsapp_id"], "The consultation has ended. Thank you for using SynMed Telehealth.")
        except Exception:
            pass
    elif patient_details.get("source") != "web":
        try:
            await _send_telegram_message(patient_id, "The consultation has ended.")
        except Exception:
            pass

    registry.set_doctor_available(doctor_id, channel="web")
    return get_doctor_workspace(doctor_id) | {
        "message": "Consultation ended. Doctor is now online and waiting for the next manual connection.",
    }


def get_doctor_account(doctor_id: int) -> dict:
    doctor_id = _runtime_id(doctor_id)
    _restore_runtime_state()
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
    doctor_id = _runtime_id(doctor_id)
    if not is_verified(doctor_id):
        return {
            "found": False,
            "message": "Doctor is not verified on SynMed.",
            "doctor": None,
        }

    existing = doctor_profiles.get(doctor_id, {}) or {}
    license_expiry_date = payload.get("license_expiry_date", "").strip()
    license_updates = {}
    if payload.get("license_file_data"):
        file_id, file_type, file_name, file_size = _save_doctor_license_upload(
            payload.get("license_file_name") or "annual-licence",
            payload.get("license_file_type") or "application/octet-stream",
            payload.get("license_file_data") or "",
        )
        license_updates = {
            "license_file_id": file_id,
            "license_file_type": file_type,
            "license_file_name": file_name,
            "license_file_size": file_size,
        }
    if license_expiry_date != (existing.get("license_expiry_date") or ""):
        license_updates["license_reminder_sent_at"] = None

    create_or_update_profile(
        doctor_id,
        {
            **existing,
            **license_updates,
            "name": payload.get("name", "").strip(),
            "specialty": payload.get("specialty", "").strip(),
            "experience": payload.get("experience", "").strip(),
            "email": payload.get("email", "").strip().lower(),
            "license_id": payload.get("license_id", "").strip(),
            "license_expiry_date": license_expiry_date,
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


def send_due_license_expiry_reminders(now: datetime | None = None) -> int:
    current = now or datetime.now(UTC)
    today = current.date()
    window_end = today + timedelta(days=14)
    sent = 0

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT telegram_id, name, email, license_id, license_expiry_date, license_reminder_sent_at
            FROM doctor_profiles
            WHERE verified = 1
              AND COALESCE(email, '') != ''
              AND COALESCE(license_expiry_date, '') != ''
            """
        )
        rows = cursor.fetchall()

    for row in rows:
        try:
            expiry_date = datetime.strptime(row["license_expiry_date"], "%Y-%m-%d").date()
        except ValueError:
            continue
        if not (today <= expiry_date <= window_end):
            continue
        if row["license_reminder_sent_at"]:
            continue

        days_left = (expiry_date - today).days
        email = (row["email"] or "").strip().lower()
        subject = "Your SynMed annual licence is nearing expiry"
        body = (
            f"Hello Dr. {row['name'] or 'Doctor'},\n\n"
            f"Your annual licence ({row['license_id'] or 'no licence number recorded'}) expires on {expiry_date.isoformat()}."
            f" That is in {days_left} day{'s' if days_left != 1 else ''}.\n\n"
            "Please sign in to your SynMed doctor account and upload your renewed annual licence before it expires.\n\n"
            "Thank you,\nSynMed Telehealth"
        )
        try:
            if not send_plain_email(email, subject, body):
                continue
        except Exception:
            continue

        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE doctor_profiles
                SET license_reminder_sent_at = ?
                WHERE telegram_id = ?
                """,
                (_now_iso(), row["telegram_id"]),
            )
            conn.commit()
        sent += 1

    return sent


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
    if diagnosis.strip():
        set_consultation_diagnosis(consultation["consultation_id"], diagnosis.strip())

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
    whatsapp_delivered = await _send_whatsapp_document_notice(patient_details, "prescription", document)
    delivered_to_patient = delivered or whatsapp_delivered

    return {
        "created": True,
        "message": (
            "Prescription created and sent to the patient."
            if delivered_to_patient
            else "Prescription created successfully."
        ),
        "consultation_id": consultation["consultation_id"],
        "filename": document["filename"],
        "asset_url": document["asset_url"],
        "asset_type": document["asset_type"],
        "delivered_to_patient": delivered_to_patient,
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
    if diagnosis.strip():
        set_consultation_diagnosis(consultation["consultation_id"], diagnosis.strip())

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
    whatsapp_delivered = await _send_whatsapp_document_notice(patient_details, "investigation", document)
    delivered_to_patient = delivered or whatsapp_delivered

    return {
        "created": True,
        "message": (
            "Investigation request created and sent to the patient."
            if delivered_to_patient
            else "Investigation request created successfully."
        ),
        "consultation_id": consultation["consultation_id"],
        "filename": document["filename"],
        "asset_url": document["asset_url"],
        "asset_type": document["asset_type"],
        "delivered_to_patient": delivered_to_patient,
        "document_kind": "investigation",
        "preview_text": document["content"],
    }


async def create_doctor_medical_report(
    doctor_id: int,
    *,
    diagnosis: str,
    report_note: str,
    request_id: str | None = None,
) -> dict:
    cleaned_request_id = (request_id or "").strip()
    request = None
    if cleaned_request_id:
        consultation, patient_details, request = _medical_report_request_consultation(doctor_id, cleaned_request_id)
    else:
        consultation, patient_details = _current_consultation_for_doctor(doctor_id)
    if not consultation:
        message = "No active consultation found for this doctor."
        if cleaned_request_id and request is None:
            message = "Medical report request could not be found."
        elif cleaned_request_id and request and str(request["doctor_id"] or "") != str(doctor_id):
            message = "This medical report request is not assigned to this doctor."
        elif cleaned_request_id and request and request["payment_status"] != "paid":
            message = "Medical report payment must be verified before creating the report."
        elif cleaned_request_id:
            message = "No consultation record was found for this medical report request."
        return {
            "created": False,
            "message": message,
            "consultation_id": None,
            "filename": None,
            "asset_url": None,
            "asset_type": None,
            "delivered_to_patient": False,
            "document_kind": "medical_report",
            "preview_text": None,
        }

    document = create_medical_report_document(
        consultation_id=consultation["consultation_id"],
        doctor_id=doctor_id,
        patient_id=consultation["patient_id"],
        patient_details=patient_details,
        diagnosis=diagnosis.strip(),
        report_note=report_note.strip(),
    )
    if diagnosis.strip():
        set_consultation_diagnosis(consultation["consultation_id"], diagnosis.strip())
    email_delivered = False
    if cleaned_request_id:
        _mark_medical_report_request_fulfilled(cleaned_request_id, document["document_id"])
        try:
            email_delivered = _email_direct_medical_report(patient_details, document)
        except Exception:
            email_delivered = False

    delivered = False
    if patient_details.get("source") != "web":
        try:
            delivered = await _send_telegram_document(
                consultation["patient_id"],
                filename=document["filename"],
                content=document["file"].getvalue(),
                caption="Medical report for your SynMed consultation.",
            )
        except Exception:
            delivered = False
    whatsapp_delivered = await _send_whatsapp_document_notice(patient_details, "medical_report", document)
    delivered_to_patient = delivered or email_delivered or whatsapp_delivered

    return {
        "created": True,
        "message": (
            "Medical report created and sent to the patient."
            if delivered_to_patient
            else "Medical report created and emailed to the patient."
            if email_delivered
            else "Medical report created successfully. It is available in the patient's documents."
            if cleaned_request_id
            else "Medical report created successfully."
        ),
        "consultation_id": consultation["consultation_id"],
        "filename": document["filename"],
        "asset_url": document["asset_url"],
        "asset_type": document["asset_type"],
        "delivered_to_patient": delivered_to_patient,
        "document_kind": "medical_report",
        "preview_text": document["content"],
    }


def save_doctor_history_note(doctor_id: int, *, notes: str) -> dict:
    consultation, _patient_details = _current_consultation_for_doctor(doctor_id)
    if not consultation:
        return {
            "saved": False,
            "message": "No active consultation found for this doctor.",
            "consultation_id": None,
            "notes": "",
        }

    cleaned_notes = notes.strip()
    set_consultation_notes(consultation["consultation_id"], cleaned_notes)
    consultation["patient_details"] = {
        **(consultation.get("patient_details") or {}),
        "history": cleaned_notes or "No symptoms recorded",
    }

    return {
        "saved": True,
        "message": "Patient history saved.",
        "consultation_id": consultation["consultation_id"],
        "notes": cleaned_notes,
    }
