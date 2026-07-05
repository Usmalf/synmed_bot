import os

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from services.operational_errors import log_exception, log_operational_error


router = APIRouter()


def _verify_token() -> str:
    return os.getenv("WHATSAPP_VERIFY_TOKEN", "").strip()


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
    message_count = 0
    if isinstance(entries, list):
        for entry in entries:
            for change in entry.get("changes", []) if isinstance(entry, dict) else []:
                value = change.get("value", {}) if isinstance(change, dict) else {}
                messages = value.get("messages", []) if isinstance(value, dict) else []
                if isinstance(messages, list):
                    message_count += len(messages)

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
            "messages": message_count,
        },
    )
    return {"status": "received"}
