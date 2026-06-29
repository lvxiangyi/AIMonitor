import asyncio
import json
import uuid
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from screenshot import take_screenshot
from vision_judge import judge_screenshot, evaluate_dispute
from blocker_window import blocker


LOGS_DIR = Path(__file__).parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)
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

    def start_session(self, task: str, duration_minutes: int, check_interval_seconds: int) -> str:
        """Start a new monitoring session."""
        if self.active:
            self.stop_session()

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

        # Start background monitoring loop
        self._loop_task = asyncio.create_task(self._monitor_loop())

        return self.session_id

    def stop_session(self):
        """Stop the current session."""
        self.active = False
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()
        self._loop_task = None

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
            "logs": self.logs[-20:],  # Return last 20 logs
        }

    async def _monitor_loop(self):
        """Background loop: take screenshot, judge, update state."""
        try:
            while self.active:
                # Check if session time is up
                if self.get_remaining_seconds() <= 0:
                    print(f"[session] Session {self.session_id} time is up. Stopping.")
                    self.active = False
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

                # Update streak
                if result.get("on_task", True):
                    self.off_task_streak = 0
                    self.should_block = False
                else:
                    self.off_task_streak += 1

                # Check if should block
                if self.off_task_streak >= 2:
                    self.should_block = True
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
                    "on_task": result.get("on_task", True),
                    "confidence": result.get("confidence", 0),
                    "current_activity": result.get("current_activity", ""),
                    "reason": result.get("reason", ""),
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
