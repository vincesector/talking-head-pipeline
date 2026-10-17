#!/usr/bin/env python3
"""Find shot boundaries so the rest of the pipeline can stop smoothing across them.

Multi-angle footage breaks every temporal assumption the pipeline makes. The
head tracker penalises large frame-to-frame jumps to reject false detections on
background clutter, and averages over 9 frames to stop captions vibrating. Both
are right inside a shot and wrong across a cut, where the face legitimately
teleports.

Measured on a multi-location edit (4 locations, 7 boundaries): at one cut the raw
detection jumped 0.201 of frame height in a single frame while the smoothed
track moved 0.041 and needed 8 frames to catch up. Peak anchor error 0.110,
which is 211px on a 1920-tall frame, for 5 frames after every cut.

Histogram distance rather than pixel difference: a fast pan or a hand crossing
the lens moves pixels enormously without changing the shot, and would trip a
pixel-difference detector on every gesture.
"""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np


def detect(video_path, threshold=None, min_gap=8):
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS)
    prev = None
    scores = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        small = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (160, 284))
        hist = cv2.calcHist([small], [0], None, [64], [0, 256])
        hist /= max(hist.sum(), 1e-9)
        scores.append(0.0 if prev is None else float(np.abs(hist - prev).sum()))
        prev = hist
    cap.release()

    scores = np.array(scores)
    if threshold is None:
        # Absolute floor plus a distribution-relative term. The floor stops a
        # very static video from flagging its own noise as cuts.
        threshold = max(0.30, scores.mean() + 5 * scores.std())

    raw = [int(i) for i in np.where(scores > threshold)[0] if i > 2]
    cuts = []
    for c in raw:
        if not cuts or c - cuts[-1] > min_gap:
            cuts.append(c)
    return cuts, scores, fps, threshold


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("video")
    parser.add_argument("--out", required=True)
    parser.add_argument("--threshold", type=float, default=None)
    parser.add_argument("--min-gap", type=int, default=8,
                        help="frames; collapses a multi-frame dissolve to one boundary")
    args = parser.parse_args()

    cuts, scores, fps, threshold = detect(args.video, args.threshold, args.min_gap)
    Path(args.out).write_text(json.dumps({
        "fps": fps,
        "frames": len(scores),
        "threshold": round(float(threshold), 4),
        "cuts": cuts,
    }, indent=1))

    print(f"{len(scores)} frames | {len(cuts)} shot boundaries -> {args.out}")
    for c in cuts:
        print(f"   frame {c:5d}  ({c / fps:6.2f}s)  score {scores[c]:.3f}")


if __name__ == "__main__":
    main()
