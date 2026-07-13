import os
from datetime import datetime, timezone
from uuid import uuid4

from database import get_connection


UTC = timezone.utc
DEFAULT_PAYOUT_PREFERENCE = "weekly"
PAYOUT_PREFERENCES = {"immediate", "weekly", "monthly"}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _doctor_earning_amount() -> int:
    try:
        return max(0, int(os.getenv("DOCTOR_CONSULTATION_EARNING_NGN", "1000")))
    except ValueError:
        return 1000


def _normalize_preference(value: str | None) -> str:
    preference = (value or DEFAULT_PAYOUT_PREFERENCE).strip().lower()
    return preference if preference in PAYOUT_PREFERENCES else DEFAULT_PAYOUT_PREFERENCE


def get_doctor_payout_preference(doctor_id: str | int) -> str:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT payout_preference
            FROM doctor_payout_preferences
            WHERE doctor_id = ?
            """,
            (str(doctor_id),),
        )
        row = cursor.fetchone()
    return _normalize_preference(row["payout_preference"] if row else None)


def set_doctor_payout_preference(doctor_id: str | int, preference: str) -> dict:
    normalized = _normalize_preference(preference)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO doctor_payout_preferences (doctor_id, payout_preference, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(doctor_id) DO UPDATE SET
                payout_preference = excluded.payout_preference,
                updated_at = excluded.updated_at
            """,
            (str(doctor_id), normalized, _now_iso()),
        )
        conn.commit()
    return {"updated": True, "doctor_id": str(doctor_id), "payout_preference": normalized}


def ensure_doctor_earning_for_consultation(consultation_id: str) -> dict:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT consultation_id, patient_id, doctor_id, status, closed_at
            FROM consultations
            WHERE consultation_id = ?
            """,
            (consultation_id,),
        )
        consultation = cursor.fetchone()
        if not consultation or consultation["status"] != "closed" or not consultation["doctor_id"]:
            return {"created": False, "message": "Consultation is not closed or has no doctor."}

        cursor.execute(
            "SELECT earning_id FROM doctor_earnings WHERE consultation_id = ?",
            (consultation_id,),
        )
        existing = cursor.fetchone()
        if existing:
            return {"created": False, "earning_id": existing["earning_id"], "message": "Earning already exists."}

        doctor_id = str(consultation["doctor_id"])
        preference = get_doctor_payout_preference(doctor_id)
        earning_id = f"earn-{uuid4().hex[:14]}"
        cursor.execute(
            """
            INSERT INTO doctor_earnings (
                earning_id, consultation_id, doctor_id, patient_id, amount, currency,
                status, payout_preference, earned_at, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                earning_id,
                consultation_id,
                doctor_id,
                consultation["patient_id"],
                _doctor_earning_amount(),
                "NGN",
                "unpaid",
                preference,
                consultation["closed_at"] or _now_iso(),
                "Created when consultation was closed.",
            ),
        )
        conn.commit()
    return {"created": True, "earning_id": earning_id}


def mark_doctor_earning_paid(earning_id: str, admin_id: str | int) -> dict:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE doctor_earnings
            SET status = 'paid',
                marked_paid_at = ?,
                marked_paid_by_admin_id = ?
            WHERE earning_id = ?
            """,
            (_now_iso(), str(admin_id), earning_id),
        )
        updated = cursor.rowcount
        conn.commit()
    return {"updated": bool(updated), "earning_id": earning_id}


def list_doctor_earnings() -> dict:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                de.earning_id, de.consultation_id, de.doctor_id, de.patient_id,
                de.amount, de.currency, de.status, de.payout_preference,
                de.earned_at, de.marked_paid_at, de.marked_paid_by_admin_id,
                COALESCE(dp.name, d.name, 'Doctor ' || de.doctor_id) AS doctor_name,
                COALESCE(p.name, 'Patient ' || COALESCE(de.patient_id, '')) AS patient_name
            FROM doctor_earnings de
            LEFT JOIN doctor_profiles dp ON dp.telegram_id = CAST(de.doctor_id AS INTEGER)
            LEFT JOIN doctors d ON d.doctor_id = de.doctor_id OR CAST(d.telegram_id AS TEXT) = de.doctor_id
            LEFT JOIN patients p ON UPPER(p.patient_id) = UPPER(COALESCE(de.patient_id, ''))
            ORDER BY datetime(de.earned_at) DESC, de.id DESC
            """
        )
        earnings = [dict(row) for row in cursor.fetchall()]
        cursor.execute(
            """
            SELECT
                COALESCE(dp.telegram_id, d.telegram_id) AS doctor_id,
                COALESCE(dp.name, d.name, 'Doctor') AS doctor_name,
                COALESCE(pref.payout_preference, ?) AS payout_preference,
                COALESCE(SUM(CASE WHEN de.status = 'unpaid' THEN de.amount ELSE 0 END), 0) AS unpaid_amount,
                COALESCE(SUM(CASE WHEN de.status = 'paid' THEN de.amount ELSE 0 END), 0) AS paid_amount,
                COUNT(de.earning_id) AS completed_consultations
            FROM doctor_profiles dp
            LEFT JOIN doctors d ON d.telegram_id = dp.telegram_id
            LEFT JOIN doctor_payout_preferences pref ON pref.doctor_id = CAST(dp.telegram_id AS TEXT)
            LEFT JOIN doctor_earnings de ON de.doctor_id = CAST(dp.telegram_id AS TEXT)
            WHERE COALESCE(dp.verified, 0) = 1
            GROUP BY dp.telegram_id, dp.name, d.telegram_id, d.name, pref.payout_preference
            ORDER BY doctor_name COLLATE NOCASE
            """,
            (DEFAULT_PAYOUT_PREFERENCE,),
        )
        summaries = [dict(row) for row in cursor.fetchall()]

    totals = {
        "unpaid_amount": sum(int(item["amount"] or 0) for item in earnings if item["status"] == "unpaid"),
        "paid_amount": sum(int(item["amount"] or 0) for item in earnings if item["status"] == "paid"),
        "completed_consultations": len(earnings),
    }
    return {"earnings": earnings, "summaries": summaries, "totals": totals, "currency": "NGN"}
