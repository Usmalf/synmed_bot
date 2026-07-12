import os
import re
import json
from datetime import datetime, timezone

import httpx

from database import get_connection
from services.emergency import detect_emergency
from services.consultation_records import log_consultation_message
from services.patient_records import get_patient_by_identifier, register_patient
from services.paystack import (
    PaystackError,
    build_backend_callback_url,
    build_frontend_callback_url,
    create_payment_reference,
    get_latest_valid_payment_for_patient,
    get_payment_by_reference,
    initialize_transaction,
    is_payment_within_validity_window,
    mark_payment_status,
    mark_payment_verified,
    verify_transaction,
)
from synmed_utils.active_chats import end_chat, get_last_consultation, is_in_chat, touch_chat_activity
import synmed_utils.doctor_registry as registry
from .auth_service import send_patient_web_access_setup
from .chat_realtime_service import realtime_hub
from .settings_service import get_payment_settings
from .support_ai_service import create_support_ticket


WHATSAPP_API_VERSION = os.getenv("WHATSAPP_API_VERSION", "v20.0").strip() or "v20.0"
UTC = timezone.utc
COMMAND_WORDS = {
    "hi",
    "hello",
    "hey",
    "menu",
    "start",
    "1",
    "2",
    "3",
    "4",
    "5",
    "6",
    "7",
    "register",
    "signin",
    "sign in",
    "login",
    "consult",
    "consultation",
    "start consultation",
    "payment",
    "pay",
    "payment support",
    "medical report",
    "report",
    "agent",
    "support",
    "customer care",
    "human",
    "web",
    "website",
    "continue on web",
    "guide",
    "help",
    "cancel",
    "end",
    "end chat",
}


class WhatsAppConfigurationError(RuntimeError):
    pass


def _access_token() -> str:
    return os.getenv("WHATSAPP_ACCESS_TOKEN", "").strip()


def _phone_number_id() -> str:
    return os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip()


def is_configured() -> bool:
    return bool(_access_token() and _phone_number_id())


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def build_basic_menu(name: str = "") -> str:
    greeting = f"Hello {name.strip()}." if name.strip() else "Hello."
    return (
        f"{greeting}\n\n"
        "Welcome to SynMed Telehealth. How can we help you today?\n\n"
        "Reply with:\n"
        "1 - Register or sign in\n"
        "2 - Start consultation\n"
        "3 - Payment support\n"
        "4 - Medical report\n"
        "5 - Talk to customer care\n"
        "6 - Continue on web\n"
        "7 - WhatsApp consultation guide"
    )


def _frontend_base_url() -> str:
    return os.getenv("FRONTEND_BASE_URL", "").strip().rstrip("/") or "https://synmedhealth.com"


def _digits(value: str) -> str:
    return re.sub(r"\D+", "", value or "")


def _patient_phone_from_whatsapp_id(whatsapp_id: str) -> str:
    digits = _digits(whatsapp_id)
    if digits.startswith("234") and len(digits) == 13:
        return "0" + digits[3:]
    return digits


def _session(whatsapp_id: str) -> dict | None:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT whatsapp_id, name, state, payload_json, updated_at, created_at
            FROM whatsapp_sessions
            WHERE whatsapp_id = ?
            """,
            (whatsapp_id,),
        )
        row = cursor.fetchone()
    if not row:
        return None
    try:
        payload = json.loads(row["payload_json"] or "{}")
    except json.JSONDecodeError:
        payload = {}
    return {
        "whatsapp_id": row["whatsapp_id"],
        "name": row["name"] or "",
        "state": row["state"],
        "payload": payload,
        "updated_at": row["updated_at"],
        "created_at": row["created_at"],
    }


def _session_by_payment_reference(reference: str) -> dict | None:
    cleaned_reference = (reference or "").strip()
    if not cleaned_reference:
        return None
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT whatsapp_id, name, state, payload_json, updated_at, created_at
            FROM whatsapp_sessions
            WHERE payload_json LIKE ?
            ORDER BY updated_at DESC
            LIMIT 20
            """,
            (f"%{cleaned_reference}%",),
        )
        rows = cursor.fetchall()
    for row in rows:
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except json.JSONDecodeError:
            payload = {}
        if cleaned_reference in {
            str(payload.get("reference") or "").strip(),
            str(payload.get("payment_reference") or "").strip(),
        }:
            return {
                "whatsapp_id": row["whatsapp_id"],
                "name": row["name"] or "",
                "state": row["state"],
                "payload": payload,
                "updated_at": row["updated_at"],
                "created_at": row["created_at"],
            }
    return None


def _save_session(whatsapp_id: str, state: str, payload: dict | None = None, name: str = "") -> None:
    now = _now_iso()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO whatsapp_sessions (whatsapp_id, name, state, payload_json, updated_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(whatsapp_id) DO UPDATE SET
                name = excluded.name,
                state = excluded.state,
                payload_json = excluded.payload_json,
                updated_at = excluded.updated_at
            """,
            (whatsapp_id, name or "", state, json.dumps(payload or {}), now, now),
        )
        conn.commit()


def _clear_session(whatsapp_id: str) -> None:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM whatsapp_sessions WHERE whatsapp_id = ?", (whatsapp_id,))
        conn.commit()


def _cancel_whatsapp_flow(whatsapp_id: str) -> str:
    patient = _lookup_patient_from_phone(whatsapp_id)
    if patient:
        registry.remove_patient_from_queue(patient["id"])
        if is_in_chat(patient["id"]):
            end_chat(patient["id"])
    _clear_session(whatsapp_id)
    return "Current WhatsApp consultation process cancelled.\n\n" + build_basic_menu()


def _lookup_patient_from_phone(whatsapp_id: str) -> dict | None:
    digits = _digits(whatsapp_id)
    if not digits:
        return None
    candidates = {digits}
    if digits.startswith("234") and len(digits) > 3:
        candidates.add("0" + digits[3:])
    for candidate in candidates:
        patient = get_patient_by_identifier(candidate)
        if patient:
            return patient

    suffix = digits[-10:] if len(digits) >= 10 else digits
    if len(suffix) < 7:
        return None
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, patient_id, telegram_id, name, age, gender, phone, email,
                   email_verified_at, address, allergy, medical_conditions, password_hash, created_at, updated_at
            FROM patients
            WHERE REPLACE(REPLACE(REPLACE(REPLACE(phone, '+', ''), ' ', ''), '-', ''), '(', '') LIKE ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (f"%{suffix}",),
        )
        row = cursor.fetchone()
    if not row:
        return None
    return {
        "id": row["id"],
        "hospital_number": row["patient_id"],
        "telegram_id": row["telegram_id"],
        "name": row["name"],
        "age": row["age"],
        "gender": row["gender"],
        "phone": row["phone"],
        "email": row["email"],
        "email_verified_at": row["email_verified_at"],
        "address": row["address"],
        "allergy": row["allergy"],
        "medical_conditions": row["medical_conditions"],
        "password_hash": row["password_hash"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _lookup_patient_from_message(message_text: str, whatsapp_id: str) -> dict | None:
    tokens = re.findall(r"SM\d+|[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}|\+?\d[\d\s()-]{6,}", message_text or "", flags=re.I)
    for token in tokens:
        patient = get_patient_by_identifier(token.strip())
        if patient:
            return patient
    return _lookup_patient_from_phone(whatsapp_id)


def _whatsapp_recipient_from_patient(patient: dict | None) -> str:
    if not patient:
        return ""
    digits = _digits(patient.get("phone") or "")
    if not digits:
        return ""
    if digits.startswith("0") and len(digits) == 11:
        return "234" + digits[1:]
    return digits


def _patient_record_reply(patient: dict) -> str:
    web_url = _frontend_base_url()
    password_state = "ready for web sign-in" if patient.get("password_hash") else "not yet set up for web sign-in"
    return (
        "I found your SynMed patient record.\n\n"
        f"Name: {patient.get('name') or 'Patient'}\n"
        f"Hospital Number: {patient.get('hospital_number')}\n"
        f"Email: {patient.get('email') or 'Not recorded'}\n"
        f"Web access: {password_state}\n\n"
        f"To continue on the website, open: {web_url}/signin"
    )


def _create_whatsapp_support_ticket(patient: dict | None, message_text: str, whatsapp_id: str, name: str = "") -> str:
    patient_name = patient.get("name") if patient else (name or "WhatsApp user")
    ai_reply = (
        "All our customer-care agents are currently busy, but your WhatsApp message has been sent to the support queue. "
        "A SynMed customer-care agent will review it and respond."
    )
    ticket_message = (
        f"WhatsApp sender: {whatsapp_id}\n"
        f"Name: {patient_name}\n\n"
        f"{message_text.strip() or 'Customer requested WhatsApp support.'}"
    )
    ticket = create_support_ticket(
        patient,
        "whatsapp",
        ticket_message,
        ai_reply,
        contact_email=patient.get("email", "") if patient else "",
    )
    return f"{ai_reply}\n\nSupport ticket {ticket['ticket_id']} has been opened."


def _web_setup_reply(patient: dict | None) -> str:
    if not patient:
        return (
            "I could not find your SynMed patient record from this WhatsApp number. "
            "Please send your hospital number or email, for example: setup SM0001."
        )
    if not (patient.get("email") or "").strip():
        return (
            "Your patient record does not have an email yet. Please reply with your email address, "
            "or contact customer care so we can help you activate web access."
        )
    if (patient.get("password_hash") or "").strip():
        return f"Your SynMed web access is already active. Sign in here: {_frontend_base_url()}/signin"

    setup = send_patient_web_access_setup(
        hospital_number=patient["hospital_number"],
        email=patient["email"],
    )
    if setup.get("delivered"):
        return (
            "I sent a secure SynMed web-access setup link to your email. "
            "Use it to create your web password, then sign in with the same patient record."
        )
    return (
        "I generated your web-access setup link, but email delivery is not available right now. "
        "Please try again later or contact customer care."
    )


def _continue_on_web_reply(patient: dict | None = None) -> str:
    patient_line = ""
    if patient:
        patient_line = f"\n\nI found your SynMed record as {patient.get('name') or 'Patient'} ({patient.get('hospital_number')})."
    return (
        "Yes. You can continue securely on the SynMed website.\n\n"
        f"Open: {_frontend_base_url()}/signin"
        f"{patient_line}\n\n"
        "Use the same email or hospital number connected to your SynMed record."
    )


def _whatsapp_consultation_guide_reply() -> str:
    return (
        "How to use SynMed on WhatsApp:\n\n"
        "1. Reply 1 to register if you are new.\n"
        "2. Reply 2 to start a consultation.\n"
        "3. If payment is needed, complete the Paystack link and reply paid followed by your reference.\n"
        "4. Send your symptoms when asked. You will be placed in the doctor queue.\n"
        "5. Once a doctor connects, continue chatting here on WhatsApp.\n\n"
        "You can reply menu anytime to see the options again."
    )


def _consultation_payment_config(patient_type: str) -> dict:
    settings = get_payment_settings()
    if patient_type == "new":
        return {
            "amount": settings["new_patient_fee"],
            "currency": settings["currency"],
            "label": settings["new_patient_label"],
        }
    return {
        "amount": settings["returning_patient_fee"],
        "currency": settings["currency"],
        "label": settings["returning_patient_label"],
    }


async def _initialize_whatsapp_payment(
    *,
    patient_type: str,
    email: str,
    whatsapp_id: str,
    patient: dict | None = None,
    registration: dict | None = None,
) -> dict:
    config = _consultation_payment_config(patient_type)
    reference = create_payment_reference(prefix="wa")
    metadata = {
        "patient_type": patient_type,
        "patient_id": (patient or {}).get("hospital_number") or "",
        "source": "whatsapp",
        "telegram_id": 0,
        "whatsapp_id": whatsapp_id,
    }
    if registration:
        metadata["registration_payload_json"] = json.dumps(registration)
    callback_url = build_backend_callback_url(
        "/payments/web-return",
        {"callback_path": "/signin"},
    ) or build_frontend_callback_url(
        "/signin",
        {"payment_reference": reference, "reference": reference, "status": "success"},
    )
    result = await initialize_transaction(
        email=email,
        amount_ngn=config["amount"],
        currency=config["currency"],
        reference=reference,
        label=config["label"],
        metadata=metadata,
        callback_url=callback_url,
    )
    return {
        "reference": reference,
        "authorization_url": result["authorization_url"],
        "amount": config["amount"],
        "currency": config["currency"],
        "label": config["label"],
    }


def _payment_prompt(payment: dict) -> str:
    return (
        f"{payment['label']}\n"
        f"Amount: {payment['currency']} {payment['amount']:,}\n\n"
        f"Pay here: {payment['authorization_url']}\n\n"
        f"After payment, reply: paid {payment['reference']}"
    )


def _start_registration_reply(whatsapp_id: str, name: str = "") -> str:
    existing = _lookup_patient_from_phone(whatsapp_id)
    if existing:
        return (
            f"I found your SynMed record as {existing.get('name')} ({existing.get('hospital_number')}).\n\n"
            "Reply 2 to start a consultation, or reply setup if you want web access."
        )
    _save_session(whatsapp_id, "register_name", {"phone": _patient_phone_from_whatsapp_id(whatsapp_id), "whatsapp_id": whatsapp_id}, name)
    return "Let us create your SynMed patient record.\n\nPlease type your full name."


async def _continue_registration(session: dict, text: str) -> str:
    whatsapp_id = session["whatsapp_id"]
    state = session["state"]
    payload = dict(session.get("payload") or {})
    value = text.strip()

    if state == "register_name":
        if len(value) < 3:
            return "Please enter your full name."
        payload["name"] = value
        _save_session(whatsapp_id, "register_age", payload, session.get("name", ""))
        return "How old are you? Reply with your age in years."

    if state == "register_age":
        if not value.isdigit() or not (0 < int(value) < 130):
            return "Please enter a valid age in years."
        payload["age"] = int(value)
        _save_session(whatsapp_id, "register_gender", payload, session.get("name", ""))
        return "What is your gender? Reply Male, Female, or your preferred description."

    if state == "register_gender":
        if len(value) < 2:
            return "Please enter your gender."
        payload["gender"] = value
        _save_session(whatsapp_id, "register_email", payload, session.get("name", ""))
        return "Please enter your email address. We will use it for receipts, documents, and web access."

    if state == "register_email":
        email = value.lower()
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            return "Please enter a valid email address."
        if get_patient_by_identifier(email):
            _clear_session(whatsapp_id)
            return (
                "A SynMed patient account already exists with this email.\n\n"
                "Reply 2 to start a consultation, or reply setup with your hospital number to activate web access."
            )
        payload["email"] = email
        _save_session(whatsapp_id, "register_address", payload, session.get("name", ""))
        return "Please enter your address or city."

    if state == "register_address":
        if len(value) < 2:
            return "Please enter your address or city."
        payload["address"] = value
        _save_session(whatsapp_id, "register_allergy", payload, session.get("name", ""))
        return "Do you have any allergies? Reply none if you do not."

    if state == "register_allergy":
        payload["allergy"] = "" if value.lower() in {"none", "nil", "no"} else value
        payload.setdefault("medical_conditions", "")
        try:
            payment = await _initialize_whatsapp_payment(
                patient_type="new",
                email=payload["email"],
                whatsapp_id=whatsapp_id,
                registration=payload,
            )
        except PaystackError as exc:
            return f"Unable to start payment right now: {exc}"
        except Exception:
            return "Unable to start payment right now. Please try again shortly."
        payload["payment_reference"] = payment["reference"]
        _save_session(whatsapp_id, "awaiting_payment", payload, session.get("name", ""))
        return (
            "Your registration details have been saved pending payment.\n\n"
            f"{_payment_prompt(payment)}"
        )

    return build_basic_menu(session.get("name", ""))


async def _verify_whatsapp_payment(reference: str, whatsapp_id: str, name: str = "") -> str:
    payment = get_payment_by_reference(reference)
    if not payment:
        return "I could not find that payment reference. Please check it and try again."
    if payment["status"] == "verified" and is_payment_within_validity_window(payment):
        patient = get_patient_by_identifier(payment["patient_id"] or "")
        if patient:
            _save_session(whatsapp_id, "awaiting_symptoms", {"patient_id": patient["hospital_number"], "reference": reference}, name)
            return "Payment is already verified.\n\nPlease describe your symptoms so I can place you in the doctor queue."

    try:
        verification = await verify_transaction(reference)
    except PaystackError as exc:
        return f"Unable to verify payment right now: {exc}"
    except Exception:
        return "Unable to verify payment right now. Please try again shortly."

    paystack_status = (verification.get("status") or "").lower()
    amount_ngn = int(verification.get("amount", 0)) // 100
    currency = verification.get("currency")
    if paystack_status != "success":
        mark_payment_status(reference, status="pending_verification", paystack_status=paystack_status or "pending")
        return "Payment is not confirmed yet. If you have just paid, please wait a moment and reply with the payment reference again."
    if amount_ngn != payment["amount"] or currency != payment["currency"]:
        mark_payment_status(reference, status="amount_mismatch", paystack_status=paystack_status)
        return "Payment amount could not be matched to this SynMed transaction. Please contact customer care."

    patient = get_patient_by_identifier(payment["patient_id"] or "")
    if payment["patient_type"] == "new" and not patient:
        try:
            registration = json.loads(payment["registration_payload_json"] or "{}")
        except json.JSONDecodeError:
            registration = {}
        required = ["name", "age", "gender", "phone", "email", "address"]
        if any(not str(registration.get(field, "")).strip() for field in required):
            return "Registration details for this payment are incomplete. Please contact customer care."
        patient = register_patient(
            telegram_id=None,
            name=registration["name"],
            age=str(registration["age"]),
            gender=registration["gender"],
            phone=registration["phone"],
            email=registration["email"],
            address=registration["address"],
            allergy=registration.get("allergy", ""),
            medical_conditions=registration.get("medical_conditions", ""),
            email_verified_at=None,
        )
        try:
            send_patient_web_access_setup(hospital_number=patient["hospital_number"], email=patient["email"])
        except Exception:
            pass

    if not patient:
        return "Payment was verified, but I could not find the patient record attached to it. Please contact customer care."

    mark_payment_verified(reference, paystack_status=paystack_status, patient_id=patient["hospital_number"])
    _save_session(whatsapp_id, "awaiting_symptoms", {"patient_id": patient["hospital_number"], "reference": reference}, name)
    return (
        f"Payment verified for {patient['name']} ({patient['hospital_number']}).\n\n"
        "Please describe your symptoms so I can place you in the doctor queue."
    )


async def notify_whatsapp_payment_verified(reference: str, patient: dict | None = None) -> dict:
    payment = get_payment_by_reference(reference)
    if not payment or payment["status"] != "verified":
        return {"notified": False, "reason": "payment_not_verified"}

    session = _session_by_payment_reference(reference)
    whatsapp_id = (session or {}).get("whatsapp_id") or ""
    if not whatsapp_id:
        return {"notified": False, "reason": "whatsapp_session_not_found"}

    patient = patient or get_patient_by_identifier(payment["patient_id"] or "")
    if not patient:
        return {"notified": False, "reason": "patient_not_found"}

    _save_session(
        whatsapp_id,
        "awaiting_symptoms",
        {"patient_id": patient["hospital_number"], "reference": reference},
        (session or {}).get("name", ""),
    )
    if not is_configured():
        return {"notified": False, "reason": "whatsapp_not_configured", "session_updated": True}

    await send_text_message(
        whatsapp_id,
        (
            f"Payment verified for {patient['name']} ({patient['hospital_number']}).\n\n"
            "Please describe your symptoms so I can place you in the doctor queue."
        ),
    )
    return {"notified": True, "reason": "sent", "session_updated": True}


async def _start_consultation_reply(whatsapp_id: str, name: str = "") -> str:
    patient = _lookup_patient_from_phone(whatsapp_id)
    if not patient:
        return _start_registration_reply(whatsapp_id, name)
    payment = get_latest_valid_payment_for_patient(patient["hospital_number"])
    if payment:
        _save_session(whatsapp_id, "awaiting_symptoms", {"patient_id": patient["hospital_number"], "reference": payment["reference"]}, name)
        return (
            f"I found an active consultation payment for {patient['name']} ({patient['hospital_number']}).\n\n"
            "Please describe your symptoms so I can place you in the doctor queue."
        )
    try:
        initialized = await _initialize_whatsapp_payment(
            patient_type="returning",
            email=patient.get("email") or f"{_digits(whatsapp_id)}@synmed.whatsapp",
            whatsapp_id=whatsapp_id,
            patient=patient,
        )
    except PaystackError as exc:
        return f"Unable to start payment right now: {exc}"
    except Exception:
        return "Unable to start payment right now. Please try again shortly."
    _save_session(
        whatsapp_id,
        "awaiting_payment",
        {"patient_id": patient["hospital_number"], "reference": initialized["reference"]},
        name,
    )
    return (
        f"I found your SynMed record as {patient['name']} ({patient['hospital_number']}).\n\n"
        f"{_payment_prompt(initialized)}"
    )


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
        "medical_conditions": patient.get("medical_conditions") or "",
    }


async def _queue_whatsapp_consultation(whatsapp_id: str, symptoms: str, session: dict | None = None, name: str = "") -> str:
    patient_id = ((session or {}).get("payload") or {}).get("patient_id")
    reference = ((session or {}).get("payload") or {}).get("reference")
    patient = get_patient_by_identifier(patient_id or "") or _lookup_patient_from_phone(whatsapp_id)
    if not patient:
        _clear_session(whatsapp_id)
        return "Patient record missing. Reply 1 to register or 5 to contact customer care."

    payment = get_payment_by_reference(reference or "") or get_latest_valid_payment_for_patient(patient["hospital_number"])
    if not payment or payment["status"] != "verified" or not is_payment_within_validity_window(payment):
        _save_session(whatsapp_id, "idle", {"patient_id": patient["hospital_number"]}, name)
        return "A verified consultation payment is required before queueing. Reply 2 to start payment."

    patient_runtime_id = patient["id"]
    consultation = get_last_consultation(patient_runtime_id)
    if consultation and is_in_chat(patient_runtime_id):
        return await _relay_patient_chat_message(whatsapp_id, symptoms)

    emergency = detect_emergency(symptoms)
    patient_details = {
        "reference": payment["reference"],
        "hospital_number": patient["hospital_number"],
        "name": patient["name"],
        "age": str(patient["age"]),
        "gender": patient["gender"],
        "phone": patient["phone"],
        "email": patient.get("email") or "",
        "address": patient.get("address") or "N/A",
        "allergy": patient.get("allergy") or "None recorded",
        "medical_conditions": patient.get("medical_conditions") or "None recorded",
        "history": symptoms,
        "telegram_id": patient.get("telegram_id"),
        "source": "web",
        "channel": "whatsapp",
        "whatsapp_id": whatsapp_id,
        "emergency_flag": emergency["is_emergency"],
        "emergency_matches": ", ".join(emergency["matches"]) if emergency["matches"] else "",
        "submitted_at": _now_iso(),
    }
    registry.remove_patient_from_queue(patient_runtime_id)
    registry.queue_patient(patient_runtime_id, patient_details)
    _save_session(whatsapp_id, "queued", {"patient_id": patient["hospital_number"], "reference": payment["reference"]}, name)
    return (
        "Your symptoms have been submitted and you are now in the doctor queue.\n\n"
        "A verified SynMed doctor will join shortly. Please keep this WhatsApp chat open; your consultation messages will appear here."
    )


def _active_consultation_for_whatsapp(whatsapp_id: str) -> tuple[dict | None, dict | None]:
    patient = _lookup_patient_from_phone(whatsapp_id)
    if not patient:
        return None, None
    consultation = get_last_consultation(patient["id"])
    if consultation and is_in_chat(patient["id"]):
        return patient, consultation
    return patient, None


async def _relay_patient_chat_message(whatsapp_id: str, message_text: str) -> str:
    patient, consultation = _active_consultation_for_whatsapp(whatsapp_id)
    if not patient or not consultation:
        return "No active consultation is connected yet. Reply 2 to start or continue a consultation."
    consultation_id = consultation["consultation_id"]
    message = log_consultation_message(
        consultation_id,
        sender_id=patient["id"],
        sender_role="patient_whatsapp",
        message_text=message_text.strip(),
    )
    touch_chat_activity(patient["id"])
    await realtime_hub.broadcast_message(consultation_id, message)
    return ""


async def send_patient_document_notice(patient: dict | None, document_kind: str) -> bool:
    recipient = _whatsapp_recipient_from_patient(patient)
    if not recipient or not is_configured():
        return False
    label = {
        "prescription": "prescription",
        "investigation": "investigation request",
        "medical_report": "medical report",
    }.get(document_kind, "clinical document")
    message = (
        f"Your SynMed {label} is ready.\n\n"
        "For privacy, please sign in to your SynMed dashboard to view or download it securely:\n"
        f"{_frontend_base_url()}/patient/documents"
    )
    await send_text_message(recipient, message)
    return True


def build_keyword_reply(message_text: str, name: str = "", sender: str = "") -> str:
    normalized = (message_text or "").strip().lower()
    if normalized in {"hi", "hello", "hey", "menu", "start"}:
        return build_basic_menu(name)
    if normalized.startswith("setup") or normalized in {"web access", "activate web", "setup link"}:
        return _web_setup_reply(_lookup_patient_from_message(message_text, sender))
    if normalized in {"6", "web", "website", "continue on web", "open web", "synmed website"}:
        return _continue_on_web_reply(_lookup_patient_from_phone(sender))
    if normalized in {"7", "guide", "how", "how to", "whatsapp guide", "consultation guide", "help"}:
        return _whatsapp_consultation_guide_reply()
    if normalized.startswith("record") or normalized.startswith("patient") or re.search(r"\bSM\d+\b", message_text or "", flags=re.I):
        patient = _lookup_patient_from_message(message_text, sender)
        if patient:
            return _patient_record_reply(patient)
        return (
            "I could not find that patient record. Please send your hospital number, phone number, or email, "
            "or reply 5 to talk to customer care."
        )
    if normalized in {"1", "register", "signin", "sign in", "login"}:
        return (
            "To use SynMed on the web, please sign in or register here:\n"
            f"{_frontend_base_url()}/signin\n\n"
            "You can also reply 2 to start a consultation."
        )
    if normalized in {"2", "consult", "consultation", "start consultation"}:
        patient = _lookup_patient_from_phone(sender)
        patient_line = f" I found your record as {patient['name']} ({patient['hospital_number']})." if patient else ""
        return (
            f"To start your consultation, please continue securely from your SynMed patient dashboard.{patient_line}\n\n"
            f"{_frontend_base_url()}/signin\n\n"
            "After signing in, tap Start Consultation, complete payment if requested, and submit your symptoms. "
            "A verified doctor will join your consultation as soon as one is available."
        )
    if normalized in {"3", "payment", "pay", "payment support"}:
        return (
            "For payment support, please send your payment reference or the email/phone number used for payment. "
            "A SynMed support agent will review it."
        )
    if normalized in {"4", "medical report", "report"}:
        return (
            "For a medical report, please sign in to SynMed and open Medical Reports from your dashboard. "
            "A verified doctor will review eligible requests."
        )
    if normalized in {"5", "agent", "support", "customer care", "human"} or "agent" in normalized or "customer care" in normalized:
        return _create_whatsapp_support_ticket(_lookup_patient_from_phone(sender), message_text, sender, name)
    return (
        "Thank you for contacting SynMed Telehealth. I can help with registration, consultation, payment support, "
        "medical reports, and customer care.\n\n"
        "Reply menu to see the options."
    )


async def build_whatsapp_reply(message_text: str, name: str = "", sender: str = "") -> str:
    normalized = (message_text or "").strip().lower()
    session = _session(sender)

    if normalized == "cancel":
        return _cancel_whatsapp_flow(sender)

    patient, active_consultation = _active_consultation_for_whatsapp(sender)
    if active_consultation and normalized in {"end", "end chat"}:
        end_chat(patient["id"])
        _clear_session(sender)
        return "Your consultation has been ended. Thank you for using SynMed Telehealth."
    if active_consultation and normalized not in COMMAND_WORDS and not normalized.startswith("paid"):
        return await _relay_patient_chat_message(sender, message_text)

    if normalized in {"hi", "hello", "hey", "menu", "start"}:
        return build_basic_menu(name)
    if session and session["state"].startswith("register_"):
        return await _continue_registration(session, message_text)
    if session and session["state"] == "awaiting_symptoms" and normalized not in COMMAND_WORDS and not normalized.startswith("paid"):
        return await _queue_whatsapp_consultation(sender, message_text, session, name)
    if session and session["state"] == "queued" and normalized not in COMMAND_WORDS:
        return (
            "You are still in the doctor queue. A SynMed doctor will join as soon as one is available.\n\n"
            "If you want to cancel, reply cancel."
        )

    paid_match = re.search(r"\bpaid\s+([A-Za-z0-9_-]+)", message_text or "", flags=re.I)
    if paid_match:
        return await _verify_whatsapp_payment(paid_match.group(1), sender, name)
    reference_match = re.search(r"\bwa-[A-Za-z0-9]+\b", message_text or "", flags=re.I)
    if normalized.startswith("paid") and reference_match:
        return await _verify_whatsapp_payment(reference_match.group(0), sender, name)

    if normalized in {"1", "register"}:
        return _start_registration_reply(sender, name)
    if normalized in {"2", "consult", "consultation", "start consultation"}:
        return await _start_consultation_reply(sender, name)

    return build_keyword_reply(message_text, name, sender)


async def send_text_message(to: str, message: str) -> dict:
    token = _access_token()
    phone_number_id = _phone_number_id()
    if not token or not phone_number_id:
        raise WhatsAppConfigurationError("WhatsApp access token or phone number ID is not configured.")

    url = f"https://graph.facebook.com/{WHATSAPP_API_VERSION}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"preview_url": True, "body": message},
    }
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
    response.raise_for_status()
    return response.json()


def send_text_message_sync(to: str, message: str) -> dict:
    token = _access_token()
    phone_number_id = _phone_number_id()
    if not token or not phone_number_id:
        raise WhatsAppConfigurationError("WhatsApp access token or phone number ID is not configured.")

    url = f"https://graph.facebook.com/{WHATSAPP_API_VERSION}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"preview_url": True, "body": message},
    }
    with httpx.Client(timeout=20) as client:
        response = client.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
    response.raise_for_status()
    return response.json()
