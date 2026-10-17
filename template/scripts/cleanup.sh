#!/usr/bin/env bash
# Delete the disposable intermediates once the creator has confirmed the video is done.
#
# NEVER run this without asking first. The PNG matte sequence is the bulk of
# the project size and regenerating it costs ~12 minutes per minute of footage.
#
# Usage: ./scripts/cleanup.sh [--dry-run]
set -euo pipefail

cd "$(dirname "$0")/.."
DRY=${1:-}

targets=(
  "remotion/public/cut"        # RGBA matte PNG sequence, the big one
  "remotion/public/frames"     # any extracted frame dumps
  "renders/qa"                 # QA contact sheets
  "renders/draft.mp4"          # low-res proof render
  ".venv"                      # python env, recreate in seconds
  "remotion/node_modules"      # recreate with npm install
)

total=0
for t in "${targets[@]}"; do
  if [ -e "$t" ]; then
    size=$(du -sk "$t" | cut -f1)
    total=$((total + size))
    printf "%-30s %6s MB\n" "$t" "$((size / 1024))"
  fi
done

printf "\n%-30s %6s MB\n" "TOTAL RECLAIMABLE" "$((total / 1024))"

if [ "$DRY" = "--dry-run" ]; then
  echo "dry run, nothing deleted"
  exit 0
fi

for t in "${targets[@]}"; do
  [ -e "$t" ] && rm -rf "$t"
done

echo "deleted. kept: plan.json, source, track.json, captions.json, final render"
