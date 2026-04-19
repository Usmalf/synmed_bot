import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
import smtplib
import time
from email.message import EmailMessage

from fastapi import HTTPException
import httpx

from database import get_connection
from synmed_utils.admin import is_admin
from synmed_utils.doctor_profiles import create_or_update_profile, doctor_profiles, get_profile_by_identifier
from synmed_utils.verified_doctors import is_verified
from services.patient_records import get_patient_by_identifier


TOKEN_TTL_SECONDS = 60 * 60 * 12
OTP_TTL_SECONDS = 60 * 10
EMAIL_VERIFY_TTL_SECONDS = 60 * 60 * 24
UTC = timezone.utc


def _secret_key() -> str:
    return os.getenv("AUTH_SECRET_KEY") or os.getenv("BOT_TOKEN") or "synmed-dev-secret"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _future_iso(seconds: int) -> str:
    return (datetime.now(UTC) + timedelta(seconds=seconds)).isoformat()


def _sign(payload: str) -> str:
    digest = hmac.new(_secret_key().encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")


def _otp_hash(value: str) -> str:
    return hmac.new(_secret_key().encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()


def _password_hash(value: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256",
        value.encode("utf-8"),
        _secret_key().encode("utf-8"),
        120000,
    ).hex()


def _issue_otp_code() -> str:
    seed = f"{time.time_ns()}"[-6:]
    return seed.zfill(6)


def _issue_link_token() -> str:
    return base64.urlsafe_b64encode(os.urandom(24)).decode("utf-8").rstrip("=")


def issue_token(*, role: str, user_id: int) -> str:
    payload = {
        "role": role,
        "user_id": user_id,
        "exp": int(time.time()) + TOKEN_TTL_SECONDS,
    }
    encoded_payload = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8").rstrip("=")
    signature = _sign(encoded_payload)
    return f"{encoded_payload}.{signature}"


def decode_token(token: str) -> dict:
    try:
        encoded_payload, signature = token.split(".", 1)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid token format.") from exc

    expected_signature = _sign(encoded_payload)
    if not hmac.compare_digest(signature, expected_signature):
        raise HTTPException(status_code=401, detail="Invalid token signature.")

    padded_payload = encoded_payload + "=" * (-len(encoded_payload) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(padded_payload).decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid token payload.") from exc

    if payload.get("exp", 0) < int(time.time()):
        raise HTTPException(status_code=401, detail="Session has expired.")

    return payload


def build_session_response(role: str, user_id: int) -> dict:
    if role == "doctor":
        profile = doctor_profiles.get(user_id, {})
        display_name = profile.get("name") or f"Doctor {user_id}"
    elif role == "admin":
        display_name = f"Admin {user_id}"
    elif role == "patient":
        patient = get_patient_by_identifier(str(user_id))
        display_name = patient["name"] if patient else f"Patient {user_id}"
    else:
        display_name = f"User {user_id}"

    return {
        "authenticated": True,
        "token": issue_token(role=role, user_id=user_id),
        "user": {
            "role": role,
            "user_id": user_id,
            "display_name": display_name,
        },
        "message": "Session created successfully.",
    }


def _resolve_doctor_account(identifier: str) -> tuple[int, dict]:
    doctor_id, profile = get_profile_by_identifier(identifier)
    if doctor_id is None or not profile:
        normalized = str(identifier).strip()
        if normalized.isdigit():
            fallback_doctor_id = int(normalized)
            if is_verified(fallback_doctor_id):
                profile = doctor_profiles.get(fallback_doctor_id, {}) or {}
                doctor_id = fallback_doctor_id
            else:
                doctor_id = None
                profile = None
    if doctor_id is None or not is_verified(doctor_id):
        raise HTTPException(status_code=403, detail="Doctor is not verified on SynMed.")
    return doctor_id, profile or doctor_profiles.get(doctor_id, {}) or {}


def _doctor_delivery_target(doctor_id: int, profile: dict, otp_channel: str) -> tuple[str, str]:
    normalized_channel = (otp_channel or "telegram").strip().lower()
    if normalized_channel == "telegram":
        return "telegram", str(doctor_id)
    if normalized_channel == "email":
        email = (profile.get("email") or "").strip().lower()
        if not email:
            raise HTTPException(status_code=400, detail="Doctor account does not have an email address yet.")
        return "email", email
    raise HTTPException(status_code=400, detail="Unsupported OTP channel.")


def _patient_delivery_target(patient: dict, otp_channel: str) -> tuple[str, str]:
    normalized_channel = (otp_channel or "email").strip().lower()
    if normalized_channel == "telegram":
        telegram_id = patient.get("telegram_id")
        if not telegram_id:
            raise HTTPException(status_code=400, detail="No Telegram account is linked to this patient record yet.")
        return "telegram", str(telegram_id)
    if normalized_channel == "email":
        email = (patient.get("email") or "").strip().lower()
        if not email:
            raise HTTPException(status_code=400, detail="No verified email is attached to this patient record yet.")
        return "email", email
    raise HTTPException(status_code=400, detail="Unsupported OTP channel.")


def login_doctor(identifier: str, password: str, otp_channel: str = "telegram") -> dict:
    doctor_id, profile = _resolve_doctor_account(identifier)
    stored_password_hash = profile.get("password_hash") or ""
    if not stored_password_hash or not hmac.compare_digest(stored_password_hash, _password_hash(password)):
        raise HTTPException(status_code=403, detail="Doctor credentials are invalid.")

    channel, delivery_target = _doctor_delivery_target(doctor_id, profile, otp_channel)
    code = _issue_otp_code()
    _store_otp(role="doctor_login", identifier=str(doctor_id), delivery_target=delivery_target, code=code)

    try:
        delivered = _deliver_otp(channel, delivery_target, code)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Unable to send doctor OTP via {channel} right now.") from exc

    if not delivered:
        raise HTTPException(status_code=503, detail=f"Unable to send doctor OTP via {channel} right now.")

    return {
        "success": True,
        "message": f"Doctor OTP sent via {channel}.",
        "expires_in_seconds": OTP_TTL_SECONDS,
        "delivery_target": delivery_target,
        "debug_code": code if _is_debug_otp_visible() else None,
    }


def verify_doctor_login(identifier: str, otp_code: str) -> dict:
    doctor_id, _ = _resolve_doctor_account(identifier)
    _consume_valid_otp(role="doctor_login", identifier=str(doctor_id), otp_code=otp_code)
    return build_session_response("doctor", doctor_id)


def request_doctor_signup(identifier: str, email: str, password: str, otp_channel: str = "telegram") -> dict:
    doctor_id, profile = _resolve_doctor_account(identifier)
    normalized_email = email.strip().lower()
    if not normalized_email:
        raise HTTPException(status_code=400, detail="Email is required.")

    code = _issue_otp_code()
    channel, delivery_target = _doctor_delivery_target(
        doctor_id,
        {**profile, "email": normalized_email},
        otp_channel,
    )
    context_json = json.dumps(
        {
            "email": normalized_email,
            "password_hash": _password_hash(password),
        }
    )
    _store_otp(
        role="doctor_signup",
        identifier=str(doctor_id),
        delivery_target=delivery_target,
        code=code,
        context_json=context_json,
    )

    try:
        delivered = _deliver_otp(channel, delivery_target, code)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Unable to send doctor signup OTP via {channel} right now.") from exc

    if not delivered:
        raise HTTPException(status_code=503, detail=f"Unable to send doctor signup OTP via {channel} right now.")

    return {
        "success": True,
        "message": f"Doctor signup OTP sent via {channel}.",
        "expires_in_seconds": OTP_TTL_SECONDS,
        "delivery_target": delivery_target,
        "debug_code": code if _is_debug_otp_visible() else None,
    }


def verify_doctor_signup(identifier: str, otp_code: str) -> dict:
    doctor_id, profile = _resolve_doctor_account(identifier)
    row = _consume_valid_otp(role="doctor_signup", identifier=str(doctor_id), otp_code=otp_code)
    context = json.loads(row["context_json"] or "{}")
    create_or_update_profile(
        doctor_id,
        {
            **profile,
            "email": (context.get("email") or profile.get("email") or "").strip().lower(),
            "password_hash": context.get("password_hash") or profile.get("password_hash") or "",
            "updated_at": _now_iso(),
            "verified": True,
        },
    )
    return {
        "success": True,
        "message": "Doctor web access activated successfully. You can now sign in.",
    }


def request_doctor_recovery(identifier: str, email: str, new_password: str, otp_channel: str = "email") -> dict:
    doctor_id, profile = _resolve_doctor_account(identifier)
    normalized_email = email.strip().lower()
    if not normalized_email:
        raise HTTPException(status_code=400, detail="Email is required.")

    code = _issue_otp_code()
    channel, delivery_target = _doctor_delivery_target(
        doctor_id,
        {**profile, "email": normalized_email},
        otp_channel,
    )
    context_json = json.dumps(
        {
            "email": normalized_email,
            "password_hash": _password_hash(new_password),
        }
    )
    _store_otp(
        role="doctor_recovery",
        identifier=str(doctor_id),
        delivery_target=delivery_target,
        code=code,
        context_json=context_json,
    )

    try:
        delivered = _deliver_otp(channel, delivery_target, code)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Unable to send doctor recovery OTP via {channel} right now.") from exc

    if not delivered:
        raise HTTPException(status_code=503, detail=f"Unable to send doctor recovery OTP via {channel} right now.")

    return {
        "success": True,
        "message": f"Doctor recovery OTP sent via {channel}.",
        "expires_in_seconds": OTP_TTL_SECONDS,
        "delivery_target": delivery_target,
        "debug_code": code if _is_debug_otp_visible() else None,
    }


def verify_doctor_recovery(identifier: str, otp_code: str) -> dict:
    doctor_id, profile = _resolve_doctor_account(identifier)
    row = _consume_valid_otp(role="doctor_recovery", identifier=str(doctor_id), otp_code=otp_code)
    context = json.loads(row["context_json"] or "{}")
    create_or_update_profile(
        doctor_id,
        {
            **profile,
            "email": (context.get("email") or profile.get("email") or "").strip().lower(),
            "password_hash": context.get("password_hash") or profile.get("password_hash") or "",
            "updated_at": _now_iso(),
            "verified": True,
        },
    )
    return {
        "success": True,
        "message": "Doctor account recovery completed successfully. You can now sign in.",
    }


def login_admin(admin_id: int) -> dict:
    if not is_admin(admin_id):
        raise HTTPException(status_code=403, detail="Admin is not authorized.")
    return build_session_response("admin", admin_id)


def login_patient(identifier: str, password: str, otp_channel: str = "email") -> dict:
    patient = get_patient_by_identifier(identifier)
    if not patient:
        raise HTTPException(status_code=403, detail="Patient credentials are invalid.")
    if not patient.get("email_verified_at"):
        raise HTTPException(status_code=403, detail="Please verify your email address before signing in.")
    stored_password_hash = patient.get("password_hash") or ""
    if not stored_password_hash or not hmac.compare_digest(stored_password_hash, _password_hash(password)):
        raise HTTPException(status_code=403, detail="Patient credentials are invalid.")
    code = _issue_otp_code()
    channel, delivery_target = _patient_delivery_target(patient, otp_channel)
    _store_otp(role="patient_login", identifier=patient["hospital_number"], delivery_target=delivery_target, code=code)

    try:
        delivered = _deliver_otp(channel, delivery_target, code)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Unable to send login OTP via {channel} right now.") from exc

    if not delivered:
        raise HTTPException(status_code=503, detail=f"Unable to send login OTP via {channel} right now.")

    return {
        "success": True,
        "message": f"Login OTP sent via {channel}.",
        "expires_in_seconds": OTP_TTL_SECONDS,
        "delivery_target": delivery_target,
        "debug_code": code if _is_debug_otp_visible() else None,
    }


def verify_patient_login(identifier: str, otp_code: str) -> dict:
    patient = get_patient_by_identifier(identifier)
    if not patient:
        raise HTTPException(status_code=403, detail="Patient credentials are invalid.")
    _consume_valid_otp(role="patient_login", identifier=patient["hospital_number"], otp_code=otp_code)
    return build_session_response("patient", patient["hospital_number"])


def request_patient_recovery(identifier: str, email: str, new_password: str) -> dict:
    patient = get_patient_by_identifier(identifier)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient record was not found.")
    normalized_email = email.strip().lower()
    if not normalized_email:
        raise HTTPException(status_code=400, detail="Email is required.")
    code = _issue_otp_code()
    context_json = json.dumps(
        {
            "email": normalized_email,
            "password_hash": hash_patient_password(new_password),
        }
    )
    _store_otp(
        role="patient_recovery",
        identifier=patient["hospital_number"],
        delivery_target=normalized_email,
        code=code,
        context_json=context_json,
    )

    delivered = False
    try:
        delivered = _deliver_otp("email", normalized_email, code)
    except Exception:
        delivered = False

    return {
        "success": True,
        "message": (
            "Recovery OTP sent to your email."
            if delivered
            else "Recovery OTP generated, but email delivery is not configured correctly yet."
        ),
        "expires_in_seconds": OTP_TTL_SECONDS,
        "delivery_target": normalized_email,
        "debug_code": code if _is_debug_otp_visible() else None,
    }


def verify_patient_recovery(identifier: str, otp_code: str) -> dict:
    patient = get_patient_by_identifier(identifier)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient record was not found.")
    row = _consume_valid_otp(
        role="patient_recovery",
        identifier=patient["hospital_number"],
        otp_code=otp_code,
    )
    context = json.loads(row["context_json"] or "{}")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE patients
            SET email = ?, password_hash = ?, email_verified_at = ?, updated_at = ?
            WHERE patient_id = ?
            """,
            (
                context.get("email") or patient.get("email") or "",
                context.get("password_hash") or patient.get("password_hash") or "",
                _now_iso(),
                _now_iso(),
                patient["hospital_number"],
            ),
        )
        conn.commit()

    return {
        "success": True,
        "message": "Recovery completed successfully. You can now sign in with your password.",
    }


def _resolve_identity(
    role: str,
    *,
    user_id: int | None = None,
    hospital_number: str | None = None,
    email: str | None = None,
) -> tuple[str, str, str]:
    normalized_role = role.strip().lower()
    if normalized_role == "doctor":
        if not user_id or not is_verified(user_id):
            raise HTTPException(status_code=403, detail="Doctor is not verified on SynMed.")
        return str(user_id), str(user_id), "telegram"

    if normalized_role == "admin":
        if not user_id or not is_admin(user_id):
            raise HTTPException(status_code=403, detail="Admin is not authorized.")
        return str(user_id), str(user_id), "telegram"

    if normalized_role == "patient":
        patient = get_patient_by_identifier(hospital_number or "")
        if not patient or (patient.get("email") or "").strip().lower() != (email or "").strip().lower():
            raise HTTPException(status_code=403, detail="Patient credentials are invalid.")
        return patient["hospital_number"], patient["email"], "email"

    raise HTTPException(status_code=400, detail="Unsupported auth role.")


def _send_telegram_otp(chat_id: int, code: str) -> bool:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        return False
    response = httpx.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": f"Your SynMed OTP is {code}. It expires in {OTP_TTL_SECONDS // 60} minutes.",
        },
        timeout=20,
    )
    response.raise_for_status()
    return True


def _send_email_otp(email: str, code: str) -> bool:
    host = os.getenv("SMTP_HOST", "").strip()
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USERNAME", "").strip()
    password = os.getenv("SMTP_PASSWORD", "").strip().replace(" ", "")
    from_email = os.getenv("SMTP_FROM_EMAIL", username).strip()
    use_ssl = os.getenv("SMTP_USE_SSL", "0") == "1" or port == 465
    if not host or not from_email:
        return False

    message = EmailMessage()
    message["Subject"] = "Your SynMed OTP Code"
    message["From"] = from_email
    message["To"] = email
    message.set_content(
        f"Your SynMed OTP is {code}. It expires in {OTP_TTL_SECONDS // 60} minutes."
    )

    if use_ssl:
        with smtplib.SMTP_SSL(host, port, timeout=20) as server:
            if username and password:
                server.login(username, password)
            server.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=20) as server:
            if os.getenv("SMTP_USE_TLS", "1") == "1":
                server.starttls()
            if username and password:
                server.login(username, password)
            server.send_message(message)
    return True


def _send_email_verification_link(email: str, verify_url: str) -> bool:
    host = os.getenv("SMTP_HOST", "").strip()
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USERNAME", "").strip()
    password = os.getenv("SMTP_PASSWORD", "").strip().replace(" ", "")
    from_email = os.getenv("SMTP_FROM_EMAIL", username).strip()
    use_ssl = os.getenv("SMTP_USE_SSL", "0") == "1" or port == 465
    if not host or not from_email:
        return False

    message = EmailMessage()
    message["Subject"] = "Verify Your SynMed Account"
    message["From"] = from_email
    message["To"] = email
    message.set_content(
        "Welcome to SynMed Telehealth.\n\n"
        f"Please verify your email by opening this link:\n{verify_url}\n\n"
        "This link expires in 24 hours."
    )

    if use_ssl:
        with smtplib.SMTP_SSL(host, port, timeout=20) as server:
            if username and password:
                server.login(username, password)
            server.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=20) as server:
            if os.getenv("SMTP_USE_TLS", "1") == "1":
                server.starttls()
            if username and password:
                server.login(username, password)
            server.send_message(message)
    return True


def _is_debug_otp_visible() -> bool:
    return os.getenv("AUTH_DEV_OTP_VISIBLE", "1") == "1"


def _mask_email(value: str) -> str:
    local, _, domain = value.partition("@")
    if not local or not domain:
        return value
    if len(local) <= 2:
        masked_local = f"{local[0]}*"
    else:
        masked_local = f"{local[0]}{'*' * max(len(local) - 2, 1)}{local[-1]}"
    return f"{masked_local}@{domain}"


def get_delivery_status() -> dict:
    bot_token_ready = bool(os.getenv("BOT_TOKEN", "").strip())
    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_from_email = (os.getenv("SMTP_FROM_EMAIL", "") or os.getenv("SMTP_USERNAME", "")).strip()
    smtp_ready = bool(smtp_host and smtp_from_email)

    telegram_message = (
        "Telegram delivery is configured. Doctors and admins must have started the SynMed bot before requesting OTP."
        if bot_token_ready
        else "Telegram delivery is not ready yet. Add a valid BOT_TOKEN to enable doctor/admin OTP delivery."
    )
    email_message = (
        f"Email delivery is configured from {_mask_email(smtp_from_email)}."
        if smtp_ready
        else "Email delivery is not ready yet. Add SMTP host, sender address, and credentials to enable patient OTP delivery."
    )

    return {
        "telegram": {
            "ready": bot_token_ready,
            "label": "Telegram OTP",
            "message": telegram_message,
        },
        "email": {
            "ready": smtp_ready,
            "label": "Email OTP",
            "message": email_message,
        },
        "dev_debug_code_visible": _is_debug_otp_visible(),
    }


def _deliver_otp(channel: str, delivery_target: str, code: str) -> bool:
    if channel == "telegram":
        return _send_telegram_otp(int(delivery_target), code)
    if channel == "email":
        return _send_email_otp(delivery_target, code)
    return False


def _store_otp(
    *,
    role: str,
    identifier: str,
    delivery_target: str,
    code: str,
    context_json: str | None = None,
    ttl_seconds: int = OTP_TTL_SECONDS,
):
    code_hash = _otp_hash(code)
    expires_at = _future_iso(ttl_seconds)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE auth_otps
            SET consumed_at = ?
            WHERE role = ? AND identifier = ? AND consumed_at IS NULL
            """,
            (_now_iso(), role, identifier),
        )
        cursor.execute(
            """
            INSERT INTO auth_otps (
                role, identifier, delivery_target, code_hash, expires_at, consumed_at, context_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (role, identifier, delivery_target, code_hash, expires_at, None, context_json, _now_iso()),
        )
        conn.commit()


def _consume_valid_otp(*, role: str, identifier: str, otp_code: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, code_hash, expires_at, consumed_at, context_json, delivery_target
            FROM auth_otps
            WHERE role = ? AND identifier = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (role, identifier),
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=401, detail="No OTP request found.")
        if row["consumed_at"]:
            raise HTTPException(status_code=401, detail="OTP has already been used.")
        if datetime.fromisoformat(row["expires_at"]) < datetime.now(UTC):
            raise HTTPException(status_code=401, detail="OTP has expired.")
        if not hmac.compare_digest(row["code_hash"], _otp_hash(otp_code.strip())):
            raise HTTPException(status_code=401, detail="OTP code is invalid.")

        cursor.execute(
            "UPDATE auth_otps SET consumed_at = ? WHERE id = ?",
            (_now_iso(), row["id"]),
        )
        conn.commit()
        return row


def request_signup_otp(email: str) -> dict:
    normalized_email = email.strip().lower()
    if not normalized_email:
        raise HTTPException(status_code=400, detail="Email is required.")

    code = _issue_otp_code()
    _store_otp(role="patient_signup", identifier=normalized_email, delivery_target=normalized_email, code=code)

    delivered = False
    try:
        delivered = _deliver_otp("email", normalized_email, code)
    except Exception:
        delivered = False

    return {
        "success": True,
        "message": (
            "Signup OTP sent via email."
            if delivered
            else "Signup OTP generated, but email delivery is not configured correctly yet."
        ),
        "expires_in_seconds": OTP_TTL_SECONDS,
        "delivery_target": normalized_email,
        "debug_code": code if _is_debug_otp_visible() else None,
    }

def request_otp(role: str, *, user_id: int | None = None, hospital_number: str | None = None, email: str | None = None) -> dict:
    identifier, delivery_target, channel = _resolve_identity(
        role,
        user_id=user_id,
        hospital_number=hospital_number,
        email=email,
    )
    code = _issue_otp_code()
    _store_otp(role=role, identifier=identifier, delivery_target=delivery_target, code=code)

    delivered = False
    try:
        delivered = _deliver_otp(channel, delivery_target, code)
    except Exception:
        delivered = False

    return {
        "success": True,
        "message": (
            f"OTP sent via {channel}."
            if delivered
            else f"OTP generated, but {channel} delivery is not configured correctly yet."
        ),
        "expires_in_seconds": OTP_TTL_SECONDS,
        "delivery_target": delivery_target,
        "debug_code": code if _is_debug_otp_visible() else None,
    }


def verify_otp(
    role: str,
    *,
    otp_code: str,
    user_id: int | None = None,
    hospital_number: str | None = None,
    email: str | None = None,
) -> dict:
    identifier, _, _ = _resolve_identity(
        role,
        user_id=user_id,
        hospital_number=hospital_number,
        email=email,
    )
    _consume_valid_otp(role=role, identifier=identifier, otp_code=otp_code)

    normalized_role = role.strip().lower()
    if normalized_role == "doctor":
        return build_session_response("doctor", int(identifier))
    if normalized_role == "admin":
        return build_session_response("admin", int(identifier))
    return build_session_response("patient", identifier)


def hash_patient_password(password: str) -> str:
    if len(password.strip()) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters long.")
    return _password_hash(password)


def send_patient_email_verification(*, hospital_number: str, email: str) -> dict:
    token = _issue_link_token()
    _store_otp(
        role="patient_email_verify",
        identifier=hospital_number,
        delivery_target=email.strip().lower(),
        code=token,
        ttl_seconds=EMAIL_VERIFY_TTL_SECONDS,
    )
    base_url = os.getenv("AUTH_VERIFY_BASE_URL", "http://127.0.0.1:5173/patient/verify-email").strip()
    verify_url = f"{base_url}?hospital_number={hospital_number}&token={token}"

    delivered = False
    try:
        delivered = _send_email_verification_link(email.strip().lower(), verify_url)
    except Exception:
        delivered = False

    return {
        "success": True,
        "message": (
            "Verification email sent."
            if delivered
            else "Verification link generated, but email delivery is not configured correctly yet."
        ),
        "verify_url": verify_url if _is_debug_otp_visible() else None,
    }


def verify_patient_email_link(hospital_number: str, token: str) -> dict:
    patient = get_patient_by_identifier(hospital_number)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient record was not found.")
    _consume_valid_otp(role="patient_email_verify", identifier=patient["hospital_number"], otp_code=token)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE patients
            SET email_verified_at = ?, updated_at = ?
            WHERE patient_id = ?
            """,
            (_now_iso(), _now_iso(), patient["hospital_number"]),
        )
        conn.commit()

    return {
        "success": True,
        "message": "Email verified successfully. You can now sign in to SynMed Web.",
    }
