# Release readiness review (local)

- **Tests:** `python -m unittest discover -s tests -v` on Python 3.9+ (stdlib only).
- **Trust:** `agentsys verify-log` after E2E; human actions blocked when `AGENTSYS_DISPATCHED=1`.
- **Gaps:** Vendor MCP config snippets unverified; setuptools 58 on macOS system Python blocks `pip install .` without newer venv.
- **Coverage:** not collected in CI (no coverage.py dependency by design).
