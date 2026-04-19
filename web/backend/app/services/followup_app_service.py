from datetime import datetime
from uuid import uuid4

from database import get_connection
from services.followups import (
    confirm_follow_up_booking,
    get_follow_up_by_reference,
    schedule_follow_up,
)
from services.patient_records import get_patient_by_identifier, update_patient_record
from services.paystack import (
    create_payment_reference,
    get_payment_by_reference,
    initialize_transaction,
    mark_payment_status,
    mark_payment_verified,
    redeem_payment_token,
    verify_transaction,
)


PAYSTACK_CURRENCY = "NGN"
FOLLOWUP_PAYMENT_LABEL = "SynMed Appointment Booking Fee"
FOLLOWUP_FEE_NGN = 2000


def _appointment_payload(row) -> dict:
    return {
        "appointment_id": row["appointment_id"],
        "short_reference": row["appointment_id"][:8],
        "consultation_id": row["consultation_id"],
        "patient_id": row["patient_id"],
        "doctor_id": row["doctor_id"],
        "scheduled_for": row["scheduled_for"],
        "notes": row["notes"] or "",
        "status": row["status"],
        "payment_status": row["payment_status"] or "unpaid",
        "payment_reference": row["payment_reference"],
        "payment_token": row["payment_token"],
        "confirmed_at": row["confirmed_at"],
        "created_at": row["created_at"],
        "reminder_sent_at": row["reminder_sent_at"],
    }


def _patient_followups(patient_id: str) -> list[dict]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT appointment_id, consultation_id, patient_id, doctor_id,
                   scheduled_for, notes, status, created_at, reminder_sent_at,
                   payment_status, payment_reference, payment_token, confirmed_at
            FROM follow_up_appointments
            WHERE patient_id = ?
            ORDER BY scheduled_for DESC, created_at DESC
            """,
            (patient_id,),
        )
        rows = cursor.fetchall()
    return [_appointment_payload(row) for row in rows]


def list_patient_followups(patient_identifier: str) -> dict:
    patient = get_patient_by_identifier(patient_identifier)
    if not patient:
        return {
            "found": False,
            "message": "Patient record was not found.",
            "appointments": [],
        }

    appointments = _patient_followups(patient["hospital_number"])
    return {
        "found": True,
        "message": "Follow-up appointments loaded." if appointments else "No follow-up appointments found yet.",
        "appointments": appointments,
    }


def get_patient_followup(reference: str, patient_identifier: str) -> dict:
    appointment = get_follow_up_by_reference(reference)
    if not appointment:
        return {
            "found": False,
            "message": "Appointment reference could not be found.",
            "appointment": None,
        }

    if appointment["patient_id"] != patient_identifier:
        return {
            "found": False,
            "message": "This appointment does not belong to the signed-in patient.",
            "appointment": None,
        }

    return {
        "found": True,
        "message": "Appointment loaded.",
        "appointment": _appointment_payload(appointment),
    }


def create_patient_followup_booking(patient_identifier: str, payload: dict) -> dict:
    patient = get_patient_by_identifier(patient_identifier)
    if not patient:
        return {
            "created": False,
            "message": "Patient record was not found.",
            "appointment": None,
        }

    try:
        scheduled_for = datetime.strptime(
            f"{payload['scheduled_date']} {payload['scheduled_time']}",
            "%Y-%m-%d %H:%M",
        ).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return {
            "created": False,
            "message": "Appointment date or time was invalid.",
            "appointment": None,
        }

    appointment = schedule_follow_up(
        consultation_id=f"self-booked-{uuid4().hex[:12]}",
        patient_id=patient["hospital_number"],
        doctor_id=0,
        scheduled_for=scheduled_for,
        notes=(payload.get("notes") or "").strip() or "Self-booked appointment",
    )
    row = get_follow_up_by_reference(appointment["appointment_id"])
    return {
        "created": True,
        "message": "Appointment created successfully.",
        "appointment": _appointment_payload(row),
    }


async def initialize_followup_payment(reference: str, patient_identifier: str, payload: dict) -> dict:
    appointment = get_follow_up_by_reference(reference)
    if not appointment:
        return {
            "initialized": False,
            "message": "Appointment reference could not be found.",
            "appointment": None,
        }

    if appointment["patient_id"] != patient_identifier:
        return {
            "initialized": False,
            "message": "This appointment does not belong to the signed-in patient.",
            "appointment": None,
        }

    patient = get_patient_by_identifier(patient_identifier)
    if not patient:
        return {
            "initialized": False,
            "message": "Patient record linked to this appointment could not be found.",
            "appointment": None,
        }

    email = (payload.get("email") or patient.get("email") or "").strip()
    if not email:
        return {
            "initialized": False,
            "message": "An email address is required before payment can start.",
            "appointment": _appointment_payload(appointment),
        }

    if email != (patient.get("email") or ""):
        update_patient_record(patient["hospital_number"], "email", email)

    payment_reference = create_payment_reference()
    result = await initialize_transaction(
        email=email,
        amount_ngn=FOLLOWUP_FEE_NGN,
        currency=PAYSTACK_CURRENCY,
        reference=payment_reference,
        label=FOLLOWUP_PAYMENT_LABEL,
        metadata={
            "patient_type": "returning",
            "patient_id": patient["hospital_number"],
            "source": "web_appointment",
            "telegram_id": patient.get("telegram_id") or 0,
            "purpose": "appointment",
            "appointment_id": appointment["appointment_id"],
        },
    )

    return {
        "initialized": True,
        "message": "Appointment payment initialized successfully.",
        "appointment": _appointment_payload(appointment),
        "reference": payment_reference,
        "authorization_url": result["authorization_url"],
        "access_code": result["access_code"],
        "amount": FOLLOWUP_FEE_NGN,
        "currency": PAYSTACK_CURRENCY,
        "label": FOLLOWUP_PAYMENT_LABEL,
    }


async def verify_followup_payment(reference: str, patient_identifier: str, payment_reference: str) -> dict:
    appointment = get_follow_up_by_reference(reference)
    if not appointment:
        return {
            "verified": False,
            "message": "Appointment reference could not be found.",
            "appointment": None,
            "payment_reference": payment_reference,
            "paystack_status": None,
        }

    if appointment["patient_id"] != patient_identifier:
        return {
            "verified": False,
            "message": "This appointment does not belong to the signed-in patient.",
            "appointment": None,
            "payment_reference": payment_reference,
            "paystack_status": None,
        }

    payment = get_payment_by_reference(payment_reference)
    if not payment:
        return {
            "verified": False,
            "message": "Payment reference was not found.",
            "appointment": _appointment_payload(appointment),
            "payment_reference": payment_reference,
            "paystack_status": None,
        }

    if payment["patient_id"] != patient_identifier:
        return {
            "verified": False,
            "message": "That payment does not belong to the signed-in patient.",
            "appointment": _appointment_payload(appointment),
            "payment_reference": payment_reference,
            "paystack_status": None,
        }

    verification = await verify_transaction(payment_reference)
    paystack_status = (verification.get("status") or "").lower()
    amount_ngn = int(verification.get("amount", 0)) // 100
    currency = verification.get("currency")

    if paystack_status != "success":
        mark_payment_status(
            payment_reference,
            status="pending_verification",
            paystack_status=paystack_status or "pending",
        )
        return {
            "verified": False,
            "message": "Payment is not confirmed yet.",
            "appointment": _appointment_payload(appointment),
            "payment_reference": payment_reference,
            "paystack_status": paystack_status or "pending",
        }

    if amount_ngn != payment["amount"] or currency != payment["currency"]:
        mark_payment_status(
            payment_reference,
            status="amount_mismatch",
            paystack_status=paystack_status,
        )
        return {
            "verified": False,
            "message": "Payment amount or currency did not match the expected values.",
            "appointment": _appointment_payload(appointment),
            "payment_reference": payment_reference,
            "paystack_status": paystack_status,
        }

    payment_token = mark_payment_verified(
        payment_reference,
        paystack_status=paystack_status,
        patient_id=patient_identifier,
    )
    updated = confirm_follow_up_booking(
        appointment_id=appointment["appointment_id"],
        payment_status="paid",
        payment_reference=payment_reference,
        payment_token=payment_token,
    )
    return {
        "verified": True,
        "message": "Appointment payment verified successfully.",
        "appointment": _appointment_payload(updated),
        "payment_reference": payment_reference,
        "paystack_status": paystack_status,
    }


def mark_followup_pay_later(reference: str, patient_identifier: str) -> dict:
    appointment = get_follow_up_by_reference(reference)
    if not appointment:
        return {
            "success": False,
            "message": "Appointment reference could not be found.",
            "appointment": None,
        }

    if appointment["patient_id"] != patient_identifier:
        return {
            "success": False,
            "message": "This appointment does not belong to the signed-in patient.",
            "appointment": None,
        }

    updated = confirm_follow_up_booking(
        appointment_id=appointment["appointment_id"],
        payment_status="pay_later",
    )
    return {
        "success": True,
        "message": "Appointment saved with pay-later status.",
        "appointment": _appointment_payload(updated),
    }


def redeem_followup_payment_code(reference: str, patient_identifier: str, payment_code: str) -> dict:
    appointment = get_follow_up_by_reference(reference)
    if not appointment:
        return {
            "success": False,
            "message": "Appointment reference could not be found.",
            "appointment": None,
        }

    if appointment["patient_id"] != patient_identifier:
        return {
            "success": False,
            "message": "This appointment does not belong to the signed-in patient.",
            "appointment": None,
        }

    redeemed = redeem_payment_token(payment_token=payment_code.strip(), patient_id=patient_identifier)
    if not redeemed:
        return {
            "success": False,
            "message": "That payment code is invalid, expired, or does not belong to this patient.",
            "appointment": _appointment_payload(appointment),
        }

    updated = confirm_follow_up_booking(
        appointment_id=appointment["appointment_id"],
        payment_status="paid",
        payment_reference=redeemed["reference"],
        payment_token=redeemed["payment_token"],
    )
    return {
        "success": True,
        "message": "Appointment marked as paid using the supplied payment code.",
        "appointment": _appointment_payload(updated),
    }
