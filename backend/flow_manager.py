import asyncio
import uuid
from datetime import datetime
from typing import Optional

from report_manager import record_block
from session_manager import session_manager


class FlowManager:
    def __init__(self):
        self.pending_resume: Optional[dict] = None
        self._break_task: Optional[asyncio.Task] = None

    def continue_work(self, task: str, duration_minutes: int, check_interval_seconds: int) -> str:
        session_id = session_manager.start_session(
            task=task,
            duration_minutes=duration_minutes,
            check_interval_seconds=check_interval_seconds,
            source="flow",
        )
        return session_id

    def start_break(
        self,
        break_minutes: int,
        activity: str,
        task: str,
        duration_minutes: int,
        check_interval_seconds: int,
    ):
        now = datetime.now()
        break_id = str(uuid.uuid4())[:8]
        self.pending_resume = {
            "break_id": break_id,
            "task": task,
            "duration_minutes": duration_minutes,
            "check_interval_seconds": check_interval_seconds,
            "activity": activity,
            "break_minutes": break_minutes,
            "started_at": now.isoformat(),
        }
        record_block({
            "session_id": f"break-{break_id}",
            "task": activity,
            "source": "flow",
            "status": "break",
            "planned_start": now.isoformat(),
            "planned_end": None,
            "actual_start": now.isoformat(),
            "actual_end": None,
            "duration_minutes": break_minutes,
            "focus_minutes": 0,
            "total_checks": 0,
            "focused_checks": 0,
            "distracted_checks": 0,
            "api_error_checks": 0,
        })
        if self._break_task and not self._break_task.done():
            self._break_task.cancel()
        self._break_task = asyncio.create_task(self._break_timer(self.pending_resume.copy()))

    async def _break_timer(self, payload: dict):
        try:
            await asyncio.sleep(int(payload["break_minutes"]) * 60)
            from blocker_window import blocker
            blocker.show_resume_prompt(payload)
        except asyncio.CancelledError:
            pass

    def resume_after_break(self, payload: Optional[dict] = None) -> str:
        resume = payload or self.pending_resume
        if not resume:
            raise ValueError("No pending break to resume.")
        self.pending_resume = None
        return session_manager.start_session(
            task=resume["task"],
            duration_minutes=int(resume["duration_minutes"]),
            check_interval_seconds=int(resume["check_interval_seconds"]),
            source="flow",
        )

    def pause_day(self, activity: str):
        now = datetime.now().isoformat()
        record_block({
            "session_id": f"pause-{str(uuid.uuid4())[:8]}",
            "task": activity,
            "source": "flow",
            "status": "day_paused",
            "planned_start": None,
            "planned_end": None,
            "actual_start": now,
            "actual_end": now,
            "duration_minutes": 0,
            "focus_minutes": 0,
            "total_checks": 0,
            "focused_checks": 0,
            "distracted_checks": 0,
            "api_error_checks": 0,
        })
        if self._break_task and not self._break_task.done():
            self._break_task.cancel()
        self.pending_resume = None


flow_manager = FlowManager()
