#!/usr/bin/env bash
# Idempotent GitHub repo settings (requires `gh` auth).
set -euo pipefail
REPO="${GITHUB_REPOSITORY:-theDeviser/agentsys}"
DRY="${1:-}"

run() {
  if [[ "$DRY" == "--dry-run" ]]; then
    echo "DRY: $*"
  else
    "$@"
  fi
}

run gh repo edit "$REPO" \
  --description "Local-first coordination for AI coding agents — gates, reviews, audit log" \
  --add-topic agents --add-topic mcp --add-topic cursor --add-topic devtools

run gh api -X PATCH "repos/$REPO" -f has_discussions=true 2>/dev/null || true
run gh api -X PUT "repos/$REPO/pages" -f build_type=workflow 2>/dev/null || true

echo "Done. Verify Pages, Discussions, and vulnerability reporting in the GitHub UI."
