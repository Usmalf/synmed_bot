import os
import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from database import get_database_path
from services import storage_service


UTC = timezone.utc


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


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def create_database_backup() -> dict:
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
    database_snapshot = backup_dir / f"synmed_backup_{timestamp}.db"
    source = Path(get_database_path())
    if not source.exists():
        raise FileNotFoundError(f"Database file not found: {source}")

    _sqlite_snapshot(source, database_snapshot)
    storage_root = storage_service.STORAGE_ROOT
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.write(database_snapshot, "database/synmed.db")
        if storage_root.exists():
            for path in storage_root.rglob("*"):
                if not path.is_file():
                    continue
                if _is_relative_to(path, backup_dir):
                    continue
                zip_file.write(path, f"storage/{path.relative_to(storage_root).as_posix()}")

    database_snapshot.unlink(missing_ok=True)
    return {
        "source": str(source),
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
    return {
        "database_path": str(database_path),
        "database_exists": database_path.exists(),
        "database_size": database_path.stat().st_size if database_path.exists() else 0,
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
