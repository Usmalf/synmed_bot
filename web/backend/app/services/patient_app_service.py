import hmac

from database import get_connection
from services.consultation_records import get_patient_history_by_identifier
from services.paystack import get_latest_valid_payment_for_patient
from services.patient_records import get_patient_by_identifier, register_patient, update_patient_record
from .auth_service import hash_patient_password, send_patient_email_verification
from .medical_report_app_service import (
    create_patient_medical_report_request,
    initialize_medical_report_payment,
    list_patient_medical_report_requests,
    verify_medical_report_payment,
)


def _generated_document_url(asset_path: str | None) -> str:
    filename = (asset_path or "").replace("generated_documents/", "", 1)
    return f"/generated-documents/{filename}" if filename else ""


def _patient_documents_for_consultation(consultation_id: str) -> list[dict]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT rx_id AS document_id, created_at, asset_path, asset_type
            FROM prescriptions
            WHERE consultation_id = ? AND asset_path IS NOT NULL
            ORDER BY created_at DESC
            """,
            (consultation_id,),
        )
        prescription_rows = cursor.fetchall()
        cursor.execute(
            """
            SELECT request_id AS document_id, created_at, asset_path, asset_type
            FROM investigation_requests
            WHERE consultation_id = ? AND asset_path IS NOT NULL
            ORDER BY created_at DESC
            """,
            (consultation_id,),
        )
        investigation_rows = cursor.fetchall()
        cursor.execute(
            """
            SELECT letter_id AS document_id, created_at, asset_path, asset_type
            FROM clinical_letters
            WHERE consultation_id = ? AND letter_type = 'medical_report' AND asset_path IS NOT NULL
            ORDER BY created_at DESC
            """,
            (consultation_id,),
        )
        medical_report_rows = cursor.fetchall()

    documents = []
    for row in prescription_rows:
        documents.append(
            {
                "document_id": row["document_id"],
                "kind": "prescription",
                "title": "Prescription",
                "created_at": row["created_at"],
                "asset_url": _generated_document_url(row["asset_path"]),
                "asset_type": row["asset_type"] or "image/png",
            }
        )
    for row in investigation_rows:
        documents.append(
            {
                "document_id": row["document_id"],
                "kind": "investigation",
                "title": "Investigation Request",
                "created_at": row["created_at"],
                "asset_url": _generated_document_url(row["asset_path"]),
                "asset_type": row["asset_type"] or "image/png",
            }
        )
    for row in medical_report_rows:
        documents.append(
            {
                "document_id": row["document_id"],
                "kind": "medical_report",
                "title": "Medical Report",
                "created_at": row["created_at"],
                "asset_url": _generated_document_url(row["asset_path"]),
                "asset_type": row["asset_type"] or "application/pdf",
            }
        )
    documents.sort(key=lambda item: item["created_at"], reverse=True)
    return documents


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
                    "diagnosis": item["diagnosis"] or "",
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
            "medical_reports": [
                {
                    "consultation_id": item["consultation_id"],
                    "diagnosis": item["diagnosis"] or "N/A",
                    "report_text": item["body_text"] or "",
                    "notes": item["notes"] or "",
                    "created_at": item["created_at"],
                    "asset_url": (
                        f"/generated-documents/{(item['asset_path'] or '').replace('generated_documents/', '', 1)}"
                        if item["asset_path"]
                        else ""
                    ),
                    "asset_type": item["asset_type"] or "application/pdf",
                }
                for item in history.get("medical_reports", [])
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
            "message": "No active clinical document files are available after the 24-hour payment window.",
            "documents": [],
        }

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT consultation_id
            FROM consultations
            WHERE patient_id = ?
              AND payment_reference = ?
            ORDER BY COALESCE(closed_at, created_at) DESC
            LIMIT 1
            """,
            (patient["hospital_number"], payment["reference"]),
        )
        consultation = cursor.fetchone()
        if not consultation:
            cursor.execute(
                """
                SELECT consultation_id
                FROM consultations
                WHERE patient_id = ?
                ORDER BY COALESCE(closed_at, created_at) DESC
                LIMIT 1
                """,
                (patient["hospital_number"],),
            )
            consultation = cursor.fetchone()

    if not consultation:
        return {
            "found": False,
            "message": "No consultation documents were found for this patient yet.",
            "documents": [],
            "reference": payment["reference"],
        }

    documents = _patient_documents_for_consultation(consultation["consultation_id"])
    return {
        "found": bool(documents),
        "message": "Clinical documents loaded." if documents else "No clinical documents have been issued for this consultation yet.",
        "consultation_id": consultation["consultation_id"],
        "documents": documents,
        "reference": payment["reference"],
    }


def list_current_patient_medical_report_requests(identifier: str) -> dict:
    return list_patient_medical_report_requests(identifier)


def create_current_patient_medical_report_request(identifier: str, payload: dict) -> dict:
    return create_patient_medical_report_request(identifier, payload)


async def initialize_current_patient_medical_report_payment(identifier: str, request_id: str, payload: dict) -> dict:
    return await initialize_medical_report_payment(request_id, identifier, payload)


async def verify_current_patient_medical_report_payment(identifier: str, request_id: str, payment_reference: str) -> dict:
    return await verify_medical_report_payment(request_id, identifier, payment_reference)
