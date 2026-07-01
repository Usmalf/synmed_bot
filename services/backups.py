import json
import os
import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from database import get_connection, get_database_path, is_postgres_enabled
from services import storage_service


UTC = timezone.utc
BACKUP_TABLES = [
    "doctors",
    "patients",
    "payments",
    "dismissed_payment_attention",
    "consultations",
    "consultation_messages",
    "consultation_timeline",
    "admin_audit_logs",
    "follow_up_appointments",
    "prescriptions",
    "investigation_requests",
    "clinical_letters",
    "admin_alert_states",
    "internal_messages",
    "operational_error_logs",
    "medical_report_requests",
    "partner_facilities",
    "partner_requests",
    "admin_accounts",
    "admin_email_reminders",
    "customer_care_accounts",
    "support_tickets",
    "support_ticket_messages",
    "support_ticket_logs",
    "support_ticket_feedback",
    "patient_consents",
    "doctor_ratings",
    "doctor_reviews",
    "doctor_profiles",
    "pending_doctor_requests",
    "doctor_runtime_presence",
    "waiting_patients_runtime",
    "active_consultations_runtime",
    "consultation_calls_runtime",
    "support_runtime_presence",
    "support_waiting_runtime",
    "support_active_chats_runtime",
    "auth_otps",
    "health_tips",
    "app_settings",
]


def _backup_root() -> Path:
    configured = os.getenv("SYNMED_BACKUP_ROOT")
    if configured:
        root = Path(configured)
    else:
        root = Path(get_database_path()).resolve().parent / "backups"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%d_%H%M%S")


def _sqlite_snapshot(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source) as source_conn:
        with sqlite3.connect(destination) as backup_conn:
            source_conn.backup(backup_conn)


def _postgres_table_exists(cursor, table_name: str) -> bool:
    cursor.execute(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = current_schema() AND table_name = ?
        """,
        (table_name,),
    )
    return cursor.fetchone() is not None


def _postgres_export(destination: Path) -> dict:
    destination.parent.mkdir(parents=True, exist_ok=True)
    exported_tables = {}
    total_rows = 0
    with get_connection() as conn:
        cursor = conn.cursor()
        for table in BACKUP_TABLES:
            if not _postgres_table_exists(cursor, table):
                exported_tables[table] = {"columns": [], "rows": [], "row_count": 0}
                continue
            cursor.execute(
                """
                SELECT column_name AS name
                FROM information_schema.columns
                WHERE table_schema = current_schema() AND table_name = ?
                ORDER BY ordinal_position
                """,
                (table,),
            )
            columns = [row["name"] for row in cursor.fetchall()]
            cursor.execute(f'SELECT * FROM "{table}"')
            rows = [dict(row) for row in cursor.fetchall()]
            exported_tables[table] = {
                "columns": columns,
                "rows": rows,
                "row_count": len(rows),
            }
            total_rows += len(rows)

    payload = {
        "format": "synmed-postgresql-json-v1",
        "created_at": datetime.now(UTC).isoformat(),
        "database_provider": "postgresql",
        "table_count": len(exported_tables),
        "row_count": total_rows,
        "tables": exported_tables,
    }
    destination.write_text(json.dumps(payload, ensure_ascii=True, indent=2, default=str), encoding="utf-8")
    return {
        "path": str(destination),
        "filename": destination.name,
        "size": destination.stat().st_size,
        "row_count": total_rows,
    }


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def create_database_backup() -> dict:
    if is_postgres_enabled():
        backup_dir = _backup_root()
        destination = backup_dir / f"synmed_postgres_backup_{_timestamp()}.json"
        backup = _postgres_export(destination)
        return {
            "source": "postgresql",
            **backup,
        }

    source = Path(get_database_path())
    if not source.exists():
        raise FileNotFoundError(f"Database file not found: {source}")

    backup_dir = _backup_root()
    timestamp = _timestamp()
    destination = backup_dir / f"synmed_backup_{timestamp}.db"
    _sqlite_snapshot(source, destination)
    return {
        "source": str(source),
        "path": str(destination),
        "filename": destination.name,
        "size": destination.stat().st_size,
    }


def create_full_backup_archive() -> dict:
    backup_dir = _backup_root()
    timestamp = _timestamp()
    archive = backup_dir / f"synmed_full_backup_{timestamp}.zip"
    database_snapshot = None
    source = "postgresql" if is_postgres_enabled() else str(Path(get_database_path()))
    if is_postgres_enabled():
        database_snapshot = backup_dir / f"synmed_postgres_backup_{timestamp}.json"
        _postgres_export(database_snapshot)
        database_archive_name = f"database/{database_snapshot.name}"
    else:
        database_snapshot = backup_dir / f"synmed_backup_{timestamp}.db"
        source_path = Path(get_database_path())
        if not source_path.exists():
            raise FileNotFoundError(f"Database file not found: {source_path}")
        _sqlite_snapshot(source_path, database_snapshot)
        database_archive_name = "database/synmed.db"

    storage_root = storage_service.STORAGE_ROOT
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.write(database_snapshot, database_archive_name)
        if storage_root.exists():
            for path in storage_root.rglob("*"):
                if not path.is_file():
                    continue
                if _is_relative_to(path, backup_dir):
                    continue
                zip_file.write(path, f"storage/{path.relative_to(storage_root).as_posix()}")

    if database_snapshot:
        database_snapshot.unlink(missing_ok=True)
    return {
        "source": source,
        "storage_root": str(storage_root),
        "path": str(archive),
        "filename": archive.name,
        "size": archive.stat().st_size,
    }


def get_backup_status() -> dict:
    database_path = Path(get_database_path())
    storage_root = storage_service.STORAGE_ROOT
    backup_dir = _backup_root()
    storage_file_count = 0
    storage_total_size = 0
    if storage_root.exists():
        for path in storage_root.rglob("*"):
            if not path.is_file():
                continue
            if _is_relative_to(path, backup_dir):
                continue
            storage_file_count += 1
            storage_total_size += path.stat().st_size

    backups = sorted(
        (path for path in backup_dir.glob("synmed*backup_*") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    latest = backups[0] if backups else None
    database_provider = "postgresql" if is_postgres_enabled() else "sqlite"
    return {
        "database_provider": database_provider,
        "database_path": str(database_path),
        "database_exists": True if is_postgres_enabled() else database_path.exists(),
        "database_size": 0 if is_postgres_enabled() else database_path.stat().st_size if database_path.exists() else 0,
        "database_backup_supported": True,
        "database_backup_format": "json" if is_postgres_enabled() else "sqlite",
        "storage_root": str(storage_root),
        "storage_exists": storage_root.exists(),
        "storage_file_count": storage_file_count,
        "storage_total_size": storage_total_size,
        "backup_root": str(backup_dir),
        "latest_backup": {
            "filename": latest.name,
            "size": latest.stat().st_size,
            "created_at": datetime.fromtimestamp(latest.stat().st_mtime, UTC).isoformat(),
        } if latest else None,
    }
