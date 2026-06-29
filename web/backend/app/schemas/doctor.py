from pydantic import BaseModel


class DoctorWorkspaceResponse(BaseModel):
    found: bool
    message: str
    doctor: dict | None = None
    queue: list[dict] = []
    active_consultation: dict | None = None
    medical_report_requests: list[dict] = []
    call: dict | None = None


class DoctorPresenceRequest(BaseModel):
    doctor_id: int
    action: str


class DoctorQueueConnectRequest(BaseModel):
    runtime_patient_id: int


class DoctorMessageRequest(BaseModel):
    doctor_id: int
    message_text: str


class DoctorAttachmentRequest(BaseModel):
    filename: str
    content_type: str = "application/octet-stream"
    data: str


class DoctorTranscriptResponse(BaseModel):
    found: bool
    message: str
    consultation_id: str | None = None
    transcript: list[dict] = []
    call: dict | None = None


class DoctorMessageResponse(BaseModel):
    sent: bool
    message: str
    consultation_id: str | None = None
    transcript: list[dict] = []
    call: dict | None = None


class DoctorEndChatRequest(BaseModel):
    doctor_id: int


class DoctorPrescriptionRequest(BaseModel):
    diagnosis: str
    medications_text: str
    notes: str = ""


class DoctorInvestigationRequest(BaseModel):
    diagnosis: str
    tests_text: str
    notes: str = ""


class DoctorMedicalReportRequest(BaseModel):
    diagnosis: str
    report_note: str
    request_id: str | None = None


class DoctorHistorySaveRequest(BaseModel):
    notes: str = ""


class DoctorDocumentResponse(BaseModel):
    created: bool
    message: str
    consultation_id: str | None = None
    filename: str | None = None
    asset_url: str | None = None
    asset_type: str | None = None
    delivered_to_patient: bool = False
    document_kind: str | None = None
    preview_text: str | None = None


class DoctorHistorySaveResponse(BaseModel):
    saved: bool
    message: str
    consultation_id: str | None = None
    notes: str = ""


class DoctorCallStartRequest(BaseModel):
    call_type: str
    offer_sdp: dict


class DoctorCallAcceptRequest(BaseModel):
    answer_sdp: dict


class DoctorCallCandidateRequest(BaseModel):
    candidate: dict


class DoctorCallResponse(BaseModel):
    ok: bool
    message: str
    consultation_id: str | None = None
    call: dict | None = None


class DoctorAccountUpdateRequest(BaseModel):
    name: str
    specialty: str
    experience: str
    email: str
    license_id: str
    license_expiry_date: str = ""
    license_file_name: str | None = None
    license_file_type: str | None = None
    license_file_data: str | None = None
    license_file_size: int | None = None


class DoctorPasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str


class DoctorAccountResponse(BaseModel):
    found: bool
    message: str
    doctor: dict | None = None


class DoctorInternalMessageRequest(BaseModel):
    recipient_role: str = "doctor"
    recipient_id: int
    subject: str
    body: str = ""
