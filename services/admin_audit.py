from datetime import datetime, timezone

from database import get_connection


UTC = timezone.utc


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def log_admin_action(*, admin_id: int, action: str, target_type: str, target_id: str, details: str = ""):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO admin_audit_logs (
                admin_id, action, target_type, target_id, details, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (admin_id, action, target_type, target_id, details, _now_iso()),
        )
        conn.commit()


def get_recent_admin_actions(limit: int = 20):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT admin_id, action, target_type, target_id, details, created_at
            FROM admin_audit_logs
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
        return cursor.fetchall()
