# Integrating agentsys with coding agents

Identity is always `harness:account:role` (or `agent:harness:role` for automation). The MCP server and CLI read identity from startup args / `AGENTSYS_ACTOR`, not from tool payloads.

## MCP (stdio)

Run from the git project root (or pass `--db`):

```bash
export AGENTSYS_ACTOR=cursor:alice:implementer
agentsys mcp
```

Exposed tools: `claim`, `heartbeat`, `finding`, `checkpoint`, `submit`, `resume`, `status`, `list_tasks`. There is no approve, merge, or human review tool.

### Cursor — *unverified*

Cursor’s MCP client configuration format changes between releases. Point a custom MCP server at the command above if your build supports arbitrary stdio servers. We have not re-verified the exact `mcp.json` schema against current Cursor docs in this repo.

### Claude Code — *unverified*

Claude Code documents project-level MCP servers under user settings; use the same `agentsys mcp` command with `AGENTSYS_ACTOR=claude:you:work`. Confirm paths in Anthropic’s latest Claude Code documentation before relying on this in production.

### Codex CLI — *unverified*

OpenAI’s Codex CLI MCP wiring should mirror any stdio MCP server entry. Set `AGENTSYS_ACTOR=codex:you:work`. Treat config file names and flags as vendor-controlled.

### Grok Build — *unverified*

Install the [Grok Build CLI](https://docs.x.ai/docs/grok-build) (`curl -fsSL https://x.ai/cli/install.sh | bash`), run `grok login`, then use the same stdio MCP entry with `AGENTSYS_ACTOR=grok:you:work`. Headless dispatch uses `agentsys dispatch <task> --adapter grok --account you`.

## Routing rules (optional)

Add `routing.rules` to [`.agentsys/profile.json`](../agentsys/profile.py) (commit this file in your repo). Each rule matches a task `kind` (`research`, `implement`, or `*`) and lists `prefer` candidates in order. Routing checks that the CLI is installed, a budget exists, `check_dispatch` passes, and optional `max_pct` is not exceeded (uses the rolling window percent when set).

```bash
agentsys route t-abc12345          # print adapter, account, reason (no spend)
agentsys dispatch t-abc12345 --adapter auto --account ignored
```

Routing never bypasses per-account caps.

## Review assignment (optional)

Set `review.pairs` in `.agentsys/profile.json` to map author harness → reviewer harness (`"*"` is the fallback). When `require_different_harness` is true (default), reviewers must use a different harness than anyone who claimed or submitted the task.

```bash
agentsys reviewer t-abc12345
```

## Git hooks

```bash
export AGENTSYS_ACTOR=human:you
agentsys hooks install
```

Hooks call `agentsys hooks merge-check` and `agentsys hooks push-check`. Fast-forward merges do not run `pre-merge-commit`; prefer `git config merge.ff false` or rely on `pre-push` plus CI `check-branch`.

Human override (recorded in the event log):

```bash
agentsys check-branch agent/t-abc12345 --override-reason "hotfix" --as human:you
```

## Environment

| Variable | Purpose |
|----------|---------|
| `AGENTSYS_ACTOR` | Default identity |
| `AGENTSYS_DB` | Store path |
| `AGENTSYS_LEDGER` | Shared usage ledger |
| `AGENTSYS_CLI` | Path used by git hooks (tests set this) |
| `AGENTSYS_DISPATCHED` | Set in adapter children; blocks forged human actions |
