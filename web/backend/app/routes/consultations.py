import asyncio

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ..schemas.consultation import (
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
    end_patient_consultation,
    get_consultation_documents,
    get_consultation_transcript,
    get_consultation_status,
    send_patient_message,
    submit_consultation_feedback,
    submit_consultation_request,
)

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
