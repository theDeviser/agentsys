"""Read-only import of vendor usage logs from synthetic fixtures (no prompt text stored)."""
from __future__ import annotations

import json
from pathlib import Path

from .ledger import Ledger


def parse_claude_lines(lines: list[str]) -> list[dict]:
    out = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        rid = row.get("id") or row.get("message_id")
        if not rid:
            continue
        out.append({
            "id": f"claude:{rid}",
            "provider": "anthropic",
            "tokens": int(row.get("input_tokens", 0) or 0) + int(row.get("output_tokens", 0) or 0),
            "model": row.get("model"),
            "ts": float(row.get("timestamp", 0) or 0),
        })
    return out


def parse_codex_lines(lines: list[str]) -> list[dict]:
    out = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("type") != "turn.completed":
            continue
        usage = row.get("usage") or {}
        rid = row.get("id") or row.get("session_id")
        if not rid:
            continue
        out.append({
            "id": f"codex:{rid}",
            "provider": "openai",
            "tokens": int(usage.get("input_tokens", 0) or 0) + int(usage.get("output_tokens", 0) or 0),
            "model": row.get("model"),
            "ts": float(row.get("ts", 0) or 0),
        })
    return out


def import_file(path: Path, vendor: str, ledger: Ledger) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    malformed = 0
    for line in lines:
        if line.strip() and not line.strip().startswith("{") and vendor != "cursor":
            malformed += 1
    if vendor == "cursor":
        return {"imported": 0, "skipped": len(lines), "malformed": 0, "note": "Cursor local usage logs not supported"}
    parser = parse_claude_lines if vendor == "claude" else parse_codex_lines
    rows = parser(lines)
    imported = 0
    for row in rows:
        if ledger.import_usage_row(row):
            imported += 1
    return {"imported": imported, "skipped": len(rows) - imported, "malformed": malformed}
