import os
import unittest

os.environ["AIMONITOR_NO_BLOCKER_SINGLETON"] = "1"

from blocker_window import _centered_rect, _content_position


class BlockerWindowGeometryTests(unittest.TestCase):
    def test_centered_rect_handles_negative_monitor_coordinates(self):
        monitor = (-341, -1440, 3440, 1440)

        rect = _centered_rect(monitor, 520, 260)

        self.assertEqual(rect, (1119, -850, 520, 260))

    def test_content_position_centers_on_cursor_monitor_inside_virtual_overlay(self):
        virtual = (-341, -1440, 6341, 3040)
        monitor = (-341, -1440, 3440, 1440)

        x, y = _content_position(virtual, monitor)

        self.assertEqual((x, y), (1720, 720))
