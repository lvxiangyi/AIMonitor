import asyncio
from datetime import datetime
from typing import Optional

from blocker_window import blocker
from screenshot import take_screenshot
from settings_manager import get_guardian_check_interval_seconds, get_nudge_prompt, is_guardian_mode_enabled
from vision_judge import judge_guardian_screenshot


class GuardianManager:
    """Always-on lightweight guard for obvious entertainment distractions."""

    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self.latest_judgement: Optional[dict] = None
        self.last_checked_at: Optional[str] = None

    def start(self):
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._loop())

    def stop(self):
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None

    def get_status(self) -> dict:
        return {
            "enabled": is_guardian_mode_enabled(),
            "check_interval_seconds": get_guardian_check_interval_seconds(),
            "latest_judgement": self.latest_judgement,
            "last_checked_at": self.last_checked_at,
        }

    async def _loop(self):
        while True:
            interval = get_guardian_check_interval_seconds()
            await asyncio.sleep(interval)
            try:
                if is_guardian_mode_enabled() and not blocker.is_showing:
                    await self._check_once()
            except Exception as e:
                print(f"[guardian] Error: {e}")

    async def _check_once(self):
        screenshot_path = take_screenshot()
        result = judge_guardian_screenshot(screenshot_path)
        self.latest_judgement = result
        self.last_checked_at = datetime.now().isoformat()

        if result.get("judgement_status") == "api_error":
            return

        if "should_interrupt" in result:
            should_interrupt = bool(result.get("should_interrupt"))
        else:
            should_interrupt = not result.get("on_task", True)
        if should_interrupt and not blocker.is_showing:
            blocker.show(
                task="Guardian mode",
                activity=result.get("current_activity", ""),
                reason=result.get("reason", ""),
                strict_mode=True,
                nudge_message=get_nudge_prompt(),
                recovery=False,
            )


guardian_manager = GuardianManager()
