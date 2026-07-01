import os
from urllib.parse import urlparse

from database import is_postgres_enabled


BACKEND_REQUIRED = [
    "DATABASE_URL",
    "AUTH_SECRET_KEY",
    "FRONTEND_BASE_URL",
    "AUTH_VERIFY_BASE_URL",
    "BACKEND_CORS_ORIGINS",
    "SYNMED_STORAGE_ROOT",
    "SYNMED_BACKUP_ROOT",
    "BOT_TOKEN",
    "ADMIN_IDS",
    "PAYSTACK_SECRET_KEY",
    "PAYSTACK_PUBLIC_KEY",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USERNAME",
    "SMTP_PASSWORD",
    "SMTP_FROM_EMAIL",
]

BACKEND_RECOMMENDED = [
    "PAYSTACK_CURRENCY",
    "SMTP_USE_TLS",
    "SMTP_USE_SSL",
    "SMTP_TIMEOUT_SECONDS",
    "EMAIL_BRAND_NAME",
    "EMAIL_LOGO_URL",
    "SUPPORT_EMAIL",
]


def _is_set(key: str) -> bool:
    return bool((os.getenv(key) or "").strip())


def _host(value: str) -> str:
    parsed = urlparse(value)
    return parsed.netloc or value


def _item(key: str, required: bool) -> dict:
    return {
        "key": key,
        "required": required,
        "set": _is_set(key),
    }


def get_deployment_readiness() -> dict:
    required = [_item(key, True) for key in BACKEND_REQUIRED]
    recommended = [_item(key, False) for key in BACKEND_RECOMMENDED]
    warnings = []

    database_url = (os.getenv("DATABASE_URL") or "").strip()
    auth_secret = os.getenv("AUTH_SECRET_KEY") or ""
    frontend_base = (os.getenv("FRONTEND_BASE_URL") or "").strip().rstrip("/")
    verify_base = (os.getenv("AUTH_VERIFY_BASE_URL") or "").strip()
    cors_origins = (os.getenv("BACKEND_CORS_ORIGINS") or "").strip()

    if database_url and not database_url.startswith(("postgres://", "postgresql://")):
        warnings.append("DATABASE_URL should be a PostgreSQL connection URL.")
    if is_postgres_enabled() and not database_url:
        warnings.append("PostgreSQL is not active because DATABASE_URL is missing.")
    if auth_secret and len(auth_secret) < 24:
        warnings.append("AUTH_SECRET_KEY is short. Use a long stable value and do not rotate it casually.")
    if frontend_base:
        if not frontend_base.startswith("https://"):
            warnings.append("FRONTEND_BASE_URL should use https in production.")
        if verify_base and not verify_base.startswith(frontend_base):
            warnings.append("AUTH_VERIFY_BASE_URL should usually start with FRONTEND_BASE_URL.")
        allowed_origins = [item.strip().rstrip("/") for item in cors_origins.split(",") if item.strip()]
        if cors_origins and frontend_base not in allowed_origins:
            warnings.append("BACKEND_CORS_ORIGINS should include FRONTEND_BASE_URL.")
    if verify_base and "verify-email" not in verify_base:
        warnings.append("AUTH_VERIFY_BASE_URL should point to the patient email verification page.")
    if (os.getenv("AUTH_DEV_OTP_VISIBLE") or "0").strip().lower() not in {"", "0", "false"}:
        warnings.append("AUTH_DEV_OTP_VISIBLE should be 0 in production.")
    if (os.getenv("SMTP_USE_SSL") or "").strip() == "1" and (os.getenv("SMTP_USE_TLS") or "").strip() == "1":
        warnings.append("SMTP_USE_SSL and SMTP_USE_TLS should not both be 1.")

    missing_required = [item["key"] for item in required if not item["set"]]
    return {
        "ready": not missing_required and not warnings,
        "database_provider": "postgresql" if is_postgres_enabled() else "sqlite",
        "frontend_host": _host(frontend_base) if frontend_base else "",
        "database_url_set": bool(database_url),
        "required": required,
        "recommended": recommended,
        "missing_required": missing_required,
        "warnings": warnings,
    }
