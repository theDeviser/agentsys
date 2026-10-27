import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from agentsys.profile import save  # noqa: E402
from agentsys.scheduler import SchedulerError, tick  # noqa: E402

from tests.helpers import IsolatedEnv  # noqa: E402


class TestScheduler(unittest.TestCase):
    def test_dry_run_requires_rules(self):
        with IsolatedEnv() as env:
            env.cli("init", actor="human:v")
            st_path = env.store_path()
            from agentsys.store import Store
            st = Store(st_path)
            cli = [sys.executable, str(REPO / "bin" / "agentsys")]
            with self.assertRaises(SchedulerError):
                tick(st, env.root, cli, dry_run=True)

    def test_dry_run_picks_task(self):
        with IsolatedEnv() as env:
            env.cli("init", actor="human:v")
            save(env.root, {"version": 1, "commands": [],
                            "routing": {"rules": [{"kind": "*", "prefer": [{"adapter": "mock", "account": "local"}]}]}})
            env.cli("budget", "set", "mock", "local", "--limit", "10000", actor="human:v")
            tid = env.cli("task", "add", "T", "--kind", "research", actor="human:v").stdout.strip()
            from agentsys.store import Store
            st = Store(env.store_path())
            cli = [sys.executable, str(REPO / "bin" / "agentsys")]
            decisions = tick(st, env.root, cli, dry_run=True)
            self.assertTrue(any(d["task_id"] == tid and d["action"] == "would_dispatch" for d in decisions))


if __name__ == "__main__":
    unittest.main()
