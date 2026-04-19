import os
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[3]
DATABASE_PATH = ROOT_DIR / "synmed.db"

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

os.environ.setdefault("DATABASE_PATH", str(DATABASE_PATH))
