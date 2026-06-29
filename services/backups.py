import shutil
from datetime import datetime, timezone
from pathlib import Path

from database import get_database_path


UTC = timezone.utc


def create_database_backup():
    source = Path(get_database_path())
    backup_dir = Path("backups")
    backup_dir.mkdir(exist_ok=True)

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    destination = backup_dir / f"synmed_backup_{timestamp}.db"
    shutil.copy2(source, destination)
    return {
        "source": str(source),
        "path": str(destination),
        "filename": destination.name,
    }
