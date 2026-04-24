from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from database import get_database_path, init_db


ROOT_DIR = Path(__file__).resolve().parent.parent
BACKUP_DIR = ROOT_DIR / "data" / "db_backups"
MEDIA_DIRS = (
    ROOT_DIR / "generated_documents",
    ROOT_DIR / "consultation_media",
)

TABLES_TO_CLEAR = (
    "patients",
    "payments",
    "consultations",
    "consultation_messages",
    "consultation_timeline",
    "follow_up_appointments",
    "prescriptions",
    "investigation_requests",
    "clinical_letters",
    "patient_consents",
    "doctor_ratings",
    "doctor_reviews",
    "doctor_profiles",
    "pending_doctor_requests",
    "doctor_runtime_presence",
    "waiting_patients_runtime",
    "active_consultations_runtime",
    "support_runtime_presence",
    "support_waiting_runtime",
    "support_active_chats_runtime",
    "auth_otps",
)


def backup_database_file(db_path: Path) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"{db_path.stem}_keep_admin_only_backup_{timestamp}{db_path.suffix}"
    shutil.copy2(db_path, backup_path)
    return backup_path


def clear_table_data(db_path: Path):
    import sqlite3

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = OFF")
        for table_name in TABLES_TO_CLEAR:
            cursor.execute(f"DELETE FROM {table_name}")
        cursor.execute("DELETE FROM sqlite_sequence")
        conn.commit()
    finally:
        conn.close()


def clear_generated_files():
    for directory in MEDIA_DIRS:
        if not directory.exists():
            continue
        for item in directory.iterdir():
            if item.is_file():
                item.unlink()


def main():
    db_path = Path(get_database_path())
    if not db_path.is_absolute():
        db_path = ROOT_DIR / db_path

    if not db_path.exists():
        raise SystemExit(f"Database file not found: {db_path}")

    backup_path = backup_database_file(db_path)
    clear_table_data(db_path)
    clear_generated_files()
    init_db()

    print("Keep-admin-only reset completed.")
    print(f"Database backup created at: {backup_path}")
    print("Admin access remains controlled by ADMIN_IDS in your environment.")
    print("All patients, doctors, support agents, payments, consultations, documents, ratings, OTPs, and runtime state were cleared.")


if __name__ == "__main__":
    main()
