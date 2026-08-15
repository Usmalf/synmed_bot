import os
import re
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import httpx

from database import get_connection
from services import storage_service
from services.emergency import detect_emergency
from services.consultation_records import log_consultation_message
from services.consent import CONSENT_POLICY_TEXT, CONSENT_SUMMARY, has_patient_consented, record_patient_consent
from services.patient_records import get_patient_by_identifier, register_patient
from services.queue_notifications import dispatch_admins_patient_queued
from services.ratings_service import add_rating, add_review, has_rating, has_review
from services.paystack import (
    PaystackError,
    build_backend_callback_url,
    build_frontend_callback_url,
    create_payment_record,
    create_payment_reference,
    get_latest_valid_payment_for_patient,
    get_payment_by_reference,
    initialize_transaction,
    is_payment_within_validity_window,
    mark_payment_status,
    mark_payment_verified,
    verify_transaction,
)
from services.coupons import (
    CouponError,
    has_active_coupon_for_purpose,
    record_coupon_redemption,
    validate_coupon,
)
from synmed_utils.active_chats import end_chat, get_last_consultation, is_in_chat, touch_chat_activity
import synmed_utils.doctor_registry as registry
from .auth_service import send_patient_web_access_setup
from .chat_realtime_service import realtime_hub
from .settings_service import get_payment_settings
from .support_ai_service import create_support_ticket


WHATSAPP_API_VERSION = os.getenv("WHATSAPP_API_VERSION", "v20.0").strip() or "v20.0"
UTC = timezone.utc
WHATSAPP_FEEDBACK_EXPIRY_HOURS = 24
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
    "restart",
    "start over",
    "startover",
    "end",
    "end chat",
    "no thanks",
    "skip",
}
RESTART_WORDS = {"hi", "hello", "hey", "menu", "start", "restart", "start over", "startover"}


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


def _parse_iso_datetime(value: str | None):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except (TypeError, ValueError):
        return None


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


def build_more_options_menu() -> str:
    return (
        "More SynMed options\n\n"
        "Tap an option below, or reply with:\n"
        "3 - Payment support\n"
        "4 - Medical report\n"
        "5 - Talk to customer care\n"
        "6 - Continue on web\n"
        "7 - WhatsApp consultation guide"
    )


def _is_basic_menu_reply(message: str) -> bool:
    return "Welcome to SynMed Telehealth. How can we help you today?" in (message or "")


def _is_more_options_reply(message: str) -> bool:
    return "More SynMed options" in (message or "")


def _whatsapp_consent_subject(whatsapp_id: str) -> int:
    digits = _digits(whatsapp_id)
    try:
        return int(digits)
    except (TypeError, ValueError):
        return 0


def _has_whatsapp_consent(whatsapp_id: str) -> bool:
    subject = _whatsapp_consent_subject(whatsapp_id)
    return bool(subject and has_patient_consented(subject))


def _record_whatsapp_consent(whatsapp_id: str) -> None:
    subject = _whatsapp_consent_subject(whatsapp_id)
    if subject:
        record_patient_consent(subject, channel="whatsapp")


def _whatsapp_consent_prompt() -> str:
    return (
        f"{CONSENT_SUMMARY}\n\n"
        "Please choose one option to continue on WhatsApp."
    )


def _is_consent_prompt(message: str) -> bool:
    return CONSENT_SUMMARY in (message or "")


def _is_post_registration_consultation_prompt(message: str) -> bool:
    return "Would you like to proceed with consultation now?" in (message or "")


def _next_action_from_message(normalized: str) -> str:
    if normalized in {"1", "register"}:
        return "register"
    if normalized in {"2", "consult", "consultation", "start consultation"}:
        return "consult"
    return "menu"


def _save_consent_session(whatsapp_id: str, name: str, next_action: str = "menu") -> None:
    _save_session(whatsapp_id, "awaiting_consent", {"next_action": next_action}, name)


def _frontend_base_url() -> str:
    return os.getenv("FRONTEND_BASE_URL", "").strip().rstrip("/") or "https://synmedhealth.com"


def _backend_public_url() -> str:
    return (
        os.getenv("BACKEND_PUBLIC_URL", "").strip().rstrip("/")
        or os.getenv("API_BASE_URL", "").strip().rstrip("/")
        or os.getenv("VITE_API_BASE_URL", "").strip().rstrip("/")
        or _frontend_base_url()
    )


def _absolute_public_url(path_or_url: str | None) -> str:
    value = (path_or_url or "").strip()
    if not value:
        return ""
    if value.lower().startswith(("http://", "https://")):
        return value
    return f"{_backend_public_url()}/{value.lstrip('/')}"


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


def _wrong_step_reply(expected: str) -> str:
    return (
        "That response does not match this step.\n\n"
        f"{expected}\n\n"
        "You can reply start to begin again, or cancel to stop this process."
    )


def _is_yes_reply(value: str) -> bool:
    return value.strip().lower() in {"yes", "y", "yeah", "yea", "sure", "ok", "okay", "proceed", "continue"}


def _is_no_reply(value: str) -> bool:
    return value.strip().lower() in {"no", "n", "not now", "later", "skip", "no thanks", "no thank you"}


def _rating_prompt() -> str:
    return (
        "Your consultation has ended. Thank you for using SynMed Telehealth.\n\n"
        "Please rate your doctor from 1 to 5.\n"
        "You can also reply no, skip, or no thanks to skip."
    )


def _normalize_feedback_reply(message_text: str) -> str:
    normalized = (message_text or "").strip().lower()
    if normalized.startswith("rating:"):
        value = normalized.split(":", 1)[1].strip()
        if value in {"skip", "no", "no_thanks", "no thanks", "no thank you"}:
            return "no thanks"
        return value
    return normalized


def _normalize_interactive_reply(message_text: str) -> str:
    normalized = (message_text or "").strip().lower()
    if normalized.startswith("consent:"):
        return normalized
    return normalized


async def _handle_whatsapp_consent(session: dict, message_text: str, name: str = "") -> str:
    whatsapp_id = session["whatsapp_id"]
    normalized = _normalize_interactive_reply(message_text)
    if normalized == "consent:view":
        return f"{CONSENT_POLICY_TEXT}\n\n{_whatsapp_consent_prompt()}"
    if normalized in {"consent:disagree", "disagree", "no"}:
        _clear_session(whatsapp_id)
        return (
            "You have declined the SynMed Telehealth consent policy.\n"
            "We cannot continue registration or consultation on WhatsApp without consent."
        )
    if normalized not in {"consent:agree", "agree", "i agree", "yes"}:
        return _wrong_step_reply("Please tap I Agree to continue, View Policy to read the policy, or I Disagree to stop.")

    _record_whatsapp_consent(whatsapp_id)
    next_action = (session.get("payload") or {}).get("next_action") or "menu"
    _clear_session(whatsapp_id)
    if next_action == "register":
        return _start_registration_reply(whatsapp_id, name or session.get("name", ""))
    if next_action == "consult":
        return await _start_consultation_reply(whatsapp_id, name or session.get("name", ""))
    return "Thank you. Your consent has been recorded.\n\n" + build_basic_menu(name or session.get("name", ""))


async def send_whatsapp_rating_prompt(whatsapp_id: str, consultation: dict, patient_details: dict | None = None) -> bool:
    if not whatsapp_id:
        return False
    patient_id = consultation.get("patient_id")
    doctor_id = consultation.get("doctor_id")
    consultation_id = consultation.get("consultation_id")
    if not consultation_id or not patient_id or not doctor_id:
        return False
    _save_session(
        whatsapp_id,
        "awaiting_rating",
        {
            "consultation_id": consultation_id,
            "doctor_id": doctor_id,
            "patient_runtime_id": patient_id,
            "patient_id": (patient_details or {}).get("hospital_number", ""),
            "expires_at": (datetime.now(UTC) + timedelta(hours=WHATSAPP_FEEDBACK_EXPIRY_HOURS)).isoformat(),
        },
        (patient_details or {}).get("name", ""),
    )
    if not is_configured():
        return False
    try:
        await send_rating_options_message(whatsapp_id)
    except httpx.HTTPError:
        await send_text_message(whatsapp_id, _rating_prompt())
    return True


def _skip_whatsapp_feedback(whatsapp_id: str) -> str:
    _clear_session(whatsapp_id)
    return "No problem. Thank you for using SynMed Telehealth."


def _rating_payload_is_valid(payload: dict) -> bool:
    return bool(payload.get("consultation_id") and payload.get("doctor_id") and payload.get("patient_runtime_id"))


async def _handle_whatsapp_feedback(session: dict, message_text: str) -> str:
    whatsapp_id = session["whatsapp_id"]
    normalized = _normalize_feedback_reply(message_text)
    payload = dict(session.get("payload") or {})
    expires_at = _parse_iso_datetime(payload.get("expires_at"))
    if expires_at and datetime.now(UTC) >= expires_at:
        _clear_session(whatsapp_id)
        return (
            "The previous consultation feedback request has expired.\n\n"
            "Reply menu to see options, or reply 2 to start a new consultation."
        )
    if normalized in {"no", "no thanks", "no thank you", "skip"}:
        return _skip_whatsapp_feedback(whatsapp_id)
    if not _rating_payload_is_valid(payload):
        _clear_session(whatsapp_id)
        return "I could not find the consultation to rate. Thank you for using SynMed Telehealth."

    consultation_id = payload["consultation_id"]
    doctor_id = int(payload["doctor_id"])
    patient_id = int(payload["patient_runtime_id"])

    if session["state"] == "awaiting_rating":
        if not normalized.isdigit() or int(normalized) < 1 or int(normalized) > 5:
            return _wrong_step_reply("Please reply with a number from 1 to 5, or reply no, skip, or no thanks to skip.")
        rating = int(normalized)
        if not has_rating(consultation_id):
            add_rating(consultation_id, doctor_id, patient_id, rating)
        payload["rating"] = rating
        _save_session(whatsapp_id, "awaiting_review", payload, session.get("name", ""))
        return (
            f"Thank you. You rated your doctor {rating}/5.\n\n"
            "Would you like to leave a short review? Type your review, or reply no, skip, or no thanks."
        )

    if session["state"] == "awaiting_review":
        review = (message_text or "").strip()
        if len(review) < 2:
            return _wrong_step_reply("Please type a short review, or reply no, skip, or no thanks to skip.")
        if not has_review(consultation_id):
            add_review(consultation_id, doctor_id, patient_id, review)
        _clear_session(whatsapp_id)
        return "Thank you. Your review has been submitted."

    return build_basic_menu(session.get("name", ""))


def _queued_session_patient_id(session: dict) -> int | None:
    payload = session.get("payload") or {}
    patient_identifier = payload.get("patient_id") or payload.get("hospital_number")
    patient = get_patient_by_identifier(patient_identifier) if patient_identifier else _lookup_patient_from_phone(session["whatsapp_id"])
    if not patient:
        return None
    try:
        return int(patient["id"])
    except (TypeError, ValueError):
        return None


def _is_whatsapp_session_still_queued(session: dict) -> bool:
    patient_runtime_id = _queued_session_patient_id(session)
    if patient_runtime_id is None:
        return False
    return patient_runtime_id in registry.waiting_patients


def _clear_stale_queue_session(whatsapp_id: str) -> str:
    _clear_session(whatsapp_id)
    return (
        "That previous consultation has ended.\n\n"
        "Reply 2 to start a new consultation, or reply menu to see all options."
    )


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
        if patient and _patient_matches_whatsapp_sender(patient, whatsapp_id):
            return patient
    return _lookup_patient_from_phone(whatsapp_id)


def _patient_matches_whatsapp_sender(patient: dict | None, whatsapp_id: str) -> bool:
    if not patient:
        return False
    sender_digits = _digits(whatsapp_id)
    patient_digits = _digits(patient.get("phone") or "")
    if not sender_digits or not patient_digits:
        return False
    sender_candidates = {sender_digits}
    if sender_digits.startswith("234") and len(sender_digits) > 3:
        sender_candidates.add("0" + sender_digits[3:])
    if sender_digits.startswith("0") and len(sender_digits) == 11:
        sender_candidates.add("234" + sender_digits[1:])
    patient_candidates = {patient_digits}
    if patient_digits.startswith("234") and len(patient_digits) > 3:
        patient_candidates.add("0" + patient_digits[3:])
    if patient_digits.startswith("0") and len(patient_digits) == 11:
        patient_candidates.add("234" + patient_digits[1:])
    return bool(sender_candidates & patient_candidates)


def _privacy_guard_reply() -> str:
    return (
        "For privacy, I cannot show that patient record from this WhatsApp number.\n\n"
        "Please use the WhatsApp number on the patient account, sign in on the web, or contact customer care for verification."
    )


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


def _has_used_whatsapp_first_consultation_free(patient_id: str) -> bool:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT 1
            FROM payments
            WHERE UPPER(COALESCE(patient_id, '')) = UPPER(?)
              AND paystack_status = 'first_consultation_free'
            LIMIT 1
            """,
            (patient_id,),
        )
        return cursor.fetchone() is not None


def _has_whatsapp_consultation_record(patient_id: str) -> bool:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT 1
            FROM consultations
            WHERE UPPER(COALESCE(patient_id, '')) = UPPER(?)
            LIMIT 1
            """,
            (patient_id,),
        )
        return cursor.fetchone() is not None


def _grant_whatsapp_first_consultation_free(patient: dict) -> dict | None:
    patient_id = patient["hospital_number"]
    if _has_used_whatsapp_first_consultation_free(patient_id) or _has_whatsapp_consultation_record(patient_id):
        return None
    settings = get_payment_settings()
    reference = create_payment_reference(prefix="free")
    create_payment_record(
        reference=reference,
        telegram_id=int(patient.get("telegram_id") or 0),
        patient_id=patient_id,
        email=patient.get("email") or f"{patient_id.lower()}@synmed.patient",
        amount=0,
        currency=settings["currency"],
        patient_type="returning",
        label="SynMed First Consultation",
        original_amount=settings["returning_patient_fee"],
        discount_amount=settings["returning_patient_fee"],
    )
    mark_payment_verified(reference, paystack_status="first_consultation_free", patient_id=patient_id)
    expires_at = datetime.now(UTC) + timedelta(hours=24)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE payments
            SET access_expires_at = ?, grant_reason = ?
            WHERE reference = ?
            """,
            (expires_at.isoformat(), "First consultation free", reference),
        )
        conn.commit()
    return get_payment_by_reference(reference)


def _coupon_prompt(purpose: str) -> str:
    label = "registration" if purpose == "registration" else "consultation"
    return (
        f"Do you have a SynMed coupon code for this {label}?\n\n"
        "Reply with the coupon code, or reply skip to continue without one."
    )


def _is_coupon_skip(text: str) -> bool:
    return (text or "").strip().lower() in {"skip", "no", "none", "nil", "no thanks", "continue"}


async def _initialize_whatsapp_payment(
    *,
    patient_type: str,
    email: str,
    whatsapp_id: str,
    patient: dict | None = None,
    registration: dict | None = None,
    coupon_code: str = "",
) -> dict:
    config = _consultation_payment_config(patient_type)
    amount = config["amount"]
    purpose = "registration" if patient_type == "new" else "consultation"
    patient_id = (patient or {}).get("hospital_number") or ""
    phone = (patient or {}).get("phone") or (registration or {}).get("phone") or _patient_phone_from_whatsapp_id(whatsapp_id)
    reference = create_payment_reference(prefix="wa")
    metadata = {
        "patient_type": patient_type,
        "patient_id": patient_id,
        "source": "whatsapp",
        "telegram_id": 0,
        "whatsapp_id": whatsapp_id,
    }
    if registration:
        metadata["registration_payload_json"] = json.dumps(registration)
    try:
        coupon = validate_coupon(
            code=coupon_code,
            purpose=purpose,
            amount=amount,
            patient_id=patient_id,
            email=email,
            phone=phone,
        )
    except CouponError as exc:
        raise PaystackError(str(exc)) from exc
    if coupon["applied"]:
        metadata["coupon_code"] = coupon["code"]
        metadata["original_amount"] = coupon["amount_before"]
        metadata["discount_amount"] = coupon["discount_amount"]
        amount = coupon["amount_after"]
    callback_url = build_backend_callback_url(
        "/payments/whatsapp-return",
        {"reference": reference},
    ) or build_frontend_callback_url(
        "/signin",
        {"payment_reference": reference, "reference": reference, "status": "success"},
    )
    if amount == 0 and coupon["applied"]:
        create_payment_record(
            reference=reference,
            telegram_id=0,
            patient_id=patient_id,
            email=email,
            amount=0,
            currency=config["currency"],
            patient_type=patient_type,
            label=config["label"],
            registration_payload_json=metadata.get("registration_payload_json"),
            original_amount=coupon["amount_before"],
            discount_amount=coupon["discount_amount"],
            coupon_code=coupon["code"],
        )
        mark_payment_verified(reference, paystack_status="coupon_free", patient_id=patient_id or None)
        return {
            "reference": reference,
            "authorization_url": "",
            "amount": 0,
            "currency": config["currency"],
            "label": config["label"],
            "coupon": {
                "code": coupon["code"],
                "discount_amount": coupon["discount_amount"],
                "original_amount": coupon["amount_before"],
                "amount_after": 0,
            },
        }
    result = await initialize_transaction(
        email=email,
        amount_ngn=amount,
        currency=config["currency"],
        reference=reference,
        label=config["label"],
        metadata=metadata,
        callback_url=callback_url,
    )
    return {
        "reference": reference,
        "authorization_url": result["authorization_url"],
        "amount": amount,
        "currency": config["currency"],
        "label": config["label"],
        "coupon": (
            {
                "code": coupon["code"],
                "discount_amount": coupon["discount_amount"],
                "original_amount": coupon["amount_before"],
                "amount_after": coupon["amount_after"],
            }
            if coupon["applied"]
            else None
        ),
    }


def _payment_prompt(payment: dict) -> str:
    coupon_line = ""
    if payment.get("coupon"):
        coupon_line = (
            f"Coupon {payment['coupon']['code']} applied. "
            f"You saved {payment['currency']} {payment['coupon']['discount_amount']:,}.\n"
        )
    if not payment.get("authorization_url"):
        return (
            f"{payment['label']}\n"
            f"{coupon_line}"
            "No payment is required.\n\n"
            f"Reference: {payment['reference']}"
        )
    return (
        f"{payment['label']}\n"
        f"{coupon_line}"
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
            return _wrong_step_reply("Please type your full name.")
        payload["name"] = value
        _save_session(whatsapp_id, "register_age", payload, session.get("name", ""))
        return "How old are you? Reply with your age in years."

    if state == "register_age":
        if not value.isdigit() or not (0 < int(value) < 130):
            return _wrong_step_reply("Please enter a valid age in years, for example: 34.")
        payload["age"] = int(value)
        _save_session(whatsapp_id, "register_gender", payload, session.get("name", ""))
        return "What is your gender? Reply Male, Female, or your preferred description."

    if state == "register_gender":
        if len(value) < 2:
            return _wrong_step_reply("Please enter your gender, for example: Male or Female.")
        payload["gender"] = value
        _save_session(whatsapp_id, "register_email", payload, session.get("name", ""))
        return "Please enter your email address. We will use it for receipts, documents, and web access."

    if state == "register_email":
        email = value.lower()
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            return _wrong_step_reply("Please enter a valid email address, for example: patient@example.com.")
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
            return _wrong_step_reply("Please enter your address or city.")
        payload["address"] = value
        _save_session(whatsapp_id, "register_allergy", payload, session.get("name", ""))
        return "Do you have any allergies? Reply none if you do not."

    if state == "register_allergy":
        payload["allergy"] = "" if value.lower() in {"none", "nil", "no"} else value
        payload.setdefault("medical_conditions", "")
        try:
            patient = register_patient(
                telegram_id=None,
                name=payload["name"],
                age=str(payload["age"]),
                gender=payload["gender"],
                phone=payload["phone"],
                email=payload["email"],
                address=payload["address"],
                allergy=payload.get("allergy", ""),
                medical_conditions=payload.get("medical_conditions", ""),
                email_verified_at=None,
            )
        except Exception:
            return "Unable to complete registration right now. Please try again shortly."
        try:
            send_patient_web_access_setup(hospital_number=patient["hospital_number"], email=patient["email"])
        except Exception:
            pass
        _save_session(
            whatsapp_id,
            "post_registration_consultation_choice",
            {"patient_id": patient["hospital_number"]},
            session.get("name", ""),
        )
        return (
            f"Registration completed for {patient['name']} ({patient['hospital_number']}).\n\n"
            "We have sent your web access setup link to your email for future web sign-in.\n\n"
            "Would you like to proceed with consultation now? Reply yes to enter your symptoms, or no to return to the menu."
        )

    return build_basic_menu(session.get("name", ""))


async def _handle_post_registration_consultation_choice(session: dict, message_text: str, name: str = "") -> str:
    whatsapp_id = session["whatsapp_id"]
    display_name = name or session.get("name", "")
    if _is_yes_reply(message_text):
        return await _start_consultation_reply(whatsapp_id, display_name)
    if _is_no_reply(message_text):
        _save_session(
            whatsapp_id,
            "idle",
            {"patient_id": (session.get("payload") or {}).get("patient_id", "")},
            display_name,
        )
        return "No problem. You can reply 2 whenever you are ready to start consultation.\n\n" + build_basic_menu(display_name)
    return _wrong_step_reply("Please reply yes to proceed with consultation now, or no to return to the menu.")


async def _verify_whatsapp_payment(reference: str, whatsapp_id: str, name: str = "") -> str:
    payment = get_payment_by_reference(reference)
    if not payment:
        return "I could not find that payment reference. Please check it and try again."
    if payment["status"] == "verified" and is_payment_within_validity_window(payment):
        patient = get_patient_by_identifier(payment["patient_id"] or "")
        if patient:
            _save_session(whatsapp_id, "awaiting_symptoms", {"patient_id": patient["hospital_number"], "reference": reference}, name)
            return "Payment is already verified.\n\nPlease describe your symptoms so I can place you in the doctor queue."

    if payment["status"] == "verified" and payment["paystack_status"] == "coupon_free":
        paystack_status = "coupon_free"
        amount_ngn = int(payment["amount"] or 0)
        currency = payment["currency"]
    else:
        try:
            verification = await verify_transaction(reference)
        except PaystackError as exc:
            return f"Unable to verify payment right now: {exc}"
        except Exception:
            return "Unable to verify payment right now. Please try again shortly."

        paystack_status = (verification.get("status") or "").lower()
        amount_ngn = int(verification.get("amount", 0)) // 100
        currency = verification.get("currency")
    if paystack_status not in {"success", "coupon_free"}:
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
    if payment["coupon_code"]:
        record_coupon_redemption(
            reference=reference,
            code=payment["coupon_code"],
            purpose="registration" if payment["patient_type"] == "new" else "consultation",
            amount_before=int(payment["original_amount"] or payment["amount"] or 0),
            discount_amount=int(payment["discount_amount"] or 0),
            amount_after=int(payment["amount"] or 0),
            patient_id=patient["hospital_number"],
            email=payment["email"] or patient.get("email") or "",
            phone=patient.get("phone") or "",
        )
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
    if not payment:
        payment = _grant_whatsapp_first_consultation_free(patient)
    if payment:
        _save_session(whatsapp_id, "awaiting_symptoms", {"patient_id": patient["hospital_number"], "reference": payment["reference"]}, name)
        if payment["paystack_status"] == "first_consultation_free":
            return (
                f"Your first SynMed consultation is free for {patient['name']} ({patient['hospital_number']}).\n\n"
                "Please describe your symptoms so I can place you in the doctor queue."
            )
        return (
            f"I found an active consultation payment for {patient['name']} ({patient['hospital_number']}).\n\n"
            "Please describe your symptoms so I can place you in the doctor queue."
        )
    if has_active_coupon_for_purpose("consultation"):
        _save_session(whatsapp_id, "consultation_coupon", {"patient_id": patient["hospital_number"]}, name)
        return (
            f"I found your SynMed record as {patient['name']} ({patient['hospital_number']}).\n\n"
            f"{_coupon_prompt('consultation')}"
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


async def _continue_consultation_coupon(session: dict, text: str) -> str:
    whatsapp_id = session["whatsapp_id"]
    payload = dict(session.get("payload") or {})
    patient = get_patient_by_identifier(payload.get("patient_id") or "") or _lookup_patient_from_phone(whatsapp_id)
    if not patient:
        _clear_session(whatsapp_id)
        return "Patient record missing. Reply 1 to register or 5 to contact customer care."
    coupon_code = "" if _is_coupon_skip(text) else text.strip()
    try:
        initialized = await _initialize_whatsapp_payment(
            patient_type="returning",
            email=patient.get("email") or f"{_digits(whatsapp_id)}@synmed.whatsapp",
            whatsapp_id=whatsapp_id,
            patient=patient,
            coupon_code=coupon_code,
        )
    except PaystackError as exc:
        return f"Unable to start payment right now: {exc}"
    except Exception:
        return "Unable to start payment right now. Please try again shortly."
    if not initialized.get("authorization_url"):
        _save_session(
            whatsapp_id,
            "awaiting_payment",
            {"patient_id": patient["hospital_number"], "reference": initialized["reference"]},
            session.get("name", ""),
        )
        return await _verify_whatsapp_payment(initialized["reference"], whatsapp_id, session.get("name", ""))
    _save_session(
        whatsapp_id,
        "awaiting_payment",
        {"patient_id": patient["hospital_number"], "reference": initialized["reference"]},
        session.get("name", ""),
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
    dispatch_admins_patient_queued(patient_details, channel="whatsapp")
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


def _extension_for_media(filename: str, content_type: str, media_type: str) -> str:
    extension = Path(filename or "").suffix[:16]
    if extension:
        return extension
    if content_type == "image/jpeg":
        return ".jpg"
    if content_type == "image/png":
        return ".png"
    if content_type == "video/mp4":
        return ".mp4"
    if content_type in {"audio/ogg", "audio/opus"} or media_type in {"audio", "voice"}:
        return ".ogg"
    if content_type == "application/pdf":
        return ".pdf"
    return ".bin"


def _message_text_for_media(filename: str, content_type: str, media_type: str) -> str:
    if media_type in {"audio", "voice"} or content_type.startswith("audio/"):
        return "Voice message"
    if media_type == "image" or content_type.startswith("image/"):
        return filename or "Photo attachment"
    if media_type == "video" or content_type.startswith("video/"):
        return filename or "Video attachment"
    return filename or "Document attachment"


async def _download_whatsapp_media(media_id: str) -> tuple[bytes, str]:
    token = _access_token()
    if not token:
        raise WhatsAppConfigurationError("WhatsApp access token is not configured.")

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        metadata_response = await client.get(
            f"https://graph.facebook.com/{WHATSAPP_API_VERSION}/{media_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        metadata_response.raise_for_status()
        metadata = metadata_response.json()
        media_url = metadata.get("url")
        content_type = metadata.get("mime_type") or "application/octet-stream"
        if not media_url:
            raise RuntimeError("WhatsApp media URL was not returned.")
        media_response = await client.get(media_url, headers={"Authorization": f"Bearer {token}"})
        media_response.raise_for_status()
        return media_response.content, media_response.headers.get("content-type") or content_type


async def handle_whatsapp_media_message(message: dict) -> str:
    whatsapp_id = (message.get("from") or "").strip()
    media_id = (message.get("media_id") or "").strip()
    media_type = (message.get("media_type") or "document").strip().lower()
    filename = (message.get("filename") or "").strip()
    if not whatsapp_id or not media_id:
        return ""

    patient, consultation = _active_consultation_for_whatsapp(whatsapp_id)
    if not patient or not consultation:
        return "No active consultation is connected yet. Reply 2 to start or continue a consultation."

    content, content_type = await _download_whatsapp_media(media_id)
    extension = _extension_for_media(filename, content_type, media_type)
    stored_name = f"whatsapp-{uuid4().hex}{extension}"
    asset_path = f"consultation_media/chat_uploads/{stored_name}"
    storage_service.save_bytes(asset_path, content)

    consultation_id = consultation["consultation_id"]
    message_text = _message_text_for_media(filename, content_type, media_type)
    transcript_message = log_consultation_message(
        consultation_id,
        sender_id=patient["id"],
        sender_role="patient_whatsapp",
        message_text=message_text,
        asset_path=asset_path,
        asset_type=content_type,
    )
    touch_chat_activity(patient["id"])
    await realtime_hub.broadcast_message(consultation_id, transcript_message)
    return ""


async def send_patient_document_notice(
    patient: dict | None,
    document_kind: str,
    document_url: str = "",
    filename: str = "",
) -> bool:
    recipient = _whatsapp_recipient_from_patient(patient)
    if not recipient or not is_configured():
        return False
    label = {
        "prescription": "prescription",
        "investigation": "investigation request",
        "medical_report": "medical report",
    }.get(document_kind, "clinical document")
    direct_url = _absolute_public_url(document_url)
    if direct_url:
        await send_document_message(
            recipient,
            direct_url,
            filename or f"synmed-{document_kind.replace('_', '-')}.pdf",
            f"Your SynMed {label} is ready.",
        )
        return True

    await send_text_message(
        recipient,
        (
            f"Your SynMed {label} is ready.\n\n"
            "Open this direct document link:\n"
            f"{_frontend_base_url()}/patient/documents"
        ),
    )
    return True


def build_keyword_reply(message_text: str, name: str = "", sender: str = "") -> str:
    normalized = (message_text or "").strip().lower()
    contains_patient_identifier = bool(
        re.search(r"\bSM\d+\b|[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", message_text or "", flags=re.I)
    )
    if normalized in {"hi", "hello", "hey", "menu", "start"}:
        return build_basic_menu(name)
    if normalized in {"more_options", "more options", "more"}:
        return build_more_options_menu()
    if normalized.startswith("setup") or normalized in {"web access", "activate web", "setup link"}:
        patient = _lookup_patient_from_message(message_text, sender)
        if not patient and contains_patient_identifier:
            return _privacy_guard_reply()
        return _web_setup_reply(patient)
    if normalized in {"6", "web", "website", "continue on web", "open web", "synmed website"}:
        return _continue_on_web_reply(_lookup_patient_from_phone(sender))
    if normalized in {"7", "guide", "how", "how to", "whatsapp guide", "consultation guide", "help"}:
        return _whatsapp_consultation_guide_reply()
    if normalized.startswith("record") or normalized.startswith("patient") or re.search(r"\bSM\d+\b", message_text or "", flags=re.I):
        patient = _lookup_patient_from_message(message_text, sender)
        if patient:
            return _patient_record_reply(patient)
        if contains_patient_identifier:
            return _privacy_guard_reply()
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
    normalized = _normalize_interactive_reply(message_text)
    session = _session(sender)

    if normalized == "cancel":
        return _cancel_whatsapp_flow(sender)

    patient, active_consultation = _active_consultation_for_whatsapp(sender)
    if session and session["state"] in {"awaiting_rating", "awaiting_review"}:
        return await _handle_whatsapp_feedback(session, message_text)
    if session and session["state"] == "awaiting_consent":
        return await _handle_whatsapp_consent(session, message_text, name)

    if not active_consultation and not _has_whatsapp_consent(sender):
        next_action = _next_action_from_message(normalized)
        _save_consent_session(sender, name, next_action)
        return _whatsapp_consent_prompt()

    if session and not active_consultation and normalized in RESTART_WORDS:
        _clear_session(sender)
        return "No problem. I have restarted the WhatsApp flow.\n\n" + build_basic_menu(name)

    if active_consultation and normalized in {"end", "end chat"}:
        consultation_for_rating = active_consultation
        details = consultation_for_rating.get("patient_details") or {}
        end_chat(patient["id"])
        await send_whatsapp_rating_prompt(sender, consultation_for_rating, details)
        return _rating_prompt()
    if active_consultation and normalized not in COMMAND_WORDS and not normalized.startswith("paid"):
        return await _relay_patient_chat_message(sender, message_text)

    if normalized in RESTART_WORDS:
        return build_basic_menu(name)
    if session and session["state"] == "post_registration_consultation_choice":
        return await _handle_post_registration_consultation_choice(session, message_text, name)
    if session and session["state"].startswith("register_"):
        return await _continue_registration(session, message_text)
    if session and session["state"] == "consultation_coupon":
        return await _continue_consultation_coupon(session, message_text)
    if session and session["state"] == "awaiting_symptoms" and normalized not in COMMAND_WORDS and not normalized.startswith("paid"):
        return await _queue_whatsapp_consultation(sender, message_text, session, name)
    if session and session["state"] == "awaiting_payment" and not normalized.startswith("paid"):
        reference = (session.get("payload") or {}).get("reference") or (session.get("payload") or {}).get("payment_reference") or ""
        expected = (
            f"Please complete your Paystack payment, then reply: paid {reference}"
            if reference
            else "Please complete your Paystack payment, then reply with paid followed by your payment reference."
        )
        return _wrong_step_reply(expected)
    if session and session["state"] == "queued" and normalized not in COMMAND_WORDS:
        if not _is_whatsapp_session_still_queued(session):
            return _clear_stale_queue_session(sender)
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


async def send_rating_options_message(to: str) -> dict:
    token = _access_token()
    phone_number_id = _phone_number_id()
    if not token or not phone_number_id:
        raise WhatsAppConfigurationError("WhatsApp access token or phone number ID is not configured.")

    url = f"https://graph.facebook.com/{WHATSAPP_API_VERSION}/{phone_number_id}/messages"
    rows = [
        {"id": f"rating:{score}", "title": f"{score} star" if score == 1 else f"{score} stars"}
        for score in range(1, 6)
    ]
    rows.append({"id": "rating:skip", "title": "No thanks"})
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {"text": _rating_prompt()},
            "action": {
                "button": "Rate doctor",
                "sections": [{"title": "Doctor rating", "rows": rows}],
            },
        },
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


async def send_menu_options_message(to: str, message: str) -> dict:
    token = _access_token()
    phone_number_id = _phone_number_id()
    if not token or not phone_number_id:
        raise WhatsAppConfigurationError("WhatsApp access token or phone number ID is not configured.")

    url = f"https://graph.facebook.com/{WHATSAPP_API_VERSION}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": message},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": "1", "title": "Register / sign in"}},
                    {"type": "reply", "reply": {"id": "2", "title": "Start consult"}},
                    {"type": "reply", "reply": {"id": "more_options", "title": "More options"}},
                ],
            },
        },
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


async def send_more_options_message(to: str, message: str) -> dict:
    token = _access_token()
    phone_number_id = _phone_number_id()
    if not token or not phone_number_id:
        raise WhatsAppConfigurationError("WhatsApp access token or phone number ID is not configured.")

    url = f"https://graph.facebook.com/{WHATSAPP_API_VERSION}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": message},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": "3", "title": "Payment support"}},
                    {"type": "reply", "reply": {"id": "4", "title": "Medical report"}},
                    {"type": "reply", "reply": {"id": "5", "title": "Customer care"}},
                ],
            },
        },
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


async def send_consent_options_message(to: str, message: str) -> dict:
    token = _access_token()
    phone_number_id = _phone_number_id()
    if not token or not phone_number_id:
        raise WhatsAppConfigurationError("WhatsApp access token or phone number ID is not configured.")

    url = f"https://graph.facebook.com/{WHATSAPP_API_VERSION}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": message},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": "consent:agree", "title": "I Agree"}},
                    {"type": "reply", "reply": {"id": "consent:view", "title": "View Policy"}},
                    {"type": "reply", "reply": {"id": "consent:disagree", "title": "I Disagree"}},
                ],
            },
        },
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


async def send_post_registration_options_message(to: str, message: str) -> dict:
    token = _access_token()
    phone_number_id = _phone_number_id()
    if not token or not phone_number_id:
        raise WhatsAppConfigurationError("WhatsApp access token or phone number ID is not configured.")

    url = f"https://graph.facebook.com/{WHATSAPP_API_VERSION}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": message},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": "yes", "title": "Yes, continue"}},
                    {"type": "reply", "reply": {"id": "no", "title": "No, later"}},
                ],
            },
        },
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


async def send_whatsapp_response(to: str, message: str) -> dict:
    if _is_consent_prompt(message):
        try:
            return await send_consent_options_message(to, message)
        except httpx.HTTPError:
            return await send_text_message(to, message)
    if _is_post_registration_consultation_prompt(message):
        try:
            return await send_post_registration_options_message(to, message)
        except httpx.HTTPError:
            return await send_text_message(to, message)
    if _is_more_options_reply(message):
        try:
            return await send_more_options_message(to, message)
        except httpx.HTTPError:
            return await send_text_message(to, message)
    if _is_basic_menu_reply(message):
        try:
            return await send_menu_options_message(to, message)
        except httpx.HTTPError:
            return await send_text_message(to, message)
    return await send_text_message(to, message)


async def send_document_message(to: str, document_url: str, filename: str, caption: str = "") -> dict:
    token = _access_token()
    phone_number_id = _phone_number_id()
    if not token or not phone_number_id:
        raise WhatsAppConfigurationError("WhatsApp access token or phone number ID is not configured.")

    url = f"https://graph.facebook.com/{WHATSAPP_API_VERSION}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "document",
        "document": {
            "link": document_url,
            "filename": filename or "synmed-document.pdf",
            "caption": caption,
        },
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
