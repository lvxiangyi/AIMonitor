import os
import unittest
from unittest.mock import patch

os.environ["AIMONITOR_NO_BLOCKER_SINGLETON"] = "1"

from flow_manager import FlowManager
from report_manager import REPORT_FILE, get_daily_report
from session_manager import session_manager


class FlowManagerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._report_backup = REPORT_FILE.read_bytes() if REPORT_FILE.exists() else None
        if REPORT_FILE.exists():
            REPORT_FILE.unlink()
        session_manager.active = False
        session_manager.session_id = None
        session_manager._finalized = True
        self.flow = FlowManager()

    def tearDown(self):
        if session_manager.active:
            session_manager.stop_session(status="stopped")
        if self.flow._break_task and not self.flow._break_task.done():
            self.flow._break_task.cancel()
        if REPORT_FILE.exists():
            REPORT_FILE.unlink()
        if self._report_backup is not None:
            REPORT_FILE.write_bytes(self._report_backup)

    async def test_continue_work_starts_flow_session(self):
        with patch.object(session_manager, "start_session", return_value="abc123") as start_session:
            session_id = self.flow.continue_work("new task", 25, 30)

        self.assertEqual(session_id, "abc123")
        start_session.assert_called_once_with(
            task="new task",
            duration_minutes=25,
            check_interval_seconds=30,
            source="flow",
        )

    async def test_start_break_records_report_and_pending_resume(self):
        self.flow.start_break(
            break_minutes=10,
            activity="walk outside",
            task="product",
            duration_minutes=25,
            check_interval_seconds=30,
        )

        self.assertEqual(self.flow.pending_resume["task"], "product")
        report = get_daily_report()
        self.assertEqual(report["blocks"][0]["status"], "break")
        self.assertEqual(report["blocks"][0]["task"], "walk outside")

    async def test_pause_day_records_activity(self):
        self.flow.pause_day("go shopping")

        report = get_daily_report()
        self.assertEqual(report["blocks"][0]["status"], "day_paused")
        self.assertEqual(report["blocks"][0]["task"], "go shopping")
