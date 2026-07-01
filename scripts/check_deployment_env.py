from __future__ import annotations

import argparse
import os
from urllib.parse import urlparse

from dotenv import load_dotenv


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

FRONTEND_REQUIRED = ["VITE_API_BASE_URL"]


def _is_set(key: str) -> bool:
    return bool((os.getenv(key) or "").strip())


def _host(value: str) -> str:
    parsed = urlparse(value)
    return parsed.netloc or value


def _status_line(key: str) -> str:
    return f"{'OK' if _is_set(key) else 'MISSING':8} {key}"


def check_backend(strict: bool) -> tuple[list[str], list[str]]:
    warnings = []
    failures = []

    print("Backend environment")
    for key in BACKEND_REQUIRED:
        print(f"  {_status_line(key)}")
        if strict and not _is_set(key):
            failures.append(key)

    print("\nBackend recommended")
    for key in BACKEND_RECOMMENDED:
        print(f"  {_status_line(key)}")

    database_url = (os.getenv("DATABASE_URL") or "").strip()
    if database_url and not database_url.startswith(("postgres://", "postgresql://")):
        warnings.append("DATABASE_URL should be a PostgreSQL connection URL.")

    auth_secret = os.getenv("AUTH_SECRET_KEY") or ""
    if auth_secret and len(auth_secret) < 24:
        warnings.append("AUTH_SECRET_KEY is short. Use a long stable secret and never rotate it casually.")

    frontend_base = (os.getenv("FRONTEND_BASE_URL") or "").strip().rstrip("/")
    verify_base = (os.getenv("AUTH_VERIFY_BASE_URL") or "").strip()
    cors_origins = (os.getenv("BACKEND_CORS_ORIGINS") or "").strip()
    if frontend_base:
        if not frontend_base.startswith("https://"):
            warnings.append("FRONTEND_BASE_URL should use https in production.")
        if verify_base and not verify_base.startswith(frontend_base):
            warnings.append("AUTH_VERIFY_BASE_URL should usually start with FRONTEND_BASE_URL.")
        if cors_origins and frontend_base not in [item.strip().rstrip("/") for item in cors_origins.split(",")]:
            warnings.append("BACKEND_CORS_ORIGINS should include FRONTEND_BASE_URL.")

    if verify_base and "verify-email" not in verify_base:
        warnings.append("AUTH_VERIFY_BASE_URL should point to the patient email verification page.")

    if (os.getenv("AUTH_DEV_OTP_VISIBLE") or "0").strip() not in {"", "0", "false", "False"}:
        warnings.append("AUTH_DEV_OTP_VISIBLE should be 0 in production.")

    if (os.getenv("SMTP_USE_SSL") or "").strip() == "1" and (os.getenv("SMTP_USE_TLS") or "").strip() == "1":
        warnings.append("SMTP_USE_SSL and SMTP_USE_TLS should not both be 1.")

    if frontend_base:
        print(f"\nFrontend host: {_host(frontend_base)}")
    if database_url:
        print(f"Database URL: set ({database_url.split(':', 1)[0]})")

    return failures, warnings


def check_frontend(strict: bool) -> tuple[list[str], list[str]]:
    warnings = []
    failures = []

    print("\nFrontend build environment")
    for key in FRONTEND_REQUIRED:
        print(f"  {_status_line(key)}")
        if strict and not _is_set(key):
            failures.append(key)

    api_base = (os.getenv("VITE_API_BASE_URL") or "").strip().rstrip("/")
    if api_base and not api_base.startswith("https://"):
        warnings.append("VITE_API_BASE_URL should use https in production.")
    if api_base:
        print(f"Backend API host: {_host(api_base)}")

    return failures, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Check SynMed deployment environment readiness without printing secrets.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when required variables are missing.")
    parser.add_argument("--no-dotenv", action="store_true", help="Do not load .env before checking.")
    args = parser.parse_args()

    if not args.no_dotenv:
        load_dotenv()

    backend_failures, backend_warnings = check_backend(args.strict)
    frontend_failures, frontend_warnings = check_frontend(args.strict)
    failures = backend_failures + frontend_failures
    warnings = backend_warnings + frontend_warnings

    if warnings:
        print("\nWarnings")
        for item in warnings:
            print(f"  - {item}")

    if failures:
        print("\nMissing required variables")
        for item in failures:
            print(f"  - {item}")
        return 1

    print("\nEnvironment check complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
