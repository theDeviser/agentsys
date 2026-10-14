"""Verification pipeline. A task is never 'verified' because an agent said so — only because these pass."""
from __future__ import annotations

import json
import py_compile
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import gitops
from .store import path_allowed

SECRET_PATTERNS = [
    ("aws-access-key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("openai-style-key", re.compile(r"\bsk-(?:proj-|ant-)?[A-Za-z0-9_\-]{20,}")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}")),
    ("slack-token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}")),
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("assigned-secret", re.compile(
        r"(?i)\b(api[_-]?key|secret|access[_-]?token|auth[_-]?token|password|passwd)\b[\"']?\s*[:=]\s*[\"'][^\"'\s]{8,}[\"']")),
]
FORBIDDEN_FILES = re.compile(r"(^|/)(\.env(\..*)?|.*\.pem|.*\.key|id_rsa.*|.*\.p12|credentials\.json)$")
ALLOW_MARKER = "agentsys:allow-secret"


def _result(name, ok, detail, status=None):
    return {"check": name, "status": status or ("pass" if ok else "fail"), "detail": detail}


def check_scope(changed, allowed):
    bad = [f for f in changed if not path_allowed(f, allowed)]
    if not changed:
        return _result("scope", False, "no changes relative to base")
    return _result("scope", not bad, f"out of scope: {bad}" if bad else f"{len(changed)} file(s) within {allowed}")


def check_syntax(worktree: Path, changed):
    bun = shutil.which("bun")
    problems, checked, skipped = [], 0, []
    with tempfile.TemporaryDirectory() as out:
        for rel in changed:
            f = worktree / rel
            if not f.is_file():
                continue  # deleted
            ext = f.suffix.lower()
            try:
                if ext in (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"):
                    if not bun:
                        skipped.append(rel)
                        continue
                    p = subprocess.run([bun, "build", str(f), "--no-bundle"], stdout=subprocess.DEVNULL,
                                       stderr=subprocess.PIPE, text=True, timeout=60)
                    if p.returncode != 0:
                        problems.append(f"{rel}: {p.stderr.strip()[:300]}")
                elif ext == ".py":
                    py_compile.compile(str(f), cfile=str(Path(out) / "x.pyc"), doraise=True)
                elif ext == ".json":
                    json.loads(f.read_text(encoding="utf-8"))
                else:
                    continue
                checked += 1
            except (py_compile.PyCompileError, json.JSONDecodeError, UnicodeDecodeError) as e:
                problems.append(f"{rel}: {str(e)[:300]}")
    if problems:
        return _result("syntax", False, "; ".join(problems))
    if skipped and not checked:
        return _result("syntax", True, f"bun not found; skipped {skipped}", status="skipped")
    return _result("syntax", True, f"{checked} file(s) parsed" + (f"; skipped {skipped}" if skipped else ""))


def check_secrets(worktree: Path, base, changed):
    hits = [f"{f}: forbidden file type" for f in changed if FORBIDDEN_FILES.search(f)]
    for path, line in gitops.added_lines(worktree, base):
        if ALLOW_MARKER in line:
            continue
        for name, rx in SECRET_PATTERNS:
            if rx.search(line):
                hits.append(f"{path}: {name}")  # never echo the matched value
                break
    return _result("secrets", not hits, "; ".join(hits) if hits else "no secret-shaped strings in added lines")


def check_commands(worktree: Path, commands, timeout=600):
    out = []
    for cmd in commands:
        try:
            p = subprocess.run(cmd, shell=True, cwd=str(worktree), capture_output=True, text=True, timeout=timeout)
            tail = (p.stdout + p.stderr).strip()[-400:]
            out.append(_result(f"cmd: {cmd}", p.returncode == 0, f"exit {p.returncode}: {tail}"))
        except subprocess.TimeoutExpired:
            out.append(_result(f"cmd: {cmd}", False, f"timed out after {timeout}s"))
    return out


def run_pipeline(task, findings) -> list:
    if task["kind"] == "research":
        evidenced = [f for f in findings if f["kind"] in ("finding", "artifact", "output") and f["evidence"]]
        return [_result("evidence", bool(evidenced),
                         f"{len(evidenced)} finding(s) with evidence" if evidenced else
                         "research tasks need at least one finding with --evidence")]
    wt = Path(task["worktree"] or "")
    if not task["worktree"] or not wt.exists():
        return [_result("worktree", False, "task has no worktree")]
    if not gitops.is_clean(wt):
        return [_result("clean-tree", False, "uncommitted changes in worktree; checkpoint --commit first")]
    changed = gitops.changed_files(wt, task["base"])
    results = [check_scope(changed, task["allowed_paths"]), check_syntax(wt, changed),
               check_secrets(wt, task["base"], changed)]
    results += check_commands(wt, task["checks"])
    return results


def passed(results) -> bool:
    return all(r["status"] in ("pass", "skipped") for r in results)
