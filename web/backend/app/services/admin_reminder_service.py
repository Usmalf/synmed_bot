import json
import os
from datetime import datetime, timedelta, timezone

from database import get_connection
from services.backups import get_backup_status
from services.operational_errors import log_operational_error

from .auth_service import send_plain_email


UTC = timezone.utc
BACKUP_STALE_AFTER = timedelta(hours=72)
REMINDER_REPEAT_AFTER = timedelta(hours=24)


def _now() -> datetime:
    return datetime.now(UTC)


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _admin_recipients() -> list[dict]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT admin_id, email, display_name
            FROM admin_accounts
            WHERE email IS NOT NULL AND trim(email) != ''
            ORDER BY admin_id
            """
        )
        return [dict(row) for row in cursor.fetchall()]


def _last_sent_at(reminder_key: str) -> datetime | None:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT sent_at FROM admin_email_reminders WHERE reminder_key = ?",
            (reminder_key,),
        )
        row = cursor.fetchone()
    return _parse_iso(row["sent_at"]) if row else None


def _mark_sent(reminder_key: str, details: dict, sent_at: datetime) -> None:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO admin_email_reminders (reminder_key, sent_at, details)
            VALUES (?, ?, ?)
            ON CONFLICT(reminder_key) DO UPDATE SET
                sent_at = excluded.sent_at,
                details = excluded.details
            """,
            (reminder_key, sent_at.isoformat(), json.dumps(details, sort_keys=True)),
        )
        conn.commit()


def _settings_destination() -> str:
    frontend_base = os.getenv("FRONTEND_BASE_URL", "").strip().rstrip("/")
    if frontend_base:
        return f"{frontend_base}/admin/settings"
    return "Admin dashboard > Settings > Backups"


def _backup_reminder(now: datetime) -> dict | None:
    status = get_backup_status()
    latest = status.get("latest_backup")
    destination = _settings_destination()

    if not latest:
        return {
            "key": "backup-missing",
            "subject": "SynMed backup reminder: no backup has been created",
            "body": (
                "No SynMed backup has been created yet.\n\n"
                "Please open admin settings and download a full backup so patient records, "
                "clinical documents, uploads, and operational data have a recoverable copy.\n\n"
                f"Backup area: {destination}"
            ),
            "details": {
                "backup_root": status.get("backup_root"),
                "database_exists": status.get("database_exists"),
                "storage_exists": status.get("storage_exists"),
            },
        }

    latest_created = _parse_iso(latest.get("created_at"))
    if not latest_created:
        return {
            "key": "backup-age-unknown",
            "subject": "SynMed backup reminder: backup age could not be verified",
            "body": (
                "SynMed found a backup, but could not verify when it was created.\n\n"
                "Please open admin settings and download a fresh full backup.\n\n"
                f"Backup area: {destination}"
            ),
            "details": {"latest_backup": latest},
        }

    age = now - latest_created
    if age <= BACKUP_STALE_AFTER:
        return None

    age_hours = int(age.total_seconds() // 3600)
    return {
        "key": "backup-stale",
        "subject": "SynMed backup reminder: latest backup is older than 72 hours",
        "body": (
            f"The latest SynMed backup is about {age_hours} hours old.\n\n"
            "Please open admin settings and download a fresh full backup before further "
            "production changes.\n\n"
            f"Backup area: {destination}"
        ),
        "details": {
            "latest_backup": latest,
            "age_hours": age_hours,
            "backup_root": status.get("backup_root"),
        },
    }


def send_due_backup_reminders() -> dict:
    now = _now()
    reminder = _backup_reminder(now)
    if not reminder:
        return {"sent": 0, "reason": "backup_current"}

    last_sent = _last_sent_at(reminder["key"])
    if last_sent and now - last_sent < REMINDER_REPEAT_AFTER:
        return {"sent": 0, "reason": "recently_sent", "reminder_key": reminder["key"]}

    recipients = _admin_recipients()
    if not recipients:
        return {"sent": 0, "reason": "no_admin_email", "reminder_key": reminder["key"]}

    sent_count = 0
    failed = []
    for admin in recipients:
        ok = send_plain_email(admin["email"], reminder["subject"], reminder["body"])
        if ok:
            sent_count += 1
        else:
            failed.append(admin["email"])

    if sent_count:
        _mark_sent(
            reminder["key"],
            {
                **reminder["details"],
                "sent_count": sent_count,
                "failed": failed,
            },
            now,
        )

    if failed:
        log_operational_error(
            "admin_backup_reminder",
            "warning",
            "Backup reminder email failed for one or more admins.",
            details={"failed_recipients": failed, "reminder_key": reminder["key"]},
        )

    return {
        "sent": sent_count,
        "failed": failed,
        "reminder_key": reminder["key"],
    }
