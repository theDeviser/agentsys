#!/usr/bin/env bash
# Preview landing page with the same /agentsys/ URL prefix as GitHub Pages.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PREVIEW="$ROOT/.qa/site-preview"
rm -rf "$PREVIEW"
mkdir -p "$PREVIEW/agentsys"
rsync -a "$ROOT/site/" "$PREVIEW/agentsys/"
python3 scripts/build_changelog_site.py
python3 scripts/build_docs_site.py
rsync -a "$ROOT/site/" "$PREVIEW/agentsys/"
PORT="${1:-8766}"
echo "Preview: http://127.0.0.1:${PORT}/agentsys/"
cd "$PREVIEW" && exec python3 -m http.server "$PORT"
