import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from agentsys import budget, routing  # noqa: E402
from agentsys.adapters import ADAPTERS  # noqa: E402
from agentsys.profile import save  # noqa: E402
from agentsys.store import Store  # noqa: E402

from tests.helpers import IsolatedEnv  # noqa: E402


class TestRoutingPick(unittest.TestCase):
    def test_picks_first_qualifying_candidate(self):
        with IsolatedEnv() as env:
            st = Store(env.store_path())
            st.set_budget("mock", "local", 1_000_000, "human:v", reserve_pct=0)
            t = st.add_task("human:v", "R", kind="research")
            rules = [{"kind": "research", "prefer": [{"adapter": "mock", "account": "local"}]}]
            adapter, account, reason = routing.pick(st, t, rules)
            self.assertEqual((adapter.name, account), ("mock", "local"))
            self.assertIn("research", reason)

    def test_skips_over_max_pct(self):
        with IsolatedEnv() as env:
            st = Store(env.store_path())
            st.set_budget("mock", "a", 1000, "human:v", reserve_pct=0)
            import time
            st.record_run(ts_start=time.time(), adapter="mock", provider="mock", account="a",
                          usage_source="mock", tokens_in=900, tokens_out=0, tokens_cached=0)
            t = st.add_task("human:v", "R", kind="research")
            rules = [{"kind": "*", "prefer": [{"adapter": "mock", "account": "a", "max_pct": 50},
                                              {"adapter": "mock", "account": "b"}]}]
            st.set_budget("mock", "b", 1000, "human:v", reserve_pct=0)
            adapter, account, _ = routing.pick(st, t, rules)
            self.assertEqual(account, "b")

    def test_rejects_when_none_qualify(self):
        with IsolatedEnv() as env:
            st = Store(env.store_path())
            t = st.add_task("human:v", "R", kind="research")
            with self.assertRaises(routing.RoutingError) as ctx:
                routing.pick(st, t, [{"kind": "*", "prefer": [{"adapter": "claude", "account": "x"}]}])
            self.assertTrue(ctx.exception.rejections)


class TestRouteCLI(unittest.TestCase):
    def test_route_command_reads_profile(self):
        with IsolatedEnv() as env:
            env.cli("init", actor="human:v")
            save(env.root, {
                "version": 1,
                "commands": [],
                "routing": {"rules": [{"kind": "*", "prefer": [{"adapter": "mock", "account": "local"}]}]},
            })
            env.cli("budget", "set", "mock", "local", "--limit", "1000", actor="human:v")
            tid = env.cli("task", "add", "T", "--kind", "research", actor="human:v").stdout.strip()
            r = env.cli("route", tid, actor="human:v")
            self.assertIn("mock", r.stdout)
            self.assertIn("local", r.stdout)


if __name__ == "__main__":
    unittest.main()
