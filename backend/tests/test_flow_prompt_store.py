import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ["AIMONITOR_NO_BLOCKER_SINGLETON"] = "1"

import flow_prompt_store as store


class FlowPromptStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.pending_path = Path(self.temp_dir.name) / "pending_flow_prompt.json"
        patcher = patch.object(store, "PENDING_FLOW_FILE", self.pending_path)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_save_load_and_clear(self):
        summary = {"task": "math", "duration_minutes": 25}
        store.save_pending_flow(summary)
        self.assertTrue(self.pending_path.exists())
        self.assertEqual(store.load_pending_flow(), summary)
        store.clear_pending_flow()
        self.assertFalse(self.pending_path.exists())
        self.assertIsNone(store.load_pending_flow())

    def test_load_invalid_json_returns_none(self):
        self.pending_path.write_text("{not json", encoding="utf-8")
        self.assertIsNone(store.load_pending_flow())


if __name__ == "__main__":
    unittest.main()
