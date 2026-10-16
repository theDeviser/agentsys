import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from agentsys.ledger import Ledger  # noqa: E402
from agentsys.usage_import import import_file  # noqa: E402


class TestUsageImport(unittest.TestCase):
    def test_claude_dedupe_and_no_prompt(self):
        led = Ledger(REPO / "tests" / "tmp-ledger.db")
        try:
            p = REPO / "tests" / "fixtures" / "claude_usage.jsonl"
            s1 = import_file(p, "claude", led)
            s2 = import_file(p, "claude", led)
            self.assertEqual(s1["imported"], 1)
            self.assertEqual(s2["imported"], 0)
            rows = led.db.execute("SELECT * FROM imported_usage").fetchall()
            self.assertEqual(len(rows), 1)
            blob = json.dumps([dict(r) for r in rows])
            self.assertNotIn("prompt", blob.lower())
        finally:
            led.close()
            (REPO / "tests" / "tmp-ledger.db").unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
