import os

# Cache admins at startup
_ADMIN_IDS = set()
_ADMIN_IDS_RAW = None

def load_admins():
    global _ADMIN_IDS, _ADMIN_IDS_RAW
    raw = os.getenv("ADMIN_IDS", "")
    _ADMIN_IDS_RAW = raw
    _ADMIN_IDS = {int(x.strip()) for x in raw.split(",") if x.strip()}

def get_admins():
    current_raw = os.getenv("ADMIN_IDS", "")
    if _ADMIN_IDS_RAW != current_raw:
        load_admins()
    return _ADMIN_IDS

def is_admin(user_id: int) -> bool:
    return user_id in get_admins()
