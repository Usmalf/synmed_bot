from pydantic import BaseModel


class DoctorLoginRequest(BaseModel):
    identifier: str
    password: str
    otp_channel: str = "telegram"


class DoctorSignupRequest(BaseModel):
    identifier: str
    email: str
    password: str
    otp_channel: str = "telegram"


class DoctorSignupVerifyRequest(BaseModel):
    identifier: str
    otp_code: str


class DoctorLoginVerifyRequest(BaseModel):
    identifier: str
    otp_code: str


class DoctorRecoveryRequest(BaseModel):
    identifier: str
    email: str
    new_password: str
    otp_channel: str = "email"


class DoctorRecoveryVerifyRequest(BaseModel):
    identifier: str
    otp_code: str


class AdminLoginRequest(BaseModel):
    admin_id: int


class PatientLoginRequest(BaseModel):
    identifier: str
    password: str
    otp_channel: str = "email"


class PatientLoginVerifyRequest(BaseModel):
    identifier: str
    otp_code: str


class PatientRecoveryRequest(BaseModel):
    identifier: str
    email: str
    new_password: str


class PatientRecoveryVerifyRequest(BaseModel):
    identifier: str
    otp_code: str


class GenericSuccessResponse(BaseModel):
    success: bool
    message: str


class OtpRequest(BaseModel):
    role: str
    user_id: int | None = None
    hospital_number: str | None = None
    email: str | None = None


class OtpVerifyRequest(BaseModel):
    role: str
    user_id: int | None = None
    hospital_number: str | None = None
    email: str | None = None
    otp_code: str


class SessionUserResponse(BaseModel):
    role: str
    user_id: int | str
    display_name: str


class SessionResponse(BaseModel):
    authenticated: bool
    token: str | None = None
    user: SessionUserResponse | None = None
    message: str


class OtpResponse(BaseModel):
    success: bool
    message: str
    expires_in_seconds: int | None = None
    delivery_target: str | None = None
    debug_code: str | None = None


class DeliveryChannelStatus(BaseModel):
    ready: bool
    label: str
    message: str


class DeliveryStatusResponse(BaseModel):
    telegram: DeliveryChannelStatus
    email: DeliveryChannelStatus
    dev_debug_code_visible: bool
