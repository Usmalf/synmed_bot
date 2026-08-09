import asyncio
import os
import json
from datetime import datetime, timedelta, timezone

from database import get_connection
from services.paystack import (
    PaystackError,
    build_backend_callback_url,
    build_frontend_callback_url,
    create_payment_record,
    create_payment_reference,
    get_payment_by_reference,
    get_latest_valid_payment_for_patient,
    is_payment_within_validity_window,
    initialize_transaction,
    mark_payment_status,
    mark_payment_verified,
    verify_transaction,
)
from services.coupons import CouponError, has_active_coupon_for_purpose, record_coupon_redemption, validate_coupon
from services.patient_records import get_patient_by_identifier, register_patient, update_patient_record
from .auth_service import hash_patient_password, send_patient_email_verification
from .settings_service import get_payment_settings
from .whatsapp_service import notify_whatsapp_payment_verified


PAYSTACK_CURRENCY = os.getenv("PAYSTACK_CURRENCY", "NGN")
NEW_PATIENT_FEE = int(os.getenv("NEW_PATIENT_FEE_NGN", "3000"))
RETURNING_PATIENT_FEE = int(os.getenv("RETURNING_PATIENT_FEE_NGN", "2000"))
NEW_PATIENT_LABEL = os.getenv(
    "NEW_PATIENT_PAYMENT_LABEL",
    "SynMed Registration + Consultation Fee",
)
RETURNING_PATIENT_LABEL = os.getenv(
    "RETURNING_PATIENT_PAYMENT_LABEL",
    "SynMed Consultation Fee",
)
UTC = timezone.utc
FIRST_CONSULTATION_FREE_HOURS = int(os.getenv("FIRST_CONSULTATION_FREE_HOURS", "24") or "24")


def get_payment_config() -> dict:
    settings = get_payment_settings()
    return {
        **settings,
        "registration_coupons_available": has_active_coupon_for_purpose("registration"),
        "consultation_coupons_available": has_active_coupon_for_purpose("consultation"),
    }


def _has_used_first_consultation_free(patient_id: str) -> bool:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT 1
            FROM payments
            WHERE UPPER(COALESCE(patient_id, '')) = UPPER(?)
              AND paystack_status = 'first_consultation_free'
            LIMIT 1
            """,
            (patient_id,),
        )
        return cursor.fetchone() is not None


def _has_any_consultation_record(patient_id: str) -> bool:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT 1
            FROM consultations
            WHERE UPPER(COALESCE(patient_id, '')) = UPPER(?)
            LIMIT 1
            """,
            (patient_id,),
        )
        return cursor.fetchone() is not None


def _grant_first_consultation_free(patient: dict, payment_config: dict) -> dict | None:
    patient_id = patient["hospital_number"]
    if _has_used_first_consultation_free(patient_id) or _has_any_consultation_record(patient_id):
        return None
    reference = create_payment_reference(prefix="free")
    create_payment_record(
        reference=reference,
        telegram_id=int(patient.get("telegram_id") or 0),
        patient_id=patient_id,
        email=patient.get("email") or "",
        amount=0,
        currency=payment_config["currency"],
        patient_type="returning",
        label="SynMed First Consultation",
        original_amount=payment_config["returning_patient_fee"],
        discount_amount=payment_config["returning_patient_fee"],
    )
    token = mark_payment_verified(
        reference,
        paystack_status="first_consultation_free",
        patient_id=patient_id,
    )
    expires_at = datetime.now(UTC) + timedelta(hours=max(1, min(FIRST_CONSULTATION_FREE_HOURS, 168)))
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE payments
            SET access_expires_at = ?, grant_reason = ?
            WHERE reference = ?
            """,
            (expires_at.isoformat(), "First consultation free", reference),
        )
        conn.commit()
    return get_payment_by_reference(reference)


def get_current_patient_payment_status(patient_identifier: str) -> dict:
    patient = get_patient_by_identifier(patient_identifier)
    if not patient:
        return {
            "active": False,
            "message": "Patient record could not be found for payment lookup.",
            "payment": None,
        }

    payment = get_latest_valid_payment_for_patient(patient["hospital_number"])
    if not payment:
        payment = _grant_first_consultation_free(patient, get_payment_config())
    if not payment:
        return {
            "active": False,
            "message": "No active 24-hour consultation payment was found. Start a new payment to continue.",
            "payment": None,
        }

    return {
        "active": True,
        "message": {
            "admin_access_grant": "Admin has granted temporary consultation access.",
            "first_consultation_free": "Your first SynMed consultation is free. You can continue to symptoms and consultation.",
        }.get(
            payment["paystack_status"],
            "A valid payment is still active for this patient within the 24-hour access window.",
        ),
        "payment": {
            "reference": payment["reference"],
            "payment_token": payment["payment_token"],
            "verified_at": payment["verified_at"],
            "amount": payment["amount"],
            "currency": payment["currency"],
            "label": payment["label"],
            "patient_type": payment["patient_type"],
            "access_source": (
                "admin_grant"
                if payment["paystack_status"] == "admin_access_grant"
                else "first_consultation_free"
                if payment["paystack_status"] == "first_consultation_free"
                else "payment"
            ),
            "access_expires_at": payment["access_expires_at"],
            "grant_reason": payment["grant_reason"] or "",
        },
    }


async def initialize_web_payment(payload: dict) -> dict:
    payment_config = get_payment_config()
    patient_type = payload["patient_type"]
    if patient_type == "new":
        amount = payment_config["new_patient_fee"]
        label = payment_config["new_patient_label"]
    else:
        amount = payment_config["returning_patient_fee"]
        label = payment_config["returning_patient_label"]

    patient_identifier = payload.get("patient_id") or ""
    patient = get_patient_by_identifier(patient_identifier) if patient_identifier else None
    if patient_type != "new" and not patient:
        raise PaystackError("Patient record could not be found for this payment.")

    reference = create_payment_reference()
    metadata = {
        "patient_type": patient_type,
        "patient_id": patient_identifier,
        "source": "web_portal",
        "telegram_id": 0,
    }
    payer_email = payload["email"].strip().lower()
    payer_phone = patient.get("phone", "") if patient else ""
    if patient_type == "new":
        registration = payload.get("registration_payload") or {}
        required_fields = [
            "name",
            "age",
            "gender",
            "phone",
            "address",
            "email",
            "password",
        ]
        missing = [field for field in required_fields if not str(registration.get(field, "")).strip()]
        if missing:
            raise PaystackError("Complete all required registration fields before payment.")
        normalized_email = registration["email"].strip().lower()
        if get_patient_by_identifier(normalized_email):
            raise PaystackError("A patient account already exists with this email. Please sign in or recover your account.")
        payer_email = normalized_email
        payer_phone = registration["phone"].strip()
        metadata["registration_payload_json"] = json.dumps(
            {
                "name": registration["name"].strip(),
                "age": int(registration["age"]),
                "gender": registration["gender"].strip(),
                "phone": registration["phone"].strip(),
                "address": registration["address"].strip(),
                "allergy": (registration.get("allergy") or "").strip(),
                "medical_conditions": (registration.get("medical_conditions") or "").strip(),
                "email": normalized_email,
                "password_hash": hash_patient_password(registration["password"]),
            }
        )
    purpose = "registration" if patient_type == "new" else "consultation"
    try:
        coupon = validate_coupon(
            code=payload.get("coupon_code") or "",
            purpose=purpose,
            amount=amount,
            patient_id=patient_identifier,
            email=payer_email,
            phone=payer_phone,
        )
    except CouponError as exc:
        raise PaystackError(str(exc)) from exc
    if coupon["applied"]:
        metadata["coupon_code"] = coupon["code"]
        metadata["original_amount"] = coupon["amount_before"]
        metadata["discount_amount"] = coupon["discount_amount"]
        amount = coupon["amount_after"]
    callback_path = (payload.get("callback_path") or "").strip()
    if not callback_path:
        callback_path = "/patient/register" if patient_type == "new" else "/patient/consultation"
    callback_url = build_backend_callback_url(
        "/payments/web-return",
        {"callback_path": callback_path},
    ) or build_frontend_callback_url(
        callback_path,
        {
            "payment_reference": reference,
            "reference": reference,
            "status": "success",
        },
    )

    if amount == 0 and coupon["applied"]:
        create_payment_record(
            reference=reference,
            telegram_id=0,
            patient_id=patient_identifier,
            email=payer_email,
            amount=0,
            currency=payment_config["currency"],
            patient_type=patient_type,
            label=label,
            registration_payload_json=metadata.get("registration_payload_json"),
            original_amount=coupon["amount_before"],
            discount_amount=coupon["discount_amount"],
            coupon_code=coupon["code"],
        )
        mark_payment_verified(reference, paystack_status="coupon_free", patient_id=patient_identifier or None)
        return {
            "initialized": True,
            "message": f"Coupon {coupon['code']} applied. No payment is required.",
            "reference": reference,
            "authorization_url": None,
            "access_code": None,
            "amount": 0,
            "currency": payment_config["currency"],
            "label": label,
            "coupon": {
                "code": coupon["code"],
                "discount_amount": coupon["discount_amount"],
                "original_amount": coupon["amount_before"],
                "amount_after": 0,
            },
        }

    result = await initialize_transaction(
        email=payer_email,
        amount_ngn=amount,
        currency=payment_config["currency"],
        reference=reference,
        label=label,
        metadata=metadata,
        callback_url=callback_url,
    )

    return {
        "initialized": True,
        "message": "Payment initialized successfully.",
        "reference": reference,
        "authorization_url": result["authorization_url"],
        "access_code": result["access_code"],
        "amount": amount,
        "currency": payment_config["currency"],
        "label": label,
        "coupon": (
            {
                "code": coupon["code"],
                "discount_amount": coupon["discount_amount"],
                "original_amount": coupon["amount_before"],
                "amount_after": coupon["amount_after"],
            }
            if coupon["applied"]
            else None
        ),
    }


async def verify_web_payment(reference: str) -> dict:
    payment = get_payment_by_reference(reference)
    if not payment:
        return {
            "verified": False,
            "message": "Payment reference was not found.",
            "reference": reference,
            "paystack_status": None,
            "amount": None,
            "currency": None,
            "patient": None,
        }

    if payment["status"] == "verified" and not is_payment_within_validity_window(payment):
        return {
            "verified": False,
            "message": "This consultation payment has expired after the 24-hour access window. Start a new payment to continue.",
            "reference": reference,
            "paystack_status": payment["paystack_status"],
            "amount": payment["amount"],
            "currency": payment["currency"],
            "patient": None,
        }

    if payment["status"] == "verified" and payment["paystack_status"] == "coupon_free":
        paystack_status = "coupon_free"
        amount_ngn = int(payment["amount"] or 0)
        currency = payment["currency"]
    else:
        verification = await verify_transaction(reference)
        paystack_status = (verification.get("status") or "").lower()
        amount_ngn = int(verification.get("amount", 0)) // 100
        currency = verification.get("currency")

    if paystack_status not in {"success", "coupon_free"}:
        mark_payment_status(
            reference,
            status="pending_verification",
            paystack_status=paystack_status or "pending",
        )
        return {
            "verified": False,
            "message": "Payment is not confirmed yet.",
            "reference": reference,
            "paystack_status": paystack_status or "pending",
            "amount": amount_ngn,
            "currency": currency,
            "patient": None,
        }

    if amount_ngn != payment["amount"] or currency != payment["currency"]:
        mark_payment_status(
            reference,
            status="amount_mismatch",
            paystack_status=paystack_status,
        )
        return {
            "verified": False,
            "message": "Payment amount or currency did not match the expected values.",
            "reference": reference,
            "paystack_status": paystack_status,
            "amount": amount_ngn,
            "currency": currency,
            "patient": None,
        }

    payment_patient_id = payment["patient_id"] or ""
    patient = get_patient_by_identifier(payment_patient_id)
    requires_email_verification = False
    verification_delivery = None
    verification_email_result = None
    if payment["patient_type"] == "new" and not patient:
        registration_payload_raw = payment["registration_payload_json"] or ""
        if not registration_payload_raw:
            return {
                "verified": False,
                "message": "New patient registration details are missing for this payment.",
                "reference": reference,
                "paystack_status": paystack_status,
                "amount": amount_ngn,
                "currency": currency,
                "patient": None,
                "requires_email_verification": False,
                "verification_delivery": None,
            }
        registration = json.loads(registration_payload_raw)
        patient = register_patient(
            telegram_id=None,
            name=registration["name"],
            age=str(registration["age"]),
            gender=registration["gender"],
            phone=registration["phone"],
            address=registration["address"],
            allergy=registration.get("allergy", ""),
            medical_conditions=registration.get("medical_conditions", ""),
            password_hash=registration["password_hash"],
            email=registration["email"],
            email_verified_at=None,
        )
        requires_email_verification = True
        verification_delivery = patient["email"]
        payment_patient_id = patient["hospital_number"]
        verification_email_result = await asyncio.to_thread(
            send_patient_email_verification,
            hospital_number=patient["hospital_number"],
            email=patient["email"],
        )
    elif payment["patient_type"] == "new" and patient and not patient.get("email_verified_at"):
        requires_email_verification = True
        verification_delivery = patient.get("email") or payment["email"]
        if verification_delivery:
            verification_email_result = await asyncio.to_thread(
                send_patient_email_verification,
                hospital_number=patient["hospital_number"],
                email=verification_delivery,
            )
    if patient and payment["email"] and payment["email"] != (patient.get("email") or ""):
        patient = update_patient_record(payment_patient_id, "email", payment["email"])

    mark_payment_verified(
        reference,
        paystack_status=paystack_status,
        patient_id=payment_patient_id or None,
    )
    if payment["coupon_code"]:
        record_coupon_redemption(
            reference=reference,
            code=payment["coupon_code"],
            purpose="registration" if payment["patient_type"] == "new" else "consultation",
            amount_before=int(payment["original_amount"] or payment["amount"] or 0),
            discount_amount=int(payment["discount_amount"] or 0),
            amount_after=int(payment["amount"] or 0),
            patient_id=payment_patient_id or "",
            email=payment["email"] or "",
            phone=(patient.get("phone") if patient else "") or "",
        )
    try:
        await notify_whatsapp_payment_verified(reference, patient)
    except Exception:
        pass

    return {
        "verified": True,
        "message": (
            (
                "Payment verified and registration completed, but the verification email could not be sent. Please contact SynMed support or try account recovery."
                if verification_email_result and not verification_email_result.get("delivered")
                else "Payment verified, registration completed, and a verification email has been sent. Verify your email before signing in."
            )
            if requires_email_verification
            else "Payment verified. You can now continue to symptoms and consultation."
        ),
        "reference": reference,
        "paystack_status": paystack_status,
        "amount": amount_ngn,
        "currency": currency,
        "patient": (
            {
                "internal_id": patient["id"],
                "hospital_number": patient["hospital_number"],
                "name": patient["name"],
                "age": patient["age"],
                "gender": patient["gender"],
                "phone": patient["phone"],
                "email": patient.get("email") or "",
                "email_verified_at": patient.get("email_verified_at"),
                "address": patient.get("address") or "",
                "allergy": patient.get("allergy") or "",
                "medical_conditions": patient.get("medical_conditions") or "",
            }
            if patient
            else None
        ),
        "requires_email_verification": requires_email_verification,
        "verification_delivery": verification_delivery,
        "coupon": (
            {
                "code": payment["coupon_code"],
                "discount_amount": payment["discount_amount"] or 0,
                "original_amount": payment["original_amount"] or payment["amount"],
                "amount_after": payment["amount"],
            }
            if payment["coupon_code"]
            else None
        ),
    }
