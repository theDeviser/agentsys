import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from agentsys.adapter_health import check_live, check_offline  # noqa: E402
from agentsys.adapters import ADAPTERS  # noqa: E402
from tests.helpers import IsolatedEnv  # noqa: E402


class TestAdapterHealth(unittest.TestCase):
    def test_offline_includes_mock(self):
        rows = check_offline()
        mock = next(r for r in rows if r["adapter"] == "mock")
        self.assertEqual(mock["status"], "ok")

    def test_live_mock(self):
        with IsolatedEnv() as env:
            from agentsys.store import Store
            st = Store(env.store_path())
            st.set_budget("mock", "local", 1000, "human:v", reserve_pct=0)
            rows = check_live(st, "local", adapter_name="mock")
            self.assertEqual(rows[0]["status"], "ok")

    def test_live_refused_without_budget(self):
        if not ADAPTERS["claude"].binary():
            self.skipTest("claude CLI not installed")
        with IsolatedEnv() as env:
            from agentsys.store import Store
            st = Store(env.store_path())
            rows = check_live(st, "nobudget", adapter_name="claude")
            self.assertEqual(rows[0]["status"], "refused")


if __name__ == "__main__":
    unittest.main()
