from datetime import datetime, timezone

from database import get_connection


UTC = timezone.utc


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def send_internal_message(
    *,
    sender_role: str,
    sender_id: str | int,
    recipient_role: str,
    recipient_id: str | int,
    subject: str,
    body: str = "",
    attachment_name: str = "",
    attachment_url: str = "",
    attachment_type: str = "",
) -> dict:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO internal_messages (
                sender_role, sender_id, recipient_role, recipient_id,
                subject, body, attachment_name, attachment_url,
                attachment_type, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sender_role,
                str(sender_id),
                recipient_role,
                str(recipient_id),
                subject.strip(),
                body.strip(),
                attachment_name,
                attachment_url,
                attachment_type,
                _now_iso(),
            ),
        )
        message_id = cursor.lastrowid
        conn.commit()
    return {"sent": True, "message": "Internal message sent.", "message_id": message_id}


def list_internal_messages(recipient_role: str, recipient_id: str | int, limit: int = 100) -> list[dict]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, sender_role, sender_id, recipient_role, recipient_id,
                   subject, body, attachment_name, attachment_url,
                   attachment_type, read_at, created_at
            FROM internal_messages
            WHERE recipient_role = ? AND recipient_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (recipient_role, str(recipient_id), max(1, min(limit, 250))),
        )
        rows = cursor.fetchall()
    return [dict(row) for row in rows]


def mark_internal_message_read(message_id: int, recipient_role: str, recipient_id: str | int) -> bool:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE internal_messages
            SET read_at = COALESCE(read_at, ?)
            WHERE id = ? AND recipient_role = ? AND recipient_id = ?
            """,
            (_now_iso(), message_id, recipient_role, str(recipient_id)),
        )
        updated = cursor.rowcount > 0
        conn.commit()
    return updated


def list_message_doctors() -> list[dict]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT telegram_id, name, specialty
            FROM doctor_profiles
            WHERE verified = 1
            ORDER BY name COLLATE NOCASE
            """
        )
        rows = cursor.fetchall()
    return [dict(row) for row in rows]


def list_message_admins() -> list[dict]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT admin_id, display_name, email
            FROM admin_accounts
            ORDER BY display_name COLLATE NOCASE, admin_id
            """
        )
        rows = cursor.fetchall()
    return [dict(row) for row in rows]


def list_message_customer_care_accounts() -> list[dict]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT account_id, display_name, email
            FROM customer_care_accounts
            WHERE status = 'active'
            ORDER BY display_name COLLATE NOCASE, account_id
            """
        )
        rows = cursor.fetchall()
    return [dict(row) for row in rows]
