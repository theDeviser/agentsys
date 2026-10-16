"""Verification profiles and gate execution."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from agentsys import profile, verify  # noqa: E402
from tests.helpers import IsolatedEnv  # noqa: E402


class TestProfileDetect(unittest.TestCase):
    def test_detects_package_json(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "package.json").write_text(json.dumps({"scripts": {"test": "node -e 'process.exit(0)'"}}))
            d = profile.detect(root)
            self.assertTrue(any(c["name"] == "npm:test" for c in d["commands"]))


class TestProfileRun(unittest.TestCase):
    def test_no_profile_label(self):
        with IsolatedEnv() as iso:
            iso.cli("init")
            tid = iso.cli("task", "add", "P", "--path", "app/*", "--kind", "implement", actor="human:v").stdout.strip()
            wt = Path(iso.cli("claim", tid, actor="a").stdout.split("work in: ")[1].strip())
            (wt / "app" / "ui.jsx").write_text("export const A = () => <div>!</div>;\n")
            iso.cli("submit", tid, "s", actor="a")
            out = iso.cli("verify", tid, actor="system:v").stdout
            self.assertIn("verified (no tests)", out)

    def test_failing_command_blocks(self):
        with IsolatedEnv() as iso:
            iso.cli("init")
            prop = profile.detect(iso.root)
            prop["commands"] = [{"name": "fail", "command": "exit 1", "cwd": ".", "timeout": 5, "blocking": True}]
            profile.save(iso.root, prop)
            tid = iso.cli("task", "add", "F", "--path", "app/*", "--kind", "implement", actor="human:v").stdout.strip()
            wt = Path(iso.cli("claim", tid, actor="a").stdout.split("work in: ")[1].strip())
            (wt / "app" / "ui.jsx").write_text("export const A = () => <div>!</div>;\n")
            iso.cli("submit", tid, "s", actor="a")
            p = iso.cli("verify", tid, actor="system:v", ok=False)
            self.assertEqual(p.returncode, 2)
            self.assertIn("profile:fail", p.stdout)

    def test_secret_in_output_by_type(self):
        wt = Path(tempfile.mkdtemp())
        spec = {"commands": [{"name": "leak", "command": "echo 'sk-proj-abcdefghijklmnopqrstuvwxyz012345'", "timeout": 5}]}
        results, _ = profile.run_profile(wt, spec)
        self.assertIn("openai-style-key", results[0]["detail"])


if __name__ == "__main__":
    unittest.main()
