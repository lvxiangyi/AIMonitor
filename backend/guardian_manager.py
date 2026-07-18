import asyncio
import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from blocker_window import blocker
from data_paths import GUARDIAN_LOG_FILE, GUARDIAN_SCREENSHOT_DIR
from screenshot import take_screenshot
from settings_manager import get_guardian_check_interval_seconds, get_nudge_prompt, is_guardian_mode_enabled
from vision_judge import judge_guardian_screenshot


class GuardianManager:
    """Always-on lightweight guard for obvious entertainment distractions."""

    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._break_task: Optional[asyncio.Task] = None
        self.latest_judgement: Optional[dict] = None
        self.latest_screenshot_path: Optional[str] = None
        self.last_checked_at: Optional[str] = None
        self.pending_break: Optional[dict] = None

    def start(self):
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._loop())

    def stop(self):
        if self._task and not self._task.done():
            self._task.cancel()
        if self._break_task and not self._break_task.done():
            self._break_task.cancel()
        self._task = None
        self._break_task = None

    def get_status(self) -> dict:
        paused_by_session = self._is_session_active()
        enabled = is_guardian_mode_enabled()
        break_status = self._break_status()
        return {
            "enabled": enabled,
            "effective_enabled": bool(enabled and not paused_by_session and not break_status["active"]),
            "paused_by_session": paused_by_session,
            "break_status": break_status,
            "check_interval_seconds": get_guardian_check_interval_seconds(),
            "latest_judgement": self.latest_judgement,
            "latest_screenshot_path": self.latest_screenshot_path,
            "latest_screenshot_url": "/guardian/latest-screenshot" if self.latest_screenshot_path else None,
            "last_checked_at": self.last_checked_at,
        }

    async def _loop(self):
        while True:
            interval = get_guardian_check_interval_seconds()
            await asyncio.sleep(interval)
            try:
                if (
                    is_guardian_mode_enabled()
                    and not self._is_session_active()
                    and not self.pending_break
                    and not blocker.is_showing
                ):
                    await self._check_once()
            except Exception as e:
                print(f"[guardian] Error: {e}")

    def _is_session_active(self) -> bool:
        try:
            from session_manager import session_manager
            return bool(session_manager.active)
        except Exception:
            return False

    def return_to_work(self, minimum_next_step: str = ""):
        if self.pending_break:
            self.cancel_break()
        blocker.dismiss()

    def start_break(self, break_minutes: int, minimum_next_step: str) -> dict:
        step = (minimum_next_step or "").strip()
        if not step:
            raise ValueError("请输入休息后要做的最小下一步。")
        if break_minutes <= 0:
            raise ValueError("休息时长需要是正整数。")
        now = datetime.now().astimezone()
        ends_at = now + timedelta(minutes=break_minutes)
        payload = {
            "break_id": str(uuid.uuid4())[:8],
            "task": "Guardian mode",
            "activity": "Guardian 休息",
            "break_minutes": break_minutes,
            "minimum_next_step": step,
            "started_at": now.isoformat(),
            "ends_at": ends_at.isoformat(),
        }
        self.pending_break = payload
        if self._break_task and not self._break_task.done():
            self._break_task.cancel()
        self._break_task = asyncio.create_task(self._break_timer(payload.copy()))
        blocker.dismiss()
        return payload

    def cancel_break(self):
        self.pending_break = None
        if self._break_task and not self._break_task.done():
            self._break_task.cancel()
        self._break_task = None

    async def _break_timer(self, payload: dict):
        try:
            seconds = max(1, int(payload["break_minutes"]) * 60)
            if seconds > 5 * 60:
                await asyncio.sleep(seconds - 5 * 60)
                blocker.show_message(
                    "Guardian 休息提醒",
                    "休息时间还剩 5 分钟。请慢慢收尾，准备回到工作。",
                )
                await asyncio.sleep(5 * 60)
            else:
                await asyncio.sleep(seconds)
            self.pending_break = None
            blocker.show_break_end_translation({
                **payload,
                "activity": "Guardian 休息结束",
                "minimum_next_step": payload.get("minimum_next_step", ""),
                "guardian_mode": True,
                "translation_count": 3,
            })
        except asyncio.CancelledError:
            pass

    def _break_status(self) -> dict:
        if not self.pending_break:
            return {"active": False}
        try:
            ends_at = datetime.fromisoformat(self.pending_break["ends_at"])
            remaining = max(0, int((ends_at - datetime.now().astimezone()).total_seconds()))
        except Exception:
            remaining = 0
        return {
            "active": True,
            "remaining_seconds": remaining,
            **self.pending_break,
        }

    async def _check_once(self):
        screenshot_path = self._next_screenshot_path()
        take_screenshot(output_path=screenshot_path)
        result = judge_guardian_screenshot(screenshot_path)
        self.latest_judgement = result
        self.latest_screenshot_path = screenshot_path
        self.last_checked_at = datetime.now().isoformat()
        self._append_log(result, screenshot_path)

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
                recovery=True,
                recovery_mode="guardian",
                translation_count=3,
            )

    def _next_screenshot_path(self) -> str:
        now = datetime.now().astimezone()
        day_dir = GUARDIAN_SCREENSHOT_DIR / now.date().isoformat()
        day_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{now.strftime('%H%M%S')}-{uuid.uuid4()}.jpg"
        return str(day_dir / filename)

    def _append_log(self, result: dict, screenshot_path: str):
        now = datetime.now().astimezone().isoformat()
        try:
            try:
                relative_path = str(Path(screenshot_path).resolve().relative_to(GUARDIAN_SCREENSHOT_DIR.parent.resolve()))
            except Exception:
                relative_path = screenshot_path
            entry = {
                "checked_at": now,
                "screenshot_path": relative_path.replace("\\", "/"),
                "should_interrupt": bool(result.get("should_interrupt", not result.get("on_task", True))),
                "trigger_category": result.get("trigger_category", "none"),
                "confidence": result.get("confidence", 0),
                "current_activity": result.get("current_activity", ""),
                "reason": result.get("reason", ""),
                "model": result.get("model", ""),
                "judgement_status": result.get("judgement_status", "ok"),
            }
            GUARDIAN_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(GUARDIAN_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[guardian] Could not write log: {e}")


guardian_manager = GuardianManager()
