"""Repo verification profiles (.agentsys/profile.json)."""
from __future__ import annotations

import json
import os
import signal
import hashlib
import subprocess
import time
from pathlib import Path

def _result(name, ok, detail, status=None):
    return {"check": name, "status": status or ("pass" if ok else "fail"), "detail": detail}

PROFILE_PATH = ".agentsys/profile.json"
OUTPUT_TAIL = 40


def profile_path(root: Path) -> Path:
    return root / PROFILE_PATH


def load(root: Path) -> dict | None:
    p = profile_path(root)
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def section(root: Path, key: str) -> dict:
    """Return a profile subsection (empty dict if missing or not a mapping)."""
    data = load(root)
    if not data or not isinstance(data.get(key), dict):
        return {}
    return data[key]


def save(root: Path, data: dict) -> Path:
    p = profile_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return p


def detect(root: Path) -> dict:
    """Propose commands from repo markers (no network)."""
    cmds = []
    pkg = root / "package.json"
    if pkg.is_file():
        data = json.loads(pkg.read_text(encoding="utf-8"))
        scripts = data.get("scripts") or {}
        for name in ("test", "lint", "typecheck", "check"):
            if name in scripts:
                cmds.append({"name": f"npm:{name}", "command": f"npm run {name}", "cwd": ".", "timeout": 600, "blocking": True})
    if (root / "pyproject.toml").is_file() or (root / "pytest.ini").is_file() or list(root.glob("**/test_*.py")):
        cmds.append({"name": "pytest", "command": "python3 -m pytest -q", "cwd": ".", "timeout": 600, "blocking": True})
    if (root / "go.mod").is_file():
        cmds.append({"name": "go-test", "command": "go test ./...", "cwd": ".", "timeout": 600, "blocking": True})
    if (root / "Cargo.toml").is_file():
        cmds.append({"name": "cargo-test", "command": "cargo test", "cwd": ".", "timeout": 600, "blocking": True})
    mk = root / "Makefile"
    if mk.is_file() and re_search(mk.read_text(encoding="utf-8", errors="ignore"), r"^test:"):
        cmds.append({"name": "make-test", "command": "make test", "cwd": ".", "timeout": 600, "blocking": True})
    return {"version": 1, "commands": cmds}


def re_search(text: str, pattern: str) -> bool:
    import re
    return re.search(pattern, text, re.M) is not None


def scan_output(text: str) -> list[str]:
    from .verify import ALLOW_MARKER, SECRET_PATTERNS
    hits = []
    for line in text.splitlines():
        if ALLOW_MARKER in line:
            continue
        for name, rx in SECRET_PATTERNS:
            if rx.search(line):
                hits.append(name)
                break
    return hits


def run_profile(worktree: Path, profile: dict | None) -> tuple[list, bool]:
    """Run profile commands; return (results, no_tests_label)."""
    if not profile or not profile.get("commands"):
        return [], True
    results = []
    for spec in profile["commands"]:
        name = spec.get("name") or spec.get("command", "cmd")
        cmd = spec["command"]
        cwd = worktree / (spec.get("cwd") or ".")
        timeout = int(spec.get("timeout") or 600)
        blocking = bool(spec.get("blocking", True))
        t0 = time.time()
        try:
            p = subprocess.Popen(
                cmd, shell=True, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, start_new_session=True,
            )
            try:
                out, _ = p.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGKILL)
                p.wait()
                results.append(_result(f"profile:{name}", False, f"timed out after {timeout}s (process tree killed)"))
                if blocking:
                    return results, False
                continue
            dur = time.time() - t0
            out = out or ""
            digest = hashlib.sha256(out.encode()).hexdigest()[:16]
            secret_hits = scan_output(out)
            ok = p.returncode == 0 and not secret_hits
            detail = f"exit {p.returncode}, {dur:.1f}s, sha256:{digest}"
            if secret_hits:
                detail += f"; secret types in output: {', '.join(secret_hits)}"
            results.append(_result(f"profile:{name}", ok, detail, status="pass" if ok else "fail"))
            if blocking and not ok:
                return results, False
        except OSError as e:
            results.append(_result(f"profile:{name}", False, str(e)))
            if blocking:
                return results, False
    return results, False
