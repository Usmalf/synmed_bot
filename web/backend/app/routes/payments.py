from fastapi import APIRouter, Depends, HTTPException

from services.paystack import PaystackError

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
