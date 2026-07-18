import os
import sys
from pathlib import Path


def _data_env() -> str:
    value = os.getenv("AIMONITOR_DATA_ENV", "dev").strip().lower()
    return value if value in {"prod", "dev"} else "dev"


def _project_root() -> Path:
    explicit_root = os.getenv("AIMONITOR_APP_ROOT", "").strip()
    if explicit_root:
        return Path(explicit_root).expanduser().resolve()

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parent.parent


PROJECT_ROOT = _project_root()
ENV_FILE = Path(os.getenv("AIMONITOR_ENV_FILE", PROJECT_ROOT / ".env")).expanduser().resolve()
DATA_ENV = _data_env()
DATA_DIR = PROJECT_ROOT / "data" / DATA_ENV
LOGS_DIR = DATA_DIR / "logs"
SCREENSHOT_DIR = DATA_DIR / "screenshots"
DATASET_DIR = DATA_DIR / "dataset"
DATASET_SCREENSHOT_DIR = DATASET_DIR / "screenshots"
DATASET_EXPORT_DIR = DATASET_DIR / "exports"
DATASET_DB = DATASET_DIR / "dataset.db"
GUARDIAN_DIR = DATA_DIR / "guardian"
GUARDIAN_SCREENSHOT_DIR = GUARDIAN_DIR / "screenshots"
GUARDIAN_LOG_FILE = GUARDIAN_DIR / "guardian_logs.jsonl"

LOGS_DIR.mkdir(parents=True, exist_ok=True)
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
DATASET_SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
DATASET_EXPORT_DIR.mkdir(parents=True, exist_ok=True)
GUARDIAN_SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
