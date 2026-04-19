from datetime import datetime, timezone

from database import get_connection


UTC = timezone.utc
CONSENT_VERSION = "2026-04-19"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def has_user_agreed(telegram_id: int) -> bool:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT status, consent_version
            FROM user_consents
            WHERE telegram_id = ?
            """,
            (telegram_id,),
        )
        row = cursor.fetchone()

    return bool(
        row
        and row["status"] == "agreed"
        and row["consent_version"] == CONSENT_VERSION
    )


def record_user_consent(telegram_id: int, *, agreed: bool):
    status = "agreed" if agreed else "declined"
    agreed_at = _now_iso() if agreed else None
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO user_consents (
                telegram_id, consent_version, status, agreed_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                consent_version = excluded.consent_version,
                status = excluded.status,
                agreed_at = excluded.agreed_at,
                updated_at = excluded.updated_at
            """,
            (telegram_id, CONSENT_VERSION, status, agreed_at, _now_iso()),
        )
        conn.commit()


def build_policy_text(*, full: bool = False) -> str:
    intro = (
        "*SynMed Telehealth Data Protection & Telemedicine Consent*\n\n"
        "Before we provide consultation, please review how we use and protect your information."
    )

    summary_points = (
        "1. SynMed collects your biodata, contact details, medical history, chat messages, prescriptions, reports, and payment records only for care delivery, coordination, safety, record keeping, and lawful operations.\n"
        "2. Your information is shared only with the medical professionals, support staff, laboratories, pharmacies, payment processors, or regulators involved in your care or required by law.\n"
        "3. We use reasonable security safeguards to protect your records, but telemedicine and internet-based communication still carry some privacy and technical risks.\n"
        "4. Remote consultation does not replace emergency care. If your condition is urgent or life-threatening, please seek immediate in-person emergency help.\n"
        "5. By continuing, you confirm that the information you provide is accurate and that you consent to remote consultation, documentation, follow-up communication, and secure record retention."
    )

    if not full:
        return f"{intro}\n\n{summary_points}\n\nTap *I Agree* to continue, or *View Full Policy* if you want the complete notice."

    full_notice = (
        f"{intro}\n\n"
        "*Our Commitment*\n"
        "SynMed Telehealth is committed to handling personal and health information in a way that is transparent, fair, secure, and aligned with applicable Nigerian data protection expectations.\n\n"
        "*What We Collect*\n"
        "- Identity and contact details such as your name, age, gender, phone number, email, and address.\n"
        "- Health-related information such as symptoms, history, allergies, prior conditions, prescriptions, investigations, medical notes, reports, referrals, and consultation transcripts.\n"
        "- Operational records such as payment references, appointment details, follow-up records, and support interactions.\n\n"
        "*Why We Collect It*\n"
        "- To identify you correctly and create your patient record.\n"
        "- To assess, treat, refer, follow up, and coordinate your care.\n"
        "- To document consultations, prescriptions, investigations, referrals, and medical reports.\n"
        "- To process payments, improve service quality, maintain safety, and comply with lawful obligations.\n\n"
        "*Who May Receive It*\n"
        "- Verified doctors and authorised SynMed personnel involved in your care.\n"
        "- Laboratories, pharmacies, referral facilities, payment processors, cloud or messaging providers, and regulators where necessary for your care or legal compliance.\n"
        "- Emergency contacts or authorities if necessary to protect life, safety, or public health.\n\n"
        "*Your Rights*\n"
        "You may request access to your records, correction of inaccurate information, or help understanding how your information is being used, subject to medical, legal, and operational limits.\n\n"
        "*Telemedicine Risks*\n"
        "Remote care may be affected by network issues, incomplete information, technical delays, or privacy risks associated with electronic communication. Emergencies may require in-person treatment.\n\n"
        "*Consent*\n"
        "By tapping *I Agree*, you consent to SynMed providing telemedicine services, creating and storing your consultation records, and using your information for care delivery, follow-up, payment processing, and lawful health-service operations."
    )
    return full_notice
