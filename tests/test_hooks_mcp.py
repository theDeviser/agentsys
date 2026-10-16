"""Git hooks, check-branch, and MCP stdio server."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from agentsys import hooks, mcp  # noqa: E402
from tests.helpers import IsolatedEnv  # noqa: E402

CLI = [sys.executable, str(REPO / "bin" / "agentsys")]


def rpc(server: mcp.McpServer, method: str, params=None, req_id=1):
    msg = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}}
    return server.handle(msg)


class TestCheckBranch(unittest.TestCase):
    def test_blocks_then_allows_accepted(self):
        with IsolatedEnv() as iso:
            iso.env["AGENTSYS_CLI"] = " ".join(CLI)
            iso.cli("init")
            tid = iso.cli("task", "add", "H", "--path", "app/*", "--kind", "implement", actor="human:v").stdout.strip()
            branch = f"agent/{tid}"
            iso.cli("claim", tid, actor="cursor:v:w")
            p = iso.cli("check-branch", branch, actor="system:ci", ok=False)
            self.assertEqual(p.returncode, 1)
            from agentsys.store import Store
            st = Store(iso.store_path())
            t = st.get(tid)
            wt = Path(t["worktree"])
            (wt / "app" / "ui.jsx").write_text("export const A = () => <div>x</div>;\n")
            st.close()
            iso.cli("submit", tid, "done", actor="cursor:v:w")
            iso.cli("verify", tid, actor="system:v")
            iso.cli("review", tid, "approve", "--reason", "ok", actor="claude:h:r")
            iso.cli("check-branch", branch, actor="system:ci")
            iso.cli("check-branch", branch, "--override-reason", "nope", actor="cursor:v:w", ok=False)

    def test_override_recorded(self):
        with IsolatedEnv() as iso:
            iso.cli("init")
            tid = iso.cli("task", "add", "O", "--kind", "research", actor="human:v").stdout.strip()
            branch = f"agent/{tid}"
            iso.cli("claim", tid, actor="a")
            iso.cli("check-branch", branch, "--override-reason", "emergency", actor="human:v")
            st = __import__("agentsys.store", fromlist=["Store"]).Store(iso.store_path())
            kinds = [e["kind"] for e in st.events(tid)]
            self.assertIn("hook.override", kinds)
            st.close()


class TestHooksInstall(unittest.TestCase):
    def test_install_idempotent(self):
        with IsolatedEnv() as iso:
            iso.env["AGENTSYS_CLI"] = " ".join(CLI)
            iso.cli("init")
            iso.cli("hooks", "install", actor="human:v")
            iso.cli("hooks", "install", actor="human:v")
            hook = Path(iso.root / ".git" / "hooks" / "pre-push")
            self.assertTrue(hook.exists())
            self.assertIn("agentsys-managed", hook.read_text())


class TestMcp(unittest.TestCase):
    def test_full_flow_and_no_approve(self):
        with IsolatedEnv() as iso:
            iso.cli("init")
            tid = iso.cli("task", "add", "M", "--kind", "research", actor="human:v").stdout.strip()
            db = str(iso.store_path())
            srv = mcp.McpServer("agent:cursor:worker", db)
            self.assertEqual(rpc(srv, "initialize")["result"]["protocolVersion"], mcp.PROTOCOL)
            tools = rpc(srv, "tools/list")["result"]["tools"]
            names = {t["name"] for t in tools}
            self.assertIn("claim", names)
            self.assertNotIn("approve", names)
            r = rpc(srv, "tools/call", {"name": "claim", "arguments": {"task_id": tid}})
            self.assertIn("claimed", r["result"]["content"][0]["text"])
            rpc(srv, "tools/call", {"name": "finding", "arguments": {"task_id": tid, "body": "note"}})
            rpc(srv, "tools/call", {"name": "checkpoint", "arguments": {"task_id": tid, "summary": "cp"}})
            rpc(srv, "tools/call", {"name": "submit", "arguments": {"task_id": tid, "summary": "done"}})
            st = __import__("agentsys.store", fromlist=["Store"]).Store(db)
            self.assertEqual(st.get(tid)["state"], "submitted")
            st.close()

    def test_malformed_json_does_not_crash(self):
        srv = mcp.McpServer("agent:cursor:worker", str(REPO / "nonexistent.db"))
        out = srv.handle({"jsonrpc": "1.0", "id": 1, "method": "initialize"})
        self.assertEqual(out["error"]["code"], -32600)

    def test_stdio_scripted(self):
        with IsolatedEnv() as iso:
            iso.cli("init")
            tid = iso.cli("task", "add", "S", "--kind", "research", actor="human:v").stdout.strip()
            env = dict(iso.env, AGENTSYS_ACTOR="agent:cursor:worker", AGENTSYS_DB=str(iso.store_path()))
            proc = subprocess.run(
                CLI + ["mcp"],
                input=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                  "params": {"name": "list_tasks", "arguments": {}}}) + "\n",
                capture_output=True,
                text=True,
                env=env,
                cwd=str(iso.root),
            )
            self.assertEqual(proc.returncode, 0)
            line = json.loads(proc.stdout.strip().splitlines()[-1])
            self.assertIn(tid, line["result"]["content"][0]["text"])


if __name__ == "__main__":
    unittest.main()
