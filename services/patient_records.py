from datetime import datetime, timezone

from database import get_connection


UTC = timezone.utc


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _normalize_identifier(identifier: str) -> str:
    return identifier.strip()


def _clear_existing_telegram_link(cursor, telegram_id: int, *, exclude_patient_id: int | None = None):
    if telegram_id is None:
        return

    if exclude_patient_id is None:
        cursor.execute(
            """
            UPDATE patients
            SET telegram_id = NULL, updated_at = ?
            WHERE telegram_id = ?
            """,
            (_now_iso(), telegram_id),
        )
        return

    cursor.execute(
        """
        UPDATE patients
        SET telegram_id = NULL, updated_at = ?
        WHERE telegram_id = ? AND id != ?
        """,
        (_now_iso(), telegram_id, exclude_patient_id),
    )


def _row_to_patient(row):
    if row is None:
        return None
    return {
        "id": row["id"],
        "hospital_number": row["patient_id"],
        "telegram_id": row["telegram_id"],
        "name": row["name"],
        "age": row["age"],
        "gender": row["gender"],
        "phone": row["phone"],
        "email": row["email"],
        "email_verified_at": row["email_verified_at"],
        "address": row["address"],
        "allergy": row["allergy"],
        "medical_conditions": row["medical_conditions"],
        "password_hash": row["password_hash"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _next_hospital_number(cursor) -> str:
    cursor.execute(
        """
        SELECT patient_id
        FROM patients
        WHERE patient_id LIKE 'SM%'
        ORDER BY id DESC
        LIMIT 1
        """
    )
    row = cursor.fetchone()
    if not row or not row["patient_id"]:
        return "SM0001"

    current = row["patient_id"]
    number = int(current[2:]) + 1
    return f"SM{number:04d}"


def register_patient(
    *,
    telegram_id: int,
    name: str,
    age: str,
    gender: str,
    phone: str,
    address: str,
    allergy: str,
    medical_conditions: str = "",
    password_hash: str = "",
    email_verified_at: str | None = None,
    email: str = "",
):
    with get_connection() as conn:
        cursor = conn.cursor()
        hospital_number = _next_hospital_number(cursor)
        now = _now_iso()
        _clear_existing_telegram_link(cursor, telegram_id)
        cursor.execute(
            """
            INSERT INTO patients (
                patient_id, telegram_id, name, age, gender, phone,
                email, email_verified_at, address, allergy, medical_conditions, password_hash, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                hospital_number,
                telegram_id,
                name,
                int(age),
                gender,
                phone,
                email,
                email_verified_at,
                address,
                allergy,
                medical_conditions,
                password_hash,
                now,
                now,
            ),
        )
        conn.commit()

    return get_patient_by_identifier(hospital_number)


def get_patient_by_identifier(identifier: str):
    normalized = _normalize_identifier(identifier)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, patient_id, telegram_id, name, age, gender, phone, email,
                   email_verified_at, address, allergy, medical_conditions, password_hash, created_at, updated_at
            FROM patients
            WHERE UPPER(patient_id) = UPPER(?)
               OR phone = ?
               OR LOWER(email) = LOWER(?)
            """,
            (normalized, normalized, normalized),
        )
        row = cursor.fetchone()
    return _row_to_patient(row)


def get_patient_by_telegram_id(telegram_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, patient_id, telegram_id, name, age, gender, phone, email,
                   email_verified_at, address, allergy, medical_conditions, password_hash, created_at, updated_at
            FROM patients
            WHERE telegram_id = ?
            """,
            (telegram_id,),
        )
        row = cursor.fetchone()
    return _row_to_patient(row)


def attach_telegram_id(patient_id: int, telegram_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        _clear_existing_telegram_link(cursor, telegram_id, exclude_patient_id=patient_id)
        cursor.execute(
            """
            UPDATE patients
            SET telegram_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (telegram_id, _now_iso(), patient_id),
        )
        conn.commit()


def update_patient_record(identifier: str, field: str, value: str):
    allowed_fields = {"name", "age", "gender", "phone", "email", "email_verified_at", "address", "allergy", "medical_conditions", "password_hash"}
    if field not in allowed_fields:
        raise ValueError("Unsupported patient field.")

    patient = get_patient_by_identifier(identifier)
    if not patient:
        return None

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            UPDATE patients
            SET {field} = ?, updated_at = ?
            WHERE id = ?
            """,
            (int(value) if field == "age" else value, _now_iso(), patient["id"]),
        )
        conn.commit()

    return get_patient_by_identifier(identifier)


def get_registered_patient_count() -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) AS total FROM patients")
        row = cursor.fetchone()
    return row["total"] if row else 0


def search_patient_records(query: str, limit: int = 10):
    normalized = f"%{_normalize_identifier(query)}%"
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, patient_id, telegram_id, name, age, gender, phone, email,
                   email_verified_at, address, allergy, medical_conditions, password_hash, created_at, updated_at
            FROM patients
            WHERE patient_id LIKE ?
               OR phone LIKE ?
               OR name LIKE ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (normalized, normalized, normalized, limit),
        )
        rows = cursor.fetchall()
    return [_row_to_patient(row) for row in rows]


def patient_summary(patient: dict) -> str:
    return (
        f"Hospital Number: {patient['hospital_number']}\n"
        f"Name: {patient['name']}\n"
        f"Age: {patient['age']}\n"
        f"Gender: {patient['gender']}\n"
        f"Phone: {patient['phone']}\n"
        f"Email: {patient.get('email') or 'N/A'}\n"
        f"Address: {patient.get('address') or 'N/A'}\n"
        f"Allergy: {patient.get('allergy') or 'None recorded'}\n"
        f"Medical Conditions: {patient.get('medical_conditions') or 'None recorded'}"
    )
