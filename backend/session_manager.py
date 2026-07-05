import asyncio
import json
import uuid
import time
from datetime import datetime
from typing import Optional

from data_paths import LOGS_DIR
from report_manager import record_block
from screenshot import take_screenshot
from vision_judge import judge_screenshot, evaluate_dispute
from blocker_window import blocker


LOG_FILE = LOGS_DIR / "session_logs.jsonl"
MEMORY_FILE = LOGS_DIR / "dispute_memory.json"


def _load_memory() -> list:
    """Load dispute memory (accepted disputes that AI should remember)."""
    if MEMORY_FILE.exists():
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def _save_memory(memory: list):
    """Save dispute memory."""
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)


class SessionManager:
    """Manages a single focus monitoring session."""

    def __init__(self):
        self.session_id: Optional[str] = None
        self.task: Optional[str] = None
        self.duration_minutes: int = 10
        self.check_interval_seconds: int = 30
        self.active: bool = False
        self.start_time: Optional[float] = None
        self.latest_judgement: Optional[dict] = None
        self.off_task_streak: int = 0
        self.should_block: bool = False
        self.logs: list = []
        self._loop_task: Optional[asyncio.Task] = None
        self.dispute_memory: list = _load_memory()
        self.source: str = "manual"
        self.schedule_id: Optional[str] = None
        self.planned_start: Optional[str] = None
        self.planned_end: Optional[str] = None
        self.late_started: bool = False
        self._finalized: bool = False

    def start_session(
        self,
        task: str,
        duration_minutes: int,
        check_interval_seconds: int,
        source: str = "manual",
        schedule_id: Optional[str] = None,
        planned_start: Optional[str] = None,
        planned_end: Optional[str] = None,
        late_started: bool = False,
    ) -> str:
        """Start a new monitoring session."""
        task = (task or "").strip()
        if not task:
            raise ValueError("Task cannot be empty.")
        if duration_minutes <= 0:
            raise ValueError("Duration must be greater than 0.")
        if check_interval_seconds <= 0:
            raise ValueError("Check interval must be greater than 0.")

        if self.active:
            self.stop_session(status="replaced")

        self.session_id = str(uuid.uuid4())[:8]
        self.task = task
        self.duration_minutes = duration_minutes
        self.check_interval_seconds = check_interval_seconds
        self.active = True
        self.start_time = time.time()
        self.latest_judgement = None
        self.off_task_streak = 0
        self.should_block = False
        self.logs = []
        self.dispute_memory = _load_memory()
        self.source = source
        self.schedule_id = schedule_id
        self.planned_start = planned_start
        self.planned_end = planned_end
        self.late_started = late_started
        self._finalized = False

        # Start background monitoring loop
        self._loop_task = asyncio.create_task(self._monitor_loop())

        return self.session_id

    def stop_session(self, status: str = "stopped", notify: bool = False):
        """Stop the current session."""
        self._finish_session(status=status, notify=notify)
        current_task = None
        try:
            current_task = asyncio.current_task()
        except RuntimeError:
            pass
        if self._loop_task and not self._loop_task.done() and self._loop_task is not current_task:
            self._loop_task.cancel()
        self._loop_task = None

    def _finish_session(self, status: str, notify: bool = False):
        """Finalize the current session and write it to the daily report."""
        if self._finalized or not self.session_id:
            self.active = False
            return

        self.active = False
        self.should_block = False

        actual_start = datetime.fromtimestamp(self.start_time).isoformat() if self.start_time else None
        actual_end = datetime.now().isoformat()
        elapsed_minutes = 0
        if self.start_time:
            elapsed_minutes = max(0, (time.time() - self.start_time) / 60)

        valid_logs = [l for l in self.logs if l.get("judgement_status", "ok") != "api_error"]
        focused_checks = sum(1 for l in valid_logs if l.get("on_task", False))
        distracted_checks = sum(1 for l in valid_logs if not l.get("on_task", False))
        api_error_checks = sum(1 for l in self.logs if l.get("judgement_status") == "api_error")
        focus_minutes = min(elapsed_minutes, focused_checks * self.check_interval_seconds / 60)

        block = {
            "session_id": self.session_id,
            "schedule_id": self.schedule_id,
            "task": self.task,
            "source": self.source,
            "status": status,
            "late_started": self.late_started,
            "planned_start": self.planned_start,
            "planned_end": self.planned_end,
            "actual_start": actual_start,
            "actual_end": actual_end,
            "duration_minutes": round(elapsed_minutes, 1),
            "focus_minutes": round(focus_minutes, 1),
            "total_checks": len(valid_logs),
            "focused_checks": focused_checks,
            "distracted_checks": distracted_checks,
            "api_error_checks": api_error_checks,
        }
        record_block(block)
        if self.schedule_id:
            try:
                from schedule_manager import remove_schedule
                remove_schedule(self.schedule_id)
            except Exception as e:
                print(f"[session] Could not remove completed schedule {self.schedule_id}: {e}")
        self._finalized = True

        if notify:
            try:
                blocker.show_flow_prompt({
                    "task": self.task,
                    "duration_minutes": self.duration_minutes,
                    "check_interval_seconds": self.check_interval_seconds,
                    "focus_minutes": block["focus_minutes"],
                    "distracted_checks": distracted_checks,
                    "api_error_checks": api_error_checks,
                })
            except Exception as e:
                print(f"[session] End notification error (non-fatal): {e}")
        else:
            blocker.dismiss()

    def acknowledge_block(self):
        """User acknowledged the block overlay."""
        self.should_block = False
        self.off_task_streak = 0
        # Dismiss system-level blocker window
        blocker.dismiss()

    def dispute(self, reason: str) -> dict:
        """User disputes the AI judgement. Ask AI to re-evaluate."""
        result = evaluate_dispute(
            task=self.task,
            activity=self.latest_judgement.get("current_activity", "") if self.latest_judgement else "",
            original_reason=self.latest_judgement.get("reason", "") if self.latest_judgement else "",
            user_reason=reason,
            memory=self.dispute_memory,
        )

        if result.get("accepted", False):
            # AI accepted the dispute - remember this for future
            memory_entry = {
                "timestamp": datetime.now().isoformat(),
                "task": self.task,
                "activity": self.latest_judgement.get("current_activity", "") if self.latest_judgement else "",
                "user_reason": reason,
                "ai_note": result.get("ai_reason", ""),
            }
            self.dispute_memory.append(memory_entry)
            _save_memory(self.dispute_memory)

            # Clear block state
            self.should_block = False
            self.off_task_streak = 0
            blocker.dismiss()

            print(f"[session] Dispute ACCEPTED: {reason}")
        else:
            print(f"[session] Dispute REJECTED: {result.get('ai_reason', '')}")

        return result

    def get_remaining_seconds(self) -> int:
        """Get remaining time in seconds."""
        if not self.active or not self.start_time:
            return 0
        elapsed = time.time() - self.start_time
        total = self.duration_minutes * 60
        remaining = max(0, total - elapsed)
        return int(remaining)

    def get_status(self) -> dict:
        """Get current session status."""
        return {
            "active": self.active,
            "session_id": self.session_id,
            "task": self.task,
            "remaining_seconds": self.get_remaining_seconds(),
            "latest_judgement": self.latest_judgement,
            "off_task_streak": self.off_task_streak,
            "should_block": self.should_block,
            "source": self.source,
            "schedule_id": self.schedule_id,
            "planned_start": self.planned_start,
            "planned_end": self.planned_end,
            "logs": self.logs[-20:],  # Return last 20 logs
        }

    def _apply_judgement(self, result: dict) -> str:
        """Apply a judgement to streak/blocking state and return its status."""
        judgement_status = result.get("judgement_status", "ok")
        if judgement_status == "api_error":
            return judgement_status

        if result.get("on_task", True):
            self.off_task_streak = 0
            self.should_block = False
        else:
            self.off_task_streak += 1

        if self.off_task_streak >= 2:
            self.should_block = True

        return judgement_status

    async def _monitor_loop(self):
        """Background loop: take screenshot, judge, update state."""
        try:
            while self.active:
                # Check if session time is up
                if self.get_remaining_seconds() <= 0:
                    print(f"[session] Session {self.session_id} time is up. Stopping.")
                    self._finish_session(status="completed", notify=True)
                    break

                # Take screenshot
                try:
                    screenshot_path = take_screenshot()
                except Exception as e:
                    print(f"[session] Screenshot error: {e}")
                    await asyncio.sleep(self.check_interval_seconds)
                    continue

                # Judge (pass memory for context)
                result = judge_screenshot(self.task, screenshot_path, memory=self.dispute_memory)
                self.latest_judgement = result
                judgement_status = self._apply_judgement(result)

                # Check if should block
                if self.should_block:
                    # Show system-level blocker window
                    if not blocker.is_showing:
                        try:
                            blocker.show(
                                task=self.task,
                                activity=result.get("current_activity", ""),
                                reason=result.get("reason", ""),
                            )
                        except Exception as e:
                            print(f"[session] Blocker show error (non-fatal): {e}")

                # Create log entry
                log_entry = {
                    "timestamp": datetime.now().isoformat(),
                    "session_id": self.session_id,
                    "task": self.task,
                    "source": self.source,
                    "schedule_id": self.schedule_id,
                    "judgement_status": judgement_status,
                    "on_task": result.get("on_task", True),
                    "confidence": result.get("confidence", 0),
                    "current_activity": result.get("current_activity", ""),
                    "reason": result.get("reason", ""),
                    "model": result.get("model", ""),
                    "screenshot_path": screenshot_path,
                }
                self.logs.append(log_entry)

                # Write to log file
                with open(LOG_FILE, "a", encoding="utf-8") as f:
                    f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

                print(
                    f"[session] Check: on_task={result.get('on_task')} "
                    f"streak={self.off_task_streak} "
                    f"activity={result.get('current_activity')}"
                )

                # Wait for next interval
                await asyncio.sleep(self.check_interval_seconds)

        except asyncio.CancelledError:
            print(f"[session] Session {self.session_id} cancelled.")
        except Exception as e:
            print(f"[session] Monitor loop error: {e}")
            self.active = False


# Singleton session manager
session_manager = SessionManager()
