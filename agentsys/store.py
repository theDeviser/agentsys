"""Durable task store: SQLite schema, state machine, append-only audit events."""
from __future__ import annotations

import fnmatch
import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

SCHEMA_VERSION = 1

STATES = (
    "ready", "in_progress", "blocked", "submitted", "verified",
    "changes_requested", "accepted", "merged", "escalated", "cancelled",
)
TERMINAL = {"merged", "cancelled"}
DONE_FOR_DEPS = {"accepted", "merged"}
KINDS = ("research", "implement")
FINDING_KINDS = ("finding", "artifact", "decision", "blocker", "question", "output")

# action -> (allowed source states, target state)
TRANSITIONS = {
    "claim": ({"ready", "changes_requested"}, "in_progress"),
    "block": ({"in_progress", "ready"}, "blocked"),
    "unblock": ({"blocked"}, "ready"),
    "submit": ({"in_progress"}, "submitted"),
    "verify_pass": ({"submitted"}, "verified"),
    "verify_fail": ({"submitted"}, "changes_requested"),
    "approve": ({"verified"}, "accepted"),
    "reject": ({"verified"}, "changes_requested"),
    "merge": ({"accepted"}, "merged"),
    "release": ({"in_progress"}, "ready"),
    "expire": ({"in_progress"}, "ready"),
    "escalate": ({"in_progress"}, "escalated"),
    "requeue": ({"escalated", "blocked"}, "ready"),
}

DDL = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tasks (
  id TEXT PRIMARY KEY, title TEXT NOT NULL, goal TEXT NOT NULL DEFAULT '',
  acceptance TEXT NOT NULL DEFAULT '', kind TEXT NOT NULL,
  allowed_paths TEXT NOT NULL DEFAULT '[]', checks TEXT NOT NULL DEFAULT '[]',
  deps TEXT NOT NULL DEFAULT '[]', state TEXT NOT NULL, owner TEXT,
  lease_expires REAL, attempts INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 2, worktree TEXT, branch TEXT, base TEXT,
  created_by TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, actor TEXT NOT NULL,
  task_id TEXT, kind TEXT NOT NULL, payload TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS findings (
  id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL, ts REAL NOT NULL,
  author TEXT NOT NULL, kind TEXT NOT NULL, body TEXT NOT NULL,
  evidence TEXT NOT NULL DEFAULT '[]', confidence TEXT
);
CREATE TABLE IF NOT EXISTS checkpoints (
  id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL, ts REAL NOT NULL,
  author TEXT NOT NULL, summary TEXT NOT NULL, commit_sha TEXT,
  verified INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, ts_start REAL NOT NULL,
  ts_end REAL, adapter TEXT NOT NULL, provider TEXT NOT NULL, account TEXT NOT NULL,
  model TEXT, exit_code INTEGER, tokens_in INTEGER, tokens_out INTEGER,
  tokens_cached INTEGER, tokens_estimate INTEGER, cost_usd REAL, usage_source TEXT NOT NULL, note TEXT
);
CREATE TABLE IF NOT EXISTS budgets (
  provider TEXT NOT NULL, account TEXT NOT NULL, limit_tokens INTEGER NOT NULL,
  reserve_pct REAL NOT NULL DEFAULT 20, source TEXT NOT NULL, note TEXT,
  updated_at REAL NOT NULL, PRIMARY KEY (provider, account)
);
CREATE TABLE IF NOT EXISTS approvals (
  id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, action TEXT NOT NULL,
  requested_by TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '', status TEXT NOT NULL,
  decided_by TEXT, decided_at REAL, ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS events_task ON events(task_id);
CREATE INDEX IF NOT EXISTS findings_task ON findings(task_id);
"""


class TransitionError(Exception):
    """An action is not allowed from the task's current state or by this actor."""


def now() -> float:
    return time.time()


def literal_prefix(pattern: str) -> str:
    cut = len(pattern)
    for ch in "*?[":
        i = pattern.find(ch)
        if i != -1:
            cut = min(cut, i)
    return pattern[:cut]


def paths_overlap(a: list, b: list) -> bool:
    """Conservative glob overlap: overlap if either literal prefix contains the other, or a concrete path matches."""
    for pa in a:
        for pb in b:
            la, lb = literal_prefix(pa), literal_prefix(pb)
            if la.startswith(lb) or lb.startswith(la):
                return True
            if fnmatch.fnmatch(pa, pb) or fnmatch.fnmatch(pb, pa):
                return True
    return False


def path_allowed(path: str, allowed: list) -> bool:
    return any(fnmatch.fnmatch(path, pat) or path.startswith(pat.rstrip("/") + "/") and not any(c in pat for c in "*?[")
               for pat in allowed)


class Store:
    def __init__(self, db_path, lease_seconds: float = 1800):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lease_seconds = lease_seconds
        self.db = sqlite3.connect(str(self.path), timeout=10, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA busy_timeout=10000")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript(DDL)
        self.db.execute("INSERT OR IGNORE INTO meta VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def close(self):
        self.db.close()

    @contextmanager
    def tx(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield self.db
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def _event(self, db, actor, task_id, kind, payload=None):
        db.execute("INSERT INTO events (ts, actor, task_id, kind, payload) VALUES (?,?,?,?,?)",
                   (now(), actor, task_id, kind, json.dumps(payload or {}, sort_keys=True)))

    def event(self, actor, task_id, kind, payload=None):
        with self.tx() as db:
            self._event(db, actor, task_id, kind, payload)

    # ---------- tasks ----------
    def add_task(self, actor, title, kind="implement", goal="", acceptance="", allowed_paths=None,
                 checks=None, deps=None, max_attempts=2, base=None, task_id=None) -> dict:
        if kind not in KINDS:
            raise ValueError(f"kind must be one of {KINDS}")
        allowed_paths = list(allowed_paths or [])
        if kind == "implement" and not allowed_paths:
            raise ValueError("implement tasks need at least one --path (scope is enforced at verify time)")
        deps = list(deps or [])
        tid = task_id or "t-" + uuid.uuid4().hex[:8]
        ts = now()
        with self.tx() as db:
            for d in deps:
                if not db.execute("SELECT 1 FROM tasks WHERE id=?", (d,)).fetchone():
                    raise ValueError(f"unknown dependency {d}")
            db.execute(
                "INSERT INTO tasks (id,title,goal,acceptance,kind,allowed_paths,checks,deps,state,max_attempts,"
                "base,created_by,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (tid, title, goal, acceptance, kind, json.dumps(allowed_paths), json.dumps(list(checks or [])),
                 json.dumps(deps), "ready", max_attempts, base, actor, ts, ts))
            self._event(db, actor, tid, "task.created", {"title": title, "kind": kind, "paths": allowed_paths,
                                                         "deps": deps})
        return self.get(tid)

    def get(self, tid) -> dict:
        row = self.db.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
        if not row:
            raise KeyError(f"no task {tid}")
        return self._task(row)

    @staticmethod
    def _task(row) -> dict:
        t = dict(row)
        for k in ("allowed_paths", "checks", "deps"):
            t[k] = json.loads(t[k])
        return t

    def list(self, state=None) -> list:
        q, args = "SELECT * FROM tasks", ()
        if state:
            q, args = q + " WHERE state=?", (state,)
        return [self._task(r) for r in self.db.execute(q + " ORDER BY created_at", args)]

    def _move(self, db, task, action, actor, extra=None, **fields):
        sources, target = TRANSITIONS[action]
        if task["state"] not in sources:
            raise TransitionError(f"cannot {action} task {task['id']} in state '{task['state']}'")
        fields.update(state=target, updated_at=now())
        cols = ", ".join(f"{k}=?" for k in fields)
        # Optimistic guard: the row must still be in the state we read.
        cur = db.execute(f"UPDATE tasks SET {cols} WHERE id=? AND state=?",
                         (*fields.values(), task["id"], task["state"]))
        if cur.rowcount != 1:
            raise TransitionError(f"task {task['id']} changed concurrently; retry")
        self._event(db, actor, task["id"], f"task.{action}",
                    {"from": task["state"], "to": target, **(extra or {})})
        return target

    def reap(self, actor="system:reaper") -> list:
        """Return expired leases to the queue, or escalate after max_attempts."""
        moved = []
        with self.tx() as db:
            for row in db.execute("SELECT * FROM tasks WHERE state='in_progress' AND lease_expires < ?", (now(),)):
                t = self._task(row)
                if t["attempts"] >= t["max_attempts"]:
                    self._move(db, t, "escalate", actor, {"reason": "lease expired, max attempts reached",
                                                          "owner": t["owner"]}, owner=None, lease_expires=None)
                    moved.append((t["id"], "escalated"))
                else:
                    self._move(db, t, "expire", actor, {"reason": "lease expired", "owner": t["owner"]},
                               owner=None, lease_expires=None)
                    moved.append((t["id"], "ready"))
        return moved

    def claim(self, tid, actor, lease_seconds=None) -> dict:
        self.reap()
        lease = lease_seconds or self.lease_seconds
        with self.tx() as db:
            t = self._task(db.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone() or _missing(tid))
            for d in t["deps"]:
                st = db.execute("SELECT state FROM tasks WHERE id=?", (d,)).fetchone()["state"]
                if st not in DONE_FOR_DEPS:
                    raise TransitionError(f"dependency {d} is '{st}', needs accepted/merged")
            if t["kind"] == "implement":
                for row in db.execute("SELECT * FROM tasks WHERE state='in_progress' AND id!=? AND kind='implement'",
                                      (tid,)):
                    other = self._task(row)
                    if paths_overlap(t["allowed_paths"], other["allowed_paths"]):
                        raise TransitionError(
                            f"path scope overlaps in-progress task {other['id']} ({other['owner']}); "
                            "wait, narrow --path, or add a dependency")
            self._move(db, t, "claim", actor, {"lease_s": lease, "attempt": t["attempts"] + 1},
                       owner=actor, lease_expires=now() + lease, attempts=t["attempts"] + 1)
        return self.get(tid)

    def _require_owner(self, t, actor):
        if t["owner"] != actor:
            raise TransitionError(f"task {t['id']} is owned by {t['owner']!r}, not {actor!r}")

    def heartbeat(self, tid, actor, lease_seconds=None) -> dict:
        with self.tx() as db:
            t = self.get(tid)
            if t["state"] != "in_progress":
                raise TransitionError(f"task {tid} is '{t['state']}', not in_progress")
            self._require_owner(t, actor)
            exp = now() + (lease_seconds or self.lease_seconds)
            db.execute("UPDATE tasks SET lease_expires=?, updated_at=? WHERE id=?", (exp, now(), tid))
            self._event(db, actor, tid, "task.heartbeat", {"lease_expires": exp})
        return self.get(tid)

    def set_fields(self, tid, actor, kind, **fields):
        with self.tx() as db:
            cols = ", ".join(f"{k}=?" for k in fields)
            db.execute(f"UPDATE tasks SET {cols}, updated_at=? WHERE id=?", (*fields.values(), now(), tid))
            self._event(db, actor, tid, kind, fields)

    def transition(self, tid, action, actor, extra=None, owner_only=False, **fields) -> dict:
        with self.tx() as db:
            t = self.get(tid)
            if owner_only:
                self._require_owner(t, actor)
            self._move(db, t, action, actor, extra, **fields)
        return self.get(tid)

    def cancel(self, tid, actor, reason=""):
        with self.tx() as db:
            t = self.get(tid)
            if t["state"] in TERMINAL:
                raise TransitionError(f"task {tid} already {t['state']}")
            db.execute("UPDATE tasks SET state='cancelled', owner=NULL, lease_expires=NULL, updated_at=? WHERE id=?",
                       (now(), tid))
            self._event(db, actor, tid, "task.cancel", {"from": t["state"], "to": "cancelled", "reason": reason})

    # ---------- findings / checkpoints ----------
    def add_finding(self, tid, actor, body, kind="finding", evidence=None, confidence=None) -> int:
        if kind not in FINDING_KINDS:
            raise ValueError(f"kind must be one of {FINDING_KINDS}")
        self.get(tid)
        with self.tx() as db:
            cur = db.execute("INSERT INTO findings (task_id,ts,author,kind,body,evidence,confidence) VALUES (?,?,?,?,?,?,?)",
                             (tid, now(), actor, kind, body, json.dumps(list(evidence or [])), confidence))
            self._event(db, actor, tid, f"finding.{kind}", {"finding_id": cur.lastrowid})
            self._extend_if_owner(db, tid, actor)
            return cur.lastrowid

    def _extend_if_owner(self, db, tid, actor):
        db.execute("UPDATE tasks SET lease_expires=? WHERE id=? AND owner=? AND state='in_progress'",
                   (now() + self.lease_seconds, tid, actor))

    def findings(self, tid) -> list:
        rows = self.db.execute("SELECT * FROM findings WHERE task_id=? ORDER BY id", (tid,))
        return [dict(r, evidence=json.loads(r["evidence"])) for r in rows]

    def add_checkpoint(self, tid, actor, summary, commit_sha=None) -> int:
        self.get(tid)
        with self.tx() as db:
            cur = db.execute("INSERT INTO checkpoints (task_id,ts,author,summary,commit_sha) VALUES (?,?,?,?,?)",
                             (tid, now(), actor, summary, commit_sha))
            self._event(db, actor, tid, "checkpoint", {"checkpoint_id": cur.lastrowid, "sha": commit_sha})
            self._extend_if_owner(db, tid, actor)
            return cur.lastrowid

    def checkpoints(self, tid) -> list:
        return [dict(r) for r in self.db.execute("SELECT * FROM checkpoints WHERE task_id=? ORDER BY id", (tid,))]

    def mark_verified(self, tid, sha):
        with self.tx() as db:
            if sha:
                db.execute("UPDATE checkpoints SET verified=1 WHERE task_id=? AND commit_sha=?", (tid, sha))
            else:
                db.execute("UPDATE checkpoints SET verified=1 WHERE id=(SELECT MAX(id) FROM checkpoints WHERE task_id=?)",
                           (tid,))

    def authors(self, tid) -> set:
        """Everyone who owned or produced work for this task (they may not review it)."""
        rows = self.db.execute(
            "SELECT actor FROM events WHERE task_id=? AND kind IN ('task.claim','checkpoint','task.submit') "
            "UNION SELECT author FROM checkpoints WHERE task_id=?", (tid, tid))
        return {r[0] for r in rows}

    def events(self, tid=None, limit=None) -> list:
        q, args = "SELECT * FROM events", []
        if tid:
            q += " WHERE task_id=?"
            args.append(tid)
        q += " ORDER BY id"
        rows = [dict(r, payload=json.loads(r["payload"])) for r in self.db.execute(q, args)]
        return rows[-limit:] if limit else rows

    # ---------- approvals ----------
    def request_approval(self, tid, action, actor, reason="") -> int:
        with self.tx() as db:
            row = db.execute("SELECT id FROM approvals WHERE task_id IS ? AND action=? AND status='pending'",
                             (tid, action)).fetchone()
            if row:
                return row["id"]
            cur = db.execute("INSERT INTO approvals (task_id,action,requested_by,reason,status,ts) VALUES (?,?,?,?,?,?)",
                             (tid, action, actor, reason, "pending", now()))
            self._event(db, actor, tid, "approval.requested", {"approval_id": cur.lastrowid, "action": action})
            return cur.lastrowid

    def decide_approval(self, aid, actor, grant: bool):
        if not actor.startswith("human:"):
            raise TransitionError("approvals must be decided by a 'human:' actor")
        with self.tx() as db:
            row = db.execute("SELECT * FROM approvals WHERE id=?", (aid,)).fetchone()
            if not row or row["status"] != "pending":
                raise TransitionError(f"approval {aid} is not pending")
            status = "granted" if grant else "denied"
            db.execute("UPDATE approvals SET status=?, decided_by=?, decided_at=? WHERE id=?",
                       (status, actor, now(), aid))
            self._event(db, actor, row["task_id"], f"approval.{status}", {"approval_id": aid, "action": row["action"]})

    def approval_granted(self, tid, action) -> bool:
        return bool(self.db.execute("SELECT 1 FROM approvals WHERE task_id IS ? AND action=? AND status='granted'",
                                    (tid, action)).fetchone())

    def approvals(self, status=None) -> list:
        q, args = "SELECT * FROM approvals", ()
        if status:
            q, args = q + " WHERE status=?", (status,)
        return [dict(r) for r in self.db.execute(q + " ORDER BY id", args)]

    # ---------- runs / budgets ----------
    def record_run(self, **r) -> int:
        cols = ", ".join(r)
        with self.tx() as db:
            cur = db.execute(f"INSERT INTO runs ({cols}) VALUES ({','.join('?' * len(r))})", tuple(r.values()))
            self._event(db, f"{r['adapter']}:{r['account']}", r.get("task_id"), "run.recorded",
                        {"run_id": cur.lastrowid, "exit": r.get("exit_code"), "usage_source": r["usage_source"]})
            return cur.lastrowid

    def runs(self, provider=None, account=None) -> list:
        q, args = "SELECT * FROM runs WHERE 1=1", []
        if provider:
            q, args = q + " AND provider=?", args + [provider]
        if account:
            q, args = q + " AND account=?", args + [account]
        return [dict(r) for r in self.db.execute(q + " ORDER BY id", args)]

    def set_budget(self, provider, account, limit_tokens, actor, reserve_pct=20.0, source="manual", note=None):
        with self.tx() as db:
            db.execute("INSERT INTO budgets VALUES (?,?,?,?,?,?,?) ON CONFLICT(provider,account) DO UPDATE SET "
                       "limit_tokens=excluded.limit_tokens, reserve_pct=excluded.reserve_pct, source=excluded.source, "
                       "note=excluded.note, updated_at=excluded.updated_at",
                       (provider, account, int(limit_tokens), reserve_pct, source, note, now()))
            self._event(db, actor, None, "budget.set", {"provider": provider, "account": account,
                                                        "limit_tokens": int(limit_tokens), "reserve_pct": reserve_pct})

    def budgets(self) -> list:
        return [dict(r) for r in self.db.execute("SELECT * FROM budgets ORDER BY provider, account")]

    def budget(self, provider, account):
        row = self.db.execute("SELECT * FROM budgets WHERE provider=? AND account=?", (provider, account)).fetchone()
        return dict(row) if row else None


def _missing(tid):
    raise KeyError(f"no task {tid}")
