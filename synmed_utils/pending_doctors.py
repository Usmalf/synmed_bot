from database import get_connection


def _row_to_pending(row):
    if row is None:
        return None
    return {
        "name": row["name"],
        "specialty": row["specialty"],
        "experience": row["experience"],
        "license_id": row["license_id"],
        "username": row["username"],
        "file_id": row["file_id"],
        "file_type": row["file_type"],
    }


class PendingDoctorStore:
    def __getitem__(self, doctor_id: int):
        item = self.get(doctor_id)
        if item is None:
            raise KeyError(doctor_id)
        return item

    def __setitem__(self, doctor_id: int, data: dict):
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO pending_doctor_requests (
                    telegram_id, name, specialty, experience, license_id,
                    username, file_id, file_type
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(telegram_id) DO UPDATE SET
                    name = excluded.name,
                    specialty = excluded.specialty,
                    experience = excluded.experience,
                    license_id = excluded.license_id,
                    username = excluded.username,
                    file_id = excluded.file_id,
                    file_type = excluded.file_type
                """,
                (
                    doctor_id,
                    data.get("name"),
                    data.get("specialty"),
                    data.get("experience"),
                    data.get("license_id"),
                    data.get("username"),
                    data.get("file_id"),
                    data.get("file_type"),
                ),
            )
            conn.commit()

    def __contains__(self, doctor_id: int):
        return self.get(doctor_id) is not None

    def __len__(self):
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) AS total FROM pending_doctor_requests")
            row = cursor.fetchone()
        return row["total"] if row else 0

    def __bool__(self):
        return len(self) > 0

    def get(self, doctor_id: int, default=None):
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT name, specialty, experience, license_id, username, file_id, file_type
                FROM pending_doctor_requests
                WHERE telegram_id = ?
                """,
                (doctor_id,),
            )
            row = cursor.fetchone()
        item = _row_to_pending(row)
        return item if item is not None else default

    def pop(self, doctor_id: int, default=None):
        item = self.get(doctor_id)
        if item is None:
            return default
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM pending_doctor_requests WHERE telegram_id = ?",
                (doctor_id,),
            )
            conn.commit()
        return item

    def items(self):
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT telegram_id, name, specialty, experience, license_id,
                       username, file_id, file_type
                FROM pending_doctor_requests
                ORDER BY created_at ASC, telegram_id ASC
                """
            )
            rows = cursor.fetchall()
        return [(row["telegram_id"], _row_to_pending(row)) for row in rows]

    def clear(self):
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM pending_doctor_requests")
            conn.commit()


pending_doctors = PendingDoctorStore()
