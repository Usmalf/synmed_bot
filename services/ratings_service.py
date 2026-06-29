import logging
from datetime import UTC, datetime

from database import get_connection

logger = logging.getLogger(__name__)


def add_rating(consultation_id: str, doctor_id: int, patient_id: int, rating: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO doctor_ratings
            (consultation_id, doctor_id, patient_id, rating, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(consultation_id)
            DO UPDATE SET
                doctor_id = excluded.doctor_id,
                patient_id = excluded.patient_id,
                rating = excluded.rating,
                created_at = excluded.created_at
        """, (consultation_id, doctor_id, patient_id, rating, datetime.now(UTC).isoformat()))
        conn.commit()
    logger.info(
        "Rating added or updated for consultation=%s doctor=%s patient=%s rating=%s",
        consultation_id,
        doctor_id,
        patient_id,
        rating,
    )
    return {
        "consultation_id": consultation_id,
        "doctor_id": doctor_id,
        "patient_id": patient_id,
        "rating": rating,
    }


def has_rating(consultation_id: str) -> bool:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 1
            FROM doctor_ratings
            WHERE consultation_id = ?
        """, (consultation_id,))
        return cursor.fetchone() is not None


def add_review(consultation_id: str, doctor_id: int, patient_id: int, review: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 1
            FROM doctor_reviews
            WHERE consultation_id = ?
        """, (consultation_id,))
        if cursor.fetchone():
            return None

        cursor.execute("""
            INSERT INTO doctor_reviews
            (consultation_id, doctor_id, patient_id, review, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (consultation_id, doctor_id, patient_id, review, datetime.now(UTC).isoformat()))
        conn.commit()
    logger.info(
        "Review added for consultation=%s doctor=%s patient=%s",
        consultation_id,
        doctor_id,
        patient_id,
    )
    return {
        "consultation_id": consultation_id,
        "doctor_id": doctor_id,
        "patient_id": patient_id,
        "review": review,
    }


def has_review(consultation_id: str) -> bool:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 1
            FROM doctor_reviews
            WHERE consultation_id = ?
        """, (consultation_id,))
        return cursor.fetchone() is not None


def get_average_rating(doctor_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT AVG(rating) as avg_rating
            FROM doctor_ratings
            WHERE doctor_id = ?
        """, (doctor_id,))
        row = cursor.fetchone()

    avg = round(row["avg_rating"], 2) if row["avg_rating"] is not None else 0.0
    logger.info("Average rating fetched for doctor=%s avg=%s", doctor_id, avg)
    return avg


def get_total_ratings(doctor_id: int) -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) as total
            FROM doctor_ratings
            WHERE doctor_id = ?
        """, (doctor_id,))
        row = cursor.fetchone()

    total = row["total"] if row else 0
    logger.info("Total ratings fetched for doctor=%s total=%s", doctor_id, total)
    return total


def get_reviews(doctor_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT review, created_at
            FROM doctor_reviews
            WHERE doctor_id = ?
            ORDER BY created_at DESC
        """, (doctor_id,))
        rows = cursor.fetchall()

    logger.info("Fetched %s reviews for doctor=%s", len(rows), doctor_id)
    return rows
