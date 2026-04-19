import json
import sqlite3
from uuid import uuid4

from database import get_connection


def _json_dump(value) -> str:
    return json.dumps(value or {})


def _json_load(value: str | None):
    if not value:
        return {}
    return json.loads(value)


def save_doctor_presence(*, doctor_id: int, status: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO doctor_runtime_presence (doctor_id, status)
            VALUES (?, ?)
            ON CONFLICT(doctor_id) DO UPDATE SET status = excluded.status
            """,
            (doctor_id, status),
        )
        conn.commit()


def remove_doctor_presence(doctor_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM doctor_runtime_presence WHERE doctor_id = ?",
            (doctor_id,),
        )
        conn.commit()


def load_doctor_presence():
    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT doctor_id, status FROM doctor_runtime_presence"
            )
            return cursor.fetchall()
        except sqlite3.OperationalError:
            return []


def save_waiting_patient(*, patient_id: int, queue_position: int, details: dict):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO waiting_patients_runtime (patient_id, queue_position, details_json)
            VALUES (?, ?, ?)
            ON CONFLICT(patient_id) DO UPDATE SET
                queue_position = excluded.queue_position,
                details_json = excluded.details_json
            """,
            (patient_id, queue_position, _json_dump(details)),
        )
        conn.commit()


def remove_waiting_patient(patient_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM waiting_patients_runtime WHERE patient_id = ?",
            (patient_id,),
        )
        conn.commit()


def clear_waiting_patients():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM waiting_patients_runtime")
        conn.commit()


def load_waiting_patients():
    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT patient_id, queue_position, details_json
                FROM waiting_patients_runtime
                ORDER BY queue_position ASC
                """
            )
            rows = cursor.fetchall()
        except sqlite3.OperationalError:
            rows = []
    return [
        {
            "patient_id": row["patient_id"],
            "queue_position": row["queue_position"],
            "details": _json_load(row["details_json"]),
        }
        for row in rows
    ]


def save_active_consultation(*, consultation_id: str, patient_id: int, doctor_id: int, patient_details: dict):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO active_consultations_runtime (
                consultation_id, patient_id, doctor_id, patient_details_json
            )
            VALUES (?, ?, ?, ?)
            ON CONFLICT(consultation_id) DO UPDATE SET
                patient_id = excluded.patient_id,
                doctor_id = excluded.doctor_id,
                patient_details_json = excluded.patient_details_json
            """,
            (consultation_id, patient_id, doctor_id, _json_dump(patient_details)),
        )
        conn.commit()


def remove_active_consultation_by_user(user_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            DELETE FROM active_consultations_runtime
            WHERE patient_id = ? OR doctor_id = ?
            """,
            (user_id, user_id),
        )
        conn.commit()


def load_active_consultations():
    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT consultation_id, patient_id, doctor_id, patient_details_json
                FROM active_consultations_runtime
                """
            )
            rows = cursor.fetchall()
        except sqlite3.OperationalError:
            rows = []
    return [
        {
            "consultation_id": row["consultation_id"],
            "patient_id": row["patient_id"],
            "doctor_id": row["doctor_id"],
            "patient_details": _json_load(row["patient_details_json"]),
        }
        for row in rows
    ]


def save_support_presence(*, agent_id: int, status: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO support_runtime_presence (agent_id, status)
            VALUES (?, ?)
            ON CONFLICT(agent_id) DO UPDATE SET status = excluded.status
            """,
            (agent_id, status),
        )
        conn.commit()


def remove_support_presence(agent_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM support_runtime_presence WHERE agent_id = ?",
            (agent_id,),
        )
        conn.commit()


def load_support_presence():
    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT agent_id, status FROM support_runtime_presence"
            )
            return cursor.fetchall()
        except sqlite3.OperationalError:
            return []


def save_support_queue_user(*, user_id: int, queue_position: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO support_waiting_runtime (user_id, queue_position)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET queue_position = excluded.queue_position
            """,
            (user_id, queue_position),
        )
        conn.commit()


def remove_support_queue_user(user_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM support_waiting_runtime WHERE user_id = ?",
            (user_id,),
        )
        conn.commit()


def load_support_queue():
    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT user_id, queue_position
                FROM support_waiting_runtime
                ORDER BY queue_position ASC
                """
            )
            return cursor.fetchall()
        except sqlite3.OperationalError:
            return []


def save_support_chat(*, user_id: int, agent_id: int, session_id: str | None = None):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO support_active_chats_runtime (session_id, user_id, agent_id)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET agent_id = excluded.agent_id
            """,
            (session_id or uuid4().hex, user_id, agent_id),
        )
        conn.commit()


def remove_support_chat_by_user(user_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            DELETE FROM support_active_chats_runtime
            WHERE user_id = ? OR agent_id = ?
            """,
            (user_id, user_id),
        )
        conn.commit()


def load_support_chats():
    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT session_id, user_id, agent_id FROM support_active_chats_runtime"
            )
            return cursor.fetchall()
        except sqlite3.OperationalError:
            return []
