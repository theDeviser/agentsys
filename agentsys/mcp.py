"""Minimal MCP-style JSON-RPC 2.0 server over stdio (stdlib only)."""
from __future__ import annotations

import json
import sys
import traceback
from typing import Any, Callable

from . import gitops
from .store import Store, TransitionError

PROTOCOL = "2024-11-05"

TOOLS = (
    "claim", "heartbeat", "finding", "checkpoint", "submit", "resume", "status", "list_tasks",
)


class McpServer:
    def __init__(self, actor: str, db_path: str):
        self.actor = actor
        self.db_path = db_path
        self._methods: dict[str, Callable] = {
            "initialize": self._initialize,
            "tools/list": self._tools_list,
            "tools/call": self._tools_call,
        }

    def _store(self) -> Store:
        return Store(self.db_path)

    def _initialize(self, params: dict) -> dict:
        return {
            "protocolVersion": PROTOCOL,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "agentsys", "version": "0.1"},
        }

    def _tools_list(self, params: dict) -> dict:
        tools = []
        for name in TOOLS:
            tools.append({
                "name": name,
                "description": f"agentsys {name}",
                "inputSchema": {"type": "object", "properties": {"task_id": {"type": "string"}}, "additionalProperties": True},
            })
        return {"tools": tools}

    def _tools_call(self, params: dict) -> dict:
        name = params.get("name")
        args = params.get("arguments") or {}
        if name not in TOOLS:
            raise ValueError(f"unknown tool {name}")
        if name in ("approve", "merge", "review"):
            raise ValueError("tool not exposed")
        try:
            text = self._run_tool(name, args)
            return {"content": [{"type": "text", "text": text}], "isError": False}
        except (TransitionError, KeyError, ValueError, gitops.GitError) as e:
            return {"content": [{"type": "text", "text": str(e)}], "isError": True}

    def _run_tool(self, name: str, args: dict) -> str:
        st = self._store()
        try:
            if name == "list_tasks":
                tasks = st.list(state=args.get("state"))
                return json.dumps(tasks, indent=2, default=str)
            if name == "status":
                tasks = st.list()
                return json.dumps({"tasks": len(tasks), "states": {s: sum(1 for t in tasks if t["state"] == s) for s in set(t["state"] for t in tasks)}},
                                  indent=2)
            tid = args.get("task_id") or args.get("id")
            if not tid:
                raise ValueError("task_id required")
            if name == "claim":
                t = st.claim(tid, self.actor)
                if t["kind"] == "implement":
                    root = gitops.project_root(st.path.parent.parent)
                    path, branch = gitops.ensure_worktree(root, t["id"], t["base"])
                    st.set_fields(t["id"], self.actor, "task.worktree", worktree=str(path), branch=branch)
                    return f"claimed {tid}; worktree {path}"
                return f"claimed {tid}"
            if name == "heartbeat":
                t = st.heartbeat(tid, self.actor)
                return f"lease until {t['lease_expires']}"
            if name == "finding":
                fid = st.add_finding(tid, self.actor, args.get("body", ""), kind=args.get("kind", "finding"),
                                     evidence=args.get("evidence"))
                return f"finding {fid}"
            if name == "checkpoint":
                t = st.get(tid)
                sha = None
                if t["worktree"]:
                    from pathlib import Path
                    if args.get("commit"):
                        gitops.commit_all(t["worktree"], f"[{tid}] {args.get('summary','')}", self.actor)
                    if Path(t["worktree"]).exists():
                        sha = gitops.head_sha(t["worktree"])
                cid = st.add_checkpoint(tid, self.actor, args.get("summary", ""), sha)
                return f"checkpoint {cid}" + (f" @ {sha[:10]}" if sha else "")
            if name == "submit":
                t = st.get(tid)
                if t["owner"] != self.actor:
                    raise TransitionError(f"only owner {t['owner']} can submit")
                summary = args.get("summary", "submit via mcp")
                if t["worktree"]:
                    gitops.commit_all(t["worktree"], f"[{tid}] {summary}", self.actor)
                st.transition(tid, "submit", self.actor, {"summary": summary}, owner_only=True, lease_expires=None)
                return f"{tid} submitted"
            if name == "resume":
                from .cli import brief
                return brief(st, tid)
            raise ValueError(f"unhandled tool {name}")
        finally:
            st.close()

    def handle(self, msg: dict) -> dict | None:
        if msg.get("jsonrpc") != "2.0":
            return self._err(msg.get("id"), -32600, "invalid jsonrpc")
        mid = msg.get("id")
        method = msg.get("method")
        if method == "notifications/initialized":
            return None
        if method not in self._methods:
            return self._err(mid, -32601, f"method not found: {method}")
        try:
            result = self._methods[method](msg.get("params") or {})
            if mid is None:
                return None
            return {"jsonrpc": "2.0", "id": mid, "result": result}
        except Exception as e:
            return self._err(mid, -32603, str(e), data=traceback.format_exc())

    @staticmethod
    def _err(mid, code: int, message: str, data: str | None = None) -> dict:
        err: dict[str, Any] = {"code": code, "message": message}
        if data:
            err["data"] = data
        return {"jsonrpc": "2.0", "id": mid, "error": err}

    def serve_stdio(self):
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                out = self._err(None, -32700, "parse error")
                if out:
                    sys.stdout.write(json.dumps(out) + "\n")
                    sys.stdout.flush()
                continue
            if not isinstance(msg, dict):
                out = self._err(None, -32600, "invalid request")
            else:
                out = self.handle(msg)
            if out is not None:
                sys.stdout.write(json.dumps(out) + "\n")
                sys.stdout.flush()


def run_server(actor: str, db_path: str):
    McpServer(actor, db_path).serve_stdio()
