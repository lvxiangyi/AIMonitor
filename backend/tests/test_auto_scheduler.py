import os
import unittest
from datetime import datetime, timedelta

os.environ["AIMONITOR_NO_BLOCKER_SINGLETON"] = "1"

from auto_scheduler import AutoScheduler
from report_manager import REPORT_FILE, get_daily_report
from schedule_manager import SCHEDULE_FILE, add_schedule, get_schedules
from session_manager import session_manager


class AutoSchedulerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._backups = {path: path.read_bytes() if path.exists() else None for path in (SCHEDULE_FILE, REPORT_FILE)}
        for path in (SCHEDULE_FILE, REPORT_FILE):
            if path.exists():
                path.unlink()
        session_manager.active = False
        session_manager.session_id = None
        session_manager._finalized = True

    def tearDown(self):
        if session_manager.active:
            session_manager.stop_session(status="stopped")
        for path in (SCHEDULE_FILE, REPORT_FILE):
            if path.exists():
                path.unlink()
            backup = self._backups.get(path)
            if backup is not None:
                path.write_bytes(backup)

    async def test_starts_schedule_inside_window_and_marks_in_progress(self):
        now = datetime.now().replace(second=0, microsecond=0)
        start = now - timedelta(minutes=5)
        end = now + timedelta(minutes=15)
        entry = add_schedule(
            task="product development",
            date=now.date().isoformat(),
            start_time=start.strftime("%H:%M"),
            end_time=end.strftime("%H:%M"),
            strict_mode=True,
        )

        AutoScheduler().process_due_schedules(now=now)

        self.assertTrue(session_manager.active)
        self.assertEqual(session_manager.schedule_id, entry["id"])
        self.assertTrue(session_manager.late_started)
        self.assertTrue(session_manager.strict_mode)
        self.assertEqual(get_schedules()[0]["status"], "in_progress")

        session_manager.stop_session(status="completed")
        self.assertEqual(get_schedules(), [])

    async def test_missed_schedule_is_removed_and_reported(self):
        now = datetime.now().replace(second=0, microsecond=0)
        start = now - timedelta(minutes=30)
        end = now - timedelta(minutes=5)
        add_schedule(
            task="missed block",
            date=now.date().isoformat(),
            start_time=start.strftime("%H:%M"),
            end_time=end.strftime("%H:%M"),
        )

        AutoScheduler().process_due_schedules(now=now)

        self.assertEqual(get_schedules(), [])
        report = get_daily_report(now.date().isoformat())
        self.assertEqual(report["blocks"][0]["status"], "missed")

    async def test_active_session_conflict_is_skipped(self):
        now = datetime.now().replace(second=0, microsecond=0)
        start = now - timedelta(minutes=1)
        end = now + timedelta(minutes=20)
        add_schedule(
            task="conflicting block",
            date=now.date().isoformat(),
            start_time=start.strftime("%H:%M"),
            end_time=end.strftime("%H:%M"),
        )
        session_manager.active = True

        AutoScheduler().process_due_schedules(now=now)

        session_manager.active = False
        self.assertEqual(get_schedules(), [])
        report = get_daily_report(now.date().isoformat())
        self.assertEqual(report["blocks"][0]["status"], "skipped_conflict")
