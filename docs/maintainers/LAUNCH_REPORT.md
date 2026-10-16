# Launch report (agentsys → theDeviser/agentsys)

Date: 2026-10-16 · Actor: `agent:cursor:worker`

## Phase A — Preflight

| Check | Result |
|-------|--------|
| Unit tests | 53+ passed (`python3 -m unittest discover -s tests`) |
| Remote `git ls-remote` | Empty (safe to push `main`) |
| Secrets scan (regex) | Matches only in `verify.py` patterns / docs — no live tokens in tree |
| `git log --format=%ae` | `connect.vedansh@gmail.com` — **owner:** consider noreply email for future commits |
| PyPI name `agentsys` | Not claimed in this run (offline check skipped) |
| Inventory | `mcp`, `doctor`, `hooks`, `verify-log`, `THREAT_MODEL.md`, `demo` (scripted), dashboard UI |

### Known gaps (honest)

- `pip install .` on system Python 3.9 may fail if setuptools &lt; 61 — use venv or `pip install -U setuptools`.
- Adapter contract / full adversarial suite partially documented in `docs/PROGRESS.md`.
- Taste skill (`Leonxlnx/taste-skill`) not installed; site reuses dashboard tokens manually.

## CI / Pages (2026-10-16 follow-up)

- **CI failure cause:** `ruff check` on the full tree (import order, unused imports, E731). Fixed in `62f22d9` — ruff config + small cleanups; `ruff check` and 54 tests pass locally.
- **Site 404 cause:** GitHub Pages is not serving yet until **Settings → Pages → Source: GitHub Actions** is selected and the **`pages`** workflow completes. While the repo is **private**, only users with repo access can open the Pages URL (and org policy may block Pages until you go public).
- **Local verify:** `./scripts/preview_site.sh` → http://127.0.0.1:8766/agentsys/

## Phase G — DevTools QA

- Dashboard Activity filter: multi-char edit + poll while focused — OK (`.qa/dashboard-filter-fix/activity-filter.png`).
- Console: no errors on localhost dashboard during spot check.

## Phase H–J — Owner checklist

- [ ] Set GitHub repo description, topics, social preview image
- [ ] Replace `TODO(owner)` in `CODE_OF_CONDUCT.md`
- [ ] Enable Discussions + vulnerability reporting (`scripts/github_setup.sh`)
- [ ] Fresh-clone install test from GitHub
- [ ] Run Lighthouse on live Pages after first deploy
- [ ] Seed issues from `docs/maintainers/seed-issues.md` (draft only)

## Installed tools used

- Python 3.9.6 unittest, Chrome DevTools MCP (dashboard QA)
