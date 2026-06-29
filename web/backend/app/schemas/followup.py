from pydantic import BaseModel, EmailStr


class FollowUpItemResponse(BaseModel):
    appointment_id: str
    short_reference: str
    consultation_id: str
    patient_id: str
    doctor_id: str
    scheduled_for: str
    notes: str
    status: str
    payment_status: str
    payment_reference: str | None = None
    payment_token: str | None = None
    confirmed_at: str | None = None
    created_at: str
    reminder_sent_at: str | None = None


class FollowUpListResponse(BaseModel):
    found: bool
    message: str
    appointments: list[FollowUpItemResponse]


class FollowUpDetailResponse(BaseModel):
    found: bool
    message: str
    appointment: FollowUpItemResponse | None = None


class FollowUpBookingRequest(BaseModel):
    scheduled_date: str
    scheduled_time: str
    notes: str = ""


class FollowUpBookingResponse(BaseModel):
    created: bool
    message: str
    appointment: FollowUpItemResponse | None = None


class FollowUpPaymentInitializeRequest(BaseModel):
    email: EmailStr | None = None


class FollowUpPaymentInitializeResponse(BaseModel):
    initialized: bool
    message: str
    appointment: FollowUpItemResponse | None = None
    reference: str | None = None
    authorization_url: str | None = None
    access_code: str | None = None
    amount: int | None = None
    currency: str | None = None
    label: str | None = None


class FollowUpPaymentCodeRequest(BaseModel):
    payment_code: str


class FollowUpPaymentActionResponse(BaseModel):
    success: bool
    message: str
    appointment: FollowUpItemResponse | None = None


class FollowUpPaymentVerifyResponse(BaseModel):
    verified: bool
    message: str
    appointment: FollowUpItemResponse | None = None
    payment_reference: str | None = None
    paystack_status: str | None = None
