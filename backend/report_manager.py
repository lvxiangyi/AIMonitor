import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from data_paths import LOGS_DIR


REPORT_FILE = LOGS_DIR / "daily_reports.json"


def _load_reports() -> Dict[str, dict]:
    if REPORT_FILE.exists():
        try:
            with open(REPORT_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


def _save_reports(reports: Dict[str, dict]):
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(reports, f, ensure_ascii=False, indent=2)


def _date_from_iso(value: Optional[str]) -> str:
    if value:
        try:
            return datetime.fromisoformat(value).date().isoformat()
        except Exception:
            pass
    return datetime.now().date().isoformat()


def _empty_day(date: str) -> dict:
    return {
        "date": date,
        "total_focus_minutes": 0,
        "total_break_minutes": 0,
        "total_stopped_minutes": 0,
        "total_blocks": 0,
        "completed_blocks": 0,
        "today_summary": "",
        "tomorrow_plan": "",
        "blocks": [],
    }


def _recalculate(day: dict):
    blocks = day.get("blocks", [])
    day["total_blocks"] = len(blocks)
    day["completed_blocks"] = sum(1 for b in blocks if b.get("status") == "completed")
    day["total_focus_minutes"] = round(sum(float(b.get("focus_minutes", 0)) for b in blocks), 1)
    day["total_break_minutes"] = round(
        sum(float(b.get("duration_minutes", 0)) for b in blocks if b.get("status") == "break"),
        1,
    )
    day["total_stopped_minutes"] = round(
        sum(float(b.get("duration_minutes", 0)) for b in blocks if b.get("status") == "stopped_pending"),
        1,
    )


def record_block(block: dict) -> dict:
    reports = _load_reports()
    date = block.get("date") or _date_from_iso(block.get("actual_start") or block.get("planned_start"))
    block["date"] = date

    day = reports.get(date) or _empty_day(date)
    blocks = [b for b in day.get("blocks", []) if b.get("session_id") != block.get("session_id")]
    blocks.append(block)
    blocks.sort(key=lambda b: b.get("planned_start") or b.get("actual_start") or "")
    day["blocks"] = blocks
    _recalculate(day)
    reports[date] = day
    _save_reports(reports)
    return day


def get_daily_report(date: Optional[str] = None) -> dict:
    target = date or datetime.now().date().isoformat()
    reports = _load_reports()
    day = reports.get(target) or _empty_day(target)
    _recalculate(day)
    return day


def save_daily_notes(date: Optional[str], today_summary: str, tomorrow_plan: str) -> dict:
    target = date or datetime.now().date().isoformat()
    reports = _load_reports()
    day = reports.get(target) or _empty_day(target)
    day["today_summary"] = today_summary or ""
    day["tomorrow_plan"] = tomorrow_plan or ""
    _recalculate(day)
    reports[target] = day
    _save_reports(reports)
    return day
