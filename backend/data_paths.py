import os
from pathlib import Path


def _data_env() -> str:
    value = os.getenv("AIMONITOR_DATA_ENV", "dev").strip().lower()
    return value if value in {"prod", "dev"} else "dev"


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_ENV = _data_env()
DATA_DIR = PROJECT_ROOT / "data" / DATA_ENV
LOGS_DIR = DATA_DIR / "logs"
SCREENSHOT_DIR = DATA_DIR / "screenshots"

LOGS_DIR.mkdir(parents=True, exist_ok=True)
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
