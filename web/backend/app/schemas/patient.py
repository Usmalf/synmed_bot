from pydantic import BaseModel, EmailStr


class PatientLookupResponse(BaseModel):
    found: bool
    message: str
    patient: dict | None = None


class PatientRegistrationRequest(BaseModel):
    name: str
    age: int
    gender: str
    phone: str
    address: str
    allergy: str = ""
    medical_conditions: str = ""
    email: EmailStr | None = None
    password: str
    signup_otp_code: str


class PatientRegistrationResponse(BaseModel):
    created: bool
    message: str
    patient: dict | None = None


class PatientHistoryResponse(BaseModel):
    found: bool
    message: str
    history: dict | None = None


class PatientAccountUpdateRequest(BaseModel):
    name: str
    age: int
    gender: str
    phone: str
    email: EmailStr | None = None
    address: str = ""
    allergy: str = ""
    medical_conditions: str = ""


class PatientPasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str
