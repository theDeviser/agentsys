"""Profile-driven adapter and reviewer selection."""
from __future__ import annotations

from . import budget
from .adapters import ADAPTERS, Adapter


class RoutingError(Exception):
    def __init__(self, message: str, rejections: list[str] | None = None):
        super().__init__(message)
        self.rejections = rejections or []


def _usage_pct(summary: dict) -> float | None:
    if summary.get("window_pct") is not None:
        return summary["window_pct"]
    return summary.get("pct")


def pick(st, task, rules, *, role: str = "work", est=None) -> tuple[Adapter, str, str]:
    """Choose the first preferred adapter/account that passes budget and optional max_pct."""
    if not rules:
        raise RoutingError("routing.rules is empty")
    kind = task["kind"]
    rejections: list[str] = []
    for rule in rules:
        rk = rule.get("kind", "*")
        if rk not in ("*", kind):
            continue
        for cand in rule.get("prefer") or []:
            name = cand.get("adapter")
            account = cand.get("account")
            if not name or not account:
                rejections.append(f"{name}/{account}: missing adapter or account")
                continue
            adapter = ADAPTERS.get(name)
            if not adapter:
                rejections.append(f"{name}/{account}: unknown adapter")
                continue
            if not adapter.binary():
                rejections.append(f"{name}/{account}: CLI not installed")
                continue
            try:
                budget.check_dispatch(st, adapter, account, role=role, est=est)
            except budget.BudgetError as e:
                rejections.append(f"{name}/{account}: {e}")
                continue
            max_pct = cand.get("max_pct")
            if max_pct is not None:
                s = budget.summary(st, adapter.provider, account)
                pct = _usage_pct(s)
                if pct is not None and pct > float(max_pct):
                    rejections.append(f"{name}/{account}: usage {pct}% > max {max_pct}%")
                    continue
            reason = f"kind={rk} -> {name}/{account}"
            return adapter, account, reason
    raise RoutingError("no routing candidate passed checks", rejections)


def harness_of(actor: str) -> str:
    return actor.split(":", 1)[0] if actor else ""


def reviewer_for(author_actors: list[str], pairs: dict) -> str | None:
    """Map author harnesses to a reviewer harness using pairs and optional '*' fallback."""
    if not pairs:
        return None
    harnesses = {harness_of(a) for a in author_actors if a}
    for h in sorted(harnesses):
        if h in pairs:
            return pairs[h]
    return pairs.get("*")
