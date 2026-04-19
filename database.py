import os
import sqlite3
from dotenv import load_dotenv

load_dotenv()

def get_database_path():
    return os.getenv("DATABASE_PATH", "synmed.db")


def get_connection():
    conn = sqlite3.connect(get_database_path())
    conn.row_factory = sqlite3.Row
    return conn


def rebuild_feedback_table(cursor, table_name: str, value_column: str):
    legacy_name = f"{table_name}_legacy"
    cursor.execute(f"DROP TABLE IF EXISTS {legacy_name}")
    cursor.execute(f"ALTER TABLE {table_name} RENAME TO {legacy_name}")

    value_definition = (
        "INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5)"
        if value_column == "rating"
        else "TEXT NOT NULL"
    )

    cursor.execute(f"""
    CREATE TABLE {table_name} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        consultation_id TEXT NOT NULL UNIQUE,
        doctor_id INTEGER NOT NULL,
        patient_id INTEGER NOT NULL,
        {value_column} {value_definition},
        created_at TEXT NOT NULL
    )
    """)

    cursor.execute(f"""
    INSERT INTO {table_name} (consultation_id, doctor_id, patient_id, {value_column}, created_at)
    SELECT
        '{table_name}-legacy-' || id,
        COALESCE(CAST(doctor_id AS INTEGER), 0),
        COALESCE(CAST(patient_id AS INTEGER), 0),
        {value_column},
        COALESCE(created_at, CURRENT_TIMESTAMP)
    FROM {legacy_name}
    """)

    cursor.execute(f"DROP TABLE {legacy_name}")


def ensure_feedback_schema(cursor, table_name: str, value_column: str):
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = {row["name"] for row in cursor.fetchall()}
    expected = {"id", "consultation_id", "doctor_id", "patient_id", value_column, "created_at"}
    if columns and columns != expected:
        rebuild_feedback_table(cursor, table_name, value_column)


def ensure_columns(cursor, table_name: str, column_definitions: dict[str, str]):
    cursor.execute(f"PRAGMA table_info({table_name})")
    existing = {row["name"] for row in cursor.fetchall()}
    for column_name, definition in column_definitions.items():
        if column_name not in existing:
            cursor.execute(
                f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"
            )


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS doctors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        doctor_id TEXT UNIQUE,
        telegram_id INTEGER UNIQUE,
        name TEXT,
        qualification TEXT,
        license_no TEXT,
        signature_path TEXT,
        status TEXT,
        created_at TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS patients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id TEXT UNIQUE,
        telegram_id INTEGER UNIQUE,
        name TEXT,
        age INTEGER,
        gender TEXT,
        phone TEXT,
        created_at TEXT
    )
    """)
    ensure_columns(
        cursor,
        "patients",
        {
            "email": "TEXT",
            "email_verified_at": "TEXT",
            "address": "TEXT",
            "allergy": "TEXT",
            "medical_conditions": "TEXT",
            "password_hash": "TEXT",
            "updated_at": "TEXT",
        },
    )

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reference TEXT NOT NULL UNIQUE,
        telegram_id INTEGER NOT NULL,
        patient_id TEXT,
        email TEXT NOT NULL,
        amount INTEGER NOT NULL,
        currency TEXT NOT NULL,
        patient_type TEXT NOT NULL,
        label TEXT NOT NULL,
        authorization_url TEXT,
        access_code TEXT,
        status TEXT NOT NULL,
        paystack_status TEXT,
        created_at TEXT NOT NULL,
        verified_at TEXT
    )
    """)
    ensure_columns(
        cursor,
        "payments",
        {
            "payment_token": "TEXT",
            "payment_token_used_at": "TEXT",
            "registration_payload_json": "TEXT",
        },
    )

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS consultations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        consultation_id TEXT UNIQUE,
        patient_id TEXT,
        doctor_id TEXT,
        status TEXT,
        notes TEXT,
        created_at TEXT,
        closed_at TEXT
    )
    """)
    ensure_columns(
        cursor,
        "consultations",
        {
            "patient_telegram_id": "INTEGER",
            "doctor_telegram_id": "INTEGER",
            "doctor_private_notes": "TEXT",
            "diagnosis": "TEXT",
            "saved_at": "TEXT",
        },
    )

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS consultation_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        consultation_id TEXT NOT NULL,
        sender_id INTEGER NOT NULL,
        sender_role TEXT NOT NULL,
        message_text TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """)
    ensure_columns(
        cursor,
        "consultation_messages",
        {
            "asset_path": "TEXT",
            "asset_type": "TEXT",
        },
    )

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS consultation_timeline (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        consultation_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        actor_id TEXT,
        details TEXT,
        created_at TEXT NOT NULL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS admin_audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_id INTEGER NOT NULL,
        action TEXT NOT NULL,
        target_type TEXT NOT NULL,
        target_id TEXT NOT NULL,
        details TEXT,
        created_at TEXT NOT NULL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS follow_up_appointments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        appointment_id TEXT NOT NULL UNIQUE,
        consultation_id TEXT NOT NULL,
        patient_id TEXT NOT NULL,
        doctor_id TEXT NOT NULL,
        scheduled_for TEXT NOT NULL,
        notes TEXT,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """)
    ensure_columns(
        cursor,
        "follow_up_appointments",
        {
            "reminder_sent_at": "TEXT",
            "payment_status": "TEXT DEFAULT 'unpaid'",
            "payment_reference": "TEXT",
            "payment_token": "TEXT",
            "confirmed_at": "TEXT",
        },
    )

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS prescriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rx_id TEXT,
        consultation_id TEXT,
        doctor_id TEXT,
        patient_id TEXT,
        version INTEGER,
        medication_json TEXT,
        notes TEXT,
        is_latest INTEGER,
        created_at TEXT
    )
    """)
    ensure_columns(
        cursor,
        "prescriptions",
        {
            "asset_path": "TEXT",
            "asset_type": "TEXT",
        },
    )

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS investigation_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id TEXT,
        consultation_id TEXT,
        doctor_id TEXT,
        patient_id TEXT,
        diagnosis TEXT,
        tests_text TEXT,
        notes TEXT,
        created_at TEXT
    )
    """)
    ensure_columns(
        cursor,
        "investigation_requests",
        {
            "asset_path": "TEXT",
            "asset_type": "TEXT",
        },
    )

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS clinical_letters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        letter_id TEXT NOT NULL UNIQUE,
        consultation_id TEXT NOT NULL,
        doctor_id TEXT NOT NULL,
        patient_id TEXT NOT NULL,
        document_type TEXT NOT NULL,
        diagnosis TEXT NOT NULL,
        body_text TEXT NOT NULL,
        target_hospital TEXT,
        created_at TEXT NOT NULL,
        asset_path TEXT,
        asset_type TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS doctor_ratings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        consultation_id TEXT NOT NULL UNIQUE,
        doctor_id INTEGER NOT NULL,
        patient_id INTEGER NOT NULL,
        rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
        created_at TEXT NOT NULL
    )
    """)
    ensure_feedback_schema(cursor, "doctor_ratings", "rating")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS doctor_reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        consultation_id TEXT NOT NULL UNIQUE,
        doctor_id INTEGER NOT NULL,
        patient_id INTEGER NOT NULL,
        review TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """)
    ensure_feedback_schema(cursor, "doctor_reviews", "review")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS doctor_profiles (
        telegram_id INTEGER PRIMARY KEY,
        name TEXT,
        specialty TEXT,
        experience TEXT,
        license_id TEXT,
        license_file_id TEXT,
        license_file_type TEXT,
        username TEXT,
        verified INTEGER NOT NULL DEFAULT 0
    )
    """)
    ensure_columns(
        cursor,
        "doctor_profiles",
        {
            "email": "TEXT",
            "password_hash": "TEXT",
            "license_expiry_date": "TEXT",
            "updated_at": "TEXT",
        },
    )

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pending_doctor_requests (
        telegram_id INTEGER PRIMARY KEY,
        name TEXT,
        specialty TEXT,
        experience TEXT,
        license_id TEXT,
        username TEXT,
        file_id TEXT,
        file_type TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS doctor_runtime_presence (
        doctor_id INTEGER PRIMARY KEY,
        status TEXT NOT NULL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS waiting_patients_runtime (
        patient_id INTEGER PRIMARY KEY,
        queue_position INTEGER NOT NULL,
        details_json TEXT NOT NULL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS active_consultations_runtime (
        consultation_id TEXT PRIMARY KEY,
        patient_id INTEGER NOT NULL,
        doctor_id INTEGER NOT NULL,
        patient_details_json TEXT NOT NULL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS support_runtime_presence (
        agent_id INTEGER PRIMARY KEY,
        status TEXT NOT NULL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS support_waiting_runtime (
        user_id INTEGER PRIMARY KEY,
        queue_position INTEGER NOT NULL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS support_active_chats_runtime (
        session_id TEXT NOT NULL UNIQUE,
        user_id INTEGER PRIMARY KEY,
        agent_id INTEGER NOT NULL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS auth_otps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        role TEXT NOT NULL,
        identifier TEXT NOT NULL,
        delivery_target TEXT NOT NULL,
        code_hash TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        consumed_at TEXT,
        context_json TEXT,
        created_at TEXT NOT NULL
    )
    """)
    ensure_columns(
        cursor,
        "auth_otps",
        {
            "context_json": "TEXT",
        },
    )

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_consents (
        telegram_id INTEGER PRIMARY KEY,
        consent_version TEXT NOT NULL,
        status TEXT NOT NULL,
        agreed_at TEXT,
        updated_at TEXT NOT NULL
    )
    """)

    conn.commit()
    conn.close()
