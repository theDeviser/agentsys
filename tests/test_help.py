import re
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CLI = [sys.executable, str(REPO / "bin" / "agentsys")]


class TestHelpDrift(unittest.TestCase):
    def test_readme_lists_core_commands(self):
        readme = (REPO / "README.md").read_text(encoding="utf-8")
        helpout = subprocess.run(CLI + ["--help"], capture_output=True, text=True).stdout
        for cmd in ("init", "task", "dispatch", "verify", "review", "verify-log", "doctor", "mcp"):
            self.assertIn(cmd, helpout)
            self.assertRegex(readme, re.compile(rf"\b{cmd}\b"))


if __name__ == "__main__":
    unittest.main()
