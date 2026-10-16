"""End-to-end flow with mock adapters."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from tests.helpers import IsolatedEnv  # noqa: E402


class TestE2E(unittest.TestCase):
    def test_happy_path_verify_log(self):
        with IsolatedEnv() as iso:
            iso.cli("init")
            t1 = iso.cli("task", "add", "A", "--path", "app/*", "--kind", "implement", actor="human:v").stdout.strip()
            t2 = iso.cli("task", "add", "B", "--path", "docs/*", "--kind", "implement", actor="human:v").stdout.strip()
            iso.cli("claim", t1, actor="a")
            iso.cli("claim", t2, actor="b", ok=False)
            iso.cli("release", t1, actor="a")
            iso.cli("dispatch", t1, "--adapter", "mock")
            iso.cli("verify", t1, actor="system:v")
            iso.cli("review", t1, "approve", "--reason", "ok", actor="c:r")
            iso.cli("verify-log")


if __name__ == "__main__":
    unittest.main()
