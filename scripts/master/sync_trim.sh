#!/usr/bin/env bash
# sync_trim.sh <render.mp4> <source.mp4> <out.mp4> [--loudnorm [LUFS]]
#
# Remotion renders can come out with the audio a few tens of ms late versus the source (measured
# around 40 ms on Apple Silicon; it varies by machine and version, so it is MEASURED here, never
# assumed). This cross-correlates the render's audio against the source it was cut from, trims
# the delay, keeps the video stream untouched (stream copy) and prints the sync of the result
# (target |offset| under 5 ms).
#
# --loudnorm [LUFS]   optional: normalize to LUFS (default -14, social platforms) with a
#                     -1.5 dBTP-ish limiter. Off by default; the voice level is your call.
set -euo pipefail
[ $# -ge 3 ] || { sed -n 2,13p "$0"; exit 1; }
V=$1; R=$2; O=$3; shift 3
LN=""; if [ "${1:-}" = "--loudnorm" ]; then LN=${2:--14}; fi
HERE=$(cd "$(dirname "$0")" && pwd)

off=$(python3 "$HERE/xcorr_offset.py" "$R" "$V" --verbose)
D=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$V")
AF="atrim=start=$off,asetpts=PTS-STARTPTS,apad=whole_dur=$D"
if python3 -c "import sys; sys.exit(0 if float('$off') < 0 else 1)"; then
  # audio early in the render: delay it instead of trimming
  AF="adelay=$(python3 -c "print(round(-1000*float('$off'),3))"):all=1,apad=whole_dur=$D"
fi
if [ -n "$LN" ]; then
  I=$(ffmpeg -hide_banner -nostats -i "$V" -af "$AF,loudnorm=print_format=json" -f null - 2>&1 | grep '"input_i"' | grep -oE '[-0-9.]+')
  G=$(python3 -c "print(round(($LN)-($I)+0.5,2))")
  AF="$AF,aresample=192000,volume=${G}dB,alimiter=limit=0.84:attack=1:release=60:level=false,aresample=48000"
  echo "loudness in: $I LUFS, gain $G dB, target $LN LUFS"
fi
ffmpeg -v error -y -i "$V" -map 0:v -map 0:a -c:v copy -af "$AF" -t "$D" -c:a aac -b:a 256k -movflags +faststart "$O"
echo "trimmed audio delay: $(python3 -c "print(round(1000*float('$off'),1))") ms"
[ -n "$LN" ] && ffmpeg -hide_banner -nostats -i "$O" -af loudnorm=print_format=summary -f null - 2>&1 | grep -E "Input Integrated|Input True Peak" || true
echo "final sync vs source (ms): $(python3 -c "print(round(1000*float('$(python3 "$HERE/xcorr_offset.py" "$R" "$O")'),1))")"
