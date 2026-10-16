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
