"""Self-contained scripted demo in a temp git repo (<30s). Used by `agentsys demo`."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CLI = [sys.executable, str(REPO / "bin" / "agentsys")]


def _sh(args, cwd: Path):
    return subprocess.run(args, cwd=str(cwd), capture_output=True, text=True)


def _init_project(parent: Path) -> Path:
    root = parent / "proj"
    root.mkdir()
    for c in (["init", "-q", "-b", "main"], ["config", "user.email", "demo@agentsys.local"],
              ["config", "user.name", "agentsys demo"]):
        _sh(["git", *c], root)
    (root / "app").mkdir()
    (root / "app" / "ui.jsx").write_text("export const A = () => <div>hi</div>;\n", encoding="utf-8")
    (root / ".gitignore").write_text(".agent-system/\n", encoding="utf-8")
    _sh(["git", "add", "-A"], root)
    _sh(["git", "commit", "-q", "-m", "init"], root)
    return root


def _cli(root: Path, env: dict, *args, actor=None, ok=True):
    e = dict(env)
    if actor:
        e["AGENTSYS_ACTOR"] = actor
    p = subprocess.run(CLI + list(args), cwd=str(root), capture_output=True, text=True, env=e)
    if ok and p.returncode != 0:
        raise RuntimeError(f"agentsys {' '.join(args)} failed ({p.returncode}): {p.stderr}{p.stdout}")
    return p


def run_demo_story(step=print) -> None:
    """Run the onboarding story; raises on failure. Temp dir removed on exit."""
    t0 = time.time()
    tmp = Path(tempfile.mkdtemp(prefix="agentsys-demo-"))
    home = tmp / "home"
    home.mkdir()
    ledger = tmp / "ledger.db"
    root = _init_project(tmp)
    env = {k: v for k, v in os.environ.items() if not k.startswith("AGENTSYS_")}
    env["HOME"] = str(home)
    env["AGENTSYS_LEDGER"] = str(ledger)
    env["AGENTSYS_DEMO"] = "1"
    env["AGENTSYS_SKIP_TTY_CONFIRM"] = "1"
    try:
        step("1/10 init store")
        _cli(root, env, "init", actor="human:demo")

        step("2/10 add implement task (gate will fail once, then pass)")
        tid = _cli(root, env, "task", "add", "Add greeting", "--path", "app/*", "--goal", "greet users",
                   "--check", "test -f app/greeting.txt", actor="human:demo").stdout.strip()

        step("3/10 worker claims and edits worktree (no greeting file yet)")
        out = _cli(root, env, "claim", tid, actor="mock:local:work").stdout
        wt = Path(out.split("work in: ")[1].strip())
        (wt / "app" / "ui.jsx").write_text("export const A = () => <div>hello</div>;\n", encoding="utf-8")
        _cli(root, env, "submit", tid, "ui only", actor="mock:local:work")

        step("4/10 verify fails — missing app/greeting.txt")
        vf = _cli(root, env, "verify", tid, actor="system:verifier", ok=False)
        if vf.returncode == 0:
            raise RuntimeError("expected verify to fail")
        step("   gate failure recorded (fix next)")

        step("5/10 fix: add greeting file and resubmit")
        _cli(root, env, "claim", tid, actor="mock:local:work")
        (wt / "app" / "greeting.txt").write_text("hello\n", encoding="utf-8")
        _cli(root, env, "submit", tid, "greeting added", actor="mock:local:work")
        _cli(root, env, "verify", tid, actor="system:verifier")

        step("6/10 independent reviewer approves (different harness)")
        bad = _cli(root, env, "review", tid, "approve", "--reason", "nope", actor="mock:local:work", ok=False)
        if bad.returncode == 0:
            raise RuntimeError("author review should be refused")
        _cli(root, env, "review", tid, "approve", "--reason", "diff matches goal", actor="claude:peer:reviewer")

        step("7/10 agent tries to merge as human — refused")
        mf = _cli(root, env, "merge", tid, actor="claude:peer:reviewer", ok=False)
        if mf.returncode not in (1, 4):
            raise RuntimeError(f"expected merge refusal, got {mf.returncode}")

        step("8/10 human grants merge approval (demo-only TTY bypass via AGENTSYS_DEMO)")
        _cli(root, env, "approve", "1", actor="human:demo")

        step("9/10 merge-check then merge")
        _cli(root, env, "merge-check", tid, actor="system:verifier")
        _cli(root, env, "merge", tid, "--cleanup", actor="human:demo")
        if "hello" not in (root / "app" / "ui.jsx").read_text(encoding="utf-8"):
            raise RuntimeError("merge did not land changes")

        step("10/10 verify-log chain OK")
        _cli(root, env, "verify-log", actor="system:verifier")

        elapsed = time.time() - t0
        step(f"done in {elapsed:.1f}s — temp repo discarded")
        if elapsed > 30:
            raise RuntimeError(f"demo exceeded 30s ({elapsed:.1f}s)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
