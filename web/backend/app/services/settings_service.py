import os
from datetime import datetime, timezone

from database import get_connection


UTC = timezone.utc


DEFAULT_PAYMENT_SETTINGS = {
    "new_patient_fee": os.getenv("NEW_PATIENT_FEE_NGN", "3000"),
    "returning_patient_fee": os.getenv("RETURNING_PATIENT_FEE_NGN", "2000"),
    "new_patient_label": os.getenv("NEW_PATIENT_PAYMENT_LABEL", "SynMed Registration + Consultation Fee"),
    "returning_patient_label": os.getenv("RETURNING_PATIENT_PAYMENT_LABEL", "SynMed Consultation Fee"),
    "followup_fee": os.getenv("FOLLOWUP_FEE_NGN", "2000"),
    "followup_label": os.getenv("FOLLOWUP_PAYMENT_LABEL", "SynMed Appointment Booking Fee"),
    "medical_report_fee": os.getenv("MEDICAL_REPORT_FEE_NGN", "5000"),
    "medical_report_label": os.getenv("MEDICAL_REPORT_LABEL", "SynMed Medical Report Fee"),
}

DEFAULT_EMAIL_BRANDING_SETTINGS = {
    "email_brand_name": os.getenv("EMAIL_BRAND_NAME", "SynMed Telehealth"),
    "email_logo_url": os.getenv("EMAIL_LOGO_URL", ""),
    "email_support_address": os.getenv("SUPPORT_EMAIL", os.getenv("SMTP_FROM_EMAIL", "")),
    "email_footer_text": os.getenv(
        "EMAIL_FOOTER_TEXT",
        "This message was sent by SynMed Telehealth. Please do not share OTP codes with anyone.",
    ),
}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _ensure_app_settings_table(cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS app_settings (
            setting_key TEXT PRIMARY KEY,
            setting_value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


def _read_settings(keys: list[str]) -> dict[str, str]:
    if not keys:
        return {}
    placeholders = ",".join("?" for _ in keys)
    with get_connection() as conn:
        cursor = conn.cursor()
        _ensure_app_settings_table(cursor)
        cursor.execute(
            f"SELECT setting_key, setting_value FROM app_settings WHERE setting_key IN ({placeholders})",
            keys,
        )
        rows = cursor.fetchall()
        conn.commit()
    return {row["setting_key"]: row["setting_value"] for row in rows}


def _write_settings(values: dict[str, str]) -> None:
    timestamp = _now_iso()
    with get_connection() as conn:
        cursor = conn.cursor()
        _ensure_app_settings_table(cursor)
        for key, value in values.items():
            cursor.execute(
                """
                INSERT INTO app_settings (setting_key, setting_value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(setting_key) DO UPDATE SET
                    setting_value = excluded.setting_value,
                    updated_at = excluded.updated_at
                """,
                (key, str(value), timestamp),
            )
        conn.commit()


def _positive_int(value: str, fallback: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = int(fallback)
    return max(1, number)


def get_payment_settings() -> dict:
    values = {**DEFAULT_PAYMENT_SETTINGS, **_read_settings(list(DEFAULT_PAYMENT_SETTINGS.keys()))}
    return {
        "currency": os.getenv("PAYSTACK_CURRENCY", "NGN"),
        "new_patient_fee": _positive_int(values["new_patient_fee"], DEFAULT_PAYMENT_SETTINGS["new_patient_fee"]),
        "returning_patient_fee": _positive_int(values["returning_patient_fee"], DEFAULT_PAYMENT_SETTINGS["returning_patient_fee"]),
        "new_patient_label": values["new_patient_label"].strip() or DEFAULT_PAYMENT_SETTINGS["new_patient_label"],
        "returning_patient_label": values["returning_patient_label"].strip() or DEFAULT_PAYMENT_SETTINGS["returning_patient_label"],
        "followup_fee": _positive_int(values["followup_fee"], DEFAULT_PAYMENT_SETTINGS["followup_fee"]),
        "followup_label": values["followup_label"].strip() or DEFAULT_PAYMENT_SETTINGS["followup_label"],
        "medical_report_fee": _positive_int(values["medical_report_fee"], DEFAULT_PAYMENT_SETTINGS["medical_report_fee"]),
        "medical_report_label": values["medical_report_label"].strip() or DEFAULT_PAYMENT_SETTINGS["medical_report_label"],
    }


def get_email_branding_settings() -> dict:
    values = {**DEFAULT_EMAIL_BRANDING_SETTINGS, **_read_settings(list(DEFAULT_EMAIL_BRANDING_SETTINGS.keys()))}
    return {
        "brand_name": values["email_brand_name"].strip() or DEFAULT_EMAIL_BRANDING_SETTINGS["email_brand_name"],
        "logo_url": values["email_logo_url"].strip(),
        "support_address": values["email_support_address"].strip(),
        "footer_text": values["email_footer_text"].strip() or DEFAULT_EMAIL_BRANDING_SETTINGS["email_footer_text"],
    }


def update_email_branding_settings(payload: dict) -> dict:
    brand_name = (payload.get("brand_name") or "").strip()
    logo_url = (payload.get("logo_url") or "").strip()
    support_address = (payload.get("support_address") or "").strip()
    footer_text = (payload.get("footer_text") or "").strip()
    if not brand_name:
        return {"updated": False, "message": "Brand name cannot be empty.", "email_branding": get_email_branding_settings()}
    if logo_url and not logo_url.lower().startswith(("http://", "https://")):
        return {"updated": False, "message": "Logo URL must start with http:// or https://.", "email_branding": get_email_branding_settings()}

    _write_settings(
        {
            "email_brand_name": brand_name,
            "email_logo_url": logo_url,
            "email_support_address": support_address,
            "email_footer_text": footer_text,
        }
    )
    return {"updated": True, "message": "Email branding settings updated.", "email_branding": get_email_branding_settings()}


def update_payment_settings(payload: dict) -> dict:
    new_patient_fee = _positive_int(payload.get("new_patient_fee"), DEFAULT_PAYMENT_SETTINGS["new_patient_fee"])
    returning_patient_fee = _positive_int(payload.get("returning_patient_fee"), DEFAULT_PAYMENT_SETTINGS["returning_patient_fee"])
    followup_fee = _positive_int(payload.get("followup_fee"), DEFAULT_PAYMENT_SETTINGS["followup_fee"])
    medical_report_fee = _positive_int(payload.get("medical_report_fee"), DEFAULT_PAYMENT_SETTINGS["medical_report_fee"])
    new_patient_label = (payload.get("new_patient_label") or "").strip()
    returning_patient_label = (payload.get("returning_patient_label") or "").strip()
    followup_label = (payload.get("followup_label") or "").strip()
    medical_report_label = (payload.get("medical_report_label") or "").strip()
    if not new_patient_label or not returning_patient_label or not followup_label or not medical_report_label:
        return {"updated": False, "message": "Payment labels cannot be empty.", "payments": get_payment_settings()}

    _write_settings(
        {
            "new_patient_fee": str(new_patient_fee),
            "returning_patient_fee": str(returning_patient_fee),
            "new_patient_label": new_patient_label,
            "returning_patient_label": returning_patient_label,
            "followup_fee": str(followup_fee),
            "followup_label": followup_label,
            "medical_report_fee": str(medical_report_fee),
            "medical_report_label": medical_report_label,
        }
    )
    return {"updated": True, "message": "Payment settings updated.", "payments": get_payment_settings()}


def get_paystack_readiness() -> dict:
    secret_ready = bool(os.getenv("PAYSTACK_SECRET_KEY", "").strip())
    public_ready = bool(os.getenv("PAYSTACK_PUBLIC_KEY", "").strip())
    ready = secret_ready and public_ready
    if ready:
        message = "Paystack keys are configured for payment initialization and verification."
    elif secret_ready:
        message = "Paystack secret key is configured, but the public key is missing."
    elif public_ready:
        message = "Paystack public key is configured, but the secret key is missing."
    else:
        message = "Paystack keys are missing."
    return {
        "label": "Paystack",
        "ready": ready,
        "message": message,
        "currency": os.getenv("PAYSTACK_CURRENCY", "NGN"),
    }
