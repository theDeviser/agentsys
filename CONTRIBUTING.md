# Contributing

- Keep it dependency-free: Python ≥ 3.9 standard library only.
- Every behaviour change comes with a test in `tests/`. Run `python3 -m unittest discover -s tests -v`.
- Regenerate docs when CLI changes: `python3 scripts/check_docs_drift.py --write`.
- Regenerate the site changelog: `python3 scripts/build_changelog_site.py`.
- New adapters must report usage only as the provider's CLI actually emits it. If a CLI doesn't report usage, record `usage_source="unknown"`; never invent numbers.
- Never add features that pool, rotate, or disguise accounts to get around provider limits.
