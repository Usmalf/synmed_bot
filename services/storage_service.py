import base64
import os
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
STORAGE_ROOT = Path(os.getenv("SYNMED_STORAGE_ROOT") or ROOT_DIR)


def local_path(asset_path: str, *, create_parent: bool = False) -> Path:
    cleaned = str(asset_path or "").strip().lstrip("/\\")
    path = STORAGE_ROOT / cleaned
    if create_parent:
        path.parent.mkdir(parents=True, exist_ok=True)
    return path


def ensure_directory(relative_dir: str) -> Path:
    path = local_path(relative_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_bytes(asset_path: str, content: bytes) -> str:
    path = local_path(asset_path, create_parent=True)
    path.write_bytes(content)
    return asset_path


def save_base64_upload(directory: str, stored_name: str, data: str) -> tuple[str, bytes]:
    encoded = data.split(",", 1)[1] if data.startswith("data:") and "," in data else data
    decoded = base64.b64decode(encoded)
    cleaned_directory = directory.strip("/\\")
    asset_path = f"{cleaned_directory}/{stored_name}"
    save_bytes(asset_path, decoded)
    return asset_path, decoded


def read_bytes(asset_path: str | None) -> bytes | None:
    if not asset_path:
        return None
    path = local_path(asset_path)
    if not path.exists():
        return None
    return path.read_bytes()


def file_size(asset_path: str | None) -> int | None:
    if not asset_path:
        return None
    try:
        path = local_path(asset_path)
        return path.stat().st_size if path.exists() else None
    except OSError:
        return None
