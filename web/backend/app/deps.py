from fastapi import Depends, Header, HTTPException

from .services.auth_service import decode_token


def get_current_session(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization token is required.")
    token = authorization.split(" ", 1)[1]
    return decode_token(token)


def require_doctor(session: dict = Depends(get_current_session)) -> dict:
    if session.get("role") != "doctor":
        raise HTTPException(status_code=403, detail="Doctor access is required.")
    return session


def require_admin(session: dict = Depends(get_current_session)) -> dict:
    if session.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access is required.")
    return session


def require_patient(session: dict = Depends(get_current_session)) -> dict:
    if session.get("role") != "patient":
        raise HTTPException(status_code=403, detail="Patient access is required.")
    return session
