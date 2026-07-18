"""
Schedule manager: allows users to plan study sessions in advance.
Stores schedules in a JSON file.
"""

import json
import uuid
from datetime import datetime, timedelta
from typing import Optional, Tuple

from data_paths import LOGS_DIR
from settings_manager import get_default_check_interval_seconds, get_default_strict_mode, get_default_trigger_threshold

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


def _parse_time(value: str):
    return datetime.strptime(value, "%H:%M").time()


def schedule_window(entry: dict) -> Tuple[datetime, datetime]:
    date_value = entry["date"]
    start = datetime.combine(datetime.fromisoformat(date_value).date(), _parse_time(entry["start_time"]))
    if entry.get("end_time"):
        end = datetime.combine(datetime.fromisoformat(date_value).date(), _parse_time(entry["end_time"]))
    else:
        end = start + timedelta(minutes=int(entry.get("duration_minutes", 0)))
    return start, end


def add_schedule(
    task: str,
    date: str,
    start_time: str,
    duration_minutes: Optional[int] = None,
    check_interval_seconds: Optional[int] = None,
    trigger_threshold: Optional[int] = None,
    end_time: Optional[str] = None,
    tags: Optional[list] = None,
    strict_mode: Optional[bool] = None,
) -> dict:
    """Add a new scheduled study session."""
    task = (task or "").strip()
    if not task:
        raise ValueError("Task cannot be empty.")
    if not date:
        raise ValueError("Date is required.")
    if not start_time:
        raise ValueError("Start time is required.")

    start_dt = datetime.combine(datetime.fromisoformat(date).date(), _parse_time(start_time))
    if end_time:
        end_dt = datetime.combine(datetime.fromisoformat(date).date(), _parse_time(end_time))
        if end_dt <= start_dt:
            raise ValueError("End time must be later than start time. Cross-midnight blocks are not supported yet.")
        duration_minutes = int((end_dt - start_dt).total_seconds() // 60)
    elif duration_minutes is not None:
        duration_minutes = int(duration_minutes)
        if duration_minutes <= 0:
            raise ValueError("Duration must be greater than 0.")
        end_dt = start_dt + timedelta(minutes=duration_minutes)
        end_time = end_dt.strftime("%H:%M")
    else:
        raise ValueError("End time or duration is required.")

    schedules = _load_schedules()
    entry = {
        "id": str(uuid.uuid4())[:8],
        "task": task,
        "date": date,
        "start_time": start_time,
        "end_time": end_time,
        "duration_minutes": duration_minutes,
        "check_interval_seconds": (
            check_interval_seconds if check_interval_seconds is not None else get_default_check_interval_seconds()
        ),
        "trigger_threshold": trigger_threshold if trigger_threshold is not None else get_default_trigger_threshold(),
        "tags": [str(tag).strip() for tag in (tags or []) if str(tag).strip()],
        "strict_mode": get_default_strict_mode() if strict_mode is None else bool(strict_mode),
        "status": "scheduled",
        "created_at": datetime.now().isoformat(),
    }
    schedules.append(entry)
    _save_schedules(schedules)
    return entry


def get_schedules() -> list:
    """Get all schedules."""
    schedules = _load_schedules()
    return sorted(schedules, key=lambda s: (s.get("date", ""), s.get("start_time", "")))


def delete_schedule(schedule_id: str) -> bool:
    """Delete a schedule by ID."""
    schedules = _load_schedules()
    new_schedules = [s for s in schedules if s["id"] != schedule_id]
    if len(new_schedules) < len(schedules):
        _save_schedules(new_schedules)
        return True
    return False


def get_schedule(schedule_id: str) -> Optional[dict]:
    for schedule in _load_schedules():
        if schedule.get("id") == schedule_id:
            return schedule
    return None


def remove_schedule(schedule_id: str) -> Optional[dict]:
    schedules = _load_schedules()
    removed = None
    kept = []
    for schedule in schedules:
        if schedule.get("id") == schedule_id:
            removed = schedule
        else:
            kept.append(schedule)
    if removed:
        _save_schedules(kept)
    return removed


def update_schedule_status(schedule_id: str, status: str):
    """Update the status of a schedule (scheduled, in_progress, completed)."""
    schedules = _load_schedules()
    for s in schedules:
        if s["id"] == schedule_id:
            s["status"] = status
            s["updated_at"] = datetime.now().isoformat()
            break
    _save_schedules(schedules)
