import os
import json
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from services.operational_errors import log_exception
from services.paystack import (
    PaystackError,
    build_frontend_callback_url,
    process_paystack_webhook,
    verify_paystack_webhook_signature,
)

from ..deps import require_patient
from ..schemas.payment import (
    CurrentPaymentStatusResponse,
    PaymentConfigResponse,
    PaymentInitializeRequest,
    PaymentInitializeResponse,
    PaymentVerifyResponse,
)
from ..services.payment_app_service import (
    get_current_patient_payment_status,
    get_payment_config,
    initialize_web_payment,
    verify_web_payment,
)


router = APIRouter()


@router.get("/config", response_model=PaymentConfigResponse)
def payment_config():
    return get_payment_config()


@router.get("/current", response_model=CurrentPaymentStatusResponse)
def current_payment_status(session: dict = Depends(require_patient)):
    return get_current_patient_payment_status(str(session["user_id"]))


@router.post("/initialize", response_model=PaymentInitializeResponse)
async def initialize_payment(payload: PaymentInitializeRequest):
    try:
        return await initialize_web_payment(payload.model_dump())
    except PaystackError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/verify/{reference}", response_model=PaymentVerifyResponse)
async def verify_payment(reference: str):
    try:
        return await verify_web_payment(reference)
    except PaystackError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/paystack-webhook")
async def paystack_webhook(request: Request):
    raw_body = await request.body()
    signature = request.headers.get("x-paystack-signature")
    if not verify_paystack_webhook_signature(raw_body, signature):
        raise HTTPException(status_code=401, detail="Invalid Paystack webhook signature.")

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid Paystack webhook payload.") from exc

    result = process_paystack_webhook(payload, raw_body)
    if result.get("payment_status") == "verified" and result.get("reference"):
        try:
            await verify_web_payment(result["reference"])
        except Exception as exc:
            log_exception(
                exc,
                source="payment_webhook_whatsapp_followup",
                path="/payments/paystack-webhook",
                method="POST",
                status_code=502,
            )
    return result


@router.get("/web-return")
async def web_payment_return(reference: str = "", trxref: str = "", callback_path: str = ""):
    payment_reference = (reference or trxref or "").strip()
    frontend_path = (callback_path or "").strip() or "/patient/register"
    redirect_params = {
        "payment_reference": payment_reference,
        "reference": payment_reference,
    }

    if not payment_reference:
        redirect_params.update(
            {
                "verified": "0",
                "status": "missing_reference",
                "message": "Payment reference was not returned by Paystack.",
            }
        )
        return RedirectResponse(build_frontend_callback_url(frontend_path, redirect_params), status_code=302)

    try:
        result = await verify_web_payment(payment_reference)
        redirect_params.update(
            {
                "verified": "1" if result.get("verified") else "0",
                "status": result.get("paystack_status") or "pending",
                "requires_email_verification": "1" if result.get("requires_email_verification") else "0",
                "message": result.get("message") or "",
            }
        )
    except Exception as exc:
        log_exception(
            exc,
            source="payment_web_return",
            path="/payments/web-return",
            method="GET",
            status_code=502,
        )
        redirect_params.update(
            {
                "verified": "0",
                "status": "verification_error",
                "message": str(exc),
            }
        )

    return RedirectResponse(build_frontend_callback_url(frontend_path, redirect_params), status_code=302)


@router.get("/telegram-return")
def telegram_payment_return(reference: str = "", trxref: str = ""):
    payment_reference = (reference or trxref or "").strip()
    bot_username = (os.getenv("BOT_USERNAME") or "Synmed2_bot").strip().lstrip("@")
    payload = quote(f"paid_{payment_reference}", safe="")
    return RedirectResponse(f"https://t.me/{bot_username}?start={payload}", status_code=302)


@router.get("/whatsapp-return")
async def whatsapp_payment_return(reference: str = "", trxref: str = ""):
    payment_reference = (reference or trxref or "").strip()
    if payment_reference:
        try:
            await verify_web_payment(payment_reference)
        except Exception as exc:
            log_exception(
                exc,
                source="payment_whatsapp_return",
                path="/payments/whatsapp-return",
                method="GET",
                status_code=502,
            )

    whatsapp_number = (
        os.getenv("WHATSAPP_PUBLIC_PHONE_NUMBER", "").strip()
        or os.getenv("WHATSAPP_BUSINESS_NUMBER", "").strip()
        or os.getenv("WHATSAPP_CONTACT_NUMBER", "").strip()
    )
    cleaned_number = "".join(character for character in whatsapp_number if character.isdigit())
    if not cleaned_number:
        return RedirectResponse(build_frontend_callback_url("/signin", {"payment_reference": payment_reference}), status_code=302)

    message = f"paid {payment_reference}" if payment_reference else "I have completed my SynMed payment."
    return RedirectResponse(f"https://wa.me/{cleaned_number}?text={quote(message, safe='')}", status_code=302)
