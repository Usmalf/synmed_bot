from database import get_connection
from synmed_utils.doctor_ratings import get_average_rating, get_total_ratings
from synmed_utils.verified_doctors import is_verified as is_db_verified


def _row_to_profile(row):
    if row is None:
        return None
    return {
        "name": row["name"],
        "specialty": row["specialty"],
        "experience": row["experience"],
        "license_id": row["license_id"],
        "license_file_id": row["license_file_id"],
        "license_file_type": row["license_file_type"],
        "username": row["username"],
        "verified": bool(row["verified"]),
    }


class DoctorProfileStore:
    def __setitem__(self, doctor_id: int, data: dict):
        create_or_update_profile(doctor_id, data)

    def get(self, doctor_id: int, default=None):
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT name, specialty, experience, license_id, license_file_id,
                       license_file_type, username, verified
                FROM doctor_profiles
                WHERE telegram_id = ?
                """,
                (doctor_id,),
            )
            row = cursor.fetchone()
        profile = _row_to_profile(row)
        return profile if profile is not None else default

    def __contains__(self, doctor_id: int):
        return self.get(doctor_id) is not None

    def items(self):
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT telegram_id, name, specialty, experience, license_id,
                       license_file_id, license_file_type, username, verified
                FROM doctor_profiles
                ORDER BY telegram_id
                """
            )
            rows = cursor.fetchall()
        return [(row["telegram_id"], _row_to_profile(row)) for row in rows]

    def __len__(self):
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) AS total FROM doctor_profiles")
            row = cursor.fetchone()
        return row["total"] if row else 0

    def clear(self):
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM doctor_profiles")
            conn.commit()


doctor_profiles = DoctorProfileStore()


def create_or_update_profile(doctor_id: int, data: dict):
    existing = doctor_profiles.get(doctor_id, {})
    merged = {**existing, **data}
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO doctor_profiles (
                telegram_id, name, specialty, experience, license_id,
                license_file_id, license_file_type, username, verified
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                name = excluded.name,
                specialty = excluded.specialty,
                experience = excluded.experience,
                license_id = excluded.license_id,
                license_file_id = excluded.license_file_id,
                license_file_type = excluded.license_file_type,
                username = excluded.username,
                verified = excluded.verified
            """,
            (
                doctor_id,
                merged.get("name"),
                merged.get("specialty"),
                merged.get("experience"),
                merged.get("license_id"),
                merged.get("license_file_id"),
                merged.get("license_file_type"),
                merged.get("username"),
                int(bool(merged.get("verified", False))),
            ),
        )
        conn.commit()


def get_profile(doctor_id: int):
    return doctor_profiles.get(doctor_id)


def mark_verified(doctor_id: int):
    create_or_update_profile(doctor_id, {"verified": True})


def is_verified(doctor_id: int) -> bool:
    profile = doctor_profiles.get(doctor_id)
    return bool(profile and profile.get("verified") is True)


def verified_badge(doctor_id: int) -> str:
    return " ✅ Verified" if is_db_verified(doctor_id) else ""


def get_rating_summary(doctor_id: int) -> str:
    avg_rating = get_average_rating(doctor_id)
    total_reviews = get_total_ratings(doctor_id)

    if total_reviews == 0:
        return "No ratings yet"

    return f"{avg_rating:.1f} star ({total_reviews} reviews)"


def top_rated_badge(doctor_id: int) -> str:
    avg = get_average_rating(doctor_id)
    total = get_total_ratings(doctor_id)

    if total >= 10 and avg >= 4.5:
        return " 🏆 Top Rated"
    return ""


def format_doctor_intro(doctor_id: int) -> str:
    profile = doctor_profiles.get(doctor_id, {})

    name = profile.get("name", "Doctor")
    specialty = profile.get("specialty", "N/A")
    experience = profile.get("experience", "N/A")
    rating_text = get_rating_summary(doctor_id)

    return (
        "You are now connected to:\n\n"
        f"Dr. {name}{verified_badge(doctor_id)}{top_rated_badge(doctor_id)}\n"
        f"- Specialty: {specialty}\n"
        f"- Experience: {experience} years\n"
        f"- Rating: {rating_text}\n\n"
        "You may begin chatting."
    )
