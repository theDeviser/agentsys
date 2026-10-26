#!/usr/bin/env python3
"""Regenerate docs/cli-reference.md from `agentsys --help` and fail on drift."""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "cli-reference.md"
CLI = [sys.executable, str(ROOT / "bin" / "agentsys"), "--help"]


def normalize(text: str) -> str:
    """Erase argparse formatting differences between Python 3.9 and 3.10+."""
    text = text.replace("optional arguments:", "options:")
    return re.sub(r"\}\n\s+\.\.\.\n", "} ...\n", text)


def capture() -> str:
    env = {**os.environ, "COLUMNS": "100", "NO_COLOR": "1"}
    p = subprocess.run(CLI, capture_output=True, text=True, cwd=ROOT, env=env)
    if p.returncode != 0:
        raise SystemExit(p.stderr)
    body = normalize(p.stdout.rstrip() + "\n")
    return (
        "# CLI reference\n\n"
        "Generated from `agentsys --help`. Do not edit by hand; run "
        "`python3 scripts/check_docs_drift.py --write`.\n\n"
        "```text\n"
        f"{body}"
        "```\n"
    )


def main() -> int:
    write = "--write" in sys.argv
    fresh = capture()
    if OUT.exists():
        current = OUT.read_text(encoding="utf-8")
        if current == fresh:
            print("docs/cli-reference.md OK")
            return 0
        if not write:
            print("docs/cli-reference.md drift; run check_docs_drift.py --write", file=sys.stderr)
            return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(fresh, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
