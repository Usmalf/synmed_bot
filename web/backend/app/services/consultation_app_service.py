import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx

from database import get_connection
from services.consultation_calls import (
    clear_consultation_call_state,
    get_consultation_call_state,
    save_consultation_call_state,
)
from services.emergency import detect_emergency
from services.consultation_records import log_consultation_message
from services import storage_service
from services.ratings_service import add_rating, add_review, has_rating, has_review
from services.paystack import get_payment_by_reference, is_payment_within_validity_window
from services.patient_records import get_patient_by_identifier
from synmed_utils.active_chats import (
    end_chat,
    get_last_consultation,
    is_in_chat,
    restore_runtime_state,
    start_chat,
)
from synmed_utils.doctor_profiles import doctor_profiles
from synmed_utils.doctor_ratings import get_average_rating, get_total_ratings
import synmed_utils.doctor_registry as registry

UTC = timezone.utc


def _restore_runtime_state():
    registry.restore_runtime_state()
    restore_runtime_state()


def _patient_payload(patient: dict) -> dict:
    return {
        "internal_id": patient["id"],
        "hospital_number": patient["hospital_number"],
        "name": patient["name"],
        "age": patient["age"],
        "gender": patient["gender"],
        "phone": patient["phone"],
        "email": patient.get("email") or "",
        "address": patient.get("address") or "",
        "allergy": patient.get("allergy") or "",
    }


def _doctor_payload(doctor_id: int) -> dict:
    profile = doctor_profiles.get(doctor_id, {})
    return {
        "doctor_id": doctor_id,
        "name": profile.get("name") or "Doctor",
        "specialty": profile.get("specialty") or "N/A",
        "experience": profile.get("experience") or "N/A",
        "average_rating": get_average_rating(doctor_id),
        "total_ratings": get_total_ratings(doctor_id),
    }


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


def _chat_asset_size(asset_path: str | None) -> int | None:
    return storage_service.file_size(asset_path)


def _save_chat_upload(filename: str, content_type: str, data: str, actor: str) -> tuple[str, str]:
    original_name = Path(filename or "attachment").name
    extension = Path(original_name).suffix[:16]
    stored_name = f"{actor}-{uuid4().hex}{extension}"
    asset_path, _decoded = storage_service.save_base64_upload("consultation_media/chat_uploads", stored_name, data)
    return asset_path, content_type or "application/octet-stream"


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


def _doctor_notice_text(patient_details: dict) -> str:
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
        "This patient is consulting via SynMed Web. Reply here in Telegram and the web patient will see your messages in the consultation room."
    )


async def submit_consultation_request(reference: str, symptoms: str) -> dict:
    _restore_runtime_state()
    payment = get_payment_by_reference(reference)
    if not payment:
        return {
            "submitted": False,
            "message": "Payment reference was not found.",
            "status": "missing_payment",
            "consultation_id": None,
            "doctor": None,
            "patient": None,
            "emergency": None,
            "call": None,
        }

    if payment["status"] != "verified":
        return {
            "submitted": False,
            "message": "Payment must be verified before consultation can begin.",
            "status": "payment_not_verified",
            "consultation_id": None,
            "doctor": None,
            "patient": None,
            "emergency": None,
            "call": None,
        }

    if not is_payment_within_validity_window(payment):
        return {
            "submitted": False,
            "message": "Consultation access has expired. Complete payment or request a new admin access grant.",
            "status": "access_expired",
            "consultation_id": None,
            "doctor": None,
            "patient": None,
            "emergency": None,
            "call": None,
        }

    patient = get_patient_by_identifier(payment["patient_id"] or "")
    if not patient:
        return {
            "submitted": False,
            "message": "Patient record linked to this payment could not be found.",
            "status": "missing_patient",
            "consultation_id": None,
            "doctor": None,
            "patient": None,
            "emergency": None,
            "call": None,
        }

    patient_runtime_id = patient["id"]
    consultation = get_last_consultation(patient_runtime_id)
    if (
        consultation
        and is_in_chat(patient_runtime_id)
        and (consultation.get("patient_details") or {}).get("reference") == reference
    ):
        doctor_id = consultation["doctor_id"]
        return {
            "submitted": True,
            "message": "Consultation is active.",
            "status": "connected",
            "consultation_id": consultation["consultation_id"],
            "doctor": _doctor_payload(doctor_id),
            "patient": _patient_payload(patient),
            "emergency": {
                "is_emergency": bool(consultation["patient_details"].get("emergency_flag")),
                "matches": consultation["patient_details"].get("emergency_matches", ""),
            },
            "call": _call_payload_for_consultation(consultation["consultation_id"]),
        }

    if patient_runtime_id in registry.waiting_patients:
        details = registry.pending_patient_details.get(patient_runtime_id, {})
        if details.get("reference") == reference:
            return {
                "submitted": True,
                "message": "Consultation request is queued and waiting for an available doctor.",
                "status": "queued",
                "consultation_id": None,
                "doctor": None,
                "patient": _patient_payload(patient),
                "emergency": {
                    "is_emergency": bool(details.get("emergency_flag")),
                    "matches": details.get("emergency_matches", ""),
                },
                "call": None,
            }

    emergency = detect_emergency(symptoms)
    patient_details = {
        "reference": reference,
        "hospital_number": patient["hospital_number"],
        "name": patient["name"],
        "age": str(patient["age"]),
        "gender": patient["gender"],
        "phone": patient["phone"],
        "address": patient.get("address") or "N/A",
        "allergy": patient.get("allergy") or "None recorded",
        "medical_conditions": patient.get("medical_conditions") or "None recorded",
        "history": symptoms,
        "telegram_id": patient.get("telegram_id"),
        "source": "web",
        "emergency_flag": emergency["is_emergency"],
        "emergency_matches": ", ".join(emergency["matches"]) if emergency["matches"] else "",
    }

    registry.remove_patient_from_queue(patient_runtime_id)
    registry.queue_patient(
        patient_runtime_id,
        {
            **patient_details,
            "reference": reference,
            "submitted_at": datetime.now(UTC).isoformat(),
        },
    )
    return {
        "submitted": True,
        "message": (
            "Your consultation request has been queued. A doctor will join shortly."
            if not emergency["is_emergency"]
            else "Your case has been queued urgently, but please seek immediate in-person emergency care if symptoms are severe."
        ),
        "status": "queued",
        "consultation_id": None,
        "doctor": None,
        "patient": _patient_payload(patient),
        "emergency": emergency,
        "call": None,
    }


def get_consultation_status(reference: str) -> dict:
    _restore_runtime_state()
    payment = get_payment_by_reference(reference)
    if not payment:
        return {
            "submitted": False,
            "message": "Payment reference was not found.",
            "status": "missing_payment",
            "consultation_id": None,
            "doctor": None,
            "patient": None,
            "emergency": None,
            "call": None,
        }

    patient = get_patient_by_identifier(payment["patient_id"] or "")
    if not patient:
        return {
            "submitted": False,
            "message": "Patient linked to this payment could not be found.",
            "status": "missing_patient",
            "consultation_id": None,
            "doctor": None,
            "patient": None,
            "emergency": None,
            "call": None,
        }

    patient_runtime_id = patient["id"]
    consultation = get_last_consultation(patient_runtime_id)
    if (
        consultation
        and is_in_chat(patient_runtime_id)
        and (consultation.get("patient_details") or {}).get("reference") == reference
    ):
        doctor_id = consultation["doctor_id"]
        return {
            "submitted": True,
            "message": "Consultation is active.",
            "status": "connected",
            "consultation_id": consultation["consultation_id"],
            "doctor": _doctor_payload(doctor_id),
            "patient": _patient_payload(patient),
            "emergency": {
                "is_emergency": bool(consultation["patient_details"].get("emergency_flag")),
                "matches": consultation["patient_details"].get("emergency_matches", ""),
            },
            "call": _call_payload_for_consultation(consultation["consultation_id"]),
        }

    if patient_runtime_id in registry.waiting_patients:
        details = registry.pending_patient_details.get(patient_runtime_id, {})
        if details.get("reference") == reference:
            return {
                "submitted": True,
                "message": "Consultation request is queued and waiting for an available doctor.",
                "status": "queued",
                "consultation_id": None,
                "doctor": None,
                "patient": _patient_payload(patient),
                "emergency": {
                    "is_emergency": bool(details.get("emergency_flag")),
                    "matches": details.get("emergency_matches", ""),
                },
                "call": None,
            }

    latest_consultation = _latest_consultation_record(patient, reference)
    if (
        latest_consultation
        and latest_consultation.get("status") == "closed"
        and (latest_consultation.get("patient_details") or {}).get("reference") == reference
        and not has_rating(latest_consultation["consultation_id"])
    ):
        doctor_id = latest_consultation.get("doctor_id")
        return {
            "submitted": True,
            "message": "Consultation ended. Please rate and review your doctor before leaving.",
            "status": "ended",
            "consultation_id": latest_consultation["consultation_id"],
            "doctor": _doctor_payload(doctor_id) if doctor_id else None,
            "patient": _patient_payload(patient),
            "emergency": None,
            "call": None,
        }

    return {
        "submitted": False,
        "message": "No active or queued consultation was found for this payment yet.",
        "status": "not_started",
        "consultation_id": None,
        "doctor": None,
        "patient": _patient_payload(patient),
        "emergency": None,
        "call": None,
    }


def _latest_consultation_record(patient: dict, reference: str | None = None):
    with get_connection() as conn:
        cursor = conn.cursor()
        if reference:
            cursor.execute(
                """
                SELECT consultation_id, doctor_id, status, notes, created_at, closed_at,
                       payment_reference
                FROM consultations
                WHERE patient_id = ?
                  AND payment_reference = ?
                ORDER BY COALESCE(closed_at, created_at) DESC
                LIMIT 1
                """,
                (patient["hospital_number"], reference),
            )
        else:
            cursor.execute(
                """
                SELECT consultation_id, doctor_id, status, notes, created_at, closed_at,
                       payment_reference
                FROM consultations
                WHERE patient_id = ?
                ORDER BY COALESCE(closed_at, created_at) DESC
                LIMIT 1
                """,
                (patient["hospital_number"],),
            )
        row = cursor.fetchone()

    if not row:
        return None

    return {
        "consultation_id": row["consultation_id"],
        "doctor_id": int(row["doctor_id"]),
        "status": row["status"],
        "notes": row["notes"],
        "created_at": row["created_at"],
        "closed_at": row["closed_at"],
        "patient_details": {"reference": row["payment_reference"]} if row["payment_reference"] else {},
    }


def _active_consultation_from_reference(reference: str):
    _restore_runtime_state()
    payment = get_payment_by_reference(reference)
    if not payment:
        return None, None

    patient = get_patient_by_identifier(payment["patient_id"] or "")
    if not patient:
        return payment, None

    consultation = get_last_consultation(patient["id"])
    if consultation and (consultation.get("patient_details") or {}).get("reference") != reference:
        consultation = None
    return payment, {
        "patient": patient,
        "consultation": consultation,
    }


def _consultation_for_feedback_from_reference(reference: str):
    payment = get_payment_by_reference(reference)
    if not payment:
        return None, None

    patient = get_patient_by_identifier(payment["patient_id"] or "")
    if not patient:
        return payment, None

    consultation = get_last_consultation(patient["id"])
    if consultation and (consultation.get("patient_details") or {}).get("reference") == reference:
        return payment, {
            "patient": patient,
            "consultation": consultation,
        }

    consultation = _latest_consultation_record(patient, reference)
    return payment, {
        "patient": patient,
        "consultation": consultation,
    }


def get_consultation_transcript(reference: str) -> dict:
    payment, payload = _active_consultation_from_reference(reference)
    if not payment:
        return {
            "found": False,
            "message": "Payment reference was not found.",
            "consultation_id": None,
            "status": None,
            "transcript": [],
            "call": None,
        }

    if not payload or not payload["consultation"]:
        return {
            "found": False,
            "message": "No active consultation transcript was found for this payment yet.",
            "consultation_id": None,
            "status": "not_started",
            "transcript": [],
            "call": None,
        }

    consultation_id = payload["consultation"]["consultation_id"]
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

    transcript = [
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

    return {
        "found": True,
        "message": "Consultation transcript loaded.",
        "consultation_id": consultation_id,
        "status": (
            "connected"
            if is_in_chat(payload["patient"]["id"])
            else payload["consultation"].get("status", "inactive")
        ),
        "transcript": transcript,
        "call": _call_payload_for_consultation(consultation_id),
    }


def get_consultation_documents(reference: str) -> dict:
    payment, payload = _active_consultation_from_reference(reference)
    if not payment:
        return {
            "found": False,
            "message": "Payment reference was not found.",
            "consultation_id": None,
            "documents": [],
            "call": None,
        }

    if not payload or not payload["consultation"]:
        return {
            "found": False,
            "message": "No active consultation documents were found for this payment yet.",
            "consultation_id": None,
            "documents": [],
            "call": None,
        }

    consultation_id = payload["consultation"]["consultation_id"]
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT rx_id AS document_id, consultation_id, created_at, asset_path, asset_type
            FROM prescriptions
            WHERE consultation_id = ? AND asset_path IS NOT NULL
            ORDER BY created_at DESC
            """,
            (consultation_id,),
        )
        prescription_rows = cursor.fetchall()
        cursor.execute(
            """
            SELECT request_id AS document_id, consultation_id, created_at, asset_path, asset_type
            FROM investigation_requests
            WHERE consultation_id = ? AND asset_path IS NOT NULL
            ORDER BY created_at DESC
            """,
            (consultation_id,),
        )
        investigation_rows = cursor.fetchall()
        cursor.execute(
            """
            SELECT letter_id AS document_id, consultation_id, created_at, asset_path, asset_type
            FROM clinical_letters
            WHERE consultation_id = ? AND letter_type = 'medical_report' AND asset_path IS NOT NULL
            ORDER BY created_at DESC
            """,
            (consultation_id,),
        )
        medical_report_rows = cursor.fetchall()

    documents = []
    for row in prescription_rows:
        filename = (row["asset_path"] or "").replace("generated_documents/", "", 1)
        documents.append(
            {
                "document_id": row["document_id"],
                "kind": "prescription",
                "title": "Prescription",
                "created_at": row["created_at"],
                "asset_url": f"/generated-documents/{filename}",
                "asset_type": row["asset_type"] or "image/png",
            }
        )
    for row in investigation_rows:
        filename = (row["asset_path"] or "").replace("generated_documents/", "", 1)
        documents.append(
            {
                "document_id": row["document_id"],
                "kind": "investigation",
                "title": "Investigation Request",
                "created_at": row["created_at"],
                "asset_url": f"/generated-documents/{filename}",
                "asset_type": row["asset_type"] or "image/png",
            }
        )
    for row in medical_report_rows:
        filename = (row["asset_path"] or "").replace("generated_documents/", "", 1)
        documents.append(
            {
                "document_id": row["document_id"],
                "kind": "medical_report",
                "title": "Medical Report",
                "created_at": row["created_at"],
                "asset_url": f"/generated-documents/{filename}",
                "asset_type": row["asset_type"] or "application/pdf",
            }
        )

    documents.sort(key=lambda item: item["created_at"], reverse=True)
    return {
        "found": True,
        "message": "Consultation documents loaded.",
        "consultation_id": consultation_id,
        "documents": documents,
        "call": _call_payload_for_consultation(consultation_id),
    }


async def send_patient_message(reference: str, message_text: str) -> dict:
    payment, payload = _active_consultation_from_reference(reference)
    if not payment:
        return {
            "sent": False,
            "message": "Payment reference was not found.",
            "consultation_id": None,
            "transcript": None,
            "call": None,
        }

    if not payload or not payload["consultation"]:
        return {
            "sent": False,
            "message": "There is no active consultation available for messaging yet.",
            "consultation_id": None,
            "transcript": None,
            "call": None,
        }

    patient = payload["patient"]
    consultation = payload["consultation"]
    consultation_id = consultation["consultation_id"]
    log_consultation_message(
        consultation_id,
        sender_id=patient["id"],
        sender_role="patient_web",
        message_text=message_text.strip(),
    )
    return {
        "sent": True,
        "message": "Message saved to the consultation transcript.",
        "consultation_id": consultation_id,
        "transcript": None,
        "call": None,
    }


async def send_patient_attachment(reference: str, filename: str, content_type: str, data: str) -> dict:
    payment, payload = _active_consultation_from_reference(reference)
    if not payment:
        return {
            "sent": False,
            "message": "Payment reference was not found.",
            "consultation_id": None,
            "transcript": None,
            "call": None,
        }

    if not payload or not payload["consultation"]:
        return {
            "sent": False,
            "message": "There is no active consultation available for attachments yet.",
            "consultation_id": None,
            "transcript": None,
            "call": None,
        }

    patient = payload["patient"]
    consultation = payload["consultation"]
    consultation_id = consultation["consultation_id"]
    asset_path, asset_type = _save_chat_upload(filename, content_type, data, "patient")
    log_consultation_message(
        consultation_id,
        sender_id=patient["id"],
        sender_role="patient_web",
        message_text="Voice message" if asset_type.startswith("audio/") else (filename or "Attachment"),
        asset_path=asset_path,
        asset_type=asset_type,
    )
    transcript = get_consultation_transcript(reference)
    return {
        "sent": True,
        "message": "Attachment sent.",
        "consultation_id": consultation_id,
        "transcript": transcript["transcript"],
        "call": _call_payload_for_consultation(consultation_id),
    }


def get_consultation_live_snapshot(reference: str) -> dict:
    status = get_consultation_status(reference)
    consultation_id = status.get("consultation_id")
    return {
        "status": status,
        "transcript": get_consultation_transcript(reference),
        "call": _call_payload_for_consultation(consultation_id),
    }


def consultation_live_snapshot_json(reference: str) -> str:
    return json.dumps(get_consultation_live_snapshot(reference))


def _patient_consultation_from_reference(reference: str):
    payment, payload = _active_consultation_from_reference(reference)
    if not payment or not payload or not payload["consultation"]:
        return payment, payload, None
    return payment, payload, payload["consultation"]["consultation_id"]


def start_patient_call(reference: str, call_type: str, offer_sdp: dict) -> dict:
    payment, payload, consultation_id = _patient_consultation_from_reference(reference)
    if not payment:
        return {"ok": False, "message": "Payment reference was not found.", "consultation_id": None, "call": None}
    if not consultation_id:
        return {"ok": False, "message": "No active consultation is available for calling yet.", "consultation_id": None, "call": None}

    current = get_consultation_call_state(consultation_id)
    next_state = save_consultation_call_state(
        consultation_id,
        {
            **current,
            "status": "ringing",
            "call_type": call_type,
            "initiated_by": "patient",
            "offer_sdp": offer_sdp,
            "answer_sdp": None,
            "patient_candidates": [],
            "doctor_candidates": [],
            "connected_at": None,
        },
    )
    return {
        "ok": True,
        "message": f"{call_type.title()} call is ringing.",
        "consultation_id": consultation_id,
        "call": next_state,
    }


def accept_patient_call(reference: str, answer_sdp: dict) -> dict:
    payment, payload, consultation_id = _patient_consultation_from_reference(reference)
    if not payment:
        return {"ok": False, "message": "Payment reference was not found.", "consultation_id": None, "call": None}
    if not consultation_id:
        return {"ok": False, "message": "No active consultation is available for calling yet.", "consultation_id": None, "call": None}

    current = get_consultation_call_state(consultation_id)
    next_state = save_consultation_call_state(
        consultation_id,
        {
            **current,
            "status": "active",
            "answer_sdp": answer_sdp,
        },
    )
    return {
        "ok": True,
        "message": "Call accepted.",
        "consultation_id": consultation_id,
        "call": next_state,
    }


def reject_patient_call(reference: str) -> dict:
    payment, payload, consultation_id = _patient_consultation_from_reference(reference)
    if not payment:
        return {"ok": False, "message": "Payment reference was not found.", "consultation_id": None, "call": None}
    if not consultation_id:
        return {"ok": False, "message": "No active consultation is available for calling yet.", "consultation_id": None, "call": None}

    current = get_consultation_call_state(consultation_id)
    next_state = save_consultation_call_state(
        consultation_id,
        {
            **current,
            "status": "rejected",
            "answer_sdp": None,
            "patient_candidates": [],
            "doctor_candidates": [],
        },
    )
    return {
        "ok": True,
        "message": "Call rejected.",
        "consultation_id": consultation_id,
        "call": next_state,
    }


def add_patient_call_candidate(reference: str, candidate: dict) -> dict:
    payment, payload, consultation_id = _patient_consultation_from_reference(reference)
    if not payment:
        return {"ok": False, "message": "Payment reference was not found.", "consultation_id": None, "call": None}
    if not consultation_id:
        return {"ok": False, "message": "No active consultation is available for calling yet.", "consultation_id": None, "call": None}

    current = get_consultation_call_state(consultation_id)
    next_candidates = [*(current.get("patient_candidates") or []), candidate]
    next_state = save_consultation_call_state(
        consultation_id,
        {
            **current,
            "patient_candidates": next_candidates,
        },
    )
    return {
        "ok": True,
        "message": "Candidate received.",
        "consultation_id": consultation_id,
        "call": next_state,
    }


def end_patient_call_session(reference: str) -> dict:
    payment, payload, consultation_id = _patient_consultation_from_reference(reference)
    if not payment:
        return {"ok": False, "message": "Payment reference was not found.", "consultation_id": None, "call": None}
    if not consultation_id:
        return {"ok": False, "message": "No active consultation is available for calling yet.", "consultation_id": None, "call": None}

    next_state = save_consultation_call_state(
        consultation_id,
        {
            **get_consultation_call_state(consultation_id),
            "status": "ended",
        },
    )
    return {
        "ok": True,
        "message": "Call ended.",
        "consultation_id": consultation_id,
        "call": next_state,
    }


async def end_patient_consultation(reference: str) -> dict:
    payment, payload = _active_consultation_from_reference(reference)
    if not payment:
        return {
            "ended": False,
            "message": "Payment reference was not found.",
            "consultation_id": None,
            "doctor": None,
        }

    patient = payload["patient"] if payload else get_patient_by_identifier(payment["patient_id"] or "")
    if patient and patient["id"] in registry.waiting_patients:
        details = registry.pending_patient_details.get(patient["id"], {})
        if details.get("reference") == reference:
            registry.remove_patient_from_queue(patient["id"])
            return {
                "ended": True,
                "message": "Consultation request cancelled. You have been removed from the waiting queue.",
                "consultation_id": None,
                "doctor": None,
            }

    if not payload or not payload["consultation"]:
        return {
            "ended": False,
            "message": "No consultation was found to end.",
            "consultation_id": None,
            "doctor": None,
        }

    consultation = payload["consultation"]
    doctor_id = int(consultation["doctor_id"])

    if is_in_chat(patient["id"]):
        end_chat(patient["id"])
        clear_consultation_call_state(consultation["consultation_id"])
        registry.set_doctor_available(doctor_id, channel="web")

    return {
        "ended": True,
        "message": "Consultation ended. Please rate and review your doctor before leaving.",
        "consultation_id": consultation["consultation_id"],
        "doctor": _doctor_payload(doctor_id),
    }


def submit_consultation_feedback(reference: str, rating: int, review: str = "") -> dict:
    payment, payload = _consultation_for_feedback_from_reference(reference)
    if not payment:
        return {
            "saved": False,
            "message": "Payment reference was not found.",
            "consultation_id": None,
        }

    if not payload or not payload["consultation"]:
        return {
            "saved": False,
            "message": "No consultation record was found for feedback.",
            "consultation_id": None,
        }

    patient = payload["patient"]
    consultation = payload["consultation"]
    consultation_id = consultation["consultation_id"]
    doctor_id = int(consultation["doctor_id"])

    if not has_rating(consultation_id):
        add_rating(consultation_id, doctor_id, patient["id"], rating)

    normalized_review = review.strip()
    if normalized_review and not has_review(consultation_id):
        add_review(consultation_id, doctor_id, patient["id"], normalized_review)

    return {
        "saved": True,
        "message": "Thank you. Your rating and review have been submitted.",
        "consultation_id": consultation_id,
    }
