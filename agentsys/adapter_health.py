"""Offline and live adapter health checks."""
from __future__ import annotations

import subprocess
import tempfile
import time
from pathlib import Path

from . import budget
from .adapters import ADAPTERS, Adapter


def _version_cmd(adapter: Adapter) -> list[str] | None:
    b = adapter.binary()
    if not b or b == "builtin":
        return None
    return [b, "--version"]


def check_offline() -> list[dict]:
    rows = []
    for a in ADAPTERS.values():
        b = a.binary()
        if not b:
            rows.append({"adapter": a.name, "status": "missing", "detail": "binary not found"})
            continue
        if b == "builtin":
            rows.append({"adapter": a.name, "status": "ok", "detail": "builtin"})
            continue
        cmd = _version_cmd(a)
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            ok = p.returncode == 0
            detail = (p.stdout or p.stderr or "").strip().splitlines()[0][:120] if ok else (p.stderr or p.stdout or "")[:120]
            rows.append({"adapter": a.name, "status": "ok" if ok else "fail", "detail": detail or b})
        except (subprocess.TimeoutExpired, OSError) as e:
            rows.append({"adapter": a.name, "status": "fail", "detail": str(e)})
    return rows


def check_live(st, account: str, adapter_name: str | None = None, *, timeout: int = 120) -> list[dict]:
    names = [adapter_name] if adapter_name else sorted(ADAPTERS)
    rows = []
    with tempfile.TemporaryDirectory(prefix="agentsys-health-") as td:
        workdir = Path(td)
        for name in names:
            a = ADAPTERS.get(name)
            if not a or not a.binary():
                rows.append({"adapter": name, "status": "missing", "detail": "binary not found"})
                continue
            acct = account if a.name != "mock" else "local"
            try:
                budget.check_dispatch(st, a, acct, est=a.default_estimate)
            except budget.BudgetError as e:
                rows.append({"adapter": name, "status": "refused", "detail": str(e)})
                continue
            started = time.time()
            res = a.run("Reply with exactly OK and nothing else.", workdir, write=False, timeout=timeout)
            st.record_run(ts_start=started, ts_end=time.time(), adapter=a.name, provider=a.provider, account=acct,
                          model=res.model, exit_code=res.exit_code, tokens_in=res.tokens_in, tokens_out=res.tokens_out,
                          tokens_cached=res.tokens_cached, tokens_estimate=a.default_estimate, cost_usd=res.cost_usd,
                          usage_source=res.usage_source, note="adapter health check")
            ok = res.exit_code == 0 and bool((res.text or "").strip())
            rows.append({"adapter": name, "status": "ok" if ok else "fail",
                         "detail": f"exit {res.exit_code}, usage={res.usage_source}"})
    return rows
