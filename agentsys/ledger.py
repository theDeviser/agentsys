"""User-level token ledger shared by every project, so an account's caps hold no matter which repo dispatches.

Project stores keep their own run history for the audit trail; budgets and the usage they're checked
against live here. Default path: ~/.agentsys/ledger.db (override with AGENTSYS_LEDGER).
"""
from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

DDL = """
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, project TEXT NOT NULL, local_id INTEGER, task_id TEXT,
  ts_start REAL NOT NULL, ts_end REAL, adapter TEXT NOT NULL, provider TEXT NOT NULL, account TEXT NOT NULL,
  model TEXT, exit_code INTEGER, tokens_in INTEGER, tokens_out INTEGER, tokens_cached INTEGER,
  tokens_estimate INTEGER, cost_usd REAL, usage_source TEXT NOT NULL, note TEXT,
  UNIQUE (project, local_id)
);
CREATE INDEX IF NOT EXISTS runs_acct ON runs(provider, account, ts_start);
CREATE TABLE IF NOT EXISTS imported_usage (
  external_id TEXT PRIMARY KEY, provider TEXT NOT NULL, tokens INTEGER NOT NULL,
  model TEXT, ts REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS budgets (
  provider TEXT NOT NULL, account TEXT NOT NULL, limit_tokens INTEGER NOT NULL,
  reserve_pct REAL NOT NULL DEFAULT 20, source TEXT NOT NULL, note TEXT, updated_at REAL NOT NULL,
  per_run_limit INTEGER, window_hours REAL, PRIMARY KEY (provider, account)
);
"""
RUN_COLS = ("task_id", "ts_start", "ts_end", "adapter", "provider", "account", "model", "exit_code", "tokens_in",
            "tokens_out", "tokens_cached", "tokens_estimate", "cost_usd", "usage_source", "note")
BUDGET_COLS = ("provider", "account", "limit_tokens", "reserve_pct", "source", "note", "updated_at",
               "per_run_limit", "window_hours")


def default_path() -> Path:
    return Path(os.environ.get("AGENTSYS_LEDGER") or Path.home() / ".agentsys" / "ledger.db").expanduser()


class Ledger:
    def __init__(self, path=None):
        self.path = Path(path) if path else default_path()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = sqlite3.connect(str(self.path), timeout=10, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA busy_timeout=10000")
        self.db.executescript(DDL)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def close(self):
        self.db.close()

    def import_from(self, store_db: sqlite3.Connection, project: str):
        """Copy a project's existing runs and budgets in. Budgets already in the ledger win."""
        for r in store_db.execute("SELECT * FROM runs"):
            r = dict(r)
            self.db.execute(f"INSERT OR IGNORE INTO runs (project, local_id, {', '.join(RUN_COLS)}) VALUES "
                            f"(?,?,{','.join('?' * len(RUN_COLS))})", (project, r["id"], *(r.get(c) for c in RUN_COLS)))
        for b in store_db.execute("SELECT * FROM budgets"):
            b = dict(b)
            self.db.execute(f"INSERT OR IGNORE INTO budgets ({', '.join(BUDGET_COLS)}) VALUES "
                            f"({','.join('?' * len(BUDGET_COLS))})", tuple(b.get(c) for c in BUDGET_COLS))

    def record_run(self, project: str, local_id: int, **r):
        self.db.execute(f"INSERT OR IGNORE INTO runs (project, local_id, {', '.join(RUN_COLS)}) VALUES "
                        f"(?,?,{','.join('?' * len(RUN_COLS))})", (project, local_id, *(r.get(c) for c in RUN_COLS)))

    def runs(self, provider=None, account=None) -> list:
        q, args = "SELECT * FROM runs WHERE 1=1", []
        if provider:
            q, args = q + " AND provider=?", args + [provider]
        if account:
            q, args = q + " AND account=?", args + [account]
        return [dict(r) for r in self.db.execute(q + " ORDER BY ts_start, id", args)]

    def set_budget(self, provider, account, limit_tokens, reserve_pct, source, note, per_run_limit, window_hours):
        self.db.execute(
            "INSERT INTO budgets VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(provider,account) DO UPDATE SET "
            "limit_tokens=excluded.limit_tokens, reserve_pct=excluded.reserve_pct, source=excluded.source, "
            "note=excluded.note, updated_at=excluded.updated_at, per_run_limit=excluded.per_run_limit, "
            "window_hours=excluded.window_hours",
            (provider, account, int(limit_tokens), reserve_pct, source, note, time.time(), per_run_limit, window_hours))

    def budgets(self) -> list:
        return [dict(r) for r in self.db.execute("SELECT * FROM budgets ORDER BY provider, account")]

    def budget(self, provider, account):
        row = self.db.execute("SELECT * FROM budgets WHERE provider=? AND account=?", (provider, account)).fetchone()
        return dict(row) if row else None

    def import_usage_row(self, row: dict) -> bool:
        try:
            self.db.execute(
                "INSERT INTO imported_usage (external_id, provider, tokens, model, ts) VALUES (?,?,?,?,?)",
                (row["id"], row["provider"], row["tokens"], row.get("model"), row.get("ts") or time.time()),
            )
            return True
        except sqlite3.IntegrityError:
            return False
