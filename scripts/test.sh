#!/usr/bin/env sh
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-python3}"
exec "$PY" -m unittest discover -s tests -v "$@"
