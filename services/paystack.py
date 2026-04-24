import os
import json
from datetime import datetime, timedelta, timezone
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


def get_payment_by_reference(reference: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT reference, telegram_id, patient_id, email, amount, currency,
                   patient_type, label, authorization_url, access_code,
                   status, paystack_status, created_at, verified_at,
                   payment_token, payment_token_used_at, registration_payload_json
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
                   payment_token, payment_token_used_at, registration_payload_json
            FROM payments
            WHERE UPPER(payment_token) = UPPER(?)
            """,
            (payment_token.strip(),),
        )
        return cursor.fetchone()


def redeem_payment_token(*, payment_token: str, patient_id: str):
    normalized_token = payment_token.strip().upper()
    normalized_patient_id = patient_id.strip().upper()
    payment = get_payment_by_token(normalized_token)
    if not payment:
        return None
    verified_at = _parse_iso_datetime(payment["verified_at"])
    if (
        payment["status"] != "verified"
        or (payment["patient_id"] or "").strip().upper() != normalized_patient_id
        or verified_at is None
        or datetime.now(UTC) - verified_at > PAYMENT_TOKEN_VALIDITY
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
):
    reference = reference or create_payment_reference(prefix="manual")
    existing = get_payment_by_reference(reference)
    if existing:
        return mark_payment_verified(
            reference,
            paystack_status="manual_override",
            patient_id=patient_id,
        )

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
    return mark_payment_verified(
        reference,
        paystack_status="manual_override",
        patient_id=patient_id,
    )


async def initialize_transaction(
    *,
    email: str,
    amount_ngn: int,
    currency: str,
    reference: str,
    label: str,
    metadata: dict | None = None,
):
    payload = {
        "email": email,
        "amount": amount_ngn * 100,
        "currency": currency,
        "reference": reference,
        "metadata": metadata or {},
    }
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
