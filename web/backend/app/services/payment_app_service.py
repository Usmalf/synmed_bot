import asyncio
import os
import json

import synmed_utils.doctor_registry as registry
from services.paystack import (
    PaystackError,
    create_payment_reference,
    get_payment_by_reference,
    get_latest_valid_payment_for_patient,
    initialize_transaction,
    mark_payment_status,
    mark_payment_verified,
    verify_transaction,
)
from services.patient_records import get_patient_by_identifier, register_patient, update_patient_record
from .auth_service import hash_patient_password, send_patient_email_verification


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


def get_payment_config() -> dict:
    return {
        "currency": PAYSTACK_CURRENCY,
        "new_patient_fee": NEW_PATIENT_FEE,
        "returning_patient_fee": RETURNING_PATIENT_FEE,
        "new_patient_label": NEW_PATIENT_LABEL,
        "returning_patient_label": RETURNING_PATIENT_LABEL,
    }


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
        return {
            "active": False,
            "message": "No active 24-hour consultation payment was found. Start a new payment to continue.",
            "payment": None,
        }

    return {
        "active": True,
        "message": "A valid payment is still active for this patient within the 24-hour access window.",
        "payment": {
            "reference": payment["reference"],
            "payment_token": payment["payment_token"],
            "verified_at": payment["verified_at"],
            "amount": payment["amount"],
            "currency": payment["currency"],
            "label": payment["label"],
            "patient_type": payment["patient_type"],
        },
    }


async def initialize_web_payment(payload: dict) -> dict:
    patient_type = payload["patient_type"]
    if patient_type == "new":
        amount = NEW_PATIENT_FEE
        label = NEW_PATIENT_LABEL
    else:
        amount = RETURNING_PATIENT_FEE
        label = RETURNING_PATIENT_LABEL

    patient_identifier = payload.get("patient_id") or ""
    patient = get_patient_by_identifier(patient_identifier) if patient_identifier else None
    if patient:
        registry.remove_patient_from_queue(patient["id"])

    reference = create_payment_reference()
    metadata = {
        "patient_type": patient_type,
        "patient_id": patient_identifier,
        "source": "web_portal",
        "telegram_id": 0,
    }
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
        metadata["registration_payload_json"] = json.dumps(
            {
                "name": registration["name"].strip(),
                "age": int(registration["age"]),
                "gender": registration["gender"].strip(),
                "phone": registration["phone"].strip(),
                "address": registration["address"].strip(),
                "allergy": (registration.get("allergy") or "").strip(),
                "medical_conditions": (registration.get("medical_conditions") or "").strip(),
                "email": registration["email"].strip(),
                "password_hash": hash_patient_password(registration["password"]),
            }
        )

    result = await initialize_transaction(
        email=payload["email"],
        amount_ngn=amount,
        currency=PAYSTACK_CURRENCY,
        reference=reference,
        label=label,
        metadata=metadata,
    )

    return {
        "initialized": True,
        "message": "Payment initialized successfully.",
        "reference": reference,
        "authorization_url": result["authorization_url"],
        "access_code": result["access_code"],
        "amount": amount,
        "currency": PAYSTACK_CURRENCY,
        "label": label,
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

    verification = await verify_transaction(reference)
    paystack_status = (verification.get("status") or "").lower()
    amount_ngn = int(verification.get("amount", 0)) // 100
    currency = verification.get("currency")

    if paystack_status != "success":
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
        asyncio.create_task(
            asyncio.to_thread(
                send_patient_email_verification,
                hospital_number=patient["hospital_number"],
                email=patient["email"],
            )
        )
    if patient:
        registry.remove_patient_from_queue(patient["id"])
    if patient and payment["email"] and payment["email"] != (patient.get("email") or ""):
        patient = update_patient_record(payment_patient_id, "email", payment["email"])

    mark_payment_verified(
        reference,
        paystack_status=paystack_status,
        patient_id=payment_patient_id or None,
    )

    return {
        "verified": True,
        "message": (
            "Payment verified, registration completed, and a verification email has been sent. Verify your email before signing in."
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
    }
