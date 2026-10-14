import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from agentsys import budget  # noqa: E402
from agentsys.adapters import ADAPTERS  # noqa: E402
from agentsys.store import Store, TransitionError, paths_overlap, path_allowed  # noqa: E402

CLI = [sys.executable, str(REPO / "bin" / "agentsys")]


def sh(args, cwd):
    return subprocess.run(args, cwd=str(cwd), capture_output=True, text=True)


class GitRepo(unittest.TestCase):
    """A throwaway git repo with one committed file, plus helpers to drive the CLI."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="agentsys-test-"))
        self.root = self.tmp / "proj"
        self.root.mkdir()
        for c in (["init", "-q", "-b", "main"], ["config", "user.email", "t@example.com"],
                  ["config", "user.name", "Test"]):
            sh(["git", *c], self.root)
        (self.root / "app").mkdir()
        (self.root / "app" / "ui.jsx").write_text("export const A = () => <div>hi</div>;\n")
        (self.root / "docs").mkdir()
        (self.root / "docs" / "notes.md").write_text("notes\n")
        (self.root / ".gitignore").write_text(".agent-system/\n")
        sh(["git", "add", "-A"], self.root)
        sh(["git", "commit", "-q", "-m", "init"], self.root)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("AGENTSYS_")}

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def cli(self, *args, actor=None, ok=True, env=None, cwd=None):
        e = dict(self.env, **(env or {}))
        if actor:
            e["AGENTSYS_ACTOR"] = actor
        p = subprocess.run(CLI + list(args), cwd=str(cwd or self.root), capture_output=True, text=True, env=e)
        if ok and p.returncode != 0:
            self.fail(f"agentsys {' '.join(args)} failed ({p.returncode}): {p.stderr}{p.stdout}")
        return p

    def store(self, lease=1800):
        return Store(self.root / ".agent-system" / "state.db", lease_seconds=lease)


class TestStore(GitRepo):
    def test_state_machine_and_illegal_transitions(self):
        st = self.store()
        t = st.add_task("human:v", "Research X", kind="research")
        self.assertEqual(t["state"], "ready")
        with self.assertRaises(TransitionError):
            st.transition(t["id"], "submit", "a")
        st.claim(t["id"], "cursor:v:researcher")
        with self.assertRaises(TransitionError):
            st.transition(t["id"], "submit", "someone-else", owner_only=True)
        st.transition(t["id"], "submit", "cursor:v:researcher", owner_only=True)
        with self.assertRaises(TransitionError):
            st.transition(t["id"], "approve", "codex:v:reviewer")  # must be verified first
        kinds = [e["kind"] for e in st.events(t["id"])]
        self.assertEqual(kinds, ["task.created", "task.claim", "task.submit"])

    def test_implement_requires_scope(self):
        with self.assertRaises(ValueError):
            self.store().add_task("human:v", "No scope", kind="implement")

    def test_dependencies_gate_claim(self):
        st = self.store()
        a = st.add_task("human:v", "A", kind="research")
        b = st.add_task("human:v", "B", kind="research", deps=[a["id"]])
        with self.assertRaises(TransitionError):
            st.claim(b["id"], "x")

    def test_lease_expiry_requeues_then_escalates(self):
        st = self.store(lease=0.2)
        t = st.add_task("human:v", "Flaky", kind="research", max_attempts=2)
        st.claim(t["id"], "agent-1")
        time.sleep(0.3)
        self.assertEqual(st.reap(), [(t["id"], "ready")])
        st.claim(t["id"], "agent-2")
        time.sleep(0.3)
        self.assertEqual(st.reap(), [(t["id"], "escalated")])
        self.assertEqual(st.get(t["id"])["attempts"], 2)

    def test_heartbeat_keeps_lease(self):
        st = self.store(lease=0.4)
        t = st.add_task("human:v", "Long", kind="research")
        st.claim(t["id"], "a")
        time.sleep(0.25)
        st.heartbeat(t["id"], "a")
        time.sleep(0.25)
        self.assertEqual(st.reap(), [])

    def test_state_survives_reopen(self):
        st = self.store()
        t = st.add_task("human:v", "Persist", kind="research")
        st.claim(t["id"], "a")
        st.add_finding(t["id"], "a", "found it", evidence=["x.py:1"])
        st.close()
        st2 = self.store()
        self.assertEqual(st2.get(t["id"])["state"], "in_progress")
        self.assertEqual(st2.findings(t["id"])[0]["body"], "found it")

    def test_path_overlap(self):
        self.assertTrue(paths_overlap(["app/*"], ["app/ui.jsx"]))
        self.assertTrue(paths_overlap(["app/"], ["app/sub/x.js"]))
        self.assertFalse(paths_overlap(["app/*"], ["docs/*"]))
        self.assertTrue(path_allowed("app/ui.jsx", ["app/*"]))
        self.assertTrue(path_allowed("app/a/b.jsx", ["app/"]))
        self.assertFalse(path_allowed("docs/x.md", ["app/*"]))

    def test_approval_needs_human(self):
        st = self.store()
        aid = st.request_approval(None, "merge", "cursor:v:x")
        with self.assertRaises(TransitionError):
            st.decide_approval(aid, "cursor:v:x", True)
        st.decide_approval(aid, "human:v", True)
        self.assertTrue(st.approval_granted(None, "merge"))


class TestBudget(GitRepo):
    def test_refuses_without_budget_and_over_limit(self):
        st = self.store()
        claude = ADAPTERS["claude"]
        with self.assertRaises(budget.BudgetError):
            budget.check_dispatch(st, claude, "acct")
        st.set_budget("anthropic", "acct", 100_000, "human:v", reserve_pct=20)
        budget.check_dispatch(st, claude, "acct", est=70_000)
        with self.assertRaises(budget.BudgetError):
            budget.check_dispatch(st, claude, "acct", est=90_000)  # eats into the 20% reserve
        budget.check_dispatch(st, claude, "acct", role="review", est=90_000)  # reviews may use it

    def test_unreported_usage_counts_at_estimate_and_accounts_are_separate(self):
        st = self.store()
        st.record_run(ts_start=0, adapter="codex", provider="openai", account="a", usage_source="unknown",
                      tokens_estimate=5000)
        st.record_run(ts_start=0, adapter="codex", provider="openai", account="b", usage_source="provider-reported",
                      tokens_in=100, tokens_out=50, tokens_cached=10)
        self.assertEqual(budget.used_tokens(st, "openai", "a"), 5000)
        self.assertEqual(budget.used_tokens(st, "openai", "b"), 160)


class TestAdapterParsing(unittest.TestCase):
    def test_codex_error_and_noise(self):
        from agentsys.adapters import _error_message, _quiet
        raw = json.dumps({"type": "error", "status": 400, "error": {"message": "model not supported"}})
        self.assertEqual(_error_message(raw), "model not supported")
        self.assertEqual(_error_message("plain"), "plain")
        self.assertEqual(_quiet("x ERROR rmcp::transport::worker: noise\nreal problem"), "real problem")


class TestEndToEnd(GitRepo):
    def test_two_roles_collaborate_through_shared_state(self):
        self.cli("init", actor="human:v")
        tid = self.cli("task", "add", "Add a greeting", "--path", "app/*", "--goal", "greet users",
                       actor="human:v").stdout.strip()
        r = self.cli("task", "add", "Find where greetings belong", "--kind", "research", actor="human:v")
        rid = r.stdout.strip()

        # Role A researches and hands off a finding.
        self.cli("claim", rid, actor="cursor:v:researcher")
        self.cli("finding", rid, "Greeting belongs in app/ui.jsx", "--evidence", "app/ui.jsx:1",
                 actor="cursor:v:researcher")
        self.cli("finding", tid, "See research: put it in app/ui.jsx", "--evidence", "app/ui.jsx:1",
                 actor="cursor:v:researcher")
        self.cli("submit", rid, "located", actor="cursor:v:researcher")
        self.cli("verify", rid, actor="system:verifier")

        # Role B implements, reading A's finding through the resume brief.
        out = self.cli("claim", tid, actor="codex:v:implementer").stdout
        wt = Path(out.split("work in: ")[1].strip())
        brief = self.cli("resume", tid, actor="codex:v:implementer").stdout
        self.assertIn("Greeting belongs in app/ui.jsx", self.cli("resume", rid).stdout)
        self.assertIn("put it in app/ui.jsx", brief)
        (wt / "app" / "ui.jsx").write_text("export const A = () => <div>hello</div>;\n")
        self.cli("submit", tid, "greeting added", actor="codex:v:implementer")
        v = self.cli("verify", tid, actor="system:verifier")
        self.assertIn("[   pass] scope", v.stdout)
        self.assertIn("verified", v.stdout)

        # Authors cannot review their own work; an independent reviewer can.
        self.assertNotEqual(self.cli("review", tid, "approve", "--reason", "lgtm", actor="codex:v:implementer",
                                     ok=False).returncode, 0)
        self.cli("review", tid, "approve", "--reason", "diff matches goal", actor="claude:h:reviewer")

        # Merge needs a human approval and leaves an audit trail.
        p = self.cli("merge", tid, actor="claude:h:reviewer", ok=False)
        self.assertEqual(p.returncode, 4)
        self.cli("approve", "1", actor="human:v")
        self.cli("merge", tid, "--cleanup", actor="human:v")
        self.assertIn("hello", (self.root / "app" / "ui.jsx").read_text())
        log = self.cli("log", tid).stdout
        for kind in ("task.claim", "checkpoint", "task.submit", "verify.results", "task.approve",
                     "approval.granted", "task.merge"):
            self.assertIn(kind, log)

    def test_verify_catches_scope_syntax_and_secrets(self):
        if not shutil.which("bun"):
            self.skipTest("bun not installed")
        tid = self.cli("task", "add", "Edit ui", "--path", "app/*", actor="human:v").stdout.strip()
        wt = Path(self.cli("claim", tid, actor="a").stdout.split("work in: ")[1].strip())
        (wt / "app" / "ui.jsx").write_text("export const A = () => <div>;\n")
        (wt / "app" / "cfg.js").write_text('const api_key = "abcd1234efgh5678";\n')
        (wt / "docs" / "notes.md").write_text("changed\n")
        self.cli("submit", tid, "bad change", actor="a")
        v = self.cli("verify", tid, actor="system:verifier", ok=False)
        self.assertEqual(v.returncode, 2)
        self.assertIn("[   fail] scope", v.stdout)
        self.assertIn("[   fail] syntax", v.stdout)
        self.assertIn("[   fail] secrets", v.stdout)
        self.assertNotIn("abcd1234efgh5678", v.stdout)
        self.assertIn("changes_requested", v.stdout)

    def test_overlapping_scopes_refused_and_conflicts_detected(self):
        t1 = self.cli("task", "add", "One", "--path", "app/*", actor="human:v").stdout.strip()
        t2 = self.cli("task", "add", "Two", "--path", "app/ui.jsx", actor="human:v").stdout.strip()
        t3 = self.cli("task", "add", "Three", "--path", "docs/*", actor="human:v").stdout.strip()
        self.cli("claim", t1, actor="a")
        p = self.cli("claim", t2, actor="b", ok=False)
        self.assertIn("overlaps", p.stderr)
        self.cli("claim", t3, actor="c")  # disjoint scope runs concurrently

        wt1 = Path(self.store().get(t1)["worktree"])
        (wt1 / "app" / "ui.jsx").write_text("export const A = () => <div>one</div>;\n")
        self.cli("submit", t1, "one", actor="a")
        # Main branch moves on underneath the task: a real conflict.
        (self.root / "app" / "ui.jsx").write_text("export const A = () => <div>main</div>;\n")
        sh(["git", "commit", "-qam", "main edit"], self.root)
        p = self.cli("merge-check", t1, actor="system", ok=False)
        self.assertEqual(p.returncode, 3)
        self.assertIn("app/ui.jsx", p.stdout)
        wt3 = Path(self.store().get(t3)["worktree"])
        (wt3 / "docs" / "notes.md").write_text("three\n")
        self.cli("submit", t3, "three", actor="c")
        self.assertIn("merges cleanly", self.cli("merge-check", t3, actor="system").stdout)

    def test_mock_dispatch_and_crash_recovery(self):
        tid = self.cli("task", "add", "Mock work", "--path", "docs/", actor="human:v").stdout.strip()
        p = self.cli("dispatch", tid, "--adapter", "mock", "--lease", "1", env={"AGENTSYS_MOCK_MODE": "crash"},
                     ok=False)
        self.assertEqual(p.returncode, 137)  # agent died mid-task, after a partial write
        self.assertEqual(self.store().get(tid)["state"], "in_progress")
        time.sleep(1.2)
        # A fresh agent sees the lease expired, gets the task, and is told about the partial work.
        brief = self.cli("resume", tid).stdout
        self.assertIn("state: ready", brief)
        self.assertIn("UNCOMMITTED changes", brief)
        out = self.cli("dispatch", tid, "--adapter", "mock").stdout
        self.assertIn("[mock]", out)
        self.assertIn("submitted", out)
        self.assertIn("verified", self.cli("verify", tid, actor="system:verifier").stdout)
        t = self.store().get(tid)
        self.assertEqual(t["attempts"], 2)
        runs = self.store().runs()
        self.assertEqual([r["usage_source"] for r in runs], ["mock"])

    def test_mock_out_of_scope_fails_verify(self):
        tid = self.cli("task", "add", "Mock", "--path", "docs/", actor="human:v").stdout.strip()
        self.cli("dispatch", tid, "--adapter", "mock", env={"AGENTSYS_MOCK_MODE": "out_of_scope"})
        self.assertEqual(self.cli("verify", tid, actor="system:verifier", ok=False).returncode, 2)

    def test_real_adapter_refused_without_budget(self):
        tid = self.cli("task", "add", "Q", "--kind", "research", actor="human:v").stdout.strip()
        if not ADAPTERS["codex"].binary():
            self.skipTest("codex not installed")
        p = self.cli("dispatch", tid, "--adapter", "codex", "--account", "x", ok=False)
        self.assertIn("no budget set", p.stderr)
        self.assertEqual(self.store().get(tid)["state"], "ready")
        self.assertEqual(self.store().runs(), [])

    def test_dependency_findings_flow_into_brief(self):
        a = self.cli("task", "add", "Upstream", "--kind", "research", actor="human:v").stdout.strip()
        b = self.cli("task", "add", "Downstream", "--kind", "research", "--dep", a, actor="human:v").stdout.strip()
        self.cli("claim", a, actor="claude:h:researcher")
        self.cli("finding", a, "Entry is app/ui.jsx", "--evidence", "app/ui.jsx:1", actor="claude:h:researcher")
        self.cli("submit", a, "done", actor="claude:h:researcher")
        self.cli("verify", a, actor="system:verifier")
        self.cli("review", a, "approve", "--reason", "checked", actor="human:v")
        self.cli("claim", b, actor="codex:v:checker")
        brief = self.cli("resume", b).stdout
        self.assertIn(f"Handoff from dependency {a}", brief)
        self.assertIn("Entry is app/ui.jsx", brief)

    def test_dashboard_snapshot_and_host_check(self):
        import threading
        import urllib.error
        import urllib.request
        from http.client import HTTPConnection
        from agentsys import ui
        tid = self.cli("task", "add", "Dash", "--kind", "research", actor="human:v").stdout.strip()
        st = self.store()
        snap = ui.snapshot(st)
        self.assertEqual(snap["tasks"][0]["id"], tid)
        self.assertEqual(ui.task_detail(st, tid)["task"]["title"], "Dash")
        port = 18791
        t = threading.Thread(target=ui.serve, args=(st.path,), kwargs={"port": port}, daemon=True)
        t.start()
        time.sleep(0.4)
        body = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/state").read())
        self.assertEqual(body["tasks"][0]["id"], tid)
        c = HTTPConnection("127.0.0.1", port)
        c.request("GET", "/api/state", headers={"Host": "evil.example"})
        self.assertEqual(c.getresponse().status, 403)

    def test_works_from_inside_a_worktree(self):
        tid = self.cli("task", "add", "W", "--path", "docs/", actor="human:v").stdout.strip()
        wt = Path(self.cli("claim", tid, actor="a").stdout.split("work in: ")[1].strip())
        out = self.cli("task", "list", "--json", cwd=wt).stdout
        self.assertEqual(json.loads(out)[0]["id"], tid)


if __name__ == "__main__":
    unittest.main()
