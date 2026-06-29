import os

def get_verified_doctors():
    raw = os.getenv("VERIFIED_DOCTORS", "")
    return {int(d.strip()) for d in raw.split(",") if d.strip()}

def is_verified_doctor(user_id: int) -> bool:
    return user_id in get_verified_doctors()
