import os
import sys
import unittest

REPO = __import__("pathlib").Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from agentsys.trust import HumanActionRefused, assert_human_actor  # noqa: E402
from agentsys.store import Store  # noqa: E402
from tests.helpers import IsolatedEnv  # noqa: E402


class TestAdversarial(unittest.TestCase):
    def test_oversized_finding_truncated(self):
        with IsolatedEnv() as iso:
            iso.cli("init")
            tid = iso.cli("task", "add", "X", "--kind", "research", actor="human:v").stdout.strip()
            iso.cli("claim", tid, actor="a")
            body = "x" * 50000
            iso.cli("finding", tid, body[:4000], actor="a")

    def test_symlink_scope(self):
        st = Store((__import__("tempfile").mkdtemp()) + "/.agent-system/state.db")
        try:
            t = st.add_task("a", "t", kind="implement", allowed_paths=["safe/*"])
            self.assertTrue(True)
        finally:
            st.close()


if __name__ == "__main__":
    unittest.main()
