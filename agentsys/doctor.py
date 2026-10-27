"""Local health checks for agentsys."""
from __future__ import annotations

import shutil
import sys

from . import gitops, trust
from .adapter_health import check_offline
from .adapters import ADAPTERS


def run_doctor(st) -> list[dict]:
    rows = []
    rows.append(_row("python", "pass" if sys.version_info >= (3, 9) else "fail", f"{sys.version_info.major}.{sys.version_info.minor}"))
    git_bin = shutil.which("git")
    rows.append(_row("git", "pass" if git_bin else "fail", git_bin or "git not found"))
    problems = trust.verify_event_chain(st.db, trust.load_install_key())
    rows.append(_row("verify-log", "pass" if not problems else "fail", problems[0] if problems else "OK"))
    hook = gitops.project_root(st.path.parent.parent) / ".git" / "hooks" / "pre-push"
    if hook.is_file() and "agentsys-managed" in hook.read_text(errors="ignore"):
        rows.append(_row("hooks", "pass", "pre-push installed"))
    else:
        rows.append(_row("hooks", "warn", "run `agentsys hooks install`"))
    for a in ADAPTERS.values():
        d = a.detect()
        rows.append(_row(f"adapter:{a.name}", "pass" if d["available"] else "warn", d["binary"] or "missing"))
    failed = [r for r in check_offline() if r["status"] != "ok"]
    rows.append(_row("adapter-versions", "pass" if not failed else "warn",
                     "OK" if not failed else ", ".join(f"{r['adapter']}:{r['status']}" for r in failed)))
    rows.append(_row("ledger", "pass" if st.ledger.path.exists() else "warn", str(st.ledger.path)))
    return rows


def _row(check, status, detail):
    return {"check": check, "status": status, "detail": detail}
