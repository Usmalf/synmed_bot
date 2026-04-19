import json
from pathlib import Path
import sqlite3

RATINGS_FILE = Path("doctor_ratings.json")

def get_connection():
    return sqlite3.connect("synmed.db")


def migrate_ratings():
    if not RATINGS_FILE.exists():
        print("doctor_ratings.json not found.")
        return

    data = json.loads(RATINGS_FILE.read_text())

    conn = get_connection()
    cursor = conn.cursor()

    for doctor_id, ratings in data.items():
        for rating in ratings:
            cursor.execute("""
            INSERT INTO doctor_ratings
            (doctor_id, patient_id, rating, created_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(doctor_id, patient_id)
            DO UPDATE SET rating = excluded.rating
            """, (
                int(doctor_id),
                0,
                rating
            ))

    conn.commit()
    conn.close()

    print("Ratings migration completed successfully.")


if __name__ == "__main__":
    migrate_ratings()
