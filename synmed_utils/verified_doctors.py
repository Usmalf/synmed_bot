from database import get_connection


# Database-backed cache only. Verification source of truth is the SQLite DB.
verified_doctors: set[int] = set()


def _query_verified_doctor_ids() -> set[int]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT d.telegram_id
        FROM doctors d
        INNER JOIN doctor_profiles dp ON dp.telegram_id = d.telegram_id
        WHERE d.status = 'verified' AND dp.verified = 1
        """
    )
    rows = cursor.fetchall()
    conn.close()
    return {row["telegram_id"] for row in rows}


def load_verified():
    global verified_doctors
    verified_doctors = _query_verified_doctor_ids()


def save_verified():
    load_verified()


def is_verified(doctor_id: int) -> bool:
    return doctor_id in _query_verified_doctor_ids()


def get_verified_doctor_ids() -> set[int]:
    return _query_verified_doctor_ids()


def add_verified_doctor(doctor_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO doctors (telegram_id, status)
        VALUES (?, ?)
        ON CONFLICT(telegram_id)
        DO UPDATE SET status = 'verified'
        """,
        (doctor_id, "verified"),
    )
    conn.commit()
    conn.close()
    load_verified()


def remove_verified_doctor(doctor_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE doctors SET status = 'unverified' WHERE telegram_id = ?",
        (doctor_id,),
    )
    conn.commit()
    conn.close()
    load_verified()


load_verified()
