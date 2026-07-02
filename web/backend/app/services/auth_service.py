import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import logging
import os
import smtplib
import time
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
import httpx

from database import get_connection
from synmed_utils.admin import is_admin
from synmed_utils.doctor_profiles import create_or_update_profile, doctor_profiles, get_profile_by_identifier
from synmed_utils.verified_doctors import is_verified
from services.patient_records import get_patient_by_identifier, register_google_patient, update_patient_record
from .settings_service import get_email_branding_settings
from services import storage_service


TOKEN_TTL_SECONDS = 60 * 60 * 12
OTP_TTL_SECONDS = 60 * 10
EMAIL_VERIFY_TTL_SECONDS = 60 * 60 * 24
UTC = timezone.utc
logger = logging.getLogger(__name__)


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
        admin_account = get_admin_account_by_identifier(str(user_id))
        display_name = (
            admin_account.get("display_name")
            or admin_account.get("email")
            or f"Admin {user_id}"
        ) if admin_account else f"Admin {user_id}"
    elif role == "customer_care":
        account = get_customer_care_account_by_identifier(str(user_id))
        display_name = (
            account.get("display_name")
            or account.get("email")
            or f"Customer Care {user_id}"
        ) if account else f"Customer Care {user_id}"
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


def _deliver_otp_checked(channel: str, delivery_target: str, code: str) -> bool:
    try:
        delivered = _deliver_otp(channel, delivery_target, code)
    except Exception as exc:
        logger.warning("OTP delivery failed via %s to %s: %s", channel, delivery_target, exc)
        raise HTTPException(status_code=503, detail=f"Unable to send OTP via {channel} right now.") from exc

    if not delivered:
        logger.warning("OTP delivery is not configured for %s to %s.", channel, delivery_target)
        raise HTTPException(status_code=503, detail=f"Unable to send OTP via {channel} right now.")

    return True


def login_doctor(identifier: str, password: str, otp_channel: str = "telegram") -> dict:
    doctor_id, profile = _resolve_doctor_account(identifier)
    stored_password_hash = profile.get("password_hash") or ""
    if not stored_password_hash or not hmac.compare_digest(stored_password_hash, _password_hash(password)):
        raise HTTPException(status_code=403, detail="Doctor credentials are invalid.")

    channel, delivery_target = _doctor_delivery_target(doctor_id, profile, otp_channel)
    code = _issue_otp_code()
    _store_otp(role="doctor_login", identifier=str(doctor_id), delivery_target=delivery_target, code=code)

    delivered = _deliver_otp_checked(channel, delivery_target, code)

    return {
        "success": True,
        "message": f"Doctor OTP sent via {channel}.",
        "expires_in_seconds": OTP_TTL_SECONDS,
        "delivery_target": delivery_target,
        "debug_code": code if _is_debug_otp_visible() else None,
        "role": "doctor",
        "otp_channel": channel,
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

    delivered = _deliver_otp_checked(channel, delivery_target, code)

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


def _allocate_web_doctor_id() -> int:
    base_id = 900_000_000_000
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT MAX(telegram_id) AS max_id
            FROM (
                SELECT telegram_id FROM doctors WHERE telegram_id >= ?
                UNION ALL
                SELECT telegram_id FROM doctor_profiles WHERE telegram_id >= ?
                UNION ALL
                SELECT telegram_id FROM pending_doctor_requests WHERE telegram_id >= ?
            )
            """,
            (base_id, base_id, base_id),
        )
        row = cursor.fetchone()
    return max(int(row["max_id"] or base_id) + 1, base_id + 1)


def _ensure_email_can_apply(email: str):
    existing_doctor_id, existing_profile = get_profile_by_identifier(email)
    if existing_doctor_id and existing_profile:
        raise HTTPException(
            status_code=409,
            detail="A doctor account already exists with this email. Please sign in or recover the account.",
        )


def _save_doctor_license_upload(filename: str, content_type: str, data: str) -> tuple[str, str, str, int]:
    if not data:
        raise HTTPException(status_code=400, detail="Latest annual licence upload is required.")

    original_name = Path(filename or "annual-licence").name
    extension = Path(original_name).suffix[:16]
    if not extension:
        extension = ".bin"
    stored_name = f"annual-license-{uuid4().hex}{extension}"
    try:
        asset_path, decoded = storage_service.save_base64_upload("doctor_application_files", stored_name, data)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Annual licence upload could not be read.") from exc
    return (
        asset_path,
        content_type or "application/octet-stream",
        original_name,
        len(decoded),
    )


def request_doctor_application(payload: dict) -> dict:
    normalized_email = (payload.get("email") or "").strip().lower()
    name = (payload.get("name") or "").strip()
    specialty = (payload.get("specialty") or "").strip()
    experience = (payload.get("experience") or "").strip()
    license_id = (payload.get("license_id") or "").strip()
    password = payload.get("password") or ""
    license_file_name = (payload.get("license_file_name") or "").strip()
    license_file_data = payload.get("license_file_data") or ""
    license_file_type = (payload.get("license_file_type") or "").strip()

    if not all([normalized_email, name, specialty, experience, license_id, password]):
        raise HTTPException(status_code=400, detail="Name, email, specialty, experience, license ID, and password are required.")
    if not license_file_data:
        raise HTTPException(status_code=400, detail="Upload your latest annual licence before submitting.")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters long.")

    _ensure_email_can_apply(normalized_email)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT telegram_id
            FROM pending_doctor_requests
            WHERE LOWER(COALESCE(email, '')) = ?
              AND COALESCE(review_status, 'pending_review') = 'pending_review'
            LIMIT 1
            """,
            (normalized_email,),
        )
        if cursor.fetchone():
            raise HTTPException(status_code=409, detail="A pending doctor application already exists for this email.")

    code = _issue_otp_code()
    context_json = json.dumps(
        {
            "name": name,
            "email": normalized_email,
            "phone": (payload.get("phone") or "").strip(),
            "specialty": specialty,
            "experience": experience,
            "license_id": license_id,
            "license_expiry_date": (payload.get("license_expiry_date") or "").strip(),
            "license_file_name": license_file_name,
            "license_file_type": license_file_type,
            "license_file_data": license_file_data,
            "password_hash": _password_hash(password),
        }
    )
    _store_otp(
        role="doctor_application",
        identifier=normalized_email,
        delivery_target=normalized_email,
        code=code,
        context_json=context_json,
    )

    _deliver_otp_checked("email", normalized_email, code)

    return {
        "success": True,
        "message": "Doctor application OTP sent via email.",
        "expires_in_seconds": OTP_TTL_SECONDS,
        "delivery_target": normalized_email,
        "debug_code": code if _is_debug_otp_visible() else None,
        "role": "doctor",
        "otp_channel": "email",
    }


def verify_doctor_application(identifier: str, otp_code: str) -> dict:
    normalized_email = identifier.strip().lower()
    _ensure_email_can_apply(normalized_email)
    row = _consume_valid_otp(role="doctor_application", identifier=normalized_email, otp_code=otp_code)
    context = json.loads(row["context_json"] or "{}")
    doctor_id = _allocate_web_doctor_id()
    submitted_at = _now_iso()
    license_file_id, license_file_type, license_file_name, license_file_size = _save_doctor_license_upload(
        context.get("license_file_name") or "annual-licence",
        context.get("license_file_type") or "application/octet-stream",
        context.get("license_file_data") or "",
    )

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO pending_doctor_requests (
                telegram_id, name, specialty, experience, license_id, username,
                file_id, file_type, email, phone, password_hash, license_expiry_date,
                review_status, submitted_at, license_file_name, license_file_size, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending_review', ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(telegram_id) DO UPDATE SET
                name = excluded.name,
                specialty = excluded.specialty,
                experience = excluded.experience,
                license_id = excluded.license_id,
                username = excluded.username,
                email = excluded.email,
                phone = excluded.phone,
                password_hash = excluded.password_hash,
                license_expiry_date = excluded.license_expiry_date,
                review_status = 'pending_review',
                submitted_at = excluded.submitted_at,
                license_file_name = excluded.license_file_name,
                license_file_size = excluded.license_file_size,
                reviewed_at = NULL,
                review_note = NULL
            """,
            (
                doctor_id,
                context.get("name"),
                context.get("specialty"),
                context.get("experience"),
                context.get("license_id"),
                (context.get("email") or "").split("@", 1)[0],
                license_file_id,
                license_file_type,
                normalized_email,
                context.get("phone") or "",
                context.get("password_hash") or "",
                context.get("license_expiry_date") or "",
                submitted_at,
                license_file_name,
                license_file_size,
            ),
        )
        conn.commit()

    return {
        "success": True,
        "message": "Email verified. Your doctor application is now waiting for admin approval.",
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

    delivered = _deliver_otp_checked(channel, delivery_target, code)

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


def get_admin_account_by_identifier(identifier: str) -> dict | None:
    normalized = str(identifier).strip().lower()
    if not normalized:
        return None

    with get_connection() as conn:
        cursor = conn.cursor()
        if normalized.isdigit():
            cursor.execute(
                """
                SELECT admin_id, email, display_name, password_hash, created_at, updated_at
                FROM admin_accounts
                WHERE admin_id = ?
                """,
                (int(normalized),),
            )
            row = cursor.fetchone()
            if row:
                return dict(row)

        cursor.execute(
            """
            SELECT admin_id, email, display_name, password_hash, created_at, updated_at
            FROM admin_accounts
            WHERE lower(email) = ?
            """,
            (normalized,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def bootstrap_admin_account(admin_id: int, email: str, display_name: str, password: str) -> dict:
    if not is_admin(admin_id):
        raise HTTPException(status_code=403, detail="This admin ID is not authorized in ADMIN_IDS.")

    normalized_email = email.strip().lower()
    normalized_name = display_name.strip()
    if not normalized_email:
        raise HTTPException(status_code=400, detail="Admin email is required.")
    if len(password.strip()) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters long.")

    existing_email = get_admin_account_by_identifier(normalized_email)
    if existing_email and int(existing_email["admin_id"]) != int(admin_id):
        raise HTTPException(status_code=409, detail="That email is already linked to another admin account.")

    now_iso = _now_iso()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO admin_accounts (admin_id, email, display_name, password_hash, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(admin_id) DO UPDATE SET
                email = excluded.email,
                display_name = excluded.display_name,
                password_hash = excluded.password_hash,
                updated_at = excluded.updated_at
            """,
            (
                admin_id,
                normalized_email,
                normalized_name or f"Admin {admin_id}",
                _password_hash(password),
                now_iso,
                now_iso,
            ),
        )
        conn.commit()

    return {
        "success": True,
        "message": "Admin web credentials saved successfully. You can now sign in with email and password.",
    }


def get_customer_care_account_by_identifier(identifier: str) -> dict | None:
    normalized = str(identifier).strip().lower()
    if not normalized:
        return None

    with get_connection() as conn:
        cursor = conn.cursor()
        if normalized.isdigit():
            cursor.execute(
                """
                SELECT account_id, email, display_name, password_hash, status,
                       created_by_admin_id, created_at, updated_at, last_login_at
                FROM customer_care_accounts
                WHERE account_id = ?
                """,
                (int(normalized),),
            )
            row = cursor.fetchone()
            if row:
                return dict(row)

        cursor.execute(
            """
            SELECT account_id, email, display_name, password_hash, status,
                   created_by_admin_id, created_at, updated_at, last_login_at
            FROM customer_care_accounts
            WHERE lower(email) = ?
            """,
            (normalized,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def list_customer_care_accounts() -> list[dict]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT account_id, email, display_name, status, created_by_admin_id,
                   created_at, updated_at, last_login_at
            FROM customer_care_accounts
            ORDER BY display_name COLLATE NOCASE ASC, account_id ASC
            """
        )
        return [dict(row) for row in cursor.fetchall()]


def create_customer_care_account(admin_id: int, email: str, display_name: str, password: str) -> dict:
    normalized_email = email.strip().lower()
    normalized_name = display_name.strip()
    if not normalized_email or not normalized_name:
        raise HTTPException(status_code=400, detail="Name and email are required.")
    if len(password.strip()) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters long.")
    if get_customer_care_account_by_identifier(normalized_email):
        raise HTTPException(status_code=409, detail="A customer care account already exists with this email.")

    now_iso = _now_iso()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO customer_care_accounts (
                email, display_name, password_hash, status,
                created_by_admin_id, created_at, updated_at
            )
            VALUES (?, ?, ?, 'pending', ?, ?, ?)
            """,
            (
                normalized_email,
                normalized_name,
                _password_hash(password),
                admin_id,
                now_iso,
                now_iso,
            ),
        )
        account_id = cursor.lastrowid
        conn.commit()

    account = get_customer_care_account_by_identifier(str(account_id))
    return {
        "created": True,
        "message": "Customer care account request created. Approve it before the agent can sign in.",
        "account": _public_customer_care_account(account),
    }


def set_customer_care_account_status(account_id: int, status: str) -> dict:
    normalized_status = (status or "").strip().lower()
    aliases = {
        "approve": "active",
        "activate": "active",
        "reactivate": "active",
        "disable": "suspended",
        "disabled": "suspended",
        "suspend": "suspended",
        "reject": "rejected",
    }
    normalized_status = aliases.get(normalized_status, normalized_status)
    if normalized_status not in {"pending", "active", "rejected", "suspended"}:
        raise HTTPException(status_code=400, detail="Unsupported customer care account status.")
    account = get_customer_care_account_by_identifier(str(account_id))
    if not account:
        raise HTTPException(status_code=404, detail="Customer care account could not be found.")

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE customer_care_accounts
            SET status = ?, updated_at = ?
            WHERE account_id = ?
            """,
            (normalized_status, _now_iso(), account_id),
        )
        conn.commit()

    return {
        "updated": True,
        "message": "Customer care account updated.",
        "account": _public_customer_care_account(get_customer_care_account_by_identifier(str(account_id))),
    }


def _public_customer_care_account(account: dict | None) -> dict | None:
    if not account:
        return None
    return {
        "account_id": account["account_id"],
        "email": account["email"],
        "display_name": account["display_name"],
        "status": account["status"],
        "created_by_admin_id": account.get("created_by_admin_id"),
        "created_at": account["created_at"],
        "updated_at": account["updated_at"],
        "last_login_at": account.get("last_login_at"),
    }


def _login_customer_care_with_password(identifier: str, password: str) -> dict | None:
    account = get_customer_care_account_by_identifier(identifier)
    if not account or account.get("status") != "active":
        return None
    stored_password_hash = account.get("password_hash") or ""
    if not stored_password_hash or not hmac.compare_digest(stored_password_hash, _password_hash(password)):
        return None

    code = _issue_otp_code()
    delivery_target = account["email"]
    _store_otp(
        role="customer_care_login",
        identifier=str(account["account_id"]),
        delivery_target=delivery_target,
        code=code,
    )

    _deliver_otp_checked("email", delivery_target, code)

    return {
        "success": True,
        "message": "Customer care OTP sent via email.",
        "expires_in_seconds": OTP_TTL_SECONDS,
        "delivery_target": delivery_target,
        "debug_code": code if _is_debug_otp_visible() else None,
        "role": "customer_care",
        "otp_channel": "email",
    }


def _login_admin_with_password(identifier: str, password: str) -> dict | None:
    normalized_identifier = str(identifier).strip()
    admin_account = get_admin_account_by_identifier(normalized_identifier)
    if admin_account:
        admin_id = int(admin_account["admin_id"])
        stored_password_hash = admin_account.get("password_hash") or ""
        if not stored_password_hash or not hmac.compare_digest(stored_password_hash, _password_hash(password)):
            return None
    else:
        if not normalized_identifier.isdigit():
            return None
        admin_id = int(normalized_identifier)
        admin_password = (os.getenv("ADMIN_WEB_PASSWORD") or "").strip()
        if not admin_password or not is_admin(admin_id):
            return None
        if not hmac.compare_digest(admin_password, password):
            return None

    code = _issue_otp_code()
    delivery_target = str(admin_id)
    _store_otp(role="admin_login", identifier=str(admin_id), delivery_target=delivery_target, code=code)

    delivered = _deliver_otp_checked("telegram", delivery_target, code)

    return {
        "success": True,
        "message": "Admin OTP sent via telegram.",
        "expires_in_seconds": OTP_TTL_SECONDS,
        "delivery_target": delivery_target,
        "debug_code": code if _is_debug_otp_visible() else None,
        "role": "admin",
        "otp_channel": "telegram",
    }


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

    delivered = _deliver_otp_checked(channel, delivery_target, code)

    return {
        "success": True,
        "message": f"Login OTP sent via {channel}.",
        "expires_in_seconds": OTP_TTL_SECONDS,
        "delivery_target": delivery_target,
        "debug_code": code if _is_debug_otp_visible() else None,
        "role": "patient",
        "otp_channel": channel,
    }


def verify_patient_login(identifier: str, otp_code: str) -> dict:
    patient = get_patient_by_identifier(identifier)
    if not patient:
        raise HTTPException(status_code=403, detail="Patient credentials are invalid.")
    _consume_valid_otp(role="patient_login", identifier=patient["hospital_number"], otp_code=otp_code)
    return build_session_response("patient", patient["hospital_number"])


def _verify_google_identity_token(credential: str) -> dict:
    google_client_id = (os.getenv("GOOGLE_CLIENT_ID") or "").strip()
    if not google_client_id:
        raise HTTPException(status_code=503, detail="Google sign-in is not configured yet.")

    try:
        response = httpx.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"id_token": credential},
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Unable to verify Google sign-in right now.") from exc

    if payload.get("aud") != google_client_id:
        raise HTTPException(status_code=401, detail="Google sign-in audience is invalid.")
    if str(payload.get("email_verified", "")).lower() != "true":
        raise HTTPException(status_code=401, detail="Google account email is not verified.")

    email = (payload.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=401, detail="Google account did not provide an email address.")

    return {
        "email": email,
        "name": (payload.get("name") or "SynMed Patient").strip(),
    }


def login_or_signup_patient_with_google(credential: str) -> dict:
    google_profile = _verify_google_identity_token(credential)
    patient = get_patient_by_identifier(google_profile["email"])
    is_new_signup = False

    if not patient:
        patient = register_google_patient(
            name=google_profile["name"],
            email=google_profile["email"],
            email_verified_at=_now_iso(),
        )
        is_new_signup = True
    else:
        updates_made = False
        if not (patient.get("email_verified_at") or "").strip():
            update_patient_record(patient["hospital_number"], "email_verified_at", _now_iso())
            updates_made = True
        if not (patient.get("name") or "").strip() and google_profile["name"]:
            update_patient_record(patient["hospital_number"], "name", google_profile["name"])
            updates_made = True
        if updates_made:
            patient = get_patient_by_identifier(patient["hospital_number"])

    response = build_session_response("patient", patient["hospital_number"])
    response["message"] = (
        "Google sign-up completed. Please finish your patient biodata in your account page."
        if is_new_signup
        else "Signed in with Google successfully."
    )
    response["next_path"] = "/patient/account" if is_new_signup else "/patient"
    return response


def request_patient_recovery(identifier: str, email: str, new_password: str) -> dict:
    normalized_email = email.strip().lower()
    if not normalized_email:
        raise HTTPException(status_code=400, detail="Email is required.")
    if len(new_password.strip()) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters long.")

    patient = get_patient_by_identifier(normalized_email)
    account_type = ""
    account_id = ""
    current_email = normalized_email
    password_hash = _password_hash(new_password)

    if patient:
        account_type = "patient"
        account_id = patient["hospital_number"]
        current_email = normalized_email
        password_hash = hash_patient_password(new_password)
    else:
        try:
            doctor_id, profile = _resolve_doctor_account(normalized_email)
        except HTTPException:
            doctor_id = None
            profile = None
        if doctor_id and profile:
            account_type = "doctor"
            account_id = str(doctor_id)
            current_email = (profile.get("email") or normalized_email).strip().lower()

    if not account_type:
        customer_care_account = get_customer_care_account_by_identifier(normalized_email)
        if customer_care_account and customer_care_account.get("status") == "active":
            account_type = "customer_care"
            account_id = str(customer_care_account["account_id"])
            current_email = (customer_care_account.get("email") or normalized_email).strip().lower()

    if not account_type:
        if get_admin_account_by_identifier(normalized_email):
            raise HTTPException(status_code=403, detail="Admin password recovery is handled by admin bootstrap.")
        raise HTTPException(status_code=404, detail="No SynMed account was found for this email.")

    code = _issue_otp_code()
    context_json = json.dumps(
        {
            "account_type": account_type,
            "account_id": account_id,
            "email": current_email,
            "password_hash": password_hash,
        }
    )
    _store_otp(
        role="patient_recovery",
        identifier=normalized_email,
        delivery_target=current_email,
        code=code,
        context_json=context_json,
    )

    delivered = _deliver_otp_checked("email", current_email, code)

    return {
        "success": True,
        "message": (
            "Recovery OTP sent to your email."
            if delivered
            else "Recovery OTP generated, but email delivery is not configured correctly yet."
        ),
        "expires_in_seconds": OTP_TTL_SECONDS,
        "delivery_target": current_email,
        "debug_code": code if _is_debug_otp_visible() else None,
    }


def verify_patient_recovery(identifier: str, otp_code: str) -> dict:
    normalized_identifier = identifier.strip().lower()
    row = _consume_valid_otp(
        role="patient_recovery",
        identifier=normalized_identifier,
        otp_code=otp_code,
    )
    context = json.loads(row["context_json"] or "{}")
    account_type = context.get("account_type") or "patient"
    account_id = context.get("account_id") or normalized_identifier
    with get_connection() as conn:
        cursor = conn.cursor()
        if account_type == "patient":
            cursor.execute(
                """
                UPDATE patients
                SET email = ?, password_hash = ?, email_verified_at = ?, updated_at = ?
                WHERE patient_id = ? OR LOWER(email) = ?
                """,
                (
                    context.get("email") or normalized_identifier,
                    context.get("password_hash") or "",
                    _now_iso(),
                    _now_iso(),
                    account_id,
                    normalized_identifier,
                ),
            )
        elif account_type == "doctor":
            cursor.execute(
                """
                UPDATE doctor_profiles
                SET password_hash = ?, updated_at = ?
                WHERE telegram_id = ?
                """,
                (context.get("password_hash") or "", _now_iso(), int(account_id)),
            )
        elif account_type == "customer_care":
            cursor.execute(
                """
                UPDATE customer_care_accounts
                SET password_hash = ?, updated_at = ?
                WHERE account_id = ?
                """,
                (context.get("password_hash") or "", _now_iso(), int(account_id)),
            )
        else:
            raise HTTPException(status_code=400, detail="Unsupported recovery account type.")
        conn.commit()

    return {
        "success": True,
        "message": "Recovery completed successfully. You can now sign in with your password.",
    }


def login_web_user(identifier: str, password: str) -> dict:
    normalized_identifier = identifier.strip()
    if not normalized_identifier or not password:
        raise HTTPException(status_code=400, detail="Identifier and password are required.")

    patient = get_patient_by_identifier(normalized_identifier)
    patient_pending_verification = False
    if patient:
        stored_password_hash = patient.get("password_hash") or ""
        if stored_password_hash and hmac.compare_digest(stored_password_hash, _password_hash(password)):
            if not patient.get("email_verified_at"):
                patient_pending_verification = True
            else:
                return login_patient(normalized_identifier, password, "email")

    try:
        doctor_id, profile = _resolve_doctor_account(normalized_identifier)
    except HTTPException:
        doctor_id = None
        profile = None
    if doctor_id and profile:
        stored_password_hash = profile.get("password_hash") or ""
        if stored_password_hash and hmac.compare_digest(stored_password_hash, _password_hash(password)):
            preferred_channel = "email" if (profile.get("email") or "").strip() else "telegram"
            return login_doctor(normalized_identifier, password, preferred_channel)

    admin_result = _login_admin_with_password(normalized_identifier, password)
    if admin_result:
        return admin_result

    customer_care_result = _login_customer_care_with_password(normalized_identifier, password)
    if customer_care_result:
        return customer_care_result

    if patient_pending_verification:
        raise HTTPException(status_code=403, detail="Please verify your email address before signing in.")

    raise HTTPException(status_code=403, detail="We could not match those credentials to a SynMed account.")


def verify_web_user_login(identifier: str, otp_code: str) -> dict:
    normalized_identifier = identifier.strip()

    patient = get_patient_by_identifier(normalized_identifier)
    if patient:
        try:
            return verify_patient_login(normalized_identifier, otp_code)
        except HTTPException:
            pass

    try:
        doctor_id, _ = _resolve_doctor_account(normalized_identifier)
    except HTTPException:
        doctor_id = None
    if doctor_id:
        try:
            return verify_doctor_login(normalized_identifier, otp_code)
        except HTTPException:
            pass

    admin_account = get_admin_account_by_identifier(normalized_identifier)
    if admin_account:
        admin_identifier = str(admin_account["admin_id"])
        _consume_valid_otp(role="admin_login", identifier=admin_identifier, otp_code=otp_code)
        return build_session_response("admin", int(admin_identifier))

    if normalized_identifier.isdigit() and is_admin(int(normalized_identifier)):
        _consume_valid_otp(role="admin_login", identifier=normalized_identifier, otp_code=otp_code)
        return build_session_response("admin", int(normalized_identifier))

    customer_care_account = get_customer_care_account_by_identifier(normalized_identifier)
    if customer_care_account:
        account_id = int(customer_care_account["account_id"])
        _consume_valid_otp(role="customer_care_login", identifier=str(account_id), otp_code=otp_code)
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE customer_care_accounts SET last_login_at = ?, updated_at = ? WHERE account_id = ?",
                (_now_iso(), _now_iso(), account_id),
            )
            conn.commit()
        return build_session_response("customer_care", account_id)

    raise HTTPException(status_code=401, detail="OTP code is invalid or has expired.")


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
    message = EmailMessage()
    message["Subject"] = "Your SynMed OTP Code"
    _set_branded_email_content(
        message,
        f"Your SynMed OTP is {code}. It expires in {OTP_TTL_SECONDS // 60} minutes.",
    )
    return _send_email_message(email, message)


def send_plain_email(email: str, subject: str, body: str) -> bool:
    message = EmailMessage()
    message["Subject"] = subject
    _set_branded_email_content(message, body)
    return _send_email_message(email, message)


def send_email_with_attachment(
    email: str,
    subject: str,
    body: str,
    filename: str,
    content: bytes,
    content_type: str = "application/pdf",
) -> bool:
    message = EmailMessage()
    message["Subject"] = subject
    _set_branded_email_content(message, body)
    maintype, _, subtype = (content_type or "application/octet-stream").partition("/")
    message.add_attachment(
        content,
        maintype=maintype or "application",
        subtype=subtype or "octet-stream",
        filename=filename,
    )
    return _send_email_message(email, message)


def _email_logo_url() -> str:
    configured = get_email_branding_settings().get("logo_url", "").strip()
    if configured:
        return configured
    base_url = os.getenv("FRONTEND_BASE_URL", "http://127.0.0.1:5173").strip().rstrip("/")
    return f"{base_url}/logo-removebg-preview.png"


def _set_branded_email_content(message: EmailMessage, body: str) -> None:
    branding = get_email_branding_settings()
    brand_name = branding["brand_name"]
    support_address = branding["support_address"]
    footer_text = branding["footer_text"]
    footer_parts = [footer_text]
    if support_address:
        footer_parts.append(f"Support: {support_address}")
    footer = " | ".join(part for part in footer_parts if part)
    plain_body = (body or "").strip()
    message.set_content(f"{brand_name}\n\n{plain_body}\n\n{footer}")
    escaped_body = (
        plain_body
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br>")
    )
    escaped_brand = brand_name.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    escaped_footer = footer.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    message.add_alternative(
        f"""
        <html>
          <body style="margin:0;padding:0;background:#f5f8fa;font-family:Arial,sans-serif;color:#173640;">
            <div style="max-width:620px;margin:0 auto;padding:24px;">
              <div style="background:#ffffff;border:1px solid #dbe8ec;border-radius:10px;padding:22px;">
                <img src="{_email_logo_url()}" alt="{escaped_brand}" style="height:54px;max-width:180px;object-fit:contain;margin-bottom:18px;" />
                <h1 style="font-size:18px;line-height:1.3;margin:0 0 14px;color:#0d5264;">{escaped_brand}</h1>
                <div style="font-size:15px;line-height:1.6;">{escaped_body}</div>
                <p style="border-top:1px solid #dbe8ec;color:#6b858e;font-size:12px;line-height:1.5;margin:22px 0 0;padding-top:14px;">{escaped_footer}</p>
              </div>
            </div>
          </body>
        </html>
        """,
        subtype="html",
    )


def _send_email_message(email: str, message: EmailMessage) -> bool:
    host = os.getenv("SMTP_HOST", "").strip()
    port = int(os.getenv("SMTP_PORT", "587"))
    timeout_seconds = int(os.getenv("SMTP_TIMEOUT_SECONDS", "20"))
    username = os.getenv("SMTP_USERNAME", "").strip()
    password = os.getenv("SMTP_PASSWORD", "").strip().replace(" ", "")
    from_email = os.getenv("SMTP_FROM_EMAIL", username).strip()
    use_ssl = os.getenv("SMTP_USE_SSL", "0") == "1" or port == 465
    if not host or not from_email:
        return False

    message["From"] = formataddr((get_email_branding_settings()["brand_name"], from_email))
    message["To"] = email
    attempts = [(port, use_ssl, os.getenv("SMTP_USE_TLS", "1") == "1")]
    fallback = (587, False, True) if use_ssl else (465, True, False)
    if fallback[0] != port:
        attempts.append(fallback)

    last_error = None
    for attempt_port, attempt_ssl, attempt_tls in attempts:
        try:
            if attempt_ssl:
                with smtplib.SMTP_SSL(host, attempt_port, timeout=timeout_seconds) as server:
                    if username and password:
                        server.login(username, password)
                    server.send_message(message)
            else:
                with smtplib.SMTP(host, attempt_port, timeout=timeout_seconds) as server:
                    if attempt_tls:
                        server.starttls()
                    if username and password:
                        server.login(username, password)
                    server.send_message(message)
            return True
        except Exception as exc:
            last_error = exc
            logger.warning("SMTP attempt failed on %s:%s ssl=%s: %s", host, attempt_port, attempt_ssl, exc)

    if last_error:
        raise last_error
    return True


def _send_email_verification_link(email: str, verify_url: str) -> bool:
    message = EmailMessage()
    message["Subject"] = "Verify Your SynMed Account"
    _set_branded_email_content(
        message,
        "Welcome to SynMed Telehealth.\n\n"
        f"Please verify your email by opening this link:\n{verify_url}\n\n"
        "This link expires in 24 hours."
    )
    return _send_email_message(email, message)


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

    delivered = _deliver_otp_checked("email", normalized_email, code)

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


def send_patient_web_access_setup(*, hospital_number: str, email: str) -> dict:
    normalized_email = email.strip().lower()
    patient = get_patient_by_identifier(hospital_number)
    if not patient:
        return {"success": False, "message": "Patient record was not found."}
    if not normalized_email:
        return {"success": False, "message": "Patient email is required for web access setup."}

    token = _issue_link_token()
    _store_otp(
        role="patient_web_setup",
        identifier=patient["hospital_number"],
        delivery_target=normalized_email,
        code=token,
        ttl_seconds=EMAIL_VERIFY_TTL_SECONDS,
    )
    base_url = os.getenv("FRONTEND_BASE_URL", "http://127.0.0.1:5173").strip().rstrip("/")
    setup_url = f"{base_url}/patient/setup-password?hospital_number={patient['hospital_number']}&token={token}"
    body = (
        f"Hello {patient.get('name') or 'Patient'},\n\n"
        "Your SynMed patient record has been created from Telegram.\n\n"
        "Use the secure link below to verify your email and create your web password. "
        "After that, this same email and password will open your SynMed web dashboard.\n\n"
        f"{setup_url}\n\n"
        "If you did not request this, please ignore this email."
    )

    delivered = False
    try:
        delivered = send_plain_email(normalized_email, "Set up your SynMed web access", body)
    except Exception:
        delivered = False

    return {
        "success": True,
        "delivered": delivered,
        "message": (
            "Web access setup email sent."
            if delivered
            else "Web access setup link generated, but email delivery is not configured correctly yet."
        ),
        "setup_url": setup_url if _is_debug_otp_visible() else None,
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


def complete_patient_web_access_setup(hospital_number: str, token: str, password: str) -> dict:
    if len(password.strip()) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters long.")
    patient = get_patient_by_identifier(hospital_number)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient record was not found.")

    _consume_valid_otp(role="patient_web_setup", identifier=patient["hospital_number"], otp_code=token)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE patients
            SET password_hash = ?, email_verified_at = COALESCE(email_verified_at, ?), updated_at = ?
            WHERE patient_id = ?
            """,
            (_password_hash(password), _now_iso(), _now_iso(), patient["hospital_number"]),
        )
        conn.commit()

    return {
        "success": True,
        "message": "Web access is ready. You can now sign in with your email and password.",
    }
