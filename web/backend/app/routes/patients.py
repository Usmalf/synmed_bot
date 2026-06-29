from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..deps import require_patient
from ..schemas.patient import (
    MedicalReportPaymentInitRequest,
    MedicalReportRequestCreateRequest,
    PatientAccountUpdateRequest,
    PatientHistoryResponse,
    PatientLookupResponse,
    PatientPasswordChangeRequest,
    PatientRegistrationRequest,
    PatientRegistrationResponse,
)
from ..services.patient_app_service import (
    change_patient_password,
    lookup_current_patient_documents,
    list_current_patient_medical_report_requests,
    lookup_patient,
    lookup_patient_history,
    create_current_patient_medical_report_request,
    initialize_current_patient_medical_report_payment,
    register_web_patient,
    update_patient_account,
    verify_current_patient_medical_report_payment,
)
from ..services.support_ai_service import (
    add_support_ticket_message,
    answer_patient_support_message,
    get_support_ticket,
    mark_support_ticket_messages_read,
    submit_support_ticket_feedback,
)

router = APIRouter()


class PatientSupportAiRequest(BaseModel):
    message: str
    escalate: bool = False
    history: list[dict] = Field(default_factory=list)


class PatientSupportTicketMessageRequest(BaseModel):
    message_text: str


class PatientSupportTicketFeedbackRequest(BaseModel):
    rating: int | None = None
    review: str = ""
    skipped: bool = False


@router.get("/lookup", response_model=PatientLookupResponse)
def lookup_patient_route(identifier: str = Query(..., min_length=1)):
    return lookup_patient(identifier)


@router.post("/register", response_model=PatientRegistrationResponse)
def register_patient_route(payload: PatientRegistrationRequest):
    return register_web_patient(payload.model_dump())


@router.get("/me")
def current_patient(session: dict = Depends(require_patient)):
    return lookup_patient(session["user_id"])


@router.get("/history", response_model=PatientHistoryResponse)
def current_patient_history(session: dict = Depends(require_patient)):
    return lookup_patient_history(session["user_id"])


@router.get("/documents")
def current_patient_documents(session: dict = Depends(require_patient)):
    return lookup_current_patient_documents(str(session["user_id"]))


@router.get("/medical-report-requests")
def current_patient_medical_report_requests(session: dict = Depends(require_patient)):
    return list_current_patient_medical_report_requests(str(session["user_id"]))


@router.post("/medical-report-requests")
def create_patient_medical_report_request(
    payload: MedicalReportRequestCreateRequest,
    session: dict = Depends(require_patient),
):
    return create_current_patient_medical_report_request(str(session["user_id"]), payload.model_dump())


@router.post("/medical-report-requests/{request_id}/pay")
async def initialize_patient_medical_report_payment(
    request_id: str,
    payload: MedicalReportPaymentInitRequest,
    session: dict = Depends(require_patient),
):
    return await initialize_current_patient_medical_report_payment(
        str(session["user_id"]),
        request_id,
        payload.model_dump(),
    )


@router.post("/medical-report-requests/{request_id}/verify/{payment_reference}")
async def verify_patient_medical_report_payment(
    request_id: str,
    payment_reference: str,
    session: dict = Depends(require_patient),
):
    return await verify_current_patient_medical_report_payment(
        str(session["user_id"]),
        request_id,
        payment_reference,
    )


@router.put("/me", response_model=PatientLookupResponse)
def update_current_patient(payload: PatientAccountUpdateRequest, session: dict = Depends(require_patient)):
    return update_patient_account(str(session["user_id"]), payload.model_dump())


@router.post("/me/password")
def change_current_patient_password(
    payload: PatientPasswordChangeRequest,
    session: dict = Depends(require_patient),
):
    return change_patient_password(str(session["user_id"]), payload.current_password, payload.new_password)


@router.post("/support/ai")
def patient_support_ai(payload: PatientSupportAiRequest, session: dict = Depends(require_patient)):
    return answer_patient_support_message(str(session["user_id"]), payload.message, payload.escalate, payload.history)


@router.get("/support-tickets/{ticket_id}")
def patient_support_ticket(ticket_id: str, session: dict = Depends(require_patient)):
    ticket = get_support_ticket(ticket_id, patient_id=str(session["user_id"]))
    if not ticket:
        raise HTTPException(status_code=404, detail="Support ticket could not be found.")
    mark_support_ticket_messages_read(ticket_id, "patient")
    return ticket


@router.post("/support-tickets/{ticket_id}/messages")
def patient_support_ticket_message(
    ticket_id: str,
    payload: PatientSupportTicketMessageRequest,
    session: dict = Depends(require_patient),
):
    result = add_support_ticket_message(
        ticket_id,
        sender_role="patient",
        sender_id=session["user_id"],
        message_text=payload.message_text,
        patient_id=str(session["user_id"]),
    )
    if not result["sent"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.post("/support-tickets/{ticket_id}/feedback")
def patient_support_ticket_feedback(
    ticket_id: str,
    payload: PatientSupportTicketFeedbackRequest,
    session: dict = Depends(require_patient),
):
    result = submit_support_ticket_feedback(
        ticket_id,
        patient_id=str(session["user_id"]),
        rating=payload.rating,
        review=payload.review,
        skipped=payload.skipped,
    )
    if not result["saved"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result
