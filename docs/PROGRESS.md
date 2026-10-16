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

## Phase 2 — git hooks, check-branch, MCP

- `agentsys hooks install|uninstall|merge-check|push-check`; `check-branch` with human `--override-reason`.
- `agentsys/mcp.py` stdio JSON-RPC (`initialize`, `tools/list`, `tools/call`); worker tools only.
- `docs/ci-example.yml`, `docs/integrations.md` (vendor snippets marked *unverified*).
- Tests: `tests/test_hooks_mcp.py`. Suite: **39 passed** on 3.9.6.

## Phase 3 — verification profiles

- `.agentsys/profile.json`, `profile detect` / `profile save`, gate runs profile in worktree (process-group kill on timeout).
- `verified (no tests)` in CLI verify output and dashboard `state_label`.
- Tests: `tests/test_profile.py`. Suite: **43 passed** on 3.9.6.

## Phase 4 — handoff

- Git-derived sections in `resume` / `brief`; `handoff --to`; tests in `tests/test_handoff.py`.

## Phase 5 — budgets / usage

- Conservative `estimate()` (max of last 5, p80 with ≥10 runs); cap labels in `budget.summary`.
- `usage import` from synthetic fixtures; dedupe via `imported_usage` table (no prompt text).
- Tests: `tests/test_usage.py`.

## Phase 6 — adapters / doctor

- `agentsys doctor` table (`agentsys/doctor.py`).

## Phase 7 — packaging / onboarding

- README positioning rewrite; issue template; `tests/test_help.py`; `agentsys demo --force`.

## Phase 8 — dashboard QA

- `docs/MANUAL_QA.md` (automated dashboard checks remain in `test_agentsys`).

## Phase 9 — release readiness

- `tests/test_e2e.py`, `tests/test_adversarial.py`, `agentsys metrics`, `docs/REVIEW_REPORT.md`.
- Suite: **51 passed** on 3.9.6; spot OK on 3.11 and 3.12.

## Open stop-and-ask

- **Phase 7:** System Python setuptools 58 still blocks `pip install .` without a newer venv; source-tree CLI + `scripts/test.sh` are verified instead.
