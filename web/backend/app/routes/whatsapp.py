import os

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from services.operational_errors import log_exception, log_operational_error
from ..services.whatsapp_service import (
    WhatsAppConfigurationError,
    build_keyword_reply,
    send_text_message,
)


router = APIRouter()


def _verify_token() -> str:
    return os.getenv("WHATSAPP_VERIFY_TOKEN", "").strip()


def _extract_text_messages(payload: dict) -> list[dict]:
    messages = []
    entries = payload.get("entry") if isinstance(payload, dict) else []
    if not isinstance(entries, list):
        return messages

    for entry in entries:
        changes = entry.get("changes", []) if isinstance(entry, dict) else []
        if not isinstance(changes, list):
            continue
        for change in changes:
            value = change.get("value", {}) if isinstance(change, dict) else {}
            contacts = value.get("contacts", []) if isinstance(value, dict) else []
            contact_names = {}
            if isinstance(contacts, list):
                for contact in contacts:
                    if not isinstance(contact, dict):
                        continue
                    profile = contact.get("profile", {}) if isinstance(contact.get("profile"), dict) else {}
                    contact_names[contact.get("wa_id")] = profile.get("name") or ""

            inbound_messages = value.get("messages", []) if isinstance(value, dict) else []
            if not isinstance(inbound_messages, list):
                continue
            for message in inbound_messages:
                if not isinstance(message, dict) or message.get("type") != "text":
                    continue
                sender = (message.get("from") or "").strip()
                text = ((message.get("text") or {}).get("body") or "").strip()
                if sender and text:
                    messages.append(
                        {
                            "from": sender,
                            "text": text,
                            "name": contact_names.get(sender, ""),
                            "message_id": message.get("id") or "",
                        }
                    )
    return messages


@router.get("/webhook", response_class=PlainTextResponse)
def verify_whatsapp_webhook(
    mode: str = Query(default="", alias="hub.mode"),
    token: str = Query(default="", alias="hub.verify_token"),
    challenge: str = Query(default="", alias="hub.challenge"),
):
    expected_token = _verify_token()
    if not expected_token:
        log_operational_error(
            source="whatsapp_webhook",
            severity="warning",
            message="WhatsApp webhook verification attempted before WHATSAPP_VERIFY_TOKEN was configured.",
        )
        raise HTTPException(status_code=503, detail="WhatsApp verify token is not configured.")

    if mode == "subscribe" and token == expected_token:
        return PlainTextResponse(content=challenge, status_code=200)

    log_operational_error(
        source="whatsapp_webhook",
        severity="warning",
        message="WhatsApp webhook verification failed.",
        status_code=403,
        details={"mode": mode, "token_supplied": bool(token)},
    )
    raise HTTPException(status_code=403, detail="WhatsApp webhook verification failed.")


@router.post("/webhook")
async def receive_whatsapp_webhook(request: Request):
    try:
        payload = await request.json()
    except Exception as exc:
        log_exception(
            exc,
            source="whatsapp_webhook",
            path=str(request.url.path),
            method=request.method,
            status_code=400,
        )
        raise HTTPException(status_code=400, detail="Invalid WhatsApp webhook payload.") from exc

    entries = payload.get("entry") if isinstance(payload, dict) else None
    text_messages = _extract_text_messages(payload)
    reply_count = 0
    for message in text_messages:
        try:
            reply = build_keyword_reply(message["text"], message.get("name", ""), message.get("from", ""))
            await send_text_message(message["from"], reply)
            reply_count += 1
        except WhatsAppConfigurationError as exc:
            log_exception(
                exc,
                source="whatsapp_webhook_send",
                path=str(request.url.path),
                method=request.method,
                status_code=503,
            )
        except Exception as exc:
            log_exception(
                exc,
                source="whatsapp_webhook_send",
                path=str(request.url.path),
                method=request.method,
                status_code=502,
            )
            log_operational_error(
                source="whatsapp_webhook_send_context",
                severity="warning",
                message="WhatsApp reply failed for inbound message.",
                path=str(request.url.path),
                method=request.method,
                status_code=502,
                details={"from": message.get("from"), "message_id": message.get("message_id")},
            )

    log_operational_error(
        source="whatsapp_webhook",
        severity="info",
        message="WhatsApp webhook payload received.",
        path=str(request.url.path),
        method=request.method,
        status_code=200,
        details={
            "object": payload.get("object") if isinstance(payload, dict) else "",
            "entries": len(entries) if isinstance(entries, list) else 0,
            "text_messages": len(text_messages),
            "replies": reply_count,
        },
    )
    return {"status": "received"}
