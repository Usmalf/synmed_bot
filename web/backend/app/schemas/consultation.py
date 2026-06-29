from pydantic import BaseModel, Field


class ConsultationRequest(BaseModel):
    reference: str
    symptoms: str = Field(..., min_length=3)


class ConsultationRequestResponse(BaseModel):
    submitted: bool
    message: str
    status: str
    consultation_id: str | None = None
    doctor: dict | None = None
    patient: dict | None = None
    emergency: dict | None = None
    call: dict | None = None


class ConsultationMessageRequest(BaseModel):
    reference: str
    message_text: str = Field(..., min_length=1)


class ConsultationAttachmentRequest(BaseModel):
    reference: str
    filename: str
    content_type: str = "application/octet-stream"
    data: str = Field(..., min_length=1)


class ConsultationMessageResponse(BaseModel):
    sent: bool
    message: str
    consultation_id: str | None = None
    transcript: list[dict] | None = None
    call: dict | None = None


class ConsultationTranscriptResponse(BaseModel):
    found: bool
    message: str
    consultation_id: str | None = None
    status: str | None = None
    transcript: list[dict] = []
    call: dict | None = None


class ConsultationDocumentListResponse(BaseModel):
    found: bool
    message: str
    consultation_id: str | None = None
    documents: list[dict] = []
    call: dict | None = None


class ConsultationEndRequest(BaseModel):
    reference: str


class ConsultationEndResponse(BaseModel):
    ended: bool
    message: str
    consultation_id: str | None = None
    doctor: dict | None = None


class ConsultationCallStartRequest(BaseModel):
    reference: str
    call_type: str
    offer_sdp: dict


class ConsultationCallAcceptRequest(BaseModel):
    reference: str
    answer_sdp: dict


class ConsultationCallCandidateRequest(BaseModel):
    reference: str
    candidate: dict


class ConsultationCallResponse(BaseModel):
    ok: bool
    message: str
    consultation_id: str | None = None
    call: dict | None = None


class ConsultationFeedbackRequest(BaseModel):
    reference: str
    rating: int = Field(..., ge=1, le=5)
    review: str = ""


class ConsultationFeedbackResponse(BaseModel):
    saved: bool
    message: str
    consultation_id: str | None = None
