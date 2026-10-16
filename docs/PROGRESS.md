# Hardening progress

Agent identity for this work: `agent:cursor:worker`. Plan: `cursor_agent_prompt.md`.

## Phase 0 — baseline

- **2026-10-16:** Baseline tests: 24 passed on `/usr/bin/python3` 3.9.6 (~15s).
- Added `docs/ARCHITECTURE.md`, this file, `.github/workflows/test.yml`, `scripts/test.sh`, `tests/helpers.py`.
- **Discrepancies logged:** `agent:cursor:worker` harness alias needed in UI (Phase 1); setuptools 58 on system Python vs pyproject `>=61` (Phase 7); `pre-merge-commit` vs FF merges (Phase 2 THREAT_MODEL).

## Phase 1 — trust model

- Hash-chained events (`prev_hash`, `event_hash`, `chain_status`), legacy migration + anchor in `meta`.
- `agentsys/trust.py`: HMAC chain, provenance, `/dev/tty` confirm, optional approver scrypt signatures.
- `verify-log`, `approver init`; human guards on CLI + dashboard actions; `AGENTSYS_DISPATCHED` in adapter children.
- UI: `agent:<harness>:<role>` harness alias; `flows()` sets `same_account_review` on snapshot API.
- Tests: `tests/test_trust.py` (9 cases). Suite: **33 passed** on Python 3.9.6.
- **Test-only:** `AGENTSYS_TEST_SUITE=1` bypasses TTY for human provenance in unit tests (not for production use).
- **Still weak:** approval signatures not verified in `verify-log` without passphrase; same-user shell can still impersonate `human:*` with a TTY.

## Open stop-and-ask

(none yet)
