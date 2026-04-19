from pydantic import BaseModel


class DoctorWorkspaceResponse(BaseModel):
    found: bool
    message: str
    doctor: dict | None = None
    queue: list[dict] = []
    active_consultation: dict | None = None


class DoctorPresenceRequest(BaseModel):
    doctor_id: int
    action: str


class DoctorQueueConnectRequest(BaseModel):
    runtime_patient_id: int


class DoctorMessageRequest(BaseModel):
    doctor_id: int
    message_text: str


class DoctorTranscriptResponse(BaseModel):
    found: bool
    message: str
    consultation_id: str | None = None
    transcript: list[dict] = []


class DoctorMessageResponse(BaseModel):
    sent: bool
    message: str
    consultation_id: str | None = None
    transcript: list[dict] = []


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


class DoctorAccountUpdateRequest(BaseModel):
    name: str
    specialty: str
    experience: str
    email: str
    license_id: str
    license_expiry_date: str = ""


class DoctorPasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str


class DoctorAccountResponse(BaseModel):
    found: bool
    message: str
    doctor: dict | None = None
