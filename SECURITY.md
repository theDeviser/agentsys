# Security model

## Scope

agentsys coordinates agents that run **as the same local user**. It provides guardrails against agent mistakes. It is **not** an isolation boundary against a malicious local process.

| Property | Status |
|---|---|
| Actor identity | Self-declared (`--as`). Not authenticated. |
| Store | Local SQLite file, mode `0600`; any process running as your user can write to it. |
| Worktrees | Separate files, not a sandbox. Agents can still reach paths outside them. |
| Real sandboxing | Delegated to each harness: `codex --sandbox`, `cursor-agent --sandbox enabled`, Claude Code `--allowedTools` / `--permission-mode`. |

## Defaults

- Child processes get no provider API-key variables (see `adapters.API_KEY_VARS`).
- `codex` runs `read-only` for research and `workspace-write` for implementation, with network off (the Codex default).
- `cursor-agent` uses `--force` only for implementation tasks, and always with `--sandbox enabled`.
- Prompts go to `claude` and `codex` over stdin. `cursor-agent` only accepts the prompt as an argument, so it is visible in `ps` to the same user; never put secrets in task text.
- The verification secret scan reports matches by type and never prints the matched value.
- Merges need a granted approval from a `human:` actor and refuse to run on a dirty main tree.

## Reporting

Open a private security advisory on the repository, or contact the maintainer directly. Please don't file public issues for vulnerabilities.
