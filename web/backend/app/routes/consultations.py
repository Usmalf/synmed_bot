import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from ..schemas.consultation import (
    ConsultationCallAcceptRequest,
    ConsultationAttachmentRequest,
    ConsultationCallCandidateRequest,
    ConsultationCallResponse,
    ConsultationCallStartRequest,
    ConsultationDocumentListResponse,
    ConsultationEndRequest,
    ConsultationEndResponse,
    ConsultationFeedbackRequest,
    ConsultationFeedbackResponse,
    ConsultationMessageRequest,
    ConsultationMessageResponse,
    ConsultationRequest,
    ConsultationRequestResponse,
    ConsultationTranscriptResponse,
)
from ..services.consultation_app_service import (
    consultation_live_snapshot_json,
    end_patient_call_session,
    end_patient_consultation,
    accept_patient_call,
    add_patient_call_candidate,
    get_consultation_documents,
    get_consultation_transcript,
    get_consultation_status,
    send_patient_message,
    send_patient_attachment,
    start_patient_call,
    reject_patient_call,
    submit_consultation_feedback,
    submit_consultation_request,
)
from ..services.chat_realtime_service import realtime_hub

router = APIRouter()


@router.post("/request", response_model=ConsultationRequestResponse)
async def request_consultation(payload: ConsultationRequest):
    return await submit_consultation_request(payload.reference, payload.symptoms)


@router.get("/status/{reference}", response_model=ConsultationRequestResponse)
def consultation_status(reference: str):
    return get_consultation_status(reference)


@router.get("/transcript/{reference}", response_model=ConsultationTranscriptResponse)
def consultation_transcript(reference: str):
    return get_consultation_transcript(reference)


@router.get("/documents/{reference}", response_model=ConsultationDocumentListResponse)
def consultation_documents(reference: str):
    return get_consultation_documents(reference)


@router.post("/message", response_model=ConsultationMessageResponse)
async def consultation_message(payload: ConsultationMessageRequest):
    return await send_patient_message(payload.reference, payload.message_text)


@router.post("/attachment", response_model=ConsultationMessageResponse)
async def consultation_attachment(payload: ConsultationAttachmentRequest):
    return await send_patient_attachment(payload.reference, payload.filename, payload.content_type, payload.data)


@router.post("/call/start", response_model=ConsultationCallResponse)
def consultation_call_start(payload: ConsultationCallStartRequest):
    return start_patient_call(payload.reference, payload.call_type, payload.offer_sdp)


@router.post("/call/accept", response_model=ConsultationCallResponse)
def consultation_call_accept(payload: ConsultationCallAcceptRequest):
    return accept_patient_call(payload.reference, payload.answer_sdp)


@router.post("/call/reject", response_model=ConsultationCallResponse)
def consultation_call_reject(payload: ConsultationEndRequest):
    return reject_patient_call(payload.reference)


@router.post("/call/candidate", response_model=ConsultationCallResponse)
def consultation_call_candidate(payload: ConsultationCallCandidateRequest):
    return add_patient_call_candidate(payload.reference, payload.candidate)


@router.post("/call/end", response_model=ConsultationCallResponse)
def consultation_call_end(payload: ConsultationEndRequest):
    return end_patient_call_session(payload.reference)


@router.post("/end", response_model=ConsultationEndResponse)
async def consultation_end(payload: ConsultationEndRequest):
    return await end_patient_consultation(payload.reference)


@router.post("/feedback", response_model=ConsultationFeedbackResponse)
def consultation_feedback(payload: ConsultationFeedbackRequest):
    return submit_consultation_feedback(payload.reference, payload.rating, payload.review)


@router.get("/stream/{reference}")
async def consultation_stream(reference: str):
    async def event_generator():
        previous_payload = None
        while True:
            payload = consultation_live_snapshot_json(reference)
            if payload != previous_payload:
                yield f"data: {payload}\n\n"
                previous_payload = payload
            await asyncio.sleep(2)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.websocket("/ws/{reference}")
async def consultation_websocket(websocket: WebSocket, reference: str):
    status = get_consultation_status(reference)
    consultation_id = status.get("consultation_id")
    if not consultation_id:
        await websocket.close(code=1008)
        return

    await realtime_hub.connect(consultation_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        realtime_hub.disconnect(consultation_id, websocket)
