"""Live dashboard over one or more agentsys stores (stdlib HTTP server, polling).

Reads are open to the local page. Writes (budgets, approvals, requeue/unblock/cancel) need the per-session token
embedded in the page, a matching Host and Origin, and JSON; they're recorded as the human running the server.
"""
from __future__ import annotations

import hmac
import json
import os
import re
import secrets
import sqlite3
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import budget
from .adapters import ADAPTERS
from .store import Store, TransitionError
from .trust import HumanActionRefused, assert_human_actor, collect_provenance

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
    if parts[0] == "agent" and len(parts) >= 3:
        return f"agent:{parts[1]}"
    return ":".join(parts[:2])


def provider_of(actor: str) -> str:
    parts = (actor or "").split(":")
    if parts[0] == "agent" and len(parts) >= 2:
        return HARNESS_PROVIDER.get(parts[1], "other")
    return HARNESS_PROVIDER.get(parts[0], "other")


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


def _account(actor: str) -> str:
    p = (actor or "").split(":")
    if p[0] == "agent" and len(p) >= 3:
        return p[2]
    return p[1] if len(p) >= 2 else ""


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
    for tid, chain in by_task.items():
        workers = {_account(s["actor"]) for s in chain
                     if any(x in s["steps"] for x in ("claimed", "ran", "submitted"))}
        for s in chain:
            if any(x in s["steps"] for x in ("approved", "requested changes")) and _account(s["actor"]) in workers:
                s["same_account_review"] = True
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


NAME = re.compile(r"[A-Za-z0-9._@+-]{1,64}")
TASK_ID = re.compile(r"t-[0-9a-f]{8}")


class BadRequest(Exception):
    pass


def _int(v, lo, hi, field, optional=True):
    if v in (None, ""):
        if optional:
            return None
        raise BadRequest(f"{field} is required")
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != int(v) or not lo <= v <= hi:
        raise BadRequest(f"{field} must be a whole number from {lo:,} to {hi:,}")
    return int(v)


def apply_action(st: Store, actor: str, body: dict) -> str:
    """Perform one human action from the dashboard. Returns a sentence describing what happened."""
    kind = body.get("action")
    human_kinds = ("approval.grant", "approval.deny", "task.requeue", "task.unblock", "task.cancel")
    if kind in human_kinds:
        try:
            prov = assert_human_actor(actor, kind, dashboard_ok=True)
        except HumanActionRefused as e:
            raise BadRequest(str(e)) from e
        os.environ["AGENTSYS_DASHBOARD_OK"] = "1"
    else:
        prov = {}
    if kind == "budget.set":
        provider, account = str(body.get("provider", "")), str(body.get("account", ""))
        if not (NAME.fullmatch(provider) and NAME.fullmatch(account)):
            raise BadRequest("provider and account may use letters, digits and . _ @ + - (max 64)")
        limit = _int(body.get("limit"), 0, 10**12, "Total cap") or 0
        per_run = _int(body.get("per_run"), 1, 10**12, "Per-run cap")
        reserve = _int(body.get("reserve_pct", 20), 0, 90, "Review reserve", optional=False)
        wh = body.get("window_hours")
        if wh in ("", None, 0):
            wh = None
        elif isinstance(wh, bool) or not isinstance(wh, (int, float)) or not 0 < wh <= 24 * 90:
            raise BadRequest("Window must be between 0 and 2,160 hours (blank = all time)")
        note = str(body.get("note") or "")[:300] or None
        st.set_budget(provider, account, limit, actor, reserve_pct=float(reserve), source="dashboard", note=note,
                      per_run_limit=per_run, window_hours=float(wh) if wh else None)
        return f"Saved limits for {provider}/{account}"
    if kind in ("approval.grant", "approval.deny"):
        aid = _int(body.get("id"), 1, 10**9, "approval id", optional=False)
        st.decide_approval(aid, actor, kind == "approval.grant", provenance=prov)
        return f"Approval #{aid} {'granted' if kind == 'approval.grant' else 'denied'}"
    if kind in ("task.requeue", "task.unblock", "task.cancel"):
        tid = str(body.get("id", ""))
        if not TASK_ID.fullmatch(tid):
            raise BadRequest("bad task id")
        if kind == "task.cancel":
            st.cancel(tid, actor, str(body.get("reason") or "cancelled from the dashboard")[:300], provenance=prov)
            return f"{tid} cancelled"
        st.transition(tid, kind.split(".")[1], actor, owner=None, lease_expires=None)
        return f"{tid} is back in the queue"
    raise BadRequest(f"unknown action {kind!r}")


def icon_bundle() -> str:
    out = {}
    if ICONS.is_dir():
        for p in sorted(ICONS.glob("*.svg")):
            if re.fullmatch(r"[a-z0-9-]+\.svg", p.name):
                svg = p.read_text(encoding="utf-8")
                svg = re.sub(r'\s(height|width|style)="[^"]*"', "", svg, count=3)
                out[p.stem] = svg
    return json.dumps(out)


def serve(db_paths, host="127.0.0.1", port=8791, actor="human:local", writable=True):
    db_paths = [Path(p) for p in (db_paths if isinstance(db_paths, (list, tuple)) else [db_paths])]
    projects = [{"id": i, "name": p.parent.parent.name, "root": str(p.parent.parent)} for i, p in enumerate(db_paths)]
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    allowed_origins = {f"http://{h}" for h in allowed_hosts}
    harnesses = [{k: d[k] for k in ("adapter", "provider", "available")} for d in (a.detect() for a in ADAPTERS.values())]
    icons = icon_bundle()
    token = secrets.token_urlsafe(32)
    config = json.dumps({"writable": writable, "actor": actor, "token": token if writable else None})
    page = lambda: (PAGE.read_text(encoding="utf-8").replace("/*__ICONS__*/{}", icons)
                    .replace("/*__CONFIG__*/{}", config))

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

        def do_POST(self):
            err = lambda code, msg: self._send(code, json.dumps({"error": msg}), "application/json")
            if self.headers.get("Host") not in allowed_hosts:
                return err(403, "forbidden host")
            if self.headers.get("Origin") not in allowed_origins:
                return err(403, "forbidden origin")
            if not writable:
                return err(403, "this dashboard was started with --read-only")
            if not hmac.compare_digest(self.headers.get("X-Agentsys-Token", ""), token):
                return err(403, "missing or stale session token; reload the page")
            if not (self.headers.get("Content-Type") or "").startswith("application/json"):
                return err(415, "expected application/json")
            url = urlparse(self.path)
            if url.path != "/api/action":
                return err(404, "not found")
            n = int(self.headers.get("Content-Length") or 0)
            if not 0 < n <= 16384:
                return err(413, "request too large")
            try:
                body = json.loads(self.rfile.read(n))
                idx = int(body.get("p", 0))
                if not 0 <= idx < len(db_paths):
                    raise BadRequest("unknown project")
                st = Store(db_paths[idx])
                try:
                    msg = apply_action(st, actor, body)
                finally:
                    st.close()
                return self._send(200, json.dumps({"ok": True, "message": msg}), "application/json")
            except (BadRequest, TransitionError, KeyError, ValueError, json.JSONDecodeError) as e:
                return err(400, str(e).strip("'\""))
            except sqlite3.Error as e:
                return err(500, f"store error: {e}")

    srv = ThreadingHTTPServer((host, port), H)
    names = ", ".join(p["name"] for p in projects)
    mode = f"actions recorded as {actor}" if writable else "read-only"
    print(f"agentsys dashboard: http://{host}:{port}  ({names}; {mode}; Ctrl-C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
