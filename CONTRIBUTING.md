# Contributing

- Keep it dependency-free: Python ≥ 3.9 standard library only.
- Every behaviour change comes with a test in `tests/`. Run `python3 -m unittest discover -s tests -v`.
- New adapters must report usage only as the provider's CLI actually emits it. If a CLI doesn't report usage, record `usage_source="unknown"`; never invent numbers.
- Never add features that pool, rotate, or disguise accounts to get around provider limits.
