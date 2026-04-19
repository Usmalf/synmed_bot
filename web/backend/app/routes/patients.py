from fastapi import APIRouter, Depends, Query

from ..deps import require_patient
from ..schemas.patient import (
    PatientAccountUpdateRequest,
    PatientHistoryResponse,
    PatientLookupResponse,
    PatientPasswordChangeRequest,
    PatientRegistrationRequest,
    PatientRegistrationResponse,
)
from ..services.patient_app_service import (
    change_patient_password,
    lookup_current_patient_documents,
    lookup_patient,
    lookup_patient_history,
    register_web_patient,
    update_patient_account,
)

router = APIRouter()


@router.get("/lookup", response_model=PatientLookupResponse)
def lookup_patient_route(identifier: str = Query(..., min_length=1)):
    return lookup_patient(identifier)


@router.post("/register", response_model=PatientRegistrationResponse)
def register_patient_route(payload: PatientRegistrationRequest):
    return register_web_patient(payload.model_dump())


@router.get("/me")
def current_patient(session: dict = Depends(require_patient)):
    return lookup_patient(session["user_id"])


@router.get("/history", response_model=PatientHistoryResponse)
def current_patient_history(session: dict = Depends(require_patient)):
    return lookup_patient_history(session["user_id"])


@router.get("/documents")
def current_patient_documents(session: dict = Depends(require_patient)):
    return lookup_current_patient_documents(str(session["user_id"]))


@router.put("/me", response_model=PatientLookupResponse)
def update_current_patient(payload: PatientAccountUpdateRequest, session: dict = Depends(require_patient)):
    return update_patient_account(str(session["user_id"]), payload.model_dump())


@router.post("/me/password")
def change_current_patient_password(
    payload: PatientPasswordChangeRequest,
    session: dict = Depends(require_patient),
):
    return change_patient_password(str(session["user_id"]), payload.current_password, payload.new_password)
