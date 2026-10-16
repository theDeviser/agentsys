"""Git-derived resume and handoff."""
from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from tests.helpers import IsolatedEnv  # noqa: E402


class TestHandoff(unittest.TestCase):
    def test_brief_shows_commit_without_checkpoint(self):
        with IsolatedEnv() as iso:
            iso.cli("init")
            tid = iso.cli("task", "add", "C", "--path", "app/*", "--kind", "implement", actor="human:v").stdout.strip()
            wt = Path(iso.cli("claim", tid, actor="cursor:a:w").stdout.split("work in: ")[1].strip())
            (wt / "app" / "ui.jsx").write_text("export const A = () => <div>c</div>;\n")
            iso.cli("checkpoint", tid, "wip", "--commit", actor="cursor:a:w")
            brief = iso.cli("resume", tid).stdout
            self.assertIn("Commits since base [git-derived]", brief)
            self.assertIn("c", brief)

    def test_handoff_command(self):
        with IsolatedEnv() as iso:
            iso.cli("init")
            tid = iso.cli("task", "add", "H", "--kind", "research", actor="human:v").stdout.strip()
            out = iso.cli("handoff", tid, "--to", "mock").stdout
            self.assertIn("agentsys dispatch", out)
            self.assertIn("--adapter mock", out)

    def test_lease_expiry_in_brief(self):
        with IsolatedEnv() as iso:
            iso.cli("init")
            tid = iso.cli("task", "add", "L", "--kind", "research", actor="human:v").stdout.strip()
            iso.cli("claim", tid, "--no-worktree", actor="a")
            iso.cli("heartbeat", tid, actor="a")
            self.assertIn("heartbeat", iso.cli("resume", tid).stdout)


if __name__ == "__main__":
    unittest.main()
