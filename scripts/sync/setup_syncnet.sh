#!/usr/bin/env bash
# Reproduce the syncnet_python install detect_sync.py depends on, from nothing.
# Idempotent: safe to re-run, only does the steps that are still missing.
#
#   setup_syncnet.sh
#
# Builds everything under a durable, non-scratch location:
#   ~/.local/share/talking-head-pipeline/syncnet/venv/           python 3.10 venv, never the system python
#   ~/.local/share/talking-head-pipeline/syncnet/syncnet_python/ joonson/syncnet_python checkout + weights
set -euo pipefail

DURABLE="$HOME/.local/share/talking-head-pipeline/syncnet"
VENV="$DURABLE/venv"
REPO="$DURABLE/syncnet_python"
REPO_URL="https://github.com/joonson/syncnet_python"
MIRROR="https://huggingface.co/lithiumice/syncnet/resolve/main"

MODEL_REL="data/syncnet_v2.model"
MODEL_SIZE=54573114
SFD_REL="detectors/s3fd/weights/sfd_face.pth"
SFD_SIZE=89844381

MIN_SPEED_BYTES=51200   # 50 KB/s -- below this for MIN_SPEED_SECS in a row, curl aborts and we fall back to ranged parallel fetch
MIN_SPEED_SECS=15
RANGE_CHUNKS=6

mkdir -p "$DURABLE"

# --- venv -------------------------------------------------------------
if [[ -x "$VENV/bin/python" ]] && "$VENV/bin/python" -c "
import sys
try:
    import torch, torchvision, torchaudio, cv2, scenedetect, python_speech_features, scipy, tqdm
except ImportError:
    sys.exit(1)
sys.exit(0 if torch.__version__.startswith('2.5.1') else 1)
" >/dev/null 2>&1; then
  echo "venv already set up at $VENV, skipping"
else
  echo "creating venv at $VENV"
  uv venv --python 3.10 "$VENV"
  uv pip install --python "$VENV/bin/python" torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1
  uv pip install --python "$VENV/bin/python" scenedetect==0.6.7.1 opencv-contrib-python==4.13.0.92 python_speech_features==0.6 tqdm scipy
fi

# --- repo checkout ------------------------------------------------------
if [[ -d "$REPO/.git" ]]; then
  echo "syncnet_python checkout already present at $REPO, skipping clone"
else
  echo "cloning $REPO_URL to $REPO"
  git clone --depth 1 "$REPO_URL" "$REPO"
fi
mkdir -p "$REPO/data" "$REPO/detectors/s3fd/weights"

# --- Apple GPU patches (idempotent) --------------------------------------
# S3FD face detection runs on MPS (4.9 -> 20 fps); SyncNet's lip model stays on CPU
# (MPS lacks max_pool3d_with_indices). The box decode/NMS step MUST run on CPU: on MPS
# it returns garbage boxes with correct confidences. Measured 2026-11-07.
"$VENV/bin/python" - "$REPO" <<'PYEOF'
import sys
from pathlib import Path
repo = Path(sys.argv[1])

def patch(rel, old, new):
    f = repo / rel
    text = f.read_text()
    if new in text:
        print(f"{rel}: GPU patch already applied")
    elif old in text:
        f.write_text(text.replace(old, new, 1))
        print(f"{rel}: GPU patch applied")
    else:
        sys.exit(f"{rel}: expected code not found, syncnet_python changed upstream; re-derive the patch")

patch("run_pipeline.py",
      "device = 'cuda' if torch.cuda.is_available() else 'cpu'\n  DET = S3FD",
      "device = 'cuda' if torch.cuda.is_available() else ('mps' if torch.backends.mps.is_available() else 'cpu')\n  DET = S3FD")
patch("detectors/s3fd/nets.py",
      """            loc.view(loc.size(0), -1, 4),
            self.softmax(conf.view(conf.size(0), -1, 2)),
            self.priors.type(type(x.data)).to(self.device)""",
      """            loc.view(loc.size(0), -1, 4).cpu(),
            self.softmax(conf.view(conf.size(0), -1, 2)).cpu(),
            self.priors.float().cpu()""")
PYEOF

# --- weight download helpers --------------------------------------------
file_size() { if [[ -f "$1" ]]; then wc -c < "$1" | tr -d ' '; else echo 0; fi; }

download_ranged() {
  # Parallel Range-request download, for when a single stream gets throttled.
  local url="$1" dest="$2" total="$3" chunks="$4"
  local tmpdir; tmpdir="$(mktemp -d)"
  local chunk_size=$(( (total + chunks - 1) / chunks ))
  local pids=()
  local i start end
  for (( i = 0; i < chunks; i++ )); do
    start=$(( i * chunk_size ))
    end=$(( start + chunk_size - 1 ))
    if (( end >= total )); then end=$(( total - 1 )); fi
    curl -fL --retry 3 --retry-delay 2 -H "Range: bytes=${start}-${end}" \
      -o "$tmpdir/part_$(printf '%03d' "$i")" "$url" &
    pids+=("$!")
  done
  local ok=0
  for pid in "${pids[@]}"; do
    wait "$pid" || ok=1
  done
  if [[ "$ok" -ne 0 ]]; then
    rm -rf "$tmpdir"
    return 1
  fi
  cat "$tmpdir"/part_* > "$dest"
  rm -rf "$tmpdir"
}

download_weight() {
  local rel="$1" expected_size="$2" budget_secs="$3"
  local dest="$REPO/$rel"
  local existing_size; existing_size="$(file_size "$dest")"
  if [[ "$existing_size" == "$expected_size" ]]; then
    echo "$rel already present ($expected_size bytes), skipping download"
    return 0
  fi

  echo "downloading $rel ($(( expected_size / 1024 / 1024 )) MB) from $MIRROR/$(basename "$rel"), budget ${budget_secs}s"
  local url="$MIRROR/$(basename "$rel")"
  local start_ts; start_ts=$(date +%s)

  # Attempt 1: single stream, aborts itself if it stalls below MIN_SPEED_BYTES/s.
  if curl -fL --retry 2 --retry-delay 2 \
      --speed-limit "$MIN_SPEED_BYTES" --speed-time "$MIN_SPEED_SECS" \
      --max-time "$budget_secs" \
      -o "$dest" "$url"; then
    if [[ "$(file_size "$dest")" == "$expected_size" ]]; then
      echo "$rel: single-stream download OK"
      return 0
    fi
    echo "$rel: single-stream download finished but size mismatch, retrying ranged"
  else
    echo "$rel: single-stream download stalled/failed, falling back to $RANGE_CHUNKS-way ranged fetch"
  fi

  local elapsed=$(( $(date +%s) - start_ts ))
  local remaining=$(( budget_secs - elapsed ))
  if (( remaining <= 0 )); then
    echo "$rel: no time left in the ${budget_secs}s budget"
    return 1
  fi

  # `timeout` is GNU coreutils (Linux; `brew install coreutils` on macOS provides gtimeout)
  local TO=(); if command -v timeout >/dev/null; then TO=(timeout "$remaining"); elif command -v gtimeout >/dev/null; then TO=(gtimeout "$remaining"); fi
  if ${TO[@]+"${TO[@]}"} bash -c "$(declare -f download_ranged); download_ranged '$url' '$dest' '$expected_size' '$RANGE_CHUNKS'"; then
    if [[ "$(file_size "$dest")" == "$expected_size" ]]; then
      echo "$rel: ranged download OK"
      return 0
    fi
  fi
  echo "$rel: ranged download failed or size mismatch within budget"
  return 1
}

WEIGHTS_OK=1
download_weight "$MODEL_REL" "$MODEL_SIZE" 450 || WEIGHTS_OK=0
download_weight "$SFD_REL" "$SFD_SIZE" 450 || WEIGHTS_OK=0

echo
echo "durable install: $DURABLE"
echo "  venv:            $VENV"
echo "  syncnet_python:  $REPO"
echo "  $MODEL_REL: $(file_size "$REPO/$MODEL_REL") / $MODEL_SIZE bytes"
echo "  $SFD_REL: $(file_size "$REPO/$SFD_REL") / $SFD_SIZE bytes"

if [[ "$WEIGHTS_OK" -ne 1 ]]; then
  echo
  echo "WARNING: one or both weight files did not finish downloading within budget."
  echo "Re-run this script to retry, or place the files by hand at the paths above."
  exit 1
fi

echo
echo "setup complete."
