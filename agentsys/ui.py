"""Read-only live dashboard over one or more agentsys stores (stdlib HTTP server, polling)."""
from __future__ import annotations

import json
import re
import sqlite3
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import budget
from .adapters import ADAPTERS
from .store import Store

HERE = Path(__file__).parent
PAGE = HERE / "ui.html"
ICONS = HERE / "static" / "icons"

HARNESS_PROVIDER = {"claude": "anthropic", "codex": "openai", "cursor": "cursor", "mock": "mock",
                     "human": "human", "system": "system", "grok": "xai", "gemini": "google"}

# Event kinds that move a task between agents, phrased for people.
STEP_LABEL = {"task.created": "created", "task.claim": "claimed", "dispatch.start": "ran", "task.submit": "submitted",
              "task.verify_pass": "verified", "task.verify_fail": "failed checks", "task.approve": "approved",
              "task.reject": "requested changes", "task.merge": "merged", "task.release": "released",
              "task.requeue": "requeued", "task.escalate": "escalated", "task.block": "blocked",
              "task.cancel": "cancelled", "approval.granted": "approved merge", "approval.denied": "denied merge",
              "dispatch.refused": "refused (budget)"}


def agent_key(actor: str) -> str:
    parts = (actor or "?").split(":")
    return ":".join(parts[:2])


def provider_of(actor: str) -> str:
    return HARNESS_PROVIDER.get((actor or "").split(":")[0], "other")


def live_runs(st: Store, events):
    last_end = {}
    for r in st.runs():
        last_end[r["task_id"]] = max(last_end.get(r["task_id"], 0), r["ts_end"] or r["ts_start"])
    out = []
    for e in events:
        if e["kind"] == "dispatch.start" and e["ts"] > last_end.get(e["task_id"], 0):
            p = e.get("payload") or {}
            out.append({"task_id": e["task_id"], "actor": e["actor"], "agent": agent_key(e["actor"]),
                        "provider": provider_of(e["actor"]), "adapter": p.get("adapter"), "estimate": p.get("estimate"),
                        "since": e["ts"]})
    return out


def flows(tasks, events):
    """Per task: the ordered chain of agents that touched it, consecutive repeats collapsed."""
    by_task = {}
    for e in events:
        if not e["task_id"] or e["kind"] not in STEP_LABEL:
            continue
        chain = by_task.setdefault(e["task_id"], [])
        step = {"agent": agent_key(e["actor"]), "actor": e["actor"], "provider": provider_of(e["actor"]),
                "did": STEP_LABEL[e["kind"]], "ts": e["ts"]}
        if chain and chain[-1]["agent"] == step["agent"]:
            if step["did"] not in chain[-1]["steps"]:
                chain[-1]["steps"].append(step["did"])
            chain[-1]["ts_end"] = e["ts"]
        else:
            chain.append({**step, "steps": [step["did"]], "ts_end": e["ts"]})
    return {t["id"]: by_task.get(t["id"], []) for t in tasks}


def agents(st: Store, events, live):
    out = {}
    for e in events:
        k = agent_key(e["actor"])
        a = out.setdefault(k, {"agent": k, "provider": provider_of(e["actor"]), "roles": set(), "tasks": set(),
                               "events": 0, "last_ts": 0, "last_kind": None, "first_ts": e["ts"]})
        role = e["actor"].split(":")[2] if e["actor"].count(":") >= 2 else None
        if role:
            a["roles"].add(role)
        if e["task_id"]:
            a["tasks"].add(e["task_id"])
        a["events"] += 1
        if e["ts"] >= a["last_ts"]:
            a["last_ts"], a["last_kind"], a["last_task"] = e["ts"], e["kind"], e["task_id"]
    for r in st.runs():
        k = f"{r['adapter']}:{r['account']}"
        if k in out:
            a = out[k]
            a["tokens"] = a.get("tokens", 0) + budget.run_total(r)
            a["runs"] = a.get("runs", 0) + 1
            a["models"] = sorted(set(a.get("models", [])) | ({r["model"]} if r["model"] else set()))
    for lr in live:
        if lr["agent"] in out:
            out[lr["agent"]]["live"] = lr
    owned = {}
    for t in st.list():
        if t["state"] == "in_progress" and t["owner"]:
            owned.setdefault(agent_key(t["owner"]), []).append(t["id"])
    res = []
    for a in out.values():
        a["roles"], a["tasks"] = sorted(a["roles"]), sorted(a["tasks"])
        a["holding"] = owned.get(a["agent"], [])
        res.append(a)
    return sorted(res, key=lambda a: -a["last_ts"])


def snapshot(st: Store) -> dict:
    tasks = st.list()
    counts = {}
    for f in st.db.execute("SELECT task_id, kind, COUNT(*) n FROM findings GROUP BY task_id, kind"):
        counts.setdefault(f["task_id"], {})[f["kind"]] = f["n"]
    for t in tasks:
        t["finding_counts"] = counts.get(t["id"], {})
    events = st.events(limit=100000)
    events.sort(key=lambda e: e["ts"])
    live = live_runs(st, events)
    accounts = {(b["provider"], b["account"]) for b in st.budgets()}
    accounts |= {(r["provider"], r["account"]) for r in st.runs() if r["provider"] not in ("mock",)}
    runs = st.runs()
    for r in runs:
        r["total"] = budget.run_total(r)
    return {
        "root": str(st.path.parent.parent),
        "now": time.time(),
        "tasks": tasks,
        "events": events[::-1][:120],
        "runs": runs[::-1],
        "live": live,
        "agents": agents(st, events, live),
        "flows": flows(tasks, events),
        "budgets": [budget_row(st, p, a) for p, a in sorted(accounts)],
        "approvals": st.approvals(),
    }


def budget_row(st: Store, provider, account):
    s = budget.summary(st, provider, account)
    ad = next((x for x in ADAPTERS.values() if x.provider == provider), None)
    if ad:
        s["adapter"] = ad.name
        s["next_estimate"] = budget.estimate(st, ad, account)
        try:
            budget.check_dispatch(st, ad, account, est=s["next_estimate"])
            s["dispatch"] = "allowed"
        except budget.BudgetError as e:
            s["dispatch"], s["refusal"] = "refused", str(e)
    return s


def task_detail(st: Store, tid: str) -> dict:
    t = st.get(tid)
    events = st.events(tid)
    return {"task": t, "findings": st.findings(tid), "checkpoints": st.checkpoints(tid),
            "events": events[::-1], "runs": [dict(r, total=budget.run_total(r)) for r in st.runs() if r["task_id"] == tid],
            "approvals": [a for a in st.approvals() if a.get("task_id") == tid]}


def icon_bundle() -> str:
    out = {}
    if ICONS.is_dir():
        for p in sorted(ICONS.glob("*.svg")):
            if re.fullmatch(r"[a-z0-9-]+\.svg", p.name):
                svg = p.read_text(encoding="utf-8")
                svg = re.sub(r'\s(height|width|style)="[^"]*"', "", svg, count=3)
                out[p.stem] = svg
    return json.dumps(out)


def serve(db_paths, host="127.0.0.1", port=8791):
    db_paths = [Path(p) for p in (db_paths if isinstance(db_paths, (list, tuple)) else [db_paths])]
    projects = [{"id": i, "name": p.parent.parent.name, "root": str(p.parent.parent)} for i, p in enumerate(db_paths)]
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    harnesses = [{k: d[k] for k in ("adapter", "provider", "available")} for d in (a.detect() for a in ADAPTERS.values())]
    icons = icon_bundle()
    page = lambda: PAGE.read_text(encoding="utf-8").replace("/*__ICONS__*/{}", icons)

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype):
            data = body.encode() if isinstance(body, str) else body
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            if ctype.startswith("text/html"):
                self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; "
                                 "script-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; "
                                 "frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.headers.get("Host") not in allowed_hosts:  # blocks DNS-rebinding
                return self._send(403, "forbidden host", "text/plain")
            url = urlparse(self.path)
            q = parse_qs(url.query)
            try:
                if url.path == "/":
                    return self._send(200, page(), "text/html; charset=utf-8")
                if url.path == "/api/projects":
                    return self._send(200, json.dumps(projects), "application/json")
                idx = int((q.get("p") or ["0"])[0])
                if not 0 <= idx < len(db_paths):
                    return self._send(404, json.dumps({"error": "unknown project"}), "application/json")
                st = Store(db_paths[idx])
                try:
                    if url.path == "/api/state":
                        out = snapshot(st)
                        out["project"], out["harnesses"] = projects[idx], harnesses
                    elif url.path == "/api/task":
                        out = task_detail(st, (q.get("id") or [""])[0])
                    else:
                        return self._send(404, "not found", "text/plain")
                finally:
                    st.close()
                return self._send(200, json.dumps(out, default=str), "application/json")
            except (KeyError, ValueError, sqlite3.Error) as e:
                return self._send(404, json.dumps({"error": str(e)}), "application/json")

    srv = ThreadingHTTPServer((host, port), H)
    names = ", ".join(p["name"] for p in projects)
    print(f"agentsys dashboard: http://{host}:{port}  ({names}; read-only; Ctrl-C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
