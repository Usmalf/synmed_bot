import os

import httpx


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
        "5 - Talk to customer care"
    )


def build_keyword_reply(message_text: str, name: str = "") -> str:
    normalized = (message_text or "").strip().lower()
    if normalized in {"hi", "hello", "hey", "menu", "start"}:
        return build_basic_menu(name)
    if normalized in {"1", "register", "signin", "sign in", "login"}:
        return (
            "To use SynMed on the web, please sign in or register here:\n"
            f"{os.getenv('FRONTEND_BASE_URL', '').strip().rstrip('/') or 'https://synmedhealth.com'}/signin\n\n"
            "You can also reply 2 to start a consultation."
        )
    if normalized in {"2", "consult", "consultation", "start consultation"}:
        return (
            "To start a consultation, please open SynMed and continue from your patient dashboard:\n"
            f"{os.getenv('FRONTEND_BASE_URL', '').strip().rstrip('/') or 'https://synmedhealth.com'}/signin\n\n"
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
    if normalized in {"5", "agent", "support", "customer care", "human"}:
        return (
            "Please describe the issue briefly. A SynMed customer-care agent will review your message."
        )
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
