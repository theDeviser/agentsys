"""Trust model: event chain, human provenance, migration, dashboard flags."""
from __future__ import annotations

import multiprocessing
import os
import sqlite3
import unittest.mock
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from agentsys import trust, ui  # noqa: E402
from agentsys.store import Store  # noqa: E402
from agentsys.trust import HumanActionRefused, assert_human_actor  # noqa: E402

from tests.helpers import IsolatedEnv  # noqa: E402

CLI = [sys.executable, str(REPO / "bin" / "agentsys")]


def _chain_writer(n, db, home, ledger):
    os.environ["AGENTSYS_HOME"] = home
    os.environ["AGENTSYS_LEDGER"] = ledger
    st = Store(db)
    for i in range(5):
        st.event(f"agent:cursor:w{n}", None, "test.tick", {"n": n, "i": i})
    st.close()


class TestHumanProvenance(unittest.TestCase):
    def test_refuse_dispatched_human(self):
        with unittest.mock.patch.dict(
            os.environ,
            {"AGENTSYS_DISPATCHED": "1"},
            clear=False,
        ):
            os.environ.pop("AGENTSYS_TEST_SUITE", None)
            with self.assertRaises(HumanActionRefused):
                assert_human_actor("human:v", "approval", dashboard_ok=False)

    def test_refuse_no_tty_without_dashboard(self):
        env = {k: v for k, v in os.environ.items() if k not in ("AGENTSYS_TEST_SUITE", "AGENTSYS_DASHBOARD_OK")}
        with unittest.mock.patch.dict(os.environ, env, clear=True):
            os.environ["AGENTSYS_DISPATCHED"] = "0"
            with self.assertRaises(HumanActionRefused):
                assert_human_actor("human:v", "approval", dashboard_ok=False)

    def test_dashboard_ok_allows(self):
        assert_human_actor("human:v", "approval", dashboard_ok=True)

    def test_cli_approve_refused_when_dispatched(self):
        with IsolatedEnv() as iso:
            iso.cli("init")
            tid = iso.cli("task", "add", "X", "--path", "app/*", "--kind", "implement", actor="human:v").stdout.strip()
            wt = Path(iso.cli("claim", tid, actor="cursor:v:w").stdout.split("work in: ")[1].strip())
            (wt / "app" / "ui.jsx").write_text("export const A = () => <div>ok</div>;\n")
            iso.cli("submit", tid, "done", actor="cursor:v:w")
            iso.cli("verify", tid, actor="system:v")
            iso.cli("review", tid, "approve", "--reason", "ok", actor="claude:h:r")
            iso.cli("merge", tid, actor="human:v", ok=False)
            env = {**iso.env, "AGENTSYS_DISPATCHED": "1", "AGENTSYS_ACTOR": "human:v"}
            env.pop("AGENTSYS_TEST_SUITE", None)
            p = subprocess.run(
                CLI + ["approve", "1"],
                cwd=str(iso.root),
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertNotEqual(p.returncode, 0)
            self.assertIn("refused", (p.stderr + p.stdout).lower())


class TestEventChain(unittest.TestCase):
    def test_verify_log_clean_after_events(self):
        with IsolatedEnv() as iso:
            iso.cli("init")
            iso.cli("task", "add", "Chain", "--kind", "research", actor="agent:cursor:worker")
            p = iso.cli("verify-log")
            self.assertIn("OK", p.stdout)

    def test_tamper_detected(self):
        with IsolatedEnv() as iso:
            iso.cli("init")
            iso.cli("task", "add", "T", "--kind", "research", actor="human:v")
            db = sqlite3.connect(str(iso.store_path()))
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT id, event_hash FROM events WHERE chain_status='chained' ORDER BY id DESC LIMIT 1").fetchone()
            db.execute("UPDATE events SET event_hash=? WHERE id=?", ("0" * 64, row["id"]))
            db.commit()
            db.close()
            p = iso.cli("verify-log", ok=False)
            self.assertNotEqual(p.returncode, 0)
            self.assertIn("hash mismatch", p.stderr)

    def test_migration_legacy_then_chain(self):
        tmp = Path(tempfile.mkdtemp(prefix="agentsys-mig-"))
        db_path = tmp / ".agent-system" / "state.db"
        db_path.parent.mkdir(parents=True)
        db = sqlite3.connect(str(db_path))
        db.executescript(
            """
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE tasks (
              id TEXT PRIMARY KEY, title TEXT NOT NULL, goal TEXT NOT NULL DEFAULT '',
              acceptance TEXT NOT NULL DEFAULT '', kind TEXT NOT NULL,
              allowed_paths TEXT NOT NULL DEFAULT '[]', checks TEXT NOT NULL DEFAULT '[]',
              deps TEXT NOT NULL DEFAULT '[]', state TEXT NOT NULL, owner TEXT,
              lease_expires REAL, attempts INTEGER NOT NULL DEFAULT 0,
              max_attempts INTEGER NOT NULL DEFAULT 2, worktree TEXT, branch TEXT, base TEXT,
              created_by TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL
            );
            CREATE TABLE events (
              id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, actor TEXT NOT NULL,
              task_id TEXT, kind TEXT NOT NULL, payload TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE findings (id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL, ts REAL NOT NULL,
              author TEXT NOT NULL, kind TEXT NOT NULL, body TEXT NOT NULL,
              evidence TEXT NOT NULL DEFAULT '[]', confidence TEXT);
            CREATE TABLE checkpoints (id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL, ts REAL NOT NULL,
              author TEXT NOT NULL, summary TEXT NOT NULL, commit_sha TEXT, verified INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE runs (id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, ts_start REAL NOT NULL,
              ts_end REAL, adapter TEXT NOT NULL, provider TEXT NOT NULL, account TEXT NOT NULL,
              model TEXT, exit_code INTEGER, tokens_in INTEGER, tokens_out INTEGER,
              tokens_cached INTEGER, tokens_estimate INTEGER, cost_usd REAL, usage_source TEXT NOT NULL, note TEXT);
            CREATE TABLE budgets (provider TEXT NOT NULL, account TEXT NOT NULL, limit_tokens INTEGER NOT NULL,
              reserve_pct REAL NOT NULL DEFAULT 20, source TEXT NOT NULL, note TEXT,
              updated_at REAL NOT NULL, PRIMARY KEY (provider, account));
            CREATE TABLE approvals (id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, action TEXT NOT NULL,
              requested_by TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '', status TEXT NOT NULL,
              decided_by TEXT, decided_at REAL, ts REAL NOT NULL);
            """
        )
        db.execute("INSERT INTO meta VALUES ('schema_version', '1')")
        db.execute(
            "INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("t-old", "Old", "", "", "research", "[]", "[]", "[]", "ready", None, None, 0, 2, None, None, None,
             "human:v", 1.0, 1.0),
        )
        db.execute("INSERT INTO events (ts, actor, task_id, kind, payload) VALUES (?,?,?,?,?)",
                   (1.0, "human:v", "t-old", "task.created", "{}"))
        db.commit()
        db.close()
        os.environ["AGENTSYS_HOME"] = str(tmp / "home")
        (tmp / "home").mkdir()
        st = Store(db_path)
        st.event("system:test", "t-old", "test.ping", {})
        n_legacy = st.db.execute("SELECT COUNT(*) FROM events WHERE chain_status='legacy'").fetchone()[0]
        self.assertGreaterEqual(n_legacy, 1)
        problems = trust.verify_event_chain(st.db, trust.load_install_key())
        self.assertEqual(problems, [])
        st.close()

    def test_multiprocess_chain(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "proj"
            root.mkdir()
            db_path = root / ".agent-system" / "state.db"
            home = str(Path(td) / "home")
            Path(home).mkdir()
            ledger = str(Path(td) / "ledger.db")
            os.environ["AGENTSYS_HOME"] = home
            Store(db_path).close()
            ctx = multiprocessing.get_context("spawn")
            procs = [ctx.Process(target=_chain_writer, args=(i, str(db_path), home, ledger)) for i in range(4)]
            for p in procs:
                p.start()
            for p in procs:
                p.join()
                self.assertEqual(p.exitcode, 0)
            st = Store(db_path)
            problems = trust.verify_event_chain(st.db, trust.load_install_key())
            self.assertEqual(problems, [])
            st.close()


class TestSameAccountReview(unittest.TestCase):
    def test_flows_flags_same_account(self):
        st = Store(Path(tempfile.mkdtemp()) / ".agent-system" / "state.db")
        try:
            t = st.add_task("human:o", "R", kind="research")
            st.claim(t["id"], "cursor:vedansh:impl")
            st.transition(t["id"], "submit", "cursor:vedansh:impl", owner_only=True, lease_expires=None)
            st.transition(t["id"], "verify_pass", "system:v")
            st.transition(t["id"], "approve", "cursor:vedansh:reviewer")
            events = st.events()
            flows = ui.flows([t], events)
            chain = flows[t["id"]]
            reviewers = [s for s in chain if s.get("same_account_review")]
            self.assertTrue(reviewers)
        finally:
            st.close()


if __name__ == "__main__":
    unittest.main()
