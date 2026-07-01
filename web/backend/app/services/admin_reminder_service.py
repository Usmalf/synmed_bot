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
EMAIL_ALERT_IDS = {
    "backend-errors",
    "open-support-tickets",
    "pending-customer-care-agents",
    "pending-payments",
    "missing-payments",
    "storage-missing",
    "delivery-setup",
}


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


def _admin_recipient(admin_id: int | str) -> dict | None:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT admin_id, email, display_name
            FROM admin_accounts
            WHERE admin_id = ? AND email IS NOT NULL AND trim(email) != ''
            """,
            (admin_id,),
        )
        row = cursor.fetchone()
    return dict(row) if row else None


def _last_sent_at(reminder_key: str) -> datetime | None:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT sent_at FROM admin_email_reminders WHERE reminder_key = ?",
            (reminder_key,),
        )
        row = cursor.fetchone()
    return _parse_iso(row["sent_at"]) if row else None


def list_admin_email_reminders() -> dict:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT reminder_key, sent_at, details
            FROM admin_email_reminders
            ORDER BY sent_at DESC
            """
        )
        rows = cursor.fetchall()

    reminders = []
    for row in rows:
        details = {}
        if row["details"]:
            try:
                details = json.loads(row["details"])
            except json.JSONDecodeError:
                details = {"raw": row["details"]}
        reminders.append({
            "reminder_key": row["reminder_key"],
            "sent_at": row["sent_at"],
            "details": details,
        })
    return {"reminders": reminders}


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


def _frontend_destination(href: str) -> str:
    frontend_base = os.getenv("FRONTEND_BASE_URL", "").strip().rstrip("/")
    if frontend_base and href:
        return f"{frontend_base}{href if href.startswith('/') else f'/{href}'}"
    return href or "Admin dashboard"


def _send_admin_reminder(reminder: dict, now: datetime) -> dict:
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
                **reminder.get("details", {}),
                "sent_count": sent_count,
                "failed": failed,
            },
            now,
        )

    if failed:
        log_operational_error(
            "admin_email_reminder",
            "warning",
            "Admin reminder email failed for one or more admins.",
            details={"failed_recipients": failed, "reminder_key": reminder["key"]},
        )

    return {
        "sent": sent_count,
        "failed": failed,
        "reminder_key": reminder["key"],
    }


def send_admin_reminder_test(admin_id: int | str) -> dict:
    admin = _admin_recipient(admin_id)
    if not admin:
        return {"sent": False, "message": "No email address is saved for this admin account."}

    now = _now()
    body = (
        "This is a SynMed admin reminder test.\n\n"
        "If you received this email, admin operational reminder delivery is working."
    )
    sent = send_plain_email(admin["email"], "SynMed admin reminder test", body)
    if sent:
        _mark_sent(
            f"manual-test-admin-{admin['admin_id']}",
            {"sent_count": 1, "target": admin["email"]},
            now,
        )
    else:
        log_operational_error(
            "admin_reminder_test",
            "warning",
            "Admin reminder test email could not be sent.",
            details={"admin_id": admin["admin_id"], "target": admin["email"]},
        )
    return {
        "sent": sent,
        "message": "Reminder test email sent." if sent else "Reminder test email could not be sent.",
        "delivery_target": admin["email"],
    }


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

    return _send_admin_reminder(reminder, now)


def send_due_operational_reminders() -> dict:
    from .admin_app_service import get_admin_alerts

    now = _now()
    alerts = [
        alert
        for alert in get_admin_alerts().get("alerts", [])
        if alert.get("id") in EMAIL_ALERT_IDS
    ]
    results = []
    for alert in alerts:
        destination = _frontend_destination(alert.get("href", ""))
        reminder = {
            "key": f"admin-alert-{alert['id']}",
            "subject": f"SynMed admin reminder: {alert['title']}",
            "body": (
                f"{alert['title']}\n\n"
                f"{alert['message']}\n\n"
                f"Open this area to review it: {destination}"
            ),
            "details": {
                "alert_id": alert["id"],
                "tone": alert.get("tone"),
                "href": alert.get("href"),
            },
        }
        results.append(_send_admin_reminder(reminder, now))

    return {
        "checked": len(alerts),
        "sent": sum(result.get("sent", 0) for result in results),
        "results": results,
    }
