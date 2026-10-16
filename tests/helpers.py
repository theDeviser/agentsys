"""Isolated temp HOME, ledger, and git project for agentsys tests."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CLI = [os.environ.get("PYTHON", "python3"), str(REPO / "bin" / "agentsys")]


def sh(args, cwd: Path):
    return subprocess.run(args, cwd=str(cwd), capture_output=True, text=True)


def init_git_project(parent: Path) -> Path:
    root = parent / "proj"
    root.mkdir()
    for c in (["init", "-q", "-b", "main"], ["config", "user.email", "t@example.com"], ["config", "user.name", "Test"]):
        sh(["git", *c], root)
    (root / "app").mkdir()
    (root / "app" / "ui.jsx").write_text("export const A = () => <div>hi</div>;\n")
    (root / ".gitignore").write_text(".agent-system/\n")
    sh(["git", "add", "-A"], root)
    sh(["git", "commit", "-q", "-m", "init"], root)
    return root


class IsolatedEnv:
    """Temp directory with its own HOME and AGENTSYS_LEDGER."""

    def __init__(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="agentsys-iso-"))
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.ledger = self.tmp / "ledger.db"
        self.root = init_git_project(self.tmp)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("AGENTSYS_")}
        self.env["HOME"] = str(self.home)
        self.env["AGENTSYS_LEDGER"] = str(self.ledger)
        self.env["AGENTSYS_TEST_SUITE"] = "1"
        self.env["AGENTSYS_SKIP_TTY_CONFIRM"] = "1"
        self._old_home = os.environ.get("HOME")
        self._old_ledger = os.environ.get("AGENTSYS_LEDGER")

    def __enter__(self):
        os.environ["HOME"] = str(self.home)
        os.environ["AGENTSYS_LEDGER"] = str(self.ledger)
        return self

    def __exit__(self, *a):
        if self._old_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = self._old_home
        if self._old_ledger is None:
            os.environ.pop("AGENTSYS_LEDGER", None)
        else:
            os.environ["AGENTSYS_LEDGER"] = self._old_ledger
        shutil.rmtree(self.tmp, ignore_errors=True)

    def cli(self, *args, actor=None, ok=True, cwd=None):
        e = dict(self.env)
        if actor:
            e["AGENTSYS_ACTOR"] = actor
        p = subprocess.run(CLI + list(args), cwd=str(cwd or self.root), capture_output=True, text=True, env=e)
        if ok and p.returncode != 0:
            raise AssertionError(f"agentsys {' '.join(args)} failed ({p.returncode}): {p.stderr}{p.stdout}")
        return p

    def store_path(self) -> Path:
        return self.root / ".agent-system" / "state.db"
