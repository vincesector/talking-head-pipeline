#!/usr/bin/env bash
# prep_vertical.sh <autocut workdir> <project dir>
# Turns autocut's 16:9 clean.mp4 into this project's vertical source and inputs:
#   track the 16:9 cut, crop 9:16 around the median head x, detect cuts, track the
#   vertical file, caption words from the verbatim pass (numerals as digits).
# After this: write plan.json (see plan_common.py), then render_and_qa.sh.
set -euo pipefail
W=$1; P=$2; PY="$P/.venv/bin/python"; THP_HOME=${THP_HOME:-$(cat "$HOME/.config/talking-head-pipeline/root" 2>/dev/null || true)}
[ -n "$THP_HOME" ] || { echo "THP_HOME is not set (run install.sh in the repo, or export THP_HOME=<repo root>)"; exit 1; }
AUTOCUT="$THP_HOME/scripts/autocut"; cd "$P"
[ -f "$W/clean.mp4" ] || { echo "no clean.mp4 in $W (run autocut --render first)"; exit 1; }
"$PY" scripts/track_head.py "$W/clean.mp4" --out "$W/track16.json" | tail -1
"$PY" scripts/crop_vertical.py "$W/clean.mp4" --track "$W/track16.json" -o remotion/public/raw.mp4
"$PY" scripts/detect_cuts.py remotion/public/raw.mp4 --out remotion/public/cuts.json | tail -1
"$PY" scripts/track_head.py remotion/public/raw.mp4 --out remotion/public/track.json --cuts remotion/public/cuts.json | tail -1
if [ -f "$W/verbatim.json" ]; then python3 "$AUTOCUT/verbatim_cut_words.py" "$W" -o remotion/public/words.json; else cp "$W/captions.json" remotion/public/words.json; echo "no verbatim pass in $W, caption words come from mlx-whisper (proofread them, Whisper smooths repeats and mangles names)"; fi
python3 -c "
import json; t=json.load(open('remotion/public/track.json')); c=json.load(open('remotion/public/cuts.json'))
print('vertical source ready | detectionRate', t['detectionRate'], '| cuts:', c.get('cuts'))"
