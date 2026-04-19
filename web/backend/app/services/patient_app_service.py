import hmac

from services.consultation_records import get_patient_history_by_identifier
from services.paystack import get_latest_valid_payment_for_patient
from services.patient_records import get_patient_by_identifier, register_patient, update_patient_record
from .auth_service import hash_patient_password, send_patient_email_verification
from .consultation_app_service import get_consultation_documents


def lookup_patient(identifier: str) -> dict:
    normalized = identifier.strip()
    if not normalized:
        return {
            "found": False,
            "message": "Hospital number or phone number is required.",
            "patient": None,
        }

    patient = get_patient_by_identifier(normalized)
    if not patient:
        return {
            "found": False,
            "message": "No patient record was found for that identifier.",
            "patient": None,
        }

    return {
        "found": True,
        "message": "Patient record found.",
        "patient": {
            "internal_id": patient["id"],
            "hospital_number": patient["hospital_number"],
            "name": patient["name"],
            "age": patient["age"],
            "gender": patient["gender"],
            "phone": patient["phone"],
            "email": patient.get("email") or "",
            "address": patient.get("address") or "",
            "allergy": patient.get("allergy") or "",
            "medical_conditions": patient.get("medical_conditions") or "",
        },
    }


def register_web_patient(payload: dict) -> dict:
    patient = register_patient(
        telegram_id=None,
        name=payload["name"].strip(),
        age=str(payload["age"]),
        gender=payload["gender"].strip(),
        phone=payload["phone"].strip(),
        address=payload["address"].strip(),
        allergy=payload.get("allergy", "").strip(),
        medical_conditions=payload.get("medical_conditions", "").strip(),
        password_hash=hash_patient_password(payload.get("password", "")),
        email=(payload.get("email") or "").strip(),
    )

    return {
        "created": True,
        "message": "Patient registration completed.",
        "patient": {
            "internal_id": patient["id"],
            "hospital_number": patient["hospital_number"],
            "name": patient["name"],
            "age": patient["age"],
            "gender": patient["gender"],
            "phone": patient["phone"],
            "email": patient.get("email") or "",
            "address": patient.get("address") or "",
            "allergy": patient.get("allergy") or "",
            "medical_conditions": patient.get("medical_conditions") or "",
        },
    }


def lookup_patient_history(identifier: str) -> dict:
    normalized = identifier.strip()
    if not normalized:
        return {
            "found": False,
            "message": "Hospital number is required to load patient history.",
            "history": None,
        }

    history = get_patient_history_by_identifier(normalized)
    if not history:
        return {
            "found": False,
            "message": "No patient history was found for that record.",
            "history": None,
        }

    return {
        "found": True,
        "message": "Patient history loaded.",
        "history": {
            "patient_id": history["patient_id"],
            "name": history["name"],
            "consultations": [
                {
                    "consultation_id": item["consultation_id"],
                    "doctor_id": item["doctor_id"],
                    "status": item["status"],
                    "summary": item["notes"] or "No summary recorded.",
                    "doctor_private_notes": item["doctor_private_notes"] or "",
                    "created_at": item["created_at"],
                    "closed_at": item["closed_at"],
                }
                for item in history["consultations"]
            ],
            "prescriptions": [
                {
                    "consultation_id": item["consultation_id"],
                    "diagnosis": item["diagnosis"],
                    "notes": item["notes"] or "",
                    "created_at": item["created_at"],
                }
                for item in history["prescriptions"]
            ],
            "investigations": [
                {
                    "consultation_id": item["consultation_id"],
                    "diagnosis": item["diagnosis"] or "N/A",
                    "tests_text": item["tests_text"] or "",
                    "notes": item["notes"] or "",
                    "created_at": item["created_at"],
                }
                for item in history["investigations"]
            ],
        },
    }


def update_patient_account(identifier: str, payload: dict) -> dict:
    patient = get_patient_by_identifier(identifier)
    if not patient:
        return {
            "found": False,
            "message": "Patient record could not be found.",
            "patient": None,
        }

    email_changed = (patient.get("email") or "").strip().lower() != (payload.get("email") or "").strip().lower()

    update_patient_record(identifier, "name", payload["name"].strip())
    update_patient_record(identifier, "age", str(payload["age"]))
    update_patient_record(identifier, "gender", payload["gender"].strip())
    update_patient_record(identifier, "phone", payload["phone"].strip())
    update_patient_record(identifier, "email", (payload.get("email") or "").strip())
    update_patient_record(identifier, "address", (payload.get("address") or "").strip())
    update_patient_record(identifier, "allergy", (payload.get("allergy") or "").strip())
    update_patient_record(identifier, "medical_conditions", (payload.get("medical_conditions") or "").strip())

    if email_changed:
        update_patient_record(identifier, "email_verified_at", "")
        if payload.get("email"):
            send_patient_email_verification(
                hospital_number=identifier,
                email=payload["email"].strip(),
            )

    return lookup_patient(identifier) | {
        "message": (
            "Patient account updated. Please verify your new email address from the mail we sent."
            if email_changed and payload.get("email")
            else "Patient account updated successfully."
        )
    }


def change_patient_password(identifier: str, current_password: str, new_password: str) -> dict:
    patient = get_patient_by_identifier(identifier)
    if not patient:
        return {
            "success": False,
            "message": "Patient record could not be found.",
        }

    current_hash = patient.get("password_hash") or ""
    if not current_hash or not hmac.compare_digest(current_hash, hash_patient_password(current_password)):
        return {
            "success": False,
            "message": "Current password is incorrect.",
        }

    update_patient_record(identifier, "password_hash", hash_patient_password(new_password))
    return {
        "success": True,
        "message": "Password changed successfully.",
    }


def lookup_current_patient_documents(identifier: str) -> dict:
    patient = get_patient_by_identifier(identifier)
    if not patient:
        return {
            "found": False,
            "message": "Patient record could not be found.",
            "documents": [],
        }

    payment = get_latest_valid_payment_for_patient(patient["hospital_number"])
    if not payment:
        return {
            "found": False,
            "message": "No active prescription or investigation files are available after the 24-hour payment window.",
            "documents": [],
        }

    result = get_consultation_documents(payment["reference"])
    return {
        "found": result["found"],
        "message": result["message"],
        "documents": result["documents"],
        "reference": payment["reference"],
    }
