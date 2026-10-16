# Hardening progress

Agent identity for this work: `agent:cursor:worker`. Plan: `cursor_agent_prompt.md`.

## Phase 0 — baseline

- **2026-10-16:** Baseline tests: 24 passed on `/usr/bin/python3` 3.9.6 (~15s).
- Added `docs/ARCHITECTURE.md`, this file, `.github/workflows/test.yml`, `scripts/test.sh`, `tests/helpers.py`.
- **Discrepancies logged:** `agent:cursor:worker` harness alias needed in UI (Phase 1); setuptools 58 on system Python vs pyproject `>=61` (Phase 7); `pre-merge-commit` vs FF merges (Phase 2 THREAT_MODEL).

## Open stop-and-ask

(none yet)
