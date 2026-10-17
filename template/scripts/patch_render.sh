#!/usr/bin/env bash
# Re-render only a range of frames and splice it into an existing render
# WITHOUT re-encoding the untouched part.
#
# A full render of a 17-minute talking head is ~25 minutes and a software
# re-encode of the splice is ~3 minutes; a fix inside the first minute needs
# seconds of new frames. So: render the patch range widened to the nearest
# keyframes of the base render, then join it to the base's head and tail by
# stream copy. Only the audio is re-encoded (seconds for a 17-minute file).
#
#   scripts/patch_render.sh --base renders/prev.mp4 --replace 0-1049 \
#       --render 0-887 --out renders/next.mp4 [extra remotion flags]
#
#   --replace A-B  frames of BASE to throw away (inclusive, base timeline)
#   --render  C-D  frames of the CURRENT plan to render in their place
#                  (inclusive, new timeline). Lengths may differ: that is how a
#                  source re-cut (frames removed) is absorbed.
#
# The patch and the base must come from the same Remotion setup (same codec
# settings), which is always the case inside one project.
# Run from the project root (the folder that holds remotion/ and renders/).
#
# Junction details, measured 2026-09-09 (B-frames make naive cuts wrong):
#   head  = base packets 0..K0-1 by packet COUNT (-frames:v); a time-based cut
#           drags in two packets of the next GOP;
#   tail  = the base itself with `inpoint K1/fps` in the concat list, which
#           shifts timestamps exactly; an extracted tail file starts two frames
#           late and leaves a 67 ms hole at the join;
#   each part carries an explicit `duration`, otherwise the AAC padding in the
#           mp4 header pushes the next part 50 ms late;
#   audio is rebuilt from the base and the patch with exact trims.
set -euo pipefail

BASE=""; REPLACE=""; RENDER=""; OUT=""
EXTRA=()
while [ $# -gt 0 ]; do
  case "$1" in
    --base) BASE=$2; shift 2;;
    --replace) REPLACE=$2; shift 2;;
    --render) RENDER=$2; shift 2;;
    --out) OUT=$2; shift 2;;
    *) EXTRA+=("$1"); shift;;
  esac
done
[ -n "$BASE" ] && [ -n "$REPLACE" ] && [ -n "$RENDER" ] && [ -n "$OUT" ] || {
  sed -n 2,22p "$0"; exit 1; }
BASE=$(cd "$(dirname "$BASE")" && pwd)/$(basename "$BASE")

NPX=${NPX:-npx}
A=${REPLACE%-*}; B=${REPLACE#*-}; C=${RENDER%-*}; D=${RENDER#*-}
FPS=$(python3 -c "import json; print(json.load(open('remotion/plan.json'))['fps'])")
secs() { python3 -c "print('%.6f' % ($1/$FPS))"; }
# nb_frames comes from the mp4 index: exact for files written by Remotion or ffmpeg,
# and instant. -count_frames would decode the whole file (a minute per 17-minute video).
count_frames() { ffprobe -v error -select_streams v:0 -show_entries stream=nb_frames -of csv=p=0 "$1" | tr -d -c 0-9; }
BASE_FRAMES=$(count_frames "$BASE")

# Keyframes of the base, as frame indices (packets only, no decode).
KEYS=$(ffprobe -v error -select_streams v:0 -show_entries packet=pts_time,flags -of csv=p=0 "$BASE" \
  | awk -F, -v fps="$FPS" '$2 ~ /K/ {printf "%d\n", $1*fps+0.5}' | sort -n)
# K0: last keyframe <= A (head is copied up to it); K1: first keyframe > B (tail copied from it).
K0=$(echo "$KEYS" | awk -v a="$A" '$1<=a {k=$1} END {print k+0}')
K1=$(echo "$KEYS" | awk -v b="$B" '$1>b {print $1; exit}')
[ -n "$K1" ] || K1=$BASE_FRAMES
# Widen the render range by the same amounts so the patch meets the copies exactly.
RC=$(( C - (A - K0) )); RD=$(( D + (K1 - 1 - B) )); PATCH_N=$(( RD - RC + 1 ))
echo "base keyframes: head copy $([ "$K0" -gt 0 ] && echo "0-$((K0-1))" || echo none), tail copy $([ "$K1" -lt "$BASE_FRAMES" ] && echo "$K1-$((BASE_FRAMES-1))" || echo none); rendering $RC-$RD (asked $C-$D)"

WORK=$(mktemp -d -t patch)
( cd remotion && "$NPX" remotion render src/index.ts Edit "$WORK/patch.mp4" --frames="$RC-$RD" --codec=h264 ${EXTRA[@]+"${EXTRA[@]}"} 2>&1 | grep -E 'Encoded|Error' | tail -1 )
[ "$(count_frames "$WORK/patch.mp4")" -eq "$PATCH_N" ] || { echo "patch has $(count_frames "$WORK/patch.mp4") frames, expected $PATCH_N"; exit 2; }

# Stream copy only works between files with identical encoder parameters. A base
# that came out of an ffmpeg splice (limited-range yuv420p, 1/15360 timebase) breaks
# the junction timestamps against a Remotion patch (full-range yuvj420p, 1/90000).
sig() { ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,profile,pix_fmt,has_b_frames,time_base,r_frame_rate,width,height -of csv=p=0 "$1"; }
if [ "$(sig "$BASE")" != "$(sig "$WORK/patch.mp4")" ]; then
  echo "base and patch have different encoder parameters:"; echo "  base:  $(sig "$BASE")"; echo "  patch: $(sig "$WORK/patch.mp4")"
  echo "The base must be a Remotion render of this project (or an earlier patch_render output). Do one full render, then patch that."
  rm -rf "$WORK"; exit 3
fi

LIST="$WORK/list.txt"; : > "$LIST"
AUD=""; ALIST=""; AN=0
if [ "$K0" -gt 0 ]; then
  ffmpeg -v error -y -i "$BASE" -frames:v "$K0" -c copy -avoid_negative_ts disabled "$WORK/head.mp4"
  [ "$(count_frames "$WORK/head.mp4")" -eq "$K0" ] || { echo "head copy is $(count_frames "$WORK/head.mp4") frames, expected $K0"; exit 2; }
  printf "file '%s'\nduration %s\n" "$WORK/head.mp4" "$(secs "$K0")" >> "$LIST"
  AUD+="[1:a]atrim=0:$(secs "$K0"),asetpts=PTS-STARTPTS[a$AN];"; ALIST+="[a$AN]"; AN=$((AN+1))
fi
printf "file '%s'\nduration %s\n" "$WORK/patch.mp4" "$(secs "$PATCH_N")" >> "$LIST"
AUD+="[2:a]atrim=0:$(secs "$PATCH_N"),asetpts=PTS-STARTPTS[a$AN];"; ALIST+="[a$AN]"; AN=$((AN+1))
if [ "$K1" -lt "$BASE_FRAMES" ]; then
  printf "file '%s'\ninpoint %s\n" "$BASE" "$(secs "$K1")" >> "$LIST"
  AUD+="[1:a]atrim=start=$(secs "$K1"),asetpts=PTS-STARTPTS[a$AN];"; ALIST+="[a$AN]"; AN=$((AN+1))
fi

ffmpeg -v error -y -f concat -safe 0 -i "$LIST" -i "$BASE" -i "$WORK/patch.mp4" \
  -filter_complex "${AUD}${ALIST}concat=n=$AN:v=0:a=1[a]" \
  -map 0:v -c:v copy -map "[a]" -c:a aac -b:a 192k -movflags +faststart "$OUT"
rm -rf "$WORK"

EXPECT=$(( A + (D - C + 1) + (BASE_FRAMES - B - 1) ))
GOT=$(count_frames "$OUT")
GAPS=$(ffprobe -v error -select_streams v:0 -show_entries packet=pts_time -of csv=p=0 "$OUT" | sort -n \
  | awk -v fps="$FPS" 'NR>1 {d=$1-prev; if (d > 1.05/fps || d < 0.95/fps) g++} {prev=$1} END {print g+0}')
echo "$OUT: $GOT frames (expected $EXPECT), timestamp gaps: $GAPS"
[ "$GOT" -eq "$EXPECT" ] && [ "$GAPS" -eq 0 ] || { echo "SPLICE CHECK FAILED"; exit 2; }
