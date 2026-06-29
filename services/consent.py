from datetime import datetime, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from database import get_connection


POLICY_VERSION = "ndpa-2025-02"

CONSENT_SUMMARY = (
    "Before you continue, please review and accept the SynMed Telehealth "
    "Data Protection and Telemedicine Consent Policy."
)

CONSENT_POLICY_TEXT = (
    "SynMed Telehealth Data Protection and Telemedicine Consent Policy\n\n"
    "1. We collect only the personal and medical information needed to provide "
    "remote medical consultation, follow-up, prescriptions, investigations, "
    "referrals, billing support, and record keeping.\n\n"
    "2. Your data may include your name, age, contact details, hospital number, "
    "medical history, allergies, consultation notes, prescriptions, investigation "
    "requests, payment status, and other clinically relevant information.\n\n"
    "3. Your information is used to deliver care, coordinate doctors and support "
    "staff, maintain medical records, comply with legal obligations, and improve "
    "service quality.\n\n"
    "4. Access to your information is restricted to authorised SynMed personnel "
    "who need it for care delivery, support, audit, compliance, or technical "
    "operations.\n\n"
    "5. By using this service, you understand that telemedicine has limits and "
    "may not replace physical examination where necessary. In emergencies, please "
    "go to the nearest hospital immediately.\n\n"
    "6. In line with the Nigeria Data Protection Act and related healthcare "
    "obligations, you may request correction of inaccurate biodata and ask "
    "questions about how your information is handled.\n\n"
    "7. If you disagree with this policy, you should not proceed with consultation "
    "through this bot."
)


def consent_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("View Full Policy", callback_data="consent:view")],
            [
                InlineKeyboardButton("I Agree", callback_data="consent:agree"),
                InlineKeyboardButton("I Disagree", callback_data="consent:disagree"),
            ],
        ]
    )


def has_patient_consented(telegram_id: int) -> bool:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id
            FROM patient_consents
            WHERE telegram_id = ?
              AND policy_version = ?
            """,
            (telegram_id, POLICY_VERSION),
        )
        row = cursor.fetchone()
    return row is not None


def record_patient_consent(telegram_id: int, channel: str = "telegram"):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO patient_consents (telegram_id, agreed_at, policy_version, channel)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                agreed_at = excluded.agreed_at,
                policy_version = excluded.policy_version,
                channel = excluded.channel
            """,
            (
                telegram_id,
                datetime.now(timezone.utc).isoformat(),
                POLICY_VERSION,
                channel,
            ),
        )
        conn.commit()
