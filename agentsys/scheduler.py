"""Background watch loop: route and dispatch ready tasks."""
from __future__ import annotations

import os
import subprocess

from . import profile, routing
from .routing import RoutingError

DONE = frozenset({"accepted", "merged"})


class SchedulerError(Exception):
    pass


def _deps_ok(st, task) -> bool:
    for dep in task.get("deps") or []:
        if st.get(dep)["state"] not in DONE:
            return False
    return True


def ready_tasks(st) -> list:
    return [t for t in st.list() if t["state"] in ("ready", "changes_requested") and _deps_ok(st, t)]


def tick(st, root, cli_cmd: list[str], *, max_parallel: int = 1, dry_run: bool = False, timeout: int = 900) -> list:
    rules = profile.section(root, "routing").get("rules") or []
    if not rules:
        raise SchedulerError("routing.rules required in .agentsys/profile.json for watch")
    st.reap()
    decisions: list[dict] = []
    ran = 0
    env = dict(os.environ)
    env["AGENTSYS_DB"] = str(st.path)
    for task in ready_tasks(st):
        if ran >= max_parallel:
            break
        try:
            adapter, account, reason = routing.pick(st, task, rules)
        except RoutingError as e:
            decisions.append({"task_id": task["id"], "action": "skip", "detail": str(e)})
            continue
        if dry_run:
            decisions.append({"task_id": task["id"], "action": "would_dispatch", "adapter": adapter.name,
                              "account": account, "reason": reason})
            ran += 1
            continue
        proc = subprocess.run(
            cli_cmd + ["dispatch", task["id"], "--adapter", "auto", "--timeout", str(timeout)],
            cwd=str(root), env=env, capture_output=True, text=True,
        )
        decisions.append({"task_id": task["id"], "action": "dispatched", "exit_code": proc.returncode,
                          "adapter": adapter.name, "account": account, "reason": reason})
        ran += 1
    st.event("system:scheduler", None, "scheduler.tick", {"decisions": decisions})
    return decisions
