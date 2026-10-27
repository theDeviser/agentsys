# agentsys roadmap

Curated capabilities beyond vendor connectors. Status: **planned** (not started), **in progress** (issue or PR open), **shipped** (on `main`).

Orchestration features below use optional keys in [`.agentsys/profile.json`](../agentsys/profile.py) (`routing`, `review`, `templates`).

## Highest value

| Item | Why | Effort | Risk | Status |
|------|-----|--------|------|--------|
| Create and edit tasks in the dashboard | Start work without the CLI | Low | Low | planned |
| Dispatch from the UI (adapter/account picker, budget preview, confirm) | Most-requested control surface | Medium | Spends real quota | planned |
| Notifications (desktop, Slack) for approvals and escalations | Reduces time waiting on humans | Low | Low | planned |
| Spend in dollars (user-maintained price table) | Token caps mislead when cost varies by model | Medium | Prices drift | planned |
| Per-model limits and allow-lists per account | Prevent expensive model surprises | Medium | Medium | planned |

## Orchestration

| Item | Why | Effort | Risk | Status | Tracking |
|------|-----|--------|------|--------|----------|
| Routing rules (`--adapter auto`, `agentsys route`) | Use several subscriptions efficiently within each account's caps | Medium | Must not bypass caps | shipped | [#9](https://github.com/theDeviser/agentsys/issues/9), PR [#15](https://github.com/theDeviser/agentsys/pull/15) |
| Review assignment (`review.pairs`, `agentsys reviewer`) | Independent review by harness, not luck | Low | Low | shipped | [#10](https://github.com/theDeviser/agentsys/issues/10), PR [#16](https://github.com/theDeviser/agentsys/pull/16) |
| Task templates and pipelines (`agentsys pipeline`) | Encode research → implement chains | Medium | Low | shipped | [#11](https://github.com/theDeviser/agentsys/issues/11), PR [#17](https://github.com/theDeviser/agentsys/pull/17) |
| Scheduler / watch mode (`agentsys watch`) | Optional background dispatch when rules exist | Medium | Spends quota if misconfigured | shipped | [#12](https://github.com/theDeviser/agentsys/issues/12), PR [#18](https://github.com/theDeviser/agentsys/pull/18) |

## Trust and verification

| Item | Why | Effort | Risk | Status |
|------|-----|--------|------|--------|
| Deeper verification (auto-detect test/lint from repo) | Stronger gate without manual `--check` every time | Medium | False positives | planned |
| Signed identities (bind actors to CLI login or local key) | Fixes self-declared actor trust gap | High | High | planned |
| Adapter health checks (`adapters --check`, doctor) | Vendor JSON breaks without notice | Low | Live check spends tokens | shipped ([#13](https://github.com/theDeviser/agentsys/issues/13), PR [#19](https://github.com/theDeviser/agentsys/pull/19)) |

## Analytics

| Item | Why | Effort | Risk | Status |
|------|-----|--------|------|--------|
| Agent scorecards (pass rate, tokens per accepted task) | Compare vendors on real outcomes | Medium | Low | planned |
| Import IDE session usage (extend `usage_import`) | Dashboard under-reports interactive chat | Medium | Format churn | planned |
| Exportable audit reports (per task or sprint) | Compliance and postmortems | Low | Low | planned |

## Reach

| Item | Why | Effort | Risk | Status |
|------|-----|--------|------|--------|
| PyPI release and Homebrew formula | Easier install than git clone | Low | Packaging maintenance | planned |
| GitHub integration (PR from accepted task, check comments) | Fits existing git workflow | High | API scope | planned |
| Team mode (shared store over git or small server) | Multi-person coordination | High | Product shape change | planned |
| Demo video / GIF on landing page | Faster comprehension | Low | Low | planned |

## Connectors (headless adapters)

| Item | Status | Tracking |
|------|--------|----------|
| Grok Build (`grok`) | shipped | `main` |
| Gemini CLI + Antigravity (MCP) coordination | planned | [#6](https://github.com/theDeviser/agentsys/issues/6) |
| OpenCode (`opencode run`) | planned | [#7](https://github.com/theDeviser/agentsys/issues/7) |

## Document maintenance

| Item | Status | Tracking |
|------|--------|----------|
| This roadmap | shipped | [#8](https://github.com/theDeviser/agentsys/issues/8), PR [#14](https://github.com/theDeviser/agentsys/pull/14) |

See also [PRODUCT_BRIEF.md](PRODUCT_BRIEF.md) §7–8 for limitations and owner questions that informed this list.
