from typing import Literal

from pydantic import BaseModel, EmailStr


class PaymentConfigResponse(BaseModel):
    currency: str
    new_patient_fee: int
    returning_patient_fee: int
    new_patient_label: str
    returning_patient_label: str


class PaymentInitializeRequest(BaseModel):
    email: EmailStr
    patient_type: Literal["new", "returning"]
    patient_id: str | None = None
    registration_payload: dict | None = None


class PaymentInitializeResponse(BaseModel):
    initialized: bool
    message: str
    reference: str | None = None
    authorization_url: str | None = None
    access_code: str | None = None
    amount: int | None = None
    currency: str | None = None
    label: str | None = None


class PaymentVerifyResponse(BaseModel):
    verified: bool
    message: str
    reference: str
    paystack_status: str | None = None
    amount: int | None = None
    currency: str | None = None
    patient: dict | None = None
    requires_email_verification: bool = False
    verification_delivery: str | None = None


class CurrentPaymentStatusResponse(BaseModel):
    active: bool
    message: str
    payment: dict | None = None
