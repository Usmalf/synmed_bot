import json
import traceback
from datetime import datetime, timezone

from database import get_connection


UTC = timezone.utc


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _serialize_details(details) -> str:
    if details is None:
        return ""
    if isinstance(details, str):
        return details
    return json.dumps(details, ensure_ascii=True, default=str)


def log_operational_error(
    *,
    source: str,
    severity: str = "error",
    message: str,
    path: str = "",
    method: str = "",
    status_code: int | None = None,
    user_role: str = "",
    user_id: str = "",
    details=None,
) -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO operational_error_logs (
                source, severity, message, path, method, status_code,
                user_role, user_id, details, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source,
                severity,
                message[:1000],
                path,
                method,
                status_code,
                user_role,
                str(user_id or ""),
                _serialize_details(details),
                _now_iso(),
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)


def log_exception(
    exc: BaseException,
    *,
    source: str,
    path: str = "",
    method: str = "",
    status_code: int | None = None,
    user_role: str = "",
    user_id: str = "",
) -> int:
    return log_operational_error(
        source=source,
        severity="error",
        message=f"{exc.__class__.__name__}: {exc}",
        path=path,
        method=method,
        status_code=status_code,
        user_role=user_role,
        user_id=user_id,
        details={"traceback": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))},
    )


def list_operational_errors(limit: int = 100, severity: str = "all") -> list[dict]:
    safe_limit = max(1, min(int(limit or 100), 500))
    params: list = []
    where_clause = ""
    if severity and severity != "all":
        where_clause = "WHERE severity = ?"
        params.append(severity)
    params.append(safe_limit)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT *
            FROM operational_error_logs
            {where_clause}
            ORDER BY datetime(created_at) DESC, id DESC
            LIMIT ?
            """,
            params,
        )
        return [dict(row) for row in cursor.fetchall()]


def get_operational_error_summary() -> dict:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) AS total FROM operational_error_logs")
        total = int(cursor.fetchone()["total"])
        cursor.execute(
            """
            SELECT severity, COUNT(*) AS count
            FROM operational_error_logs
            GROUP BY severity
            """
        )
        by_severity = {row["severity"]: int(row["count"]) for row in cursor.fetchall()}
        cursor.execute(
            """
            SELECT *
            FROM operational_error_logs
            ORDER BY datetime(created_at) DESC, id DESC
            LIMIT 1
            """
        )
        latest = cursor.fetchone()
    return {
        "total": total,
        "by_severity": by_severity,
        "latest": dict(latest) if latest else None,
    }
