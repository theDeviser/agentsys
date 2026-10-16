import os
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CLI = [sys.executable, str(REPO / "bin" / "agentsys")]


class TestDemo(unittest.TestCase):
    def test_demo_completes(self):
        env = os.environ.copy()
        env["AGENTSYS_DEMO"] = "1"
        env["AGENTSYS_ACTOR"] = "human:demo"
        p = subprocess.run(CLI + ["demo"], capture_output=True, text=True, cwd=REPO, env=env, timeout=45)
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        self.assertIn("done in", p.stdout)


if __name__ == "__main__":
    unittest.main()
