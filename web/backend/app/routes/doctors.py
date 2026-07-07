import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from ..deps import require_doctor
from ..schemas.doctor import (
    DoctorAccountResponse,
    DoctorAccountUpdateRequest,
    DoctorAttachmentRequest,
    DoctorCallAcceptRequest,
    DoctorCallCandidateRequest,
    DoctorCallResponse,
    DoctorCallStartRequest,
    DoctorDocumentResponse,
    DoctorEndChatRequest,
    DoctorHistorySaveRequest,
    DoctorHistorySaveResponse,
    DoctorInvestigationRequest,
    DoctorInternalMessageRequest,
    DoctorMedicalReportRequest,
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
    create_doctor_medical_report,
    create_doctor_prescription,
    end_doctor_call_session,
    end_doctor_chat,
    accept_doctor_call,
    add_doctor_call_candidate,
    get_doctor_account,
    get_doctor_transcript,
    get_doctor_workspace,
    reject_doctor_call,
    save_doctor_history_note,
    send_doctor_message,
    send_doctor_attachment,
    start_doctor_call,
    update_doctor_account,
    update_doctor_presence,
)
from ..services.auth_service import decode_token
from ..services.chat_realtime_service import realtime_hub
from ..services.internal_mail_service import (
    list_internal_messages,
    list_message_admins,
    list_message_doctors,
    mark_internal_message_read,
    send_internal_message,
)

router = APIRouter()


def require_doctor_stream_token(token: str = Query(default="")) -> dict:
    if not token:
        raise HTTPException(status_code=401, detail="Authorization token is required.")
    session = decode_token(token)
    if session.get("role") != "doctor":
        raise HTTPException(status_code=403, detail="Doctor access is required.")
    return session


@router.get("/mail")
def doctor_mail(session: dict = Depends(require_doctor)):
    return {
        "messages": list_internal_messages("doctor", session["user_id"]),
        "doctors": [
            doctor for doctor in list_message_doctors()
            if int(doctor["telegram_id"]) != int(session["user_id"])
        ],
        "admins": list_message_admins(),
    }


@router.post("/mail")
def doctor_send_mail(payload: DoctorInternalMessageRequest, session: dict = Depends(require_doctor)):
    return send_internal_message(
        sender_role="doctor",
        sender_id=session["user_id"],
        recipient_role=payload.recipient_role if payload.recipient_role in {"doctor", "admin"} else "doctor",
        recipient_id=payload.recipient_id,
        subject=payload.subject,
        body=payload.body,
    )


@router.post("/mail/{message_id}/read")
def doctor_read_mail(message_id: int, session: dict = Depends(require_doctor)):
    return {
        "updated": mark_internal_message_read(
            message_id,
            "doctor",
            session["user_id"],
        )
    }


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


@router.get("/transcript/stream")
async def doctor_transcript_stream(session: dict = Depends(require_doctor_stream_token)):
    async def event_generator():
        previous_payload = None
        while True:
            payload = json.dumps(get_doctor_transcript(session["user_id"]))
            if payload != previous_payload:
                yield f"data: {payload}\n\n"
                previous_payload = payload
            await asyncio.sleep(2)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.websocket("/transcript/ws")
async def doctor_transcript_websocket(websocket: WebSocket, token: str = Query(default="")):
    if not token:
        await websocket.close(code=1008)
        return
    try:
        session = decode_token(token)
    except HTTPException:
        await websocket.close(code=1008)
        return
    if session.get("role") != "doctor":
        await websocket.close(code=1008)
        return

    transcript = get_doctor_transcript(session["user_id"])
    consultation_id = transcript.get("consultation_id")
    if not consultation_id:
        await websocket.close(code=1008)
        return

    await realtime_hub.connect(consultation_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        realtime_hub.disconnect(consultation_id, websocket)


@router.post("/message", response_model=DoctorMessageResponse)
async def doctor_message(payload: DoctorMessageRequest, session: dict = Depends(require_doctor)):
    return await send_doctor_message(session["user_id"], payload.message_text)


@router.post("/attachment", response_model=DoctorMessageResponse)
async def doctor_attachment(payload: DoctorAttachmentRequest, session: dict = Depends(require_doctor)):
    return await send_doctor_attachment(session["user_id"], payload.filename, payload.content_type, payload.data)


@router.post("/call/start", response_model=DoctorCallResponse)
def doctor_call_start(payload: DoctorCallStartRequest, session: dict = Depends(require_doctor)):
    return start_doctor_call(session["user_id"], payload.call_type, payload.offer_sdp)


@router.post("/call/accept", response_model=DoctorCallResponse)
def doctor_call_accept(payload: DoctorCallAcceptRequest, session: dict = Depends(require_doctor)):
    return accept_doctor_call(session["user_id"], payload.answer_sdp)


@router.post("/call/reject", response_model=DoctorCallResponse)
def doctor_call_reject(session: dict = Depends(require_doctor)):
    return reject_doctor_call(session["user_id"])


@router.post("/call/candidate", response_model=DoctorCallResponse)
def doctor_call_candidate(payload: DoctorCallCandidateRequest, session: dict = Depends(require_doctor)):
    return add_doctor_call_candidate(session["user_id"], payload.candidate)


@router.post("/call/end", response_model=DoctorCallResponse)
def doctor_call_end(session: dict = Depends(require_doctor)):
    return end_doctor_call_session(session["user_id"])


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


@router.post("/medical-report", response_model=DoctorDocumentResponse)
async def doctor_medical_report(payload: DoctorMedicalReportRequest, session: dict = Depends(require_doctor)):
    return await create_doctor_medical_report(
        session["user_id"],
        diagnosis=payload.diagnosis,
        report_note=payload.report_note,
        request_id=payload.request_id,
    )


@router.post("/history", response_model=DoctorHistorySaveResponse)
def doctor_history(payload: DoctorHistorySaveRequest, session: dict = Depends(require_doctor)):
    return save_doctor_history_note(session["user_id"], notes=payload.notes)
