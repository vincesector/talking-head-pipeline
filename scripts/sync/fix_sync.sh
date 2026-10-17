#!/usr/bin/env bash
# Shift the audio of an already-recorded file relative to its video. Video is
# stream-copied (no quality loss), only the audio is re-encoded.
#
#   fix_sync.sh in.mp4 <offset_seconds> [out.mp4]
#
#   negative offset: the audio was LATE, so advance it by trimming its start.
#   positive offset: the audio was EARLY, so delay it by padding its start.
#                    A wireless mic into a screen recorder measured +0.240 (audio early) with
#                    detect_sync.py. Measure every file; the value drifts between sessions.
#
# Sanity check afterwards by watching a hard consonant or a clap in the output.
set -euo pipefail
in="${1:?input file}"; off="${2:?offset in seconds, e.g. -0.130}"; out="${3:-${in%.*}.synced.${in##*.}}"
if [[ "$off" == -* ]]; then
  trim="${off#-}"
  ffmpeg -v error -y -i "$in" -c:v copy -af "atrim=start=${trim},asetpts=PTS-STARTPTS" -c:a aac -b:a 192k "$out"
else
  ms=$(python3 -c "print(int(round(float('$off')*1000)))")
  ffmpeg -v error -y -i "$in" -c:v copy -af "adelay=${ms}|${ms}" -c:a aac -b:a 192k "$out"
fi
echo "wrote $out (audio shifted by ${off}s)"
