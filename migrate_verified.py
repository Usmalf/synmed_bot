print("Starting migration script...")
import json
from datetime import datetime
from database import get_connection
from services.id_generator import generate_doctor_id

FILE = "verified_doctors.json"

def migrate_verified_doctors():
    with open(FILE, "r") as f:
        telegram_ids = json.load(f)

    conn = get_connection()
    cursor = conn.cursor()

    for index, telegram_id in enumerate(telegram_ids, start=1):

        doctor_id = generate_doctor_id(index)

        cursor.execute("""
        INSERT INTO doctors
        (doctor_id, telegram_id, status, created_at)
        VALUES (?, ?, ?, ?)
        """, (
            doctor_id,
            telegram_id,
            "verified",
            datetime.utcnow().isoformat()
        ))

    conn.commit()
    conn.close()

    print("Migration completed.")

if __name__ == "__main__":
    migrate_verified_doctors()