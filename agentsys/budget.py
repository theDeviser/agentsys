"""Per-provider, per-account token ledger. Accounts are never pooled; each limit stands alone."""
from __future__ import annotations

ALERT_LEVELS = (50, 80, 95)


class BudgetError(Exception):
    pass


def used_tokens(store, provider, account) -> int:
    """Provider-reported totals; runs without usage data count at their pre-run estimate (never zero)."""
    total = 0
    for r in store.runs(provider, account):
        parts = [r["tokens_in"], r["tokens_out"], r["tokens_cached"]]
        reported = None if all(p is None for p in parts) else sum(p or 0 for p in parts)
        total += reported if reported is not None else (r["tokens_estimate"] or 0)
    return total


def estimate(store, adapter, account) -> int:
    recent = [r for r in store.runs(adapter.provider, account) if r["adapter"] == adapter.name][-5:]
    vals = [sum(x or 0 for x in (r["tokens_in"], r["tokens_out"], r["tokens_cached"])) for r in recent
            if r["usage_source"] == "provider-reported"]
    return int(sum(vals) / len(vals)) if vals else adapter.default_estimate


def summary(store, provider, account):
    b = store.budget(provider, account)
    used = used_tokens(store, provider, account)
    if not b:
        return {"provider": provider, "account": account, "limit": None, "used": used}
    limit = b["limit_tokens"]
    return {"provider": provider, "account": account, "limit": limit, "used": used,
            "remaining": limit - used, "reserve_pct": b["reserve_pct"], "pct": round(100 * used / limit, 1),
            "source": b["source"]}


def check_dispatch(store, adapter, account, role="work", est=None):
    """Raise BudgetError unless the run fits. Non-review work may not eat into the verification reserve."""
    if adapter.provider == "mock":
        return 0, []
    b = store.budget(adapter.provider, account)
    if not b:
        raise BudgetError(f"no budget set for {adapter.provider}/{account}; "
                          f"run `agentsys budget set {adapter.provider} {account} --limit N` first")
    est = est if est is not None else estimate(store, adapter, account)
    used = used_tokens(store, adapter.provider, account)
    limit = b["limit_tokens"]
    ceiling = limit if role == "review" else int(limit * (1 - b["reserve_pct"] / 100))
    if used + est > ceiling:
        raise BudgetError(f"{adapter.provider}/{account}: used {used:,} + estimate {est:,} > "
                          f"{'limit' if role == 'review' else 'limit minus reserve'} {ceiling:,}")
    alerts = [f"{adapter.provider}/{account} will pass {lvl}% of its limit"
              for lvl in ALERT_LEVELS if used < limit * lvl / 100 <= used + est]
    return est, alerts


def post_run_alerts(store, provider, account, before):
    b = store.budget(provider, account)
    if not b:
        return []
    after, limit = used_tokens(store, provider, account), b["limit_tokens"]
    out = [f"{provider}/{account} passed {lvl}% ({after:,}/{limit:,})" for lvl in ALERT_LEVELS
           if before < limit * lvl / 100 <= after]
    if after > limit:
        out.append(f"{provider}/{account} is OVER its limit ({after:,}/{limit:,}); further dispatch is refused")
    return out
