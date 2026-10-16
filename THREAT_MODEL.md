# agentsys threat model (local-first demo / team tool)

agentsys coordinates AI coding agents on one machine (or one trusted host). It is **not** a multi-tenant SaaS. Assumptions and limits below are intentional.

## Assets

- **Task store** (`.agent-system/state.db`): tasks, findings, approvals, append-only events.
- **Install key** (`~/.agentsys/install.key`): HMAC key for the event hash chain (mode `0600`).
- **Optional approver verifier** (`~/.agentsys/approver.json`): scrypt hash of a passphrase; signatures on human approvals when enabled.
- **Shared usage ledger** (`AGENTSYS_LEDGER` or default path): token budgets across projects.
- **Git worktrees and branches**: real code changes until merge.

## Trust boundaries

| Actor | Trust level |
|-------|-------------|
| Human at keyboard + TTY, or human on dashboard with session token | Can approve, deny, merge (with confirmations), cancel, requeue |
| Agent CLI / MCP (`harness:account:role` or `agent:harness:role`) | Can claim, work, submit, review **if** a different identity than authors |
| Dispatched child process (`AGENTSYS_DISPATCHED=1`) | **Cannot** perform `human:*` actions |
| Anyone with shell + write access to the store file | Can bypass all software rules (see below) |

## Controls (software)

1. **Hash-chained events** — Tampering with `prev_hash` / `event_hash` or meta `chain_prev_hash` is detected by `agentsys verify-log`. Pre-migration rows are `legacy` and anchored.
2. **Human provenance** — Human actions record TTY/dashboard/dispatch state; refused when dispatched or without TTY/token (except dashboard token path).
3. **TTY confirmation** — Sensitive CLI actions read **yes** from `/dev/tty`, not piped stdin.
4. **Reviewer independence** — Store rejects review by task authors; dashboard/API flag `same_account_review` when reviewer shares an account segment with a worker.
5. **Scope / verify gate** — Implement tasks must pass automated checks before review (extended in later phases with project test profiles).
6. **Git hooks** (when installed) — `pre-merge-commit` / `pre-push` + `check-branch` reduce accidental merges; **fast-forward merges do not run `pre-merge-commit`** — use `merge.ff=false` or rely on `pre-push` + CI.

## Out of scope / honest limits

- **Same-user shell is root.** A user who can run `sqlite3` on the store or export `AGENTSYS_ACTOR=human:…` with a real TTY can impersonate a human. The chain detects **after-the-fact** edits, not motivated same-user fraud.
- **Self-declared identities** — `AGENTSYS_ACTOR` is asserted, not cryptographically bound to vendor accounts (adapters report usage where possible).
- **Network** — Dashboard binds to localhost by default; Host/Origin/token reduce rebinding and drive-by POSTs, not a stolen laptop session.
- **Secrets in findings** — Scanners reduce accidental commits; agents can still paste secrets into the DB if the human does not run verify-log and review.

## MCP and agents

The stdlib MCP server exposes **worker** tools only (claim, heartbeat, finding, checkpoint, submit, resume, status). No approve, merge, or review-over-HTTP.

## Reporting incidents

1. Run `agentsys verify-log --strict` on a copy of the store.
2. Inspect events for unexpected `human:*` actors and `same_account_review` in the dashboard snapshot.
3. Rotate approver passphrase (`agentsys approver init`) if passphrase may be compromised.
