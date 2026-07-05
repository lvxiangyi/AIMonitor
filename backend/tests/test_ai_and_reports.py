import os
import tempfile
import unittest
from unittest.mock import patch

os.environ["AIMONITOR_NO_BLOCKER_SINGLETON"] = "1"
os.environ.pop("AIMONITOR_ENABLE_MOCK_AI", None)

import vision_judge
from report_manager import REPORT_FILE, get_daily_report, record_block
from session_manager import SessionManager


class _FailingCompletions:
    def create(self, **kwargs):
        raise Exception("Error code: 401 - User not found.")


class _FailingClient:
    class _Chat:
        completions = _FailingCompletions()

    chat = _Chat()


class AiFailureTests(unittest.TestCase):
    def test_api_error_does_not_fall_back_to_random_mock(self):
        os.environ["OPENROUTER_API_KEY"] = "sk-or-test"
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"not-a-real-image-but-readable")
            image_path = f.name

        try:
            with patch.object(vision_judge, "_get_client", return_value=_FailingClient()):
                result = vision_judge.judge_screenshot("develop product", image_path)
        finally:
            os.unlink(image_path)

        self.assertEqual(result["judgement_status"], "api_error")
        self.assertTrue(result["on_task"])
        self.assertEqual(result["confidence"], 0)
        self.assertNotIn(result["current_activity"], {"browsing social media", "watching YouTube Shorts", "playing a game"})

    def test_api_error_does_not_increase_off_task_streak(self):
        manager = SessionManager()
        manager.off_task_streak = 1
        manager.should_block = False

        status = manager._apply_judgement({
            "judgement_status": "api_error",
            "on_task": True,
        })

        self.assertEqual(status, "api_error")
        self.assertEqual(manager.off_task_streak, 1)
        self.assertFalse(manager.should_block)


class ReportTests(unittest.TestCase):
    def setUp(self):
        self._report_backup = REPORT_FILE.read_bytes() if REPORT_FILE.exists() else None
        if REPORT_FILE.exists():
            REPORT_FILE.unlink()

    def tearDown(self):
        if REPORT_FILE.exists():
            REPORT_FILE.unlink()
        if self._report_backup is not None:
            REPORT_FILE.write_bytes(self._report_backup)

    def test_daily_report_aggregates_blocks(self):
        record_block({
            "session_id": "a",
            "task": "product",
            "source": "manual",
            "status": "completed",
            "planned_start": None,
            "planned_end": None,
            "actual_start": "2026-07-05T11:00:00",
            "actual_end": "2026-07-05T11:30:00",
            "focus_minutes": 20,
            "distracted_checks": 1,
        })
        record_block({
            "session_id": "b",
            "task": "writing",
            "source": "schedule",
            "status": "missed",
            "planned_start": "2026-07-05T12:00:00",
            "planned_end": "2026-07-05T12:30:00",
            "actual_start": None,
            "actual_end": None,
            "focus_minutes": 0,
            "distracted_checks": 0,
        })

        report = get_daily_report("2026-07-05")

        self.assertEqual(report["total_blocks"], 2)
        self.assertEqual(report["completed_blocks"], 1)
        self.assertEqual(report["total_focus_minutes"], 20)
