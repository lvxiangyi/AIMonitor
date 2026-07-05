"""Persist a post-session flow prompt so it can be shown after restart or retry."""

import json
from typing import Optional

from data_paths import DATA_DIR

PENDING_FLOW_FILE = DATA_DIR / "pending_flow_prompt.json"


def save_pending_flow(summary: dict) -> None:
    with open(PENDING_FLOW_FILE, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)


def load_pending_flow() -> Optional[dict]:
    if not PENDING_FLOW_FILE.exists():
        return None
    try:
        with open(PENDING_FLOW_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def clear_pending_flow() -> None:
    if PENDING_FLOW_FILE.exists():
        PENDING_FLOW_FILE.unlink()
