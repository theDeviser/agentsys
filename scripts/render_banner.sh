#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
BANNER="$ROOT/site/banner.html"
OUT="$ROOT/assets"
mkdir -p "$OUT"
file_url="file://$BANNER"
for mode in light dark; do
  if [[ "$mode" == "dark" ]]; then
    extra="--force-dark-mode"
    out="$OUT/banner-dark.png"
  else
    extra=""
    out="$OUT/banner-light.png"
  fi
  "$CHROME" --headless=new --disable-gpu --window-size=1280,640 $extra \
    --screenshot="$out" "$file_url" 2>/dev/null
done
cp "$OUT/banner-light.png" "$OUT/social-preview.png"
echo "Wrote $OUT/banner-light.png, banner-dark.png, social-preview.png"
