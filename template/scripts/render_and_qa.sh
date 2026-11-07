#!/usr/bin/env bash
# render_and_qa.sh <project dir> [out name]: matte the plan's roto range, render, write QA sheets.
set -euo pipefail
P=$1; NAME=${2:-$(basename "$P")-v1}; cd "$P"
H=$(python3 -c "
import json; b=[e for e in json.load(open('remotion/plan.json'))['events'] if e['type']=='bigWord']; print(b[0]['at'] if b else -1)")
# every roto window gets its matte (RVM on the GPU, ~15-20 fps; --engine u2net is the old CPU
# path); frame numbers are absolute so they share one folder. --cuts resets RVM's recurrent
# state at each shot change.
# KEEP_MATTE=1 reuses an existing matte folder when the windows did not change (a plan
# tweak to sizes or a scene must not cost the matte again).
if [ "${KEEP_MATTE:-0}" = 1 ] && [ -d remotion/public/cut ]; then echo "matte kept ($(ls remotion/public/cut | wc -l | tr -d ' ') frames)"; else
rm -rf remotion/public/cut
CUTS=$([ -f remotion/public/cuts.json ] && echo "--cuts remotion/public/cuts.json" || true)
python3 -c "
import json; [print(e['from'], e['to']) for e in json.load(open('remotion/plan.json'))['events'] if e['type']=='roto']" | while read -r R0 R1; do
  ./.venv/bin/python scripts/matte_frames.py remotion/public/raw.mp4 --out remotion/public/cut --from-frame "$R0" --to-frame "$R1" --track remotion/public/track.json $CUTS | tail -1
done
fi
mkdir -p renders; ( cd remotion && npx remotion render src/index.ts Edit "../renders/$NAME.mp4" --codec=h264 2>&1 | grep -E "Encoded|Error" | tail -1 )
ffprobe -v error -select_streams v:0 -show_entries stream=nb_frames -show_entries format=duration -of csv=p=0 "renders/$NAME.mp4" | tr '\n' ' '; echo
mkdir -p qa_frames; rm -f qa_frames/*.png
ffmpeg -v error -y -i "renders/$NAME.mp4" -vf "fps=1,scale=150:-1" qa_frames/s_%03d.png; magick montage qa_frames/s_*.png -tile 17x -geometry +2+2 -background "#111" qa_frames/sweep-1fps.png 2>/dev/null || true
if [ "$H" -ge 0 ]; then ffmpeg -v error -y -ss "$(python3 -c "print(max(0,($H-15)/30))")" -t 3.2 -i "renders/$NAME.mp4" -vf "fps=5,scale=200:-1" qa_frames/h_%02d.png; magick montage qa_frames/h_*.png -tile 8x -geometry +2+2 -background "#111" qa_frames/hero.png 2>/dev/null || true; fi
echo "rendered renders/$NAME.mp4; look at qa_frames/sweep-1fps.png and qa_frames/hero.png before showing anyone"
