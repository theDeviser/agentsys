#!/usr/bin/env python3
"""Validate MCP install snippet targets in site/js/install.js."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "site" / "js" / "install.js"

REQUIRED_KEYS = ("cursor", "vscode", "claude", "codex")


def main() -> int:
    if not JS.is_file():
        print(f"missing {JS}", file=sys.stderr)
        return 1
    text = JS.read_text(encoding="utf-8")
    m = re.search(r"export const INSTALL_TARGETS\s*=\s*(\{[\s\S]*?\});", text)
    if not m:
        print("INSTALL_TARGETS not found", file=sys.stderr)
        return 1
    data = json.loads(m.group(1))
    for k in REQUIRED_KEYS:
        if k not in data:
            print(f"missing install target: {k}", file=sys.stderr)
            return 1
        low = data[k].lower()
        if not any(x in low for x in ("mcp", "agentsys", "codex", "cursor", "anthropic", "vscode")):
            print(f"suspicious target for {k}", file=sys.stderr)
            return 1
    print("install.js OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
