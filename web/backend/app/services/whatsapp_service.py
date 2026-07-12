import os
import re

import httpx

from database import get_connection
from services.patient_records import get_patient_by_identifier
from .auth_service import send_patient_web_access_setup
from .support_ai_service import create_support_ticket


WHATSAPP_API_VERSION = os.getenv("WHATSAPP_API_VERSION", "v20.0").strip() or "v20.0"


class WhatsAppConfigurationError(RuntimeError):
    pass


def _access_token() -> str:
    return os.getenv("WHATSAPP_ACCESS_TOKEN", "").strip()


def _phone_number_id() -> str:
    return os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip()


def is_configured() -> bool:
    return bool(_access_token() and _phone_number_id())


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
        "1. Reply menu anytime to see your options.\n"
        "2. Reply 1 to register or sign in on the website.\n"
        "3. Reply 2 when you want to start a consultation. We will direct you to your secure patient dashboard.\n"
        "4. Reply setup with your hospital number if you registered from Telegram and need web access, for example: setup SM0001.\n"
        "5. Reply 3 for payment support, or 5 to talk to customer care.\n\n"
        "For privacy, payments, clinical documents, and doctor chat are completed securely on SynMed."
    )


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
            f"To start a consultation, please open SynMed and continue from your patient dashboard.{patient_line}\n"
            f"{_frontend_base_url()}/signin\n\n"
            "We will add full WhatsApp consultation payments and queueing soon."
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
