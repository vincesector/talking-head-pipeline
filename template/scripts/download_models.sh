#!/usr/bin/env bash
# download_models.sh: fetch the MediaPipe face detector track_head.py needs (Apache-2.0, Google).
# Not shipped in the repo; this pulls it from Google's public model bucket into scripts/.
set -euo pipefail
cd "$(dirname "$0")"
URL=https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/latest/blaze_face_short_range.tflite
if [ -s blaze_face_short_range.tflite ]; then echo "face model already present"; exit 0; fi
curl -fL --retry 3 -o blaze_face_short_range.tflite "$URL"
echo "saved scripts/blaze_face_short_range.tflite ($(du -k blaze_face_short_range.tflite | cut -f1) KB)"
