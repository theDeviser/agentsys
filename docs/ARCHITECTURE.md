# agentsys architecture (current)

One-page map of how the tool fits together as of the hardening baseline.

## Components

| Piece | Role |
|---|---|
| `agentsys/store.py` | SQLite schema, task state machine, append-only `events`, findings, checkpoints, runs (per project), approvals |
| `agentsys/ledger.py` | User-level `~/.agentsys/ledger.db`: budgets and run totals across all projects |
| `agentsys/cli.py` | All commands; dispatches to adapters; human-facing messages and `resume` brief |
| `agentsys/verify.py` | Verification gate: scope, syntax, secrets regex, task `--check` commands |
| `agentsys/budget.py` | Pre-run cap checks, estimates, alerts |
| `agentsys/adapters.py` | Headless runs: mock, cursor-agent, claude, codex, grok, opencode |
| `agentsys/gitops.py` | Worktrees, merge-check, merge |
| `agentsys/ui.py` + `ui.html` | Local dashboard; read state; optional writes via POST `/api/action` |

## State machine

Tasks move through guarded transitions (`TRANSITIONS` in `store.py`). Every transition runs in a transaction and appends an event. Terminal states: `merged`, `cancelled`. Dependencies must be `accepted` or `merged` before claim.

Typical implement path: `ready` → `in_progress` (claim + lease) → `submitted` → `verified` (gate) → `accepted` (review) → `merged` (human approval + git merge).

## Stores

- **Project store:** `<repo>/.agent-system/state.db` (gitignored). Tasks, events, findings, checkpoints, runs for that repo.
- **Ledger:** `AGENTSYS_LEDGER` or `~/.agentsys/ledger.db`. Budget rows and imported runs; shared caps apply no matter which project dispatches.

On `Store` open, project runs/budgets are imported into the ledger idempotently.

## Identity model (today)

Actors are self-declared strings: `harness:account:role` (e.g. `codex:alice:work`, `human:vedansh`). The store enforces:

- Review: `authors(tid)` (claim/checkpoint/submit) cannot review.
- Approvals/merge: only `human:` actors in `decide_approval`.

There is no cryptographic binding to a vendor login yet (Phase 1 adds tamper-evident logs and human-action refusals).

## Adapters

`agentsys dispatch` builds a prompt (including `AGENT_RULES`), checks budget, claims or continues work, runs the vendor CLI in the task worktree, records usage, writes output as a finding, checkpoints/submits or releases on failure.

## Verification gate

`agentsys verify` runs `verify.run_pipeline`: allowed paths, syntax helpers, secret patterns (type only in reports), custom checks, and for research tasks at least one evidenced finding.

## Dashboard

Stdlib `ThreadingHTTPServer` on 127.0.0.1. Polls `/api/state` and `/api/task`. Writable mode requires per-page session token + matching Host/Origin.
