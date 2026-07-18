import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Optional

from report_manager import record_block
from session_manager import session_manager
from settings_manager import get_default_check_interval_seconds, get_default_strict_mode, get_default_trigger_threshold


class FlowManager:
    def __init__(self):
        self.pending_resume: Optional[dict] = None
        self.pending_stop: Optional[dict] = None
        self._break_task: Optional[asyncio.Task] = None
        self._stop_task: Optional[asyncio.Task] = None

    def _record_timed_block(self, payload: dict, status: str, actual_end: Optional[datetime] = None):
        started_at = datetime.fromisoformat(payload["started_at"])
        end_at = actual_end or datetime.fromisoformat(payload["ends_at"])
        duration = max(0, (end_at - started_at).total_seconds() / 60)
        record_block({
            "session_id": payload["report_id"],
            "task": payload.get("activity") or payload.get("reason") or status,
            "source": "flow",
            "status": status,
            "planned_start": started_at.isoformat(),
            "planned_end": payload.get("ends_at"),
            "actual_start": started_at.isoformat(),
            "actual_end": end_at.isoformat(),
            "duration_minutes": round(duration, 1),
            "focus_minutes": 0,
            "total_checks": 0,
            "focused_checks": 0,
            "distracted_checks": 0,
            "api_error_checks": 0,
            "tags": payload.get("tags", []),
            "reason": payload.get("reason", ""),
        })

    def continue_work(
        self,
        task: str,
        duration_minutes: int,
        check_interval_seconds: int,
        tags: Optional[list] = None,
        strict_mode: Optional[bool] = None,
        trigger_threshold: Optional[int] = None,
        first_check_delay_seconds: float = 2,
    ) -> str:
        self.cancel_pending_break()
        self.cancel_pending_stop()
        session_id = session_manager.start_session(
            task=task,
            duration_minutes=duration_minutes,
            check_interval_seconds=check_interval_seconds,
            source="flow",
            tags=tags,
            strict_mode=get_default_strict_mode() if strict_mode is None else strict_mode,
            trigger_threshold=trigger_threshold if trigger_threshold is not None else get_default_trigger_threshold(),
            first_check_delay_seconds=first_check_delay_seconds,
        )
        return session_id

    def start_break(
        self,
        break_minutes: int,
        activity: str,
        task: str,
        duration_minutes: int,
        check_interval_seconds: int,
        tags: Optional[list] = None,
        strict_mode: Optional[bool] = None,
        trigger_threshold: Optional[int] = None,
        minimum_next_step: str = "",
    ):
        now = datetime.now()
        ends_at = now + timedelta(minutes=break_minutes)
        break_id = str(uuid.uuid4())[:8]
        self.pending_resume = {
            "break_id": break_id,
            "report_id": f"break-{break_id}",
            "task": task,
            "duration_minutes": duration_minutes,
            "check_interval_seconds": check_interval_seconds,
            "activity": activity,
            "break_minutes": break_minutes,
            "started_at": now.isoformat(),
            "ends_at": ends_at.isoformat(),
            "tags": [str(tag).strip() for tag in (tags or []) if str(tag).strip()],
            "strict_mode": get_default_strict_mode() if strict_mode is None else bool(strict_mode),
            "trigger_threshold": trigger_threshold if trigger_threshold is not None else get_default_trigger_threshold(),
            "minimum_next_step": (minimum_next_step or "").strip(),
        }
        self._record_timed_block(self.pending_resume, "break")
        if self._break_task and not self._break_task.done():
            self._break_task.cancel()
        self._break_task = asyncio.create_task(self._break_timer(self.pending_resume.copy()))

    async def _break_timer(self, payload: dict):
        try:
            await asyncio.sleep(int(payload["break_minutes"]) * 60)
            from blocker_window import blocker
            if payload.get("strict_mode"):
                blocker.show_break_end_translation(payload)
            else:
                blocker.show_resume_prompt(payload)
        except asyncio.CancelledError:
            pass

    def resume_after_break(self, payload: Optional[dict] = None) -> str:
        resume = payload or self.pending_resume
        if not resume:
            raise ValueError("No pending break to resume.")
        self.pending_resume = None
        if self._break_task and not self._break_task.done():
            self._break_task.cancel()
        return session_manager.start_session(
            task=resume["task"],
            duration_minutes=int(resume["duration_minutes"]),
            check_interval_seconds=int(resume["check_interval_seconds"]),
            source="flow",
            tags=resume.get("tags", []),
            strict_mode=bool(resume.get("strict_mode", False)),
            trigger_threshold=int(resume.get("trigger_threshold") or get_default_trigger_threshold()),
            first_check_delay_seconds=2,
        )

    def start_stop_pause(self, reason: str, stop_minutes: int, tags: Optional[list] = None):
        now = datetime.now()
        ends_at = now + timedelta(minutes=stop_minutes)
        stop_id = str(uuid.uuid4())[:8]
        self.pending_stop = {
            "stop_id": stop_id,
            "report_id": f"stop-{stop_id}",
            "reason": reason,
            "activity": reason,
            "stop_minutes": stop_minutes,
            "started_at": now.isoformat(),
            "ends_at": ends_at.isoformat(),
            "task": "",
            "duration_minutes": 30,
            "check_interval_seconds": get_default_check_interval_seconds(),
            "trigger_threshold": get_default_trigger_threshold(),
            "tags": [str(tag).strip() for tag in (tags or []) if str(tag).strip()],
        }
        self._record_timed_block(self.pending_stop, "stopped_pending")
        if self._stop_task and not self._stop_task.done():
            self._stop_task.cancel()
        self._stop_task = asyncio.create_task(self._stop_timer(self.pending_stop.copy()))

    async def _stop_timer(self, payload: dict):
        try:
            await asyncio.sleep(int(payload["stop_minutes"]) * 60)
            from blocker_window import blocker
            blocker.show_stop_resume_prompt(payload)
        except asyncio.CancelledError:
            pass

    def cancel_pending_break(self):
        if not self.pending_resume:
            return
        payload = self.pending_resume
        self.pending_resume = None
        if self._break_task and not self._break_task.done():
            self._break_task.cancel()
        self._record_timed_block(payload, "break", actual_end=datetime.now())

    def cancel_pending_stop(self):
        if not self.pending_stop:
            return
        payload = self.pending_stop
        self.pending_stop = None
        if self._stop_task and not self._stop_task.done():
            self._stop_task.cancel()
        self._record_timed_block(payload, "stopped_pending", actual_end=datetime.now())

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
        if self._stop_task and not self._stop_task.done():
            self._stop_task.cancel()
        self.pending_resume = None
        self.pending_stop = None

    def get_status(self) -> dict:
        now = datetime.now()

        def serialize(kind: str, payload: Optional[dict]):
            if not payload:
                return {"active": False, "kind": kind}
            try:
                ends_at = datetime.fromisoformat(payload["ends_at"])
                remaining = max(0, int((ends_at - now).total_seconds()))
            except Exception:
                remaining = 0
            return {
                "active": True,
                "kind": kind,
                "remaining_seconds": remaining,
                **payload,
            }

        if self.pending_resume:
            return serialize("break", self.pending_resume)
        if self.pending_stop:
            return serialize("stopped_pending", self.pending_stop)
        return {"active": False, "kind": "idle"}


flow_manager = FlowManager()
