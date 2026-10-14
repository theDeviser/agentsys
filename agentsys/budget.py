"""Per-provider, per-account token ledger. Accounts are never pooled; each limit stands alone.

A budget can have any combination of:
  limit_tokens   total cap (0 = no cap, tracking only)
  window_hours   only count runs inside a rolling window (e.g. 5h for plans that reset)
  per_run_limit  refuse any single run whose estimate exceeds this
CLIs can't be stopped mid-run on tokens, so caps are enforced before dispatch and reported after.
"""
from __future__ import annotations

import time

ALERT_LEVELS = (50, 80, 95)


class BudgetError(Exception):
    pass


def run_total(r):
    parts = [r["tokens_in"], r["tokens_out"], r["tokens_cached"]]
    reported = None if all(p is None for p in parts) else sum(p or 0 for p in parts)
    return reported if reported is not None else (r["tokens_estimate"] or 0)


def _window_start(b):
    return time.time() - b["window_hours"] * 3600 if b and b.get("window_hours") else None


def used_tokens(store, provider, account, since=None) -> int:
    """Provider-reported totals; runs without usage data count at their pre-run estimate (never zero)."""
    return sum(run_total(r) for r in store.runs(provider, account) if since is None or r["ts_start"] >= since)


def spend_usd(store, provider, account, since=None):
    vals = [r["cost_usd"] for r in store.runs(provider, account)
            if r["cost_usd"] is not None and (since is None or r["ts_start"] >= since)]
    return round(sum(vals), 4) if vals else None


def estimate(store, adapter, account) -> int:
    recent = [r for r in store.runs(adapter.provider, account) if r["adapter"] == adapter.name][-5:]
    vals = [run_total(r) for r in recent if r["usage_source"] == "provider-reported"]
    return int(sum(vals) / len(vals)) if vals else adapter.default_estimate


def summary(store, provider, account):
    b = store.budget(provider, account)
    since = _window_start(b)
    used = used_tokens(store, provider, account, since)
    out = {"provider": provider, "account": account, "used": used, "used_all_time": used_tokens(store, provider, account),
           "spend_usd": spend_usd(store, provider, account), "runs": len(store.runs(provider, account)),
           "limit": None, "per_run_limit": None, "window_hours": None}
    if not b:
        return out
    limit = b["limit_tokens"] or None
    out.update(limit=limit, per_run_limit=b.get("per_run_limit"), window_hours=b.get("window_hours"),
               reserve_pct=b["reserve_pct"], source=b["source"], note=b.get("note"))
    if limit:
        out.update(remaining=limit - used, pct=round(100 * used / limit, 1))
    return out


def check_dispatch(store, adapter, account, role="work", est=None):
    """Raise BudgetError unless the run fits. Non-review work may not eat into the verification reserve."""
    if adapter.provider == "mock":
        return 0, []
    b = store.budget(adapter.provider, account)
    if not b:
        raise BudgetError(f"no budget set for {adapter.provider}/{account}; "
                          f"run `agentsys budget set {adapter.provider} {account} --limit N` first")
    est = est if est is not None else estimate(store, adapter, account)
    per_run = b.get("per_run_limit")
    if per_run and est > per_run:
        raise BudgetError(f"{adapter.provider}/{account}: estimated {est:,} tokens for this run exceeds the "
                          f"per-run cap of {per_run:,}")
    limit = b["limit_tokens"]
    if not limit:
        return est, []
    used = used_tokens(store, adapter.provider, account, _window_start(b))
    ceiling = limit if role == "review" else int(limit * (1 - b["reserve_pct"] / 100))
    if used + est > ceiling:
        raise BudgetError(f"{adapter.provider}/{account}: used {used:,} + estimate {est:,} > "
                          f"{'limit' if role == 'review' else 'limit minus reserve'} {ceiling:,}")
    alerts = [f"{adapter.provider}/{account} will pass {lvl}% of its limit"
              for lvl in ALERT_LEVELS if used < limit * lvl / 100 <= used + est]
    return est, alerts


def post_run_alerts(store, provider, account, before, run_tokens=None):
    b = store.budget(provider, account)
    if not b:
        return []
    out = []
    if b.get("per_run_limit") and run_tokens and run_tokens > b["per_run_limit"]:
        out.append(f"{provider}/{account}: this run used {run_tokens:,} tokens, over the per-run cap of "
                   f"{b['per_run_limit']:,} (CLIs can't be stopped mid-run)")
    limit = b["limit_tokens"]
    if not limit:
        return out
    after = used_tokens(store, provider, account, _window_start(b))
    out += [f"{provider}/{account} passed {lvl}% ({after:,}/{limit:,})" for lvl in ALERT_LEVELS
            if before < limit * lvl / 100 <= after]
    if after > limit:
        out.append(f"{provider}/{account} is OVER its limit ({after:,}/{limit:,}); further dispatch is refused")
    return out
