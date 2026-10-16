"""Git hook install/check for agent/* branches."""
from __future__ import annotations

import re
import shutil
import stat
from pathlib import Path

from . import gitops
from .store import Store

AGENT_BRANCH = re.compile(r"^agent/(t-[0-9a-f]{8})$")
HOOK_NAMES = ("pre-merge-commit", "pre-push")
MARKER = "# agentsys-managed\n"


def _git_dir(root: Path) -> Path:
    return Path(gitops.git(["rev-parse", "--git-dir"], root).stdout.strip())


def hook_path(root: Path, name: str) -> Path:
    return _git_dir(root) / "hooks" / name


def hook_script() -> str:
    return """#!/bin/sh
# agentsys-managed — refuse merge/push of unreviewed agent/* branches.
set -e
ROOT=$(git rev-parse --show-toplevel)
cd "$ROOT" || exit 0
CLI="${AGENTSYS_CLI:-agentsys}"
case "$(basename "$0")" in
  pre-merge-commit) exec "$CLI" hooks merge-check ;;
  pre-push) exec "$CLI" hooks push-check ;;
esac
exit 0
"""


def branches_for_merge(root: Path) -> list[str]:
    """Agent branches whose tip is being merged (best effort)."""
    p = gitops.git(["rev-parse", "-q", "MERGE_HEAD"], root, check=False)
    if p.returncode != 0:
        return []
    tip = p.stdout.strip()
    out = []
    for row in gitops.git(["branch", "--list", "agent/*"], root).stdout.splitlines():
        br = row.strip().lstrip("* ").strip()
        if not br:
            continue
        if gitops.git(["rev-parse", br], root, check=False).stdout.strip() == tip:
            out.append(br)
    return out


def push_refs(stdin_text: str) -> list[str]:
    branches = []
    for line in stdin_text.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[2].startswith("refs/heads/"):
            branches.append(parts[2][len("refs/heads/"):])
    return branches


def install(root: Path, actor: str) -> list[str]:
    root = gitops.project_root(root)
    messages = []
    for name in HOOK_NAMES:
        hp = hook_path(root, name)
        hp.parent.mkdir(parents=True, exist_ok=True)
        backup = hp.with_suffix(hp.suffix + ".agentsys-bak")
        if hp.exists() and MARKER not in hp.read_text(encoding="utf-8", errors="ignore"):
            shutil.copy2(hp, backup)
            messages.append(f"backed up {name} to {backup.name}")
        hp.write_text(hook_script(), encoding="utf-8")
        hp.chmod(hp.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        messages.append(f"installed {name}")
    db = root / ".agent-system" / "state.db"
    if db.exists():
        st = Store(db)
        st.event(actor, None, "hooks.installed", {"hooks": list(HOOK_NAMES)})
        st.close()
    return messages


def uninstall(root: Path, actor: str) -> list[str]:
    root = gitops.project_root(root)
    messages = []
    for name in HOOK_NAMES:
        hp = hook_path(root, name)
        backup = hp.with_suffix(hp.suffix + ".agentsys-bak")
        if hp.exists() and MARKER in hp.read_text(encoding="utf-8", errors="ignore"):
            hp.unlink()
            messages.append(f"removed {name}")
        if backup.exists():
            shutil.move(backup, hp)
            messages.append(f"restored {name} from backup")
    db = root / ".agent-system" / "state.db"
    if db.exists():
        st = Store(db)
        st.event(actor, None, "hooks.uninstalled", {})
        st.close()
    return messages


def task_for_branch(st: Store, branch: str):
    m = AGENT_BRANCH.match(branch.strip())
    if not m:
        return None, None
    tid = m.group(1)
    try:
        return tid, st.get(tid)
    except KeyError:
        return tid, None


def check_branch(st: Store, branch: str, actor: str, override_reason: str | None = None) -> tuple[bool, str]:
    tid, task = task_for_branch(st, branch)
    if not tid:
        return True, f"{branch}: not an agentsys agent branch"
    if not task:
        return False, f"{branch}: no task {tid} in store"
    if task["state"] in ("accepted", "merged"):
        return True, f"{branch}: task {tid} is {task['state']}"
    if override_reason:
        if not actor.startswith("human:"):
            return False, "override requires a human: actor"
        st.event(actor, tid, "hook.override", {"branch": branch, "reason": override_reason, "state": task["state"]})
        return True, f"{branch}: override recorded for task {tid} ({task['state']})"
    return False, (
        f"{branch}: task {tid} is '{task['state']}' — need accepted (verified + reviewed) "
        f"or human override with --override-reason"
    )
