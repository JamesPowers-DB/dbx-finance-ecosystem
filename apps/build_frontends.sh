#!/usr/bin/env bash
# Build the React frontends for all Databricks Apps.
# Run before `databricks bundle deploy` so frontend/dist/ exists on disk
# and gets synced to the workspace.
#
# Usage:
#   ./apps/build_frontends.sh           # build all apps
#   ./apps/build_frontends.sh helios    # build only helios-sourcing-portal

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
APPS=("helios-sourcing-portal")

# If an argument is provided, filter to matching app names
if [ $# -gt 0 ]; then
  FILTER="$1"
  FILTERED=()
  for app in "${APPS[@]}"; do
    if [[ "$app" == *"$FILTER"* ]]; then
      FILTERED+=("$app")
    fi
  done
  APPS=("${FILTERED[@]}")
fi

if [ "${#APPS[@]}" -eq 0 ]; then
  echo "No matching apps found for filter: $1" >&2
  exit 1
fi

for app in "${APPS[@]}"; do
  echo "=== Building $app ==="
  FRONTEND_DIR="$HERE/$app/frontend"
  if [ ! -d "$FRONTEND_DIR" ]; then
    echo "  SKIP: $FRONTEND_DIR not found"
    continue
  fi
  cd "$FRONTEND_DIR"
  npm install --silent
  npm run build
  if [ ! -f "dist/index.html" ]; then
    echo "FAIL: $app/frontend/dist/index.html not produced" >&2
    exit 1
  fi
  echo "  ✓ dist/ ready ($(du -sh dist | cut -f1))"
done

echo ""
echo "All frontends built. Run: databricks bundle deploy -t dev"
