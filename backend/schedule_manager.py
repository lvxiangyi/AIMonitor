"""
Schedule manager: allows users to plan study sessions in advance.
Stores schedules in a JSON file.
"""

import json
import uuid
from datetime import datetime
from pathlib import Path

LOGS_DIR = Path(__file__).parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)
SCHEDULE_FILE = LOGS_DIR / "schedules.json"


def _load_schedules() -> list:
    if SCHEDULE_FILE.exists():
        try:
            with open(SCHEDULE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def _save_schedules(schedules: list):
    with open(SCHEDULE_FILE, "w", encoding="utf-8") as f:
        json.dump(schedules, f, ensure_ascii=False, indent=2)


def add_schedule(task: str, date: str, start_time: str, duration_minutes: int, check_interval_seconds: int = 30) -> dict:
    """Add a new scheduled study session."""
    schedules = _load_schedules()
    entry = {
        "id": str(uuid.uuid4())[:8],
        "task": task,
        "date": date,
        "start_time": start_time,
        "duration_minutes": duration_minutes,
        "check_interval_seconds": check_interval_seconds,
        "status": "scheduled",
        "created_at": datetime.now().isoformat(),
    }
    schedules.append(entry)
    _save_schedules(schedules)
    return entry


def get_schedules() -> list:
    """Get all schedules."""
    return _load_schedules()


def delete_schedule(schedule_id: str) -> bool:
    """Delete a schedule by ID."""
    schedules = _load_schedules()
    new_schedules = [s for s in schedules if s["id"] != schedule_id]
    if len(new_schedules) < len(schedules):
        _save_schedules(new_schedules)
        return True
    return False


def update_schedule_status(schedule_id: str, status: str):
    """Update the status of a schedule (scheduled, in_progress, completed)."""
    schedules = _load_schedules()
    for s in schedules:
        if s["id"] == schedule_id:
            s["status"] = status
            break
    _save_schedules(schedules)
