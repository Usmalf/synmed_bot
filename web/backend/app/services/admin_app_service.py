from database import get_connection
from services.followups import get_due_follow_up_reminders
from services.patient_records import get_registered_patient_count


def _fetch_verified_doctors() -> list[dict]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                d.telegram_id,
                d.doctor_id,
                d.status,
                COALESCE(dp.name, 'Doctor') AS name,
                COALESCE(dp.specialty, 'N/A') AS specialty,
                COALESCE(dp.experience, 'N/A') AS experience,
                COALESCE(drp.status, 'offline') AS runtime_status
            FROM doctors d
            INNER JOIN doctor_profiles dp ON dp.telegram_id = d.telegram_id
            LEFT JOIN doctor_runtime_presence drp ON drp.doctor_id = d.telegram_id
            WHERE d.status = 'verified' AND dp.verified = 1
            ORDER BY dp.name COLLATE NOCASE ASC, d.telegram_id ASC
            """
        )
        rows = cursor.fetchall()
    return [
        {
            "telegram_id": row["telegram_id"],
            "doctor_id": row["doctor_id"] or "",
            "name": row["name"],
            "specialty": row["specialty"],
            "experience": row["experience"],
            "status": row["runtime_status"],
        }
        for row in rows
    ]


def _active_consultation_count() -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) AS total FROM active_consultations_runtime")
        row = cursor.fetchone()
    return row["total"] if row else 0


def get_admin_summary() -> dict:
    verified_doctors = _fetch_verified_doctors()
    return {
        "registered_patients": get_registered_patient_count(),
        "verified_doctors": len(verified_doctors),
        "verified_doctor_records": verified_doctors,
        "active_consultations": _active_consultation_count(),
        "due_followups": len(get_due_follow_up_reminders()),
    }
