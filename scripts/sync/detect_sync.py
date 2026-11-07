#!/usr/bin/env python3
"""Measure the audio/video sync offset of a talking-head recording from the
footage itself (lip motion vs speech), no clap test needed.

Wraps joonson/syncnet_python (S3FD face detection + SyncNet). Cuts N evenly
spaced 20s windows out of the video (skipping the first 2s), runs the
detector on each. Default is 2: the first window finds the
offset, the last one proves it did not drift by the end. OBS drift is linear,
so a middle window agreeing with both ends adds time, not information, and reports the offset in the same convention as
fix_sync.sh:

    negative offset: audio is LATE, advance it (trim its start)
    positive offset: audio is EARLY, delay it (pad its start)

This IS SyncNet's own "AV offset" number, unchanged -- see the derivation in
the module docstring below the imports. One unit = one 25fps frame = 40ms.

Requires the syncnet_python venv (not the system python), plus a checkout of
joonson/syncnet_python with its model weights. Both live in a durable,
non-scratch location:

    ~/.local/share/talking-head-pipeline/syncnet/venv/bin/python detect_sync.py <video> [--windows 2] [--json]

If that venv or checkout is missing (fresh machine, or the durable dir got
wiped), run setup_syncnet.sh in this directory to reproduce it from nothing:

    ./setup_syncnet.sh

It creates ~/.local/share/talking-head-pipeline/syncnet/, builds the venv with
`uv venv --python 3.10` plus the pinned packages below, clones
https://github.com/joonson/syncnet_python, and downloads its two weight
files (data/syncnet_v2.model, detectors/s3fd/weights/sfd_face.pth) from
huggingface.co/lithiumice/syncnet -- robots.ox.ac.uk (the upstream
download_model.sh source) was extremely slow when this was set up; the HF
mirror was much faster. Pinned packages, for reference:

    uv venv --python 3.10 <venv_dir>
    uv pip install --python <venv_dir>/bin/python torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1
    uv pip install --python <venv_dir>/bin/python scenedetect==0.6.7.1 opencv-contrib-python==4.13.0.92 python_speech_features==0.6 tqdm scipy

Sign convention derivation (SyncNetInstance.py):
  calc_pdist(feat1=video_feats, feat2=audio_feats, vshift) pads audio_feats
  by vshift on both ends and, for each video frame i, measures the distance
  to audio frames [i-vshift .. i+vshift]. mdist[k] is the mean distance at
  shift (k-vshift). minidx picks the best-matching shift. Then:

      offset = vshift - minidx                              (line ~143)

  Working through the index algebra: the best-matching shift shift* solves
  "audio[i+shift*] is the true partner of video[i]" and offset = -shift*, so
  "video[i] truly pairs with audio[i-offset]". A positive offset means the
  correct audio for frame i sits earlier in the track (audio arrived early,
  needs delaying); negative means it sits later (audio arrived late, needs
  advancing/trimming). That is exactly fix_sync.sh's convention, so no sign
  flip is applied here.

  Empirically re-confirmed by measuring a file and a copy of it with the
  first 130ms of audio trimmed (audio made earlier): the trimmed copy's
  offset came out consistently MORE positive than the original's, by close
  to 130ms. Advancing audio -> offset goes up -> positive means audio-early.
  Independent confirmation of the same sign, from the actual data.
"""
import argparse, json, os, re, shutil, subprocess, sys, tempfile

SYNCNET_HOME = os.path.expanduser("~/.local/share/talking-head-pipeline/syncnet")
SYNCNET_PY = os.path.join(SYNCNET_HOME, "venv", "bin", "python")
SYNCNET_REPO = os.path.join(SYNCNET_HOME, "syncnet_python")
SETUP_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "setup_syncnet.sh")

FPS = 25.0            # syncnet_python's internal working rate
MS_PER_FRAME = 1000.0 / FPS
MIN_CONFIDENCE = 3.0  # empirical floor; the SyncNet demo's own clean clip scores ~10

OFFSET_RE = re.compile(r"AV offset:\s*(-?\d+)")
CONF_RE = re.compile(r"Confidence:\s*([\d.]+)")


def ffprobe_duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                         "-of", "default=noprint_wrappers=1:nokey=1", path],
                        check=True, capture_output=True, text=True)
    return float(r.stdout.strip())


PROXY_LONG_SIDE = 1280     # 720p-class proxy windows
FACEDET_SCALE_FULL = 0.25  # syncnet_python's default face-detect scale, tuned for the source frame


# Hardware encoder on a Mac (about a second per window); software ultrafast everywhere else.
PROXY_ENCODER = (["-c:v", "h264_videotoolbox", "-b:v", "8M"] if sys.platform == "darwin"
                 else ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "23"])


def video_size(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                         "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", path],
                        check=True, capture_output=True, text=True)
    w, h = (int(x) for x in r.stdout.strip().split("x"))
    return w, h


def cut_windows(video, n, window_len=20.0, skip_start=2.0, outdir=None):
    dur = ffprobe_duration(video)
    span = dur - skip_start - window_len
    if span < 0:
        raise SystemExit(f"video too short ({dur:.1f}s) for a {window_len:.0f}s window "
                          f"after skipping the first {skip_start:.0f}s")
    step = span / (n - 1) if n > 1 else 0.0
    starts = [skip_start + i * step for i in range(n)]

    outdir = outdir or tempfile.mkdtemp(prefix="detect_sync_")
    # Windows are re-encoded as 720p proxies (hardware encoder, a second or two) instead
    # of stream-copied at full size: decoding and resizing 1440p frames dominated the run.
    # The face-detect scale rises by the same factor so the detector still sees the same
    # ~360p image.
    w, h = video_size(video)
    long_side = max(w, h)
    vf, facedet_scale = [], FACEDET_SCALE_FULL
    if long_side > PROXY_LONG_SIDE:
        vf = ["-vf", f"scale={PROXY_LONG_SIDE}:-2" if w >= h else f"scale=-2:{PROXY_LONG_SIDE}"]
        facedet_scale = round(FACEDET_SCALE_FULL * long_side / PROXY_LONG_SIDE, 4)
    clips = []
    for i, s in enumerate(starts):
        clip = os.path.join(outdir, f"win{i}_{s:.1f}.mp4")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{s:.3f}",
                         "-t", f"{window_len:.3f}", "-i", video, *vf,
                         *PROXY_ENCODER, "-c:a", "copy", clip],
                        check=True)
        clips.append((s, s + window_len, clip))
    return clips, outdir, facedet_scale


def run_syncnet_on_clip(clip, data_dir, reference, facedet_scale):
    # stage 1: face detect + track + crop (writes data_dir/pycrop/<reference>/*.avi)
    p1 = subprocess.run([SYNCNET_PY, "run_pipeline.py", "--videofile", clip,
                          "--reference", reference, "--data_dir", data_dir, "--overwrite",
                          "--facedet_scale", str(facedet_scale)],
                         cwd=SYNCNET_REPO, capture_output=True, text=True)
    if p1.returncode != 0:
        return None, p1.stdout + p1.stderr

    # stage 2: syncnet offset/confidence per face track, logged to stdout
    p2 = subprocess.run([SYNCNET_PY, "run_syncnet.py", "--videofile", clip,
                          "--reference", reference, "--data_dir", data_dir],
                         cwd=SYNCNET_REPO, capture_output=True, text=True)
    log = p1.stdout + p1.stderr + p2.stdout + p2.stderr
    if p2.returncode != 0:
        return None, log

    offsets = [int(x) for x in OFFSET_RE.findall(log)]
    confs = [float(x) for x in CONF_RE.findall(log)]
    if not offsets:
        return None, log  # no face track found (e.g. no face detected in this window)

    # multiple face tracks (scene cuts) can appear; keep the most confident one
    best = max(range(len(offsets)), key=lambda i: confs[i])
    return (offsets[best], confs[best], len(offsets)), log


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("video")
    ap.add_argument("--windows", type=int, default=2)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--window-len", type=float, default=20.0)
    ap.add_argument("--keep-tmp", action="store_true", help="do not delete the working dir (for debugging)")
    args = ap.parse_args()

    if not os.path.exists(SYNCNET_PY):
        sys.exit(f"syncnet venv python not found at {SYNCNET_PY} -- "
                  f"run {SETUP_SCRIPT} to set it up")
    if not os.path.isdir(SYNCNET_REPO):
        sys.exit(f"syncnet_python checkout not found at {SYNCNET_REPO} -- "
                  f"run {SETUP_SCRIPT} to set it up")

    clips, clipdir, facedet_scale = cut_windows(args.video, args.windows, window_len=args.window_len)
    data_dir = tempfile.mkdtemp(prefix="detect_sync_data_")

    results = []
    for i, (start, end, clip) in enumerate(clips):
        reference = f"w{i}"
        result, log = run_syncnet_on_clip(clip, data_dir, reference, facedet_scale)
        if result is None:
            print(f"window {i} [{start:.1f}-{end:.1f}s]: FAILED (no offset detected)", file=sys.stderr)
            print(log[-3000:], file=sys.stderr)
            continue
        offset_frames, confidence, n_tracks = result
        offset_ms = offset_frames * MS_PER_FRAME
        results.append({
            "window": i, "start": round(start, 1), "end": round(end, 1),
            "offset_frames": offset_frames, "offset_ms": round(offset_ms, 1),
            "confidence": round(confidence, 3), "n_face_tracks": n_tracks,
        })

    if not args.keep_tmp:
        shutil.rmtree(clipdir, ignore_errors=True)
        shutil.rmtree(data_dir, ignore_errors=True)

    if not results:
        sys.exit("no window produced a usable offset; nothing to report")

    offsets_ms = sorted(r["offset_ms"] for r in results)
    mid = len(offsets_ms) // 2
    median_ms = offsets_ms[mid] if len(offsets_ms) % 2 else (offsets_ms[mid - 1] + offsets_ms[mid]) / 2
    spread_ms = max(offsets_ms) - min(offsets_ms)
    min_conf = min(r["confidence"] for r in results)

    summary = {
        "video": args.video,
        "windows": results,
        "median_offset_ms": round(median_ms, 1),
        "median_offset_frames": round(median_ms / MS_PER_FRAME, 2),
        "spread_ms": round(spread_ms, 1),
        "min_confidence": min_conf,
        "convention": "negative=audio late/advance(trim); positive=audio early/delay(pad) -- matches fix_sync.sh",
    }

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"{'window':<8}{'start-end':<14}{'frames':<9}{'ms':<9}{'confidence':<12}")
        for r in results:
            print(f"{r['window']:<8}{r['start']:.1f}-{r['end']:.1f}{'':<4}"
                  f"{r['offset_frames']:<9}{r['offset_ms']:<9.1f}{r['confidence']:<12.3f}")
        print(f"\nmedian offset: {median_ms:+.1f} ms  ({median_ms / MS_PER_FRAME:+.2f} frames @ 25fps)")
        print(f"spread across windows: {spread_ms:.1f} ms")
        print(f"min confidence: {min_conf:.3f}")
        direction = "advance (trim) the audio" if median_ms < 0 else "delay (pad) the audio"
        print(f"fix_sync.sh offset: {median_ms/1000:+.3f}  -> {direction}")

    if spread_ms > MS_PER_FRAME + 1e-6:
        sys.exit(f"windows disagree by {spread_ms:.1f} ms, more than one 25fps frame ({MS_PER_FRAME:.0f} ms) -- "
                  f"not a stable measurement, do not trust the median")
    if min_conf < MIN_CONFIDENCE:
        sys.exit(f"lowest window confidence {min_conf:.2f} is below the {MIN_CONFIDENCE:.1f} floor -- "
                  f"detection is unreliable on this footage (bad lighting/angle/face size?)")


if __name__ == "__main__":
    main()
