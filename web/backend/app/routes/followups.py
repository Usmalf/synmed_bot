from fastapi import APIRouter, Depends

from ..deps import require_patient
from ..schemas.followup import (
    FollowUpBookingRequest,
    FollowUpBookingResponse,
    FollowUpDetailResponse,
    FollowUpListResponse,
    FollowUpPaymentActionResponse,
    FollowUpPaymentCodeRequest,
    FollowUpPaymentInitializeRequest,
    FollowUpPaymentInitializeResponse,
    FollowUpPaymentVerifyResponse,
)
from ..services.followup_app_service import (
    create_patient_followup_booking,
    get_patient_followup,
    initialize_followup_payment,
    list_patient_followups,
    mark_followup_pay_later,
    redeem_followup_payment_code,
    verify_followup_payment,
)


router = APIRouter()


@router.get("/upcoming", response_model=FollowUpListResponse)
def upcoming_followups(session: dict = Depends(require_patient)):
    return list_patient_followups(session["user_id"])


@router.post("/book", response_model=FollowUpBookingResponse)
def book_followup(payload: FollowUpBookingRequest, session: dict = Depends(require_patient)):
    return create_patient_followup_booking(session["user_id"], payload.model_dump())


@router.get("/{reference}", response_model=FollowUpDetailResponse)
def followup_detail(reference: str, session: dict = Depends(require_patient)):
    return get_patient_followup(reference, session["user_id"])


@router.post("/{reference}/payment/initialize", response_model=FollowUpPaymentInitializeResponse)
async def initialize_followup_payment_route(
    reference: str,
    payload: FollowUpPaymentInitializeRequest,
    session: dict = Depends(require_patient),
):
    return await initialize_followup_payment(reference, session["user_id"], payload.model_dump())


@router.post("/{reference}/payment/pay-later", response_model=FollowUpPaymentActionResponse)
def followup_pay_later(reference: str, session: dict = Depends(require_patient)):
    return mark_followup_pay_later(reference, session["user_id"])


@router.post("/{reference}/payment/redeem", response_model=FollowUpPaymentActionResponse)
def followup_redeem_payment_code(
    reference: str,
    payload: FollowUpPaymentCodeRequest,
    session: dict = Depends(require_patient),
):
    return redeem_followup_payment_code(reference, session["user_id"], payload.payment_code)


@router.post("/{reference}/payment/verify/{payment_reference}", response_model=FollowUpPaymentVerifyResponse)
async def followup_verify_payment(
    reference: str,
    payment_reference: str,
    session: dict = Depends(require_patient),
):
    return await verify_followup_payment(reference, session["user_id"], payment_reference)
