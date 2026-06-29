from datetime import datetime, timedelta, timezone
from uuid import uuid4

from database import get_connection


UTC = timezone.utc


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def schedule_follow_up(*, consultation_id: str, patient_id: str, doctor_id: int, scheduled_for: str, notes: str = ""):
    appointment_id = uuid4().hex
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO follow_up_appointments (
                appointment_id, consultation_id, patient_id, doctor_id,
                scheduled_for, notes, status, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                appointment_id,
                consultation_id,
                patient_id,
                str(doctor_id),
                scheduled_for,
                notes,
                "scheduled",
                _now_iso(),
            ),
        )
        conn.commit()

    return {
        "appointment_id": appointment_id,
        "consultation_id": consultation_id,
        "patient_id": patient_id,
        "doctor_id": str(doctor_id),
        "scheduled_for": scheduled_for,
        "notes": notes,
        "status": "scheduled",
    }


def get_follow_up_by_reference(reference: str):
    normalized = reference.strip().lower()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT f.appointment_id, f.consultation_id, f.patient_id, f.doctor_id,
                   f.scheduled_for, f.notes, f.status, f.created_at,
                   f.reminder_sent_at, f.payment_status, f.payment_reference,
                   f.payment_token, f.confirmed_at,
                   p.telegram_id, p.name
            FROM follow_up_appointments f
            LEFT JOIN patients p ON p.patient_id = f.patient_id
            WHERE LOWER(f.appointment_id) = ?
               OR LOWER(substr(f.appointment_id, 1, 8)) = ?
            ORDER BY f.created_at DESC
            LIMIT 1
            """,
            (normalized, normalized),
        )
        return cursor.fetchone()


def confirm_follow_up_booking(
    *,
    appointment_id: str,
    payment_status: str,
    payment_reference: str | None = None,
    payment_token: str | None = None,
):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE follow_up_appointments
            SET payment_status = ?, payment_reference = COALESCE(?, payment_reference),
                payment_token = COALESCE(?, payment_token), confirmed_at = ?
            WHERE appointment_id = ?
            """,
            (
                payment_status,
                payment_reference,
                payment_token,
                _now_iso(),
                appointment_id,
            ),
        )
        conn.commit()
    return get_follow_up_by_reference(appointment_id)


def get_upcoming_follow_ups(limit: int = 10):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT appointment_id, consultation_id, patient_id, doctor_id,
                   scheduled_for, notes, status, created_at, reminder_sent_at
            FROM follow_up_appointments
            WHERE status IN ('scheduled', 'reminded')
            ORDER BY scheduled_for ASC
            LIMIT ?
            """,
            (limit,),
        )
        return cursor.fetchall()


def get_due_follow_up_reminders(*, lead_hours: int = 24, now: datetime | None = None):
    now = now or datetime.now(UTC)
    window_end = now + timedelta(hours=lead_hours)
    due = []
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT f.appointment_id, f.consultation_id, f.patient_id, f.doctor_id,
                   f.scheduled_for, f.notes, f.status, p.telegram_id, p.name
            FROM follow_up_appointments f
            LEFT JOIN patients p ON p.patient_id = f.patient_id
            WHERE f.status = 'scheduled'
            ORDER BY f.scheduled_for ASC
            """
        )
        rows = cursor.fetchall()

    for row in rows:
        try:
            scheduled_at = datetime.strptime(row["scheduled_for"], "%Y-%m-%d %H:%M").replace(tzinfo=UTC)
        except ValueError:
            continue
        if now <= scheduled_at <= window_end:
            due.append(row)
    return due


def mark_follow_up_reminded(appointment_id: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE follow_up_appointments
            SET status = 'reminded', reminder_sent_at = ?
            WHERE appointment_id = ?
            """,
            (_now_iso(), appointment_id),
        )
        conn.commit()
