import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


class TestChangelog(unittest.TestCase):
    def test_site_changelog_generated(self):
        script = REPO / "scripts" / "build_changelog_site.py"
        p = subprocess.run([sys.executable, str(script)], cwd=REPO, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        html = (REPO / "site" / "changelog.html").read_text(encoding="utf-8")
        self.assertIn("0.1.0", html)
        self.assertIn("Activity dashboard filter", html)


if __name__ == "__main__":
    unittest.main()
