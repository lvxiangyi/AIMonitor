import asyncio
import math
from datetime import datetime
from typing import Optional

from report_manager import record_block
from schedule_manager import get_schedules, remove_schedule, schedule_window, update_schedule_status
from session_manager import session_manager
from settings_manager import get_default_check_interval_seconds, get_default_strict_mode, get_default_trigger_threshold


class AutoScheduler:
    def __init__(self):
        self._task: Optional[asyncio.Task] = None

    def start(self):
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._loop())

    def stop(self):
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None

    async def _loop(self):
        while True:
            try:
                self.process_due_schedules()
            except Exception as e:
                print(f"[auto_scheduler] Error: {e}")
            await asyncio.sleep(5)

    def process_due_schedules(self, now: Optional[datetime] = None):
        now = now or datetime.now()
        for schedule in get_schedules():
            status = schedule.get("status", "scheduled")
            try:
                start, end = schedule_window(schedule)
            except Exception as e:
                print(f"[auto_scheduler] Invalid schedule {schedule.get('id')}: {e}")
                remove_schedule(schedule.get("id"))
                continue

            if now < start:
                continue

            if now >= end:
                if not (status == "in_progress" and session_manager.active and session_manager.schedule_id == schedule["id"]):
                    self._record_non_session_block(schedule, "missed")
                    remove_schedule(schedule["id"])
                continue

            if status == "in_progress" and session_manager.active and session_manager.schedule_id == schedule["id"]:
                continue

            if session_manager.active:
                self._record_non_session_block(schedule, "skipped_conflict")
                remove_schedule(schedule["id"])
                continue

            remaining_minutes = max(1, math.ceil((end - now).total_seconds() / 60))
            late_started = now > start
            session_manager.start_session(
                task=schedule["task"],
                duration_minutes=remaining_minutes,
                check_interval_seconds=int(schedule.get("check_interval_seconds") or get_default_check_interval_seconds()),
                trigger_threshold=int(schedule.get("trigger_threshold") or get_default_trigger_threshold()),
                source="schedule",
                schedule_id=schedule["id"],
                planned_start=start.isoformat(),
                planned_end=end.isoformat(),
                late_started=late_started,
                tags=schedule.get("tags", []),
                strict_mode=bool(schedule.get("strict_mode", get_default_strict_mode())),
            )
            update_schedule_status(schedule["id"], "in_progress")
            print(f"[auto_scheduler] Started schedule {schedule['id']} for {remaining_minutes} minutes.")

    def _record_non_session_block(self, schedule: dict, status: str):
        start, end = schedule_window(schedule)
        record_block({
            "session_id": f"schedule-{schedule['id']}-{status}",
            "schedule_id": schedule["id"],
            "task": schedule.get("task", ""),
            "source": "schedule",
            "status": status,
            "late_started": False,
            "planned_start": start.isoformat(),
            "planned_end": end.isoformat(),
            "actual_start": None,
            "actual_end": None,
            "duration_minutes": 0,
            "focus_minutes": 0,
            "total_checks": 0,
            "focused_checks": 0,
            "distracted_checks": 0,
            "api_error_checks": 0,
            "tags": schedule.get("tags", []),
            "strict_mode": bool(schedule.get("strict_mode", get_default_strict_mode())),
            "trigger_threshold": int(schedule.get("trigger_threshold") or get_default_trigger_threshold()),
        })
        print(f"[auto_scheduler] Schedule {schedule['id']} recorded as {status}.")


auto_scheduler = AutoScheduler()
