"""Read-only live dashboard over the agentsys store (stdlib HTTP server, polling)."""
from __future__ import annotations

import json
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import budget
from .store import Store

PAGE = Path(__file__).with_name("ui.html")


def snapshot(st: Store) -> dict:
    tasks = st.list()
    counts = {}
    for f in st.db.execute("SELECT task_id, kind, COUNT(*) n FROM findings GROUP BY task_id, kind"):
        counts.setdefault(f["task_id"], {})[f["kind"]] = f["n"]
    for t in tasks:
        t["finding_counts"] = counts.get(t["id"], {})
    accounts = {(b["provider"], b["account"]) for b in st.budgets()}
    accounts |= {(r["provider"], r["account"]) for r in st.runs() if r["provider"] not in ("mock",)}
    return {
        "root": str(st.path.parent.parent),
        "tasks": tasks,
        "events": st.events(limit=80)[::-1],
        "runs": st.runs()[::-1][:30],
        "budgets": [budget.summary(st, p, a) for p, a in sorted(accounts)],
        "approvals": st.approvals(),
    }


def task_detail(st: Store, tid: str) -> dict:
    return {"task": st.get(tid), "findings": st.findings(tid), "checkpoints": st.checkpoints(tid),
            "events": st.events(tid)[::-1],
            "runs": [r for r in st.runs() if r["task_id"] == tid]}


def serve(db_path, host="127.0.0.1", port=8791):
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype):
            data = body.encode() if isinstance(body, str) else body
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.headers.get("Host") not in allowed_hosts:  # blocks DNS-rebinding
                return self._send(403, "forbidden host", "text/plain")
            url = urlparse(self.path)
            try:
                if url.path == "/":
                    return self._send(200, PAGE.read_text(encoding="utf-8"), "text/html; charset=utf-8")
                st = Store(db_path)
                try:
                    if url.path == "/api/state":
                        out = snapshot(st)
                    elif url.path == "/api/task":
                        out = task_detail(st, (parse_qs(url.query).get("id") or [""])[0])
                    else:
                        return self._send(404, "not found", "text/plain")
                finally:
                    st.close()
                return self._send(200, json.dumps(out, default=str), "application/json")
            except (KeyError, sqlite3.Error) as e:
                return self._send(404, json.dumps({"error": str(e)}), "application/json")

    srv = ThreadingHTTPServer((host, port), H)
    print(f"agentsys dashboard: http://{host}:{port}  (read-only; Ctrl-C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
