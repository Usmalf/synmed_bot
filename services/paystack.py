import os
import json
import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from uuid import uuid4

import httpx
from dotenv import load_dotenv

from database import get_connection


load_dotenv()

UTC = timezone.utc
PAYSTACK_BASE_URL = "https://api.paystack.co"
PAYMENT_TOKEN_VALIDITY = timedelta(hours=24)


class PaystackError(Exception):
    pass


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _parse_iso_datetime(value: str | None):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except ValueError:
        return None


def _headers() -> dict[str, str]:
    secret_key = os.getenv("PAYSTACK_SECRET_KEY", "").strip()
    if not secret_key:
        raise PaystackError("Paystack secret key is missing.")
    return {
        "Authorization": f"Bearer {secret_key}",
        "Content-Type": "application/json",
    }


def build_frontend_callback_url(path: str, params: dict | None = None) -> str:
    base_url = os.getenv("FRONTEND_BASE_URL", "").strip().rstrip("/")
    if not base_url:
        return ""
    normalized_path = f"/{(path or '').strip().lstrip('/')}"
    url = f"{base_url}{normalized_path}"
    clean_params = {
        key: value
        for key, value in (params or {}).items()
        if value is not None and str(value).strip() != ""
    }
    if clean_params:
        url = f"{url}?{urlencode(clean_params)}"
    return url


def build_backend_callback_url(path: str, params: dict | None = None) -> str:
    base_url = (
        os.getenv("BACKEND_PUBLIC_URL", "").strip().rstrip("/")
        or os.getenv("API_BASE_URL", "").strip().rstrip("/")
        or os.getenv("VITE_API_BASE_URL", "").strip().rstrip("/")
    )
    if not base_url:
        return ""
    normalized_path = f"/{(path or '').strip().lstrip('/')}"
    url = f"{base_url}{normalized_path}"
    clean_params = {
        key: value
        for key, value in (params or {}).items()
        if value is not None and str(value).strip() != ""
    }
    if clean_params:
        url = f"{url}?{urlencode(clean_params)}"
    return url


def create_payment_reference(prefix: str = "synmed") -> str:
    return f"{prefix}-{uuid4().hex[:16]}"


def create_payment_token(prefix: str = "SMP") -> str:
    return f"{prefix}-{uuid4().hex[:8].upper()}"


def create_payment_record(
    *,
    reference: str,
    telegram_id: int,
    patient_id: str | None,
    email: str,
    amount: int,
    currency: str,
    patient_type: str,
    label: str,
    registration_payload_json: str | None = None,
):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO payments (
                reference, telegram_id, patient_id, email, amount, currency,
                patient_type, label, status, created_at, registration_payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                reference,
                telegram_id,
                patient_id,
                email,
                amount,
                currency,
                patient_type,
                label,
                "initialized",
                _now_iso(),
                registration_payload_json,
            ),
        )
        conn.commit()


def update_payment_initialization(reference: str, *, authorization_url: str, access_code: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE payments
            SET authorization_url = ?, access_code = ?
            WHERE reference = ?
            """,
            (authorization_url, access_code, reference),
        )
        conn.commit()


def mark_payment_verified(reference: str, *, paystack_status: str, patient_id: str | None = None):
    token = create_payment_token()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE payments
            SET status = ?, paystack_status = ?, patient_id = COALESCE(?, patient_id), verified_at = ?, payment_token = COALESCE(payment_token, ?)
            WHERE reference = ?
            """,
            ("verified", paystack_status, patient_id, _now_iso(), token, reference),
        )
        conn.commit()
        cursor.execute("SELECT payment_token FROM payments WHERE reference = ?", (reference,))
        row = cursor.fetchone()
    return row["payment_token"] if row else token


def mark_payment_status(reference: str, *, status: str, paystack_status: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE payments
            SET status = ?, paystack_status = ?
            WHERE reference = ?
            """,
            (status, paystack_status, reference),
        )
        conn.commit()


def record_payment_event(
    *,
    event_key: str,
    event_type: str,
    reference: str | None,
    status: str | None,
    amount: int | None,
    currency: str | None,
    payload: dict,
) -> bool:
    now = _now_iso()
    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO payment_events (
                    event_key, event_type, reference, status, amount, currency,
                    payload_json, processed_at, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_key,
                    event_type,
                    reference,
                    status,
                    amount,
                    currency,
                    json.dumps(payload),
                    now,
                    now,
                ),
            )
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            return False


def verify_paystack_webhook_signature(raw_body: bytes, signature: str | None) -> bool:
    secret = os.getenv("PAYSTACK_SECRET_KEY", "").strip()
    received = (signature or "").strip()
    if not secret or not received:
        return False
    digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(digest, received)


def _payment_reference_from_event(data: dict) -> str:
    candidates = [
        data.get("reference"),
        data.get("transaction_reference"),
        data.get("refund_reference"),
        (data.get("transaction") or {}).get("reference") if isinstance(data.get("transaction"), dict) else None,
        (data.get("metadata") or {}).get("reference") if isinstance(data.get("metadata"), dict) else None,
    ]
    for candidate in candidates:
        if candidate:
            return str(candidate).strip()
    return ""


def _event_key(payload: dict, raw_body: bytes) -> str:
    candidates = [
        payload.get("id"),
        payload.get("event_id"),
        (payload.get("data") or {}).get("id") if isinstance(payload.get("data"), dict) else None,
    ]
    for candidate in candidates:
        if candidate:
            return str(candidate)
    return hashlib.sha256(raw_body).hexdigest()


def _paystack_amount_ngn(data: dict) -> int | None:
    value = data.get("amount")
    if value is None and isinstance(data.get("transaction"), dict):
        value = data["transaction"].get("amount")
    try:
        return int(value) // 100
    except (TypeError, ValueError):
        return None


def _paystack_currency(data: dict) -> str | None:
    value = data.get("currency")
    if value is None and isinstance(data.get("transaction"), dict):
        value = data["transaction"].get("currency")
    return str(value) if value else None


def _payment_status_for_event(event_type: str, data: dict) -> tuple[str | None, str]:
    normalized = (event_type or "").strip().lower()
    data_status = str(data.get("status") or "").strip().lower()
    if normalized == "charge.success":
        return "verified", "success"
    if normalized in {"refund.processed", "charge.refunded"}:
        return "refunded", data_status or normalized
    if normalized in {"refund.failed"}:
        return None, data_status or normalized
    if normalized.startswith("charge.dispute"):
        if "resolve" in normalized and data_status in {"won", "resolved", "successful"}:
            return "verified", data_status
        if "resolve" in normalized and data_status in {"lost", "refunded"}:
            return "reversed", data_status
        return "disputed", data_status or normalized
    if normalized in {"transfer.reversed", "transfer.failed"}:
        return "reversed", data_status or normalized
    return None, data_status or normalized or "unknown"


def process_paystack_webhook(payload: dict, raw_body: bytes) -> dict:
    event_type = str(payload.get("event") or "").strip()
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    reference = _payment_reference_from_event(data)
    amount = _paystack_amount_ngn(data)
    currency = _paystack_currency(data)
    next_status, paystack_status = _payment_status_for_event(event_type, data)
    event_key = _event_key(payload, raw_body)
    inserted = record_payment_event(
        event_key=event_key,
        event_type=event_type or "unknown",
        reference=reference or None,
        status=paystack_status,
        amount=amount,
        currency=currency,
        payload=payload,
    )

    payment_updated = False
    if inserted and reference and next_status:
        if next_status == "verified":
            payment = get_payment_by_reference(reference)
            mark_payment_verified(
                reference,
                paystack_status=paystack_status,
                patient_id=(payment["patient_id"] if payment else None),
            )
        else:
            mark_payment_status(reference, status=next_status, paystack_status=paystack_status)
        payment_updated = True

    return {
        "received": True,
        "inserted": inserted,
        "event": event_type or "unknown",
        "reference": reference or None,
        "payment_status": next_status,
        "payment_updated": payment_updated,
    }


def list_payment_events(limit: int = 100) -> list[dict]:
    safe_limit = max(1, min(int(limit or 100), 250))
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                event_key, event_type, reference, status, amount, currency,
                processed_at, created_at
            FROM payment_events
            ORDER BY datetime(processed_at) DESC, id DESC
            LIMIT ?
            """,
            (safe_limit,),
        )
        return [dict(row) for row in cursor.fetchall()]


def get_payment_by_reference(reference: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT reference, telegram_id, patient_id, email, amount, currency,
                   patient_type, label, authorization_url, access_code,
                   status, paystack_status, created_at, verified_at,
                   payment_token, payment_token_used_at, registration_payload_json,
                   access_expires_at, grant_reason, granted_by_admin_id
            FROM payments
            WHERE reference = ?
            """,
            (reference,),
        )
        return cursor.fetchone()


def get_payment_by_token(payment_token: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT reference, telegram_id, patient_id, email, amount, currency,
                   patient_type, label, authorization_url, access_code,
                   status, paystack_status, created_at, verified_at,
                   payment_token, payment_token_used_at, registration_payload_json,
                   access_expires_at, grant_reason, granted_by_admin_id
            FROM payments
            WHERE UPPER(payment_token) = UPPER(?)
            """,
            (payment_token.strip(),),
        )
        return cursor.fetchone()


def is_payment_within_validity_window(payment) -> bool:
    if not payment:
        return False

    access_expires_at = _parse_iso_datetime(payment["access_expires_at"])
    if access_expires_at is not None:
        return datetime.now(UTC) <= access_expires_at

    verified_at = _parse_iso_datetime(payment["verified_at"])
    if verified_at is None:
        return False

    return datetime.now(UTC) - verified_at <= PAYMENT_TOKEN_VALIDITY


def get_latest_valid_payment_for_patient(patient_id: str):
    normalized_patient_id = (patient_id or "").strip().upper()
    if not normalized_patient_id:
        return None

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT reference, telegram_id, patient_id, email, amount, currency,
                   patient_type, label, authorization_url, access_code,
                   status, paystack_status, created_at, verified_at,
                   payment_token, payment_token_used_at, registration_payload_json,
                   access_expires_at, grant_reason, granted_by_admin_id
            FROM payments
            WHERE UPPER(COALESCE(patient_id, '')) = ?
              AND status = 'verified'
            ORDER BY datetime(COALESCE(verified_at, created_at)) DESC
            """,
            (normalized_patient_id,),
        )
        rows = cursor.fetchall()

    for payment in rows:
        if is_payment_within_validity_window(payment):
            return payment
    return None


def redeem_payment_token(*, payment_token: str, patient_id: str):
    normalized_token = payment_token.strip().upper()
    normalized_patient_id = patient_id.strip().upper()
    payment = get_payment_by_token(normalized_token)
    if not payment:
        return None
    if (
        payment["status"] != "verified"
        or (payment["patient_id"] or "").strip().upper() != normalized_patient_id
        or not is_payment_within_validity_window(payment)
    ):
        return None

    return get_payment_by_token(normalized_token)


def grant_manual_payment_override(
    *,
    telegram_id: int,
    patient_id: str,
    email: str,
    amount: int,
    currency: str = "NGN",
    label: str = "SynMed Manual Payment Override",
    patient_type: str = "returning",
    reference: str | None = None,
    admin_id: int | None = None,
    reason: str = "",
    duration_hours: int = 24,
):
    reference = reference or create_payment_reference(prefix="manual")
    existing = get_payment_by_reference(reference)
    if existing:
        token = mark_payment_verified(
            reference,
            paystack_status="admin_access_grant",
            patient_id=patient_id,
        )
    else:
        create_payment_record(
            reference=reference,
            telegram_id=telegram_id,
            patient_id=patient_id,
            email=email or "",
            amount=amount,
            currency=currency,
            patient_type=patient_type,
            label=label,
        )
        token = mark_payment_verified(
            reference,
            paystack_status="admin_access_grant",
            patient_id=patient_id,
        )

    expires_at = datetime.now(UTC) + timedelta(hours=max(1, min(duration_hours, 168)))
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE payments
            SET paystack_status = 'admin_access_grant',
                access_expires_at = ?,
                grant_reason = ?,
                granted_by_admin_id = ?
            WHERE reference = ?
            """,
            (expires_at.isoformat(), reason.strip(), admin_id, reference),
        )
        conn.commit()
    return {"reference": reference, "payment_token": token, "expires_at": expires_at.isoformat()}


def revoke_manual_payment_override(reference: str) -> bool:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE payments
            SET status = 'revoked', access_expires_at = ?
            WHERE reference = ? AND paystack_status = 'admin_access_grant'
            """,
            (_now_iso(), reference),
        )
        updated = cursor.rowcount > 0
        conn.commit()
    return updated


async def initialize_transaction(
    *,
    email: str,
    amount_ngn: int,
    currency: str,
    reference: str,
    label: str,
    metadata: dict | None = None,
    callback_url: str = "",
):
    payload = {
        "email": email,
        "amount": amount_ngn * 100,
        "currency": currency,
        "reference": reference,
        "metadata": metadata or {},
    }
    if callback_url:
        payload["callback_url"] = callback_url
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{PAYSTACK_BASE_URL}/transaction/initialize",
            headers=_headers(),
            json=payload,
        )
    response.raise_for_status()
    data = response.json()
    if not data.get("status"):
        raise PaystackError(data.get("message", "Unable to initialize payment."))
    result = data["data"]
    create_payment_record(
        reference=reference,
        telegram_id=int((metadata or {}).get("telegram_id", 0)),
        patient_id=(metadata or {}).get("patient_id"),
        email=email,
        amount=amount_ngn,
        currency=currency,
        patient_type=(metadata or {}).get("patient_type", "unknown"),
        label=label,
        registration_payload_json=(metadata or {}).get("registration_payload_json"),
    )
    update_payment_initialization(
        reference,
        authorization_url=result["authorization_url"],
        access_code=result["access_code"],
    )
    return result


async def verify_transaction(reference: str):
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            f"{PAYSTACK_BASE_URL}/transaction/verify/{reference}",
            headers=_headers(),
        )
    response.raise_for_status()
    data = response.json()
    if not data.get("status"):
        raise PaystackError(data.get("message", "Unable to verify payment."))
    return data["data"]
