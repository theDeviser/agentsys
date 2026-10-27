# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Profile routing rules: `agentsys route` and `dispatch --adapter auto` choose adapter/account from `.agentsys/profile.json`.
- Product [roadmap](docs/ROADMAP.md) documenting planned capabilities beyond connectors.
- Grok Build headless adapter (`--adapter grok`, provider `xai`).
- Activity dashboard filter keeps focus while the list updates (`#activity-list` split from toolbar).
- `CHANGELOG.md`, `site/changelog.html` (generated), and `scripts/build_changelog_site.py`.
- Scripted `agentsys demo` story in a temp repo (`AGENTSYS_DEMO=1` or `--force`).
- GitHub open-source launch assets: docs set, `site/` landing, CI workflows, maintainer scripts.

### Changed

- Dashboard and site use the Claude logo for Anthropic (replacing the generic Anthropic mark).
- Landing page redesigned around the dashboard screenshot, supported CLIs, and the verify → review → human merge flow.
- CI runs on Python 3.9 and 3.14 with a separate lint job; Dependabot groups action updates into one monthly PR.

### Fixed

- Sidebar agent drill-down no longer overwrites the free-text Activity filter with a harness label.
- CI, CodeQL, and Pages workflows pinned actions to commit SHAs that don't exist, so every job failed at setup.
- Changelog page rendered Markdown links as raw text.

## [0.1.0] - 2026-10-16

First public hardening release (coordination CLI, dashboard, trust model).

### Added

- Durable SQLite task store with leases, worktrees, and scoped implement tasks.
- Hash-chained audit log (`verify-log`), human-action provenance, optional approver signatures.
- Git hooks (`hooks install`), `check-branch`, and stdio MCP worker (`agentsys mcp`).
- Repo verification profiles, git-derived `resume` / `handoff`, per-account budgets and usage import.
- `agentsys doctor`, `agentsys metrics`, adversarial and e2e tests (51+ unit tests).
- Live dashboard (`agentsys ui`) with flow, runs, budget, and activity views.

[Unreleased]: https://github.com/theDeviser/agentsys/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/theDeviser/agentsys/releases/tag/v0.1.0
