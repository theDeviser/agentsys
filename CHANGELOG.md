# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Activity dashboard filter keeps focus while the list updates (`#activity-list` split from toolbar).
- `CHANGELOG.md`, `site/changelog.html` (generated), and `scripts/build_changelog_site.py`.
- Scripted `agentsys demo` story in a temp repo (`AGENTSYS_DEMO=1` or `--force`).
- GitHub open-source launch assets: docs set, `site/` landing, CI workflows, maintainer scripts.

### Fixed

- Sidebar agent drill-down no longer overwrites the free-text Activity filter with a harness label.

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
