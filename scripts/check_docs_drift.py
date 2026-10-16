#!/usr/bin/env python3
"""Regenerate docs/cli-reference.md from `agentsys --help` and fail on drift."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "cli-reference.md"
CLI = [sys.executable, str(ROOT / "bin" / "agentsys"), "--help"]


def capture() -> str:
    p = subprocess.run(CLI, capture_output=True, text=True, cwd=ROOT)
    if p.returncode != 0:
        raise SystemExit(p.stderr)
    body = p.stdout.rstrip() + "\n"
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
