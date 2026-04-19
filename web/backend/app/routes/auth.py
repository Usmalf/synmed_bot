from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from ..deps import get_current_session
from ..schemas.auth import (
    AdminLoginRequest,
    DeliveryStatusResponse,
    DoctorLoginRequest,
    DoctorLoginVerifyRequest,
    DoctorRecoveryRequest,
    DoctorRecoveryVerifyRequest,
    DoctorSignupRequest,
    DoctorSignupVerifyRequest,
    GenericSuccessResponse,
    OtpRequest,
    OtpResponse,
    OtpVerifyRequest,
    PatientLoginRequest,
    PatientLoginVerifyRequest,
    PatientRecoveryRequest,
    PatientRecoveryVerifyRequest,
    SessionResponse,
)
from ..services.auth_service import (
    build_session_response,
    get_delivery_status,
    login_admin,
    login_doctor,
    login_patient,
    request_doctor_recovery,
    request_doctor_signup,
    request_otp,
    request_patient_recovery,
    verify_doctor_login,
    verify_doctor_recovery,
    verify_doctor_signup,
    verify_otp,
    verify_patient_email_link,
    verify_patient_login,
    verify_patient_recovery,
)


router = APIRouter()


@router.post("/doctor/login", response_model=OtpResponse)
def doctor_login(payload: DoctorLoginRequest):
    return login_doctor(payload.identifier, payload.password, payload.otp_channel)


@router.post("/doctor/login/verify", response_model=SessionResponse)
def doctor_login_verify(payload: DoctorLoginVerifyRequest):
    return verify_doctor_login(payload.identifier, payload.otp_code)


@router.post("/doctor/signup", response_model=OtpResponse)
def doctor_signup(payload: DoctorSignupRequest):
    return request_doctor_signup(payload.identifier, payload.email, payload.password, payload.otp_channel)


@router.post("/doctor/signup/verify", response_model=GenericSuccessResponse)
def doctor_signup_verify(payload: DoctorSignupVerifyRequest):
    return verify_doctor_signup(payload.identifier, payload.otp_code)


@router.post("/doctor/recovery/request", response_model=OtpResponse)
def doctor_recovery_request(payload: DoctorRecoveryRequest):
    return request_doctor_recovery(payload.identifier, payload.email, payload.new_password, payload.otp_channel)


@router.post("/doctor/recovery/verify", response_model=GenericSuccessResponse)
def doctor_recovery_verify(payload: DoctorRecoveryVerifyRequest):
    return verify_doctor_recovery(payload.identifier, payload.otp_code)


@router.post("/admin/login", response_model=SessionResponse)
def admin_login(payload: AdminLoginRequest):
    return login_admin(payload.admin_id)


@router.post("/patient/login", response_model=OtpResponse)
def patient_login(payload: PatientLoginRequest):
    return login_patient(payload.identifier, payload.password, payload.otp_channel)


@router.post("/patient/login/verify", response_model=SessionResponse)
def patient_login_verify(payload: PatientLoginVerifyRequest):
    return verify_patient_login(payload.identifier, payload.otp_code)


@router.post("/patient/recovery/request", response_model=OtpResponse)
def patient_recovery_request(payload: PatientRecoveryRequest):
    return request_patient_recovery(payload.identifier, payload.email, payload.new_password)


@router.post("/patient/recovery/verify", response_model=GenericSuccessResponse)
def patient_recovery_verify(payload: PatientRecoveryVerifyRequest):
    return verify_patient_recovery(payload.identifier, payload.otp_code)


@router.get("/verify-email", response_class=HTMLResponse)
def verify_email_link(hospital_number: str, token: str):
    result = verify_patient_email_link(hospital_number, token)
    return HTMLResponse(
        f"""
        <html>
          <head><title>SynMed Email Verification</title></head>
          <body style="font-family:Segoe UI,Tahoma,sans-serif;padding:40px;background:#07141a;color:#e9f3f7;">
            <div style="max-width:620px;margin:0 auto;background:#10222b;border:1px solid #24414d;border-radius:20px;padding:32px;">
              <h1 style="margin-top:0;">SynMed Email Verification</h1>
              <p>{result["message"]}</p>
              <p>You can now return to the website and sign in.</p>
            </div>
          </body>
        </html>
        """
    )


@router.post("/request-otp", response_model=OtpResponse)
def auth_request_otp(payload: OtpRequest):
    return request_otp(
        payload.role,
        user_id=payload.user_id,
        hospital_number=payload.hospital_number,
        email=payload.email,
    )


@router.post("/verify-otp", response_model=SessionResponse)
def auth_verify_otp(payload: OtpVerifyRequest):
    return verify_otp(
        payload.role,
        otp_code=payload.otp_code,
        user_id=payload.user_id,
        hospital_number=payload.hospital_number,
        email=payload.email,
    )


@router.get("/session", response_model=SessionResponse)
def auth_session(session: dict = Depends(get_current_session)):
    return build_session_response(session["role"], session["user_id"]) | {
        "message": "Session restored successfully."
    }


@router.get("/delivery-status", response_model=DeliveryStatusResponse)
def auth_delivery_status():
    return get_delivery_status()
