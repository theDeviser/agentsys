"""Smoke tests for dashboard Activity view markup."""
import json
import re
import sys
import threading
import time
import unittest
from http.client import HTTPConnection
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from agentsys import ui  # noqa: E402
from tests.helpers import IsolatedEnv  # noqa: E402


class TestActivityMarkup(unittest.TestCase):
    def test_dashboard_page_has_activity_list_region(self):
        with IsolatedEnv() as iso:
            iso.cli("init")
            iso.cli("task", "add", "T", "--kind", "research", actor="human:v")
            db = iso.store_path()
            port = 28791
            t = threading.Thread(target=ui.serve, args=(db,), kwargs={"port": port, "writable": False}, daemon=True)
            t.start()
            time.sleep(0.5)
            c = HTTPConnection("127.0.0.1", port)
            c.request("GET", "/")
            body = c.getresponse().read().decode()
            self.assertIn('id="activity-list"', body)
            self.assertIn("filterActivityEvents", body)
            self.assertIn("renderActivityList", body)


if __name__ == "__main__":
    unittest.main()
