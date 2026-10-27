import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from agentsys import routing  # noqa: E402
from agentsys.profile import save  # noqa: E402
from agentsys.store import Store  # noqa: E402

from tests.helpers import IsolatedEnv  # noqa: E402


class TestReviewerFor(unittest.TestCase):
    def test_pairs_and_fallback(self):
        pairs = {"codex": "claude", "*": "cursor"}
        self.assertEqual(routing.reviewer_for(["codex:alice:work"], pairs), "claude")
        self.assertEqual(routing.reviewer_for(["human:v"], pairs), "cursor")


class TestReviewHarnessGate(unittest.TestCase):
    def test_same_harness_refused_when_required(self):
        with IsolatedEnv() as env:
            env.cli("init", actor="human:v")
            save(env.root, {"version": 1, "commands": [],
                            "review": {"pairs": {"cursor": "claude"}, "require_different_harness": True}})
            tid = env.cli("task", "add", "T", "--path", "app/*", actor="human:v").stdout.strip()
            out = env.cli("claim", tid, actor="cursor:a:work").stdout
            wt = Path(out.split("work in: ")[1].strip())
            (wt / "app" / "x.jsx").write_text("export const X = 1;\n")
            env.cli("submit", tid, "added x", actor="cursor:a:work")
            env.cli("verify", tid, actor="system:v")
            p = env.cli("review", tid, "approve", "--reason", "ok", actor="cursor:b:reviewer", ok=False)
            self.assertIn("harness", p.stderr.lower())
