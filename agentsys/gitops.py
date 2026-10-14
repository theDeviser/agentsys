"""Git helpers: project root discovery, per-task worktrees, diffs, dry-run merges."""
from __future__ import annotations

import subprocess
from pathlib import Path


class GitError(Exception):
    pass


def git(args, cwd, check=True) -> subprocess.CompletedProcess:
    p = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)
    if check and p.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed: {(p.stderr or p.stdout).strip()}")
    return p


def project_root(start=".") -> Path:
    """Root of the *main* working tree, even when called from inside a linked worktree."""
    common = git(["rev-parse", "--path-format=absolute", "--git-common-dir"], start).stdout.strip()
    return Path(common).parent


def head_sha(cwd) -> str:
    return git(["rev-parse", "HEAD"], cwd).stdout.strip()


def current_branch(cwd) -> str:
    return git(["rev-parse", "--abbrev-ref", "HEAD"], cwd).stdout.strip()


def is_clean(cwd) -> bool:
    return git(["status", "--porcelain"], cwd).stdout.strip() == ""


def worktrees_dir(root: Path) -> Path:
    return root.parent / f"{root.name}.worktrees"


def ensure_worktree(root: Path, task_id: str, base: str):
    """Create (or reuse, on retry) the task's worktree on branch agent/<task_id>."""
    path = worktrees_dir(root) / task_id
    branch = f"agent/{task_id}"
    if path.exists():
        return path, branch
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = git(["rev-parse", "--verify", "--quiet", branch], root, check=False).returncode == 0
    if exists:
        git(["worktree", "add", str(path), branch], root)
    else:
        git(["worktree", "add", "-b", branch, str(path), base], root)
    return path, branch


def commit_all(cwd, message, author) -> str | None:
    """Commit everything in the worktree; returns new SHA or None if nothing changed."""
    git(["add", "-A"], cwd)
    if git(["diff", "--cached", "--quiet"], cwd, check=False).returncode == 0:
        return None
    git(["-c", f"user.name={author}", "-c", "user.email=agentsys@localhost", "commit", "-q", "-m", message], cwd)
    return head_sha(cwd)


def changed_files(cwd, base) -> list:
    out = git(["diff", "--name-only", f"{base}...HEAD"], cwd).stdout
    return [line for line in out.splitlines() if line]


def added_lines(cwd, base) -> list:
    """(path, line) pairs for lines added since base."""
    out = git(["diff", "-U0", "--no-color", f"{base}...HEAD"], cwd).stdout
    pairs, path = [], None
    for line in out.splitlines():
        if line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else None
        elif line.startswith("+") and not line.startswith("+++") and path:
            pairs.append((path, line[1:]))
    return pairs


def merge_check(root, target, branch):
    """Dry-run merge with `git merge-tree --write-tree` (git >= 2.38). Returns (clean, conflicted_paths)."""
    p = git(["merge-tree", "--write-tree", "--name-only", "--no-messages", target, branch], root, check=False)
    if p.returncode == 0:
        return True, []
    if p.returncode == 1:
        lines = p.stdout.splitlines()
        return False, [x for x in lines[1:] if x.strip()]
    raise GitError(f"merge-tree failed: {p.stderr.strip()}")


def merge(root, branch, message):
    git(["merge", "--no-ff", "-m", message, branch], root)
    return head_sha(root)


def remove_worktree(root, path):
    git(["worktree", "remove", str(path)], root)
