#!/usr/bin/env python3
"""Per-frame head tracking -> JSON for Remotion.

Emits normalized (0-1) anchor points so the JSON survives any render resolution.

Two things here are not obvious.

**Selection is not "biggest box".** A busy set produces false face detections on
background clutter (shelves, posters, reflections) and some are larger than the
real face, so picking by size locks onto the furniture. Instead: score each
detection by confidence, penalise distance from where the face was last frame,
and reject anything that is not a plausible continuation.

**Everything temporal is clipped to shot boundaries.** Multi-angle footage
breaks the continuity prior and the moving average at once: across a cut the
face legitimately teleports, so the prior fights the correct detection and the
average glides between two framings. Measured on a 4-location edit, that left
the anchor up to 0.110 of frame height wrong (211px at 1080p) for 5 frames after
every cut. Pass --cuts from detect_cuts.py and it resets instead.
"""
import argparse
import json
import math
from pathlib import Path

import cv2
import mediapipe as mp
from mediapipe.tasks.python import vision
from mediapipe.tasks.python.core.base_options import BaseOptions

# Below this, a detection is background clutter more often than a face.
MIN_CONFIDENCE = 0.55
# A face cannot cross more than this fraction of the frame in one frame.
MAX_JUMP = 0.09
# How hard to punish distance from the previous position when scoring.
CONTINUITY_WEIGHT = 3.0


def pick(detections, width, height, previous):
    best, best_score = None, -1e9
    for det in detections:
        box = det.bounding_box
        confidence = det.categories[0].score if det.categories else 0.0
        if confidence < MIN_CONFIDENCE:
            continue
        cx = (box.origin_x + box.width / 2) / width
        cy = (box.origin_y + box.height / 2) / height

        score = confidence
        if previous is not None:
            dist = math.hypot(cx - previous[0], cy - previous[1])
            if dist > MAX_JUMP:
                score -= 1.0
            score -= dist * CONTINUITY_WEIGHT

        if score > best_score:
            best_score, best = score, (cx, cy, box, confidence)
    return best


def detect(video_path: Path, model_path: Path, cuts=()):
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    detector = vision.FaceDetector.create_from_options(
        vision.FaceDetectorOptions(
            base_options=BaseOptions(model_asset_path=str(model_path)),
            running_mode=vision.RunningMode.VIDEO,
            min_detection_confidence=0.3,
        )
    )

    raw = []
    previous = None
    cutset = {int(c) for c in cuts}
    index = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if index in cutset:
            # New shot. The face may legitimately be anywhere now, so forget
            # where it was or the continuity term drags the pick backwards.
            previous = None

        image = mp.Image(
            image_format=mp.ImageFormat.SRGB,
            data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB),
        )
        result = detector.detect_for_video(image, int(index / fps * 1000))
        chosen = pick(result.detections or [], width, height, previous)

        if chosen is None:
            raw.append({"frame": index, "cx": None, "cy": None, "top": None,
                        "w": None, "h": None, "conf": 0.0})
        else:
            cx, cy, box, confidence = chosen
            previous = (cx, cy)
            raw.append({
                "frame": index, "cx": cx, "cy": cy,
                "top": box.origin_y / height,
                "w": box.width / width,
                "h": box.height / height,
                "conf": confidence,
            })
        index += 1

    cap.release()
    return raw, fps, width, height


def shots(n, cuts):
    """Frame ranges between boundaries. Temporal ops must stay inside one."""
    edges = [0] + sorted({int(c) for c in cuts if 0 < int(c) < n}) + [n]
    return [(edges[i], edges[i + 1]) for i in range(len(edges) - 1)]


def fill_gaps(track, keys, cuts=()):
    """Interpolate missing runs, never across a shot boundary."""
    for lo, hi in shots(len(track), cuts):
        for key in keys:
            known = [i for i in range(lo, hi) if track[i][key] is not None]
            if not known:
                continue
            for i in range(lo, hi):
                if track[i][key] is not None:
                    continue
                before = [k for k in known if k < i]
                after = [k for k in known if k > i]
                if not before:
                    track[i][key] = track[after[0]][key]
                elif not after:
                    track[i][key] = track[before[-1]][key]
                else:
                    a, b = before[-1], after[0]
                    t = (i - a) / (b - a)
                    track[i][key] = track[a][key] + (track[b][key] - track[a][key]) * t

    # A shot where the face was never found at all falls back to the nearest
    # known frame anywhere, which is wrong but better than a crash.
    for key in keys:
        known = [i for i, f in enumerate(track) if f[key] is not None]
        if not known:
            raise SystemExit("no face detected in any frame")
        for i in range(len(track)):
            if track[i][key] is None:
                track[i][key] = track[min(known, key=lambda k: abs(k - i))][key]
    return track


def smooth(track, keys, window, cuts=(), guard=2):
    """Centred moving average, clamped to the current shot.

    Averaging across a cut is what makes the anchor glide between two framings.
    Clamping keeps the jump instant, which is what the footage actually does.

    `guard` exists because boundary detection is not frame-exact. On real
    footage a one-frame blend put the histogram spike at 1556 while the face
    actually jumped at 1557, and that single frame of error was enough to
    reintroduce the full smear. Rather than chase perfect detection, suppress
    averaging entirely within `guard` frames of a boundary: those frames pass
    through raw, so being a frame or two out costs nothing.
    """
    half = window // 2
    out = [dict(f) for f in track]
    series = {key: [f[key] for f in track] for key in keys}
    edges = {int(c) for c in cuts}
    near = {i for c in edges for i in range(c - guard, c + guard + 1)}
    for lo_shot, hi_shot in shots(len(track), cuts):
        for key in keys:
            for i in range(lo_shot, hi_shot):
                if i in near:
                    out[i][key] = series[key][i]
                    continue
                lo = max(lo_shot, i - half)
                hi = min(hi_shot, i + half + 1)
                out[i][key] = sum(series[key][lo:hi]) / (hi - lo)
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("video")
    parser.add_argument("--model", default=str(Path(__file__).resolve().parent / "blaze_face_short_range.tflite"),
                        help="MediaPipe face detector; scripts/download_models.sh fetches it")
    parser.add_argument("--out", required=True)
    parser.add_argument("--smooth-window", type=int, default=9,
                        help="frames; higher = calmer but laggier. 9 @30fps = 0.3s")
    parser.add_argument("--cuts", help="cuts.json from detect_cuts.py. Without it, "
                                       "multi-angle footage smears the anchor "
                                       "across every shot change.")
    args = parser.parse_args()

    keys = ["cx", "cy", "top", "w", "h"]
    cuts = []
    if args.cuts:
        cuts = json.loads(Path(args.cuts).read_text())["cuts"]

    raw, fps, width, height = detect(Path(args.video), Path(args.model), cuts)
    detected = sum(1 for f in raw if f["cx"] is not None)
    confidences = [f["conf"] for f in raw if f["cx"] is not None]
    track = smooth(fill_gaps(raw, keys, cuts), keys, args.smooth_window, cuts)

    Path(args.out).write_text(json.dumps({
        "fps": fps,
        "width": width,
        "height": height,
        "frames": len(track),
        "detectionRate": round(detected / len(track), 4),
        "meanConfidence": round(sum(confidences) / len(confidences), 4) if confidences else 0,
        "cuts": cuts,
        "track": [
            {k: (round(f[k], 5) if k != "frame" else f[k]) for k in ["frame"] + keys}
            for f in track
        ],
    }, indent=1))

    mean_conf = sum(confidences) / len(confidences) if confidences else 0
    print(f"{len(track)} frames | {fps:g} fps | detection {detected/len(track):.1%} "
          f"| mean confidence {mean_conf:.2f} | {len(cuts)} cuts -> {args.out}")


if __name__ == "__main__":
    main()
