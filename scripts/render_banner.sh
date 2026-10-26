#!/usr/bin/env bash
# Render site/banner.html to the README banner and GitHub social preview.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
OUT="$ROOT/assets"
mkdir -p "$OUT"
"$CHROME" --headless=new --disable-gpu --hide-scrollbars --window-size=1280,640 \
  --virtual-time-budget=4000 --screenshot="$OUT/banner.png" "file://$ROOT/site/banner.html" 2>/dev/null
cp "$OUT/banner.png" "$OUT/social-preview.png"
echo "Wrote $OUT/banner.png and social-preview.png"
