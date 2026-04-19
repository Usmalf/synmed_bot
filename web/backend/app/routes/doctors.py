from fastapi import APIRouter, Depends

from ..deps import require_doctor
from ..schemas.doctor import (
    DoctorAccountResponse,
    DoctorAccountUpdateRequest,
    DoctorDocumentResponse,
    DoctorEndChatRequest,
    DoctorInvestigationRequest,
    DoctorMessageRequest,
    DoctorMessageResponse,
    DoctorPasswordChangeRequest,
    DoctorPresenceRequest,
    DoctorPrescriptionRequest,
    DoctorQueueConnectRequest,
    DoctorTranscriptResponse,
    DoctorWorkspaceResponse,
)
from ..services.doctor_app_service import (
    change_doctor_password,
    connect_doctor_to_selected_patient,
    create_doctor_investigation,
    create_doctor_prescription,
    end_doctor_chat,
    get_doctor_account,
    get_doctor_transcript,
    get_doctor_workspace,
    send_doctor_message,
    update_doctor_account,
    update_doctor_presence,
)

router = APIRouter()


@router.get("/me", response_model=DoctorAccountResponse)
def doctor_account(session: dict = Depends(require_doctor)):
    return get_doctor_account(session["user_id"])


@router.put("/me", response_model=DoctorAccountResponse)
def update_doctor_account_route(payload: DoctorAccountUpdateRequest, session: dict = Depends(require_doctor)):
    return update_doctor_account(session["user_id"], payload.model_dump())


@router.post("/me/password")
def change_doctor_password_route(payload: DoctorPasswordChangeRequest, session: dict = Depends(require_doctor)):
    return change_doctor_password(session["user_id"], payload.current_password, payload.new_password)


@router.get("/workspace", response_model=DoctorWorkspaceResponse)
def doctor_workspace(session: dict = Depends(require_doctor)):
    return get_doctor_workspace(session["user_id"])


@router.post("/presence", response_model=DoctorWorkspaceResponse)
def doctor_presence(payload: DoctorPresenceRequest, session: dict = Depends(require_doctor)):
    return update_doctor_presence(session["user_id"], payload.action)


@router.post("/connect", response_model=DoctorWorkspaceResponse)
def doctor_connect(payload: DoctorQueueConnectRequest, session: dict = Depends(require_doctor)):
    return connect_doctor_to_selected_patient(session["user_id"], payload.runtime_patient_id)


@router.get("/transcript", response_model=DoctorTranscriptResponse)
def doctor_transcript(session: dict = Depends(require_doctor)):
    return get_doctor_transcript(session["user_id"])


@router.post("/message", response_model=DoctorMessageResponse)
async def doctor_message(payload: DoctorMessageRequest, session: dict = Depends(require_doctor)):
    return await send_doctor_message(session["user_id"], payload.message_text)


@router.post("/end-chat", response_model=DoctorWorkspaceResponse)
async def doctor_end_chat(payload: DoctorEndChatRequest, session: dict = Depends(require_doctor)):
    return await end_doctor_chat(session["user_id"])


@router.post("/prescription", response_model=DoctorDocumentResponse)
async def doctor_prescription(payload: DoctorPrescriptionRequest, session: dict = Depends(require_doctor)):
    return await create_doctor_prescription(
        session["user_id"],
        diagnosis=payload.diagnosis,
        medications_text=payload.medications_text,
        notes=payload.notes,
    )


@router.post("/investigation", response_model=DoctorDocumentResponse)
async def doctor_investigation(payload: DoctorInvestigationRequest, session: dict = Depends(require_doctor)):
    return await create_doctor_investigation(
        session["user_id"],
        diagnosis=payload.diagnosis,
        tests_text=payload.tests_text,
        notes=payload.notes,
    )
