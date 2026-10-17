#!/usr/bin/env python3
"""Estimate how out-of-focus the background is, so sandwiched graphics can match.

Between a 23mm f2.5 and an 85mm f1.4, background
separation changes shot to shot by a large factor, so a fixed blur
constant for sandwiched text is wrong on most clips: too sharp on the 85mm and
too mushy on the 23mm.

Method: additional-blur response. Blurring an already-soft region barely changes
it; blurring a sharp region changes it a lot. Measure that response curve for
the subject (from the matte) and for the background, then find the sigma which,
applied to the subject, reproduces the background's response. That sigma is the
background's effective defocus in pixels.

Only textured pixels are sampled. A dark flat wall is unmeasurable regardless of
focus, and including it drags every estimate toward zero, which is what made a
plain Laplacian-variance comparison useless here.

Output is a recommended blur for the sandwiched plane. That plane sits between
the subject and the background but nearer the subject, so it takes a fraction of the
background's defocus, not all of it.
"""
import argparse
import glob
import json
from pathlib import Path

import cv2
import numpy as np

# The sandwiched plane is much nearer the subject than the wall behind him.
PLANE_FRACTION = 0.30
# Scatter marks fan out around that plane to read as separate depths.
SCATTER_SPREAD = (0.55, 1.7)


def sharpness(gray, mask):
    """Re-blur sharpness score (Crete et al.), restricted to textured pixels.

    Blur the region a little and see how much gradient energy it loses. A sharp
    region loses a lot; an already-defocused one barely changes. Scale-free and
    monotonic, which the earlier response-curve comparison was not.
    """
    grad = cv2.magnitude(cv2.Sobel(gray, cv2.CV_32F, 1, 0, 3),
                         cv2.Sobel(gray, cv2.CV_32F, 0, 1, 3))
    if not mask.any():
        return None
    inside = mask & (grad > np.percentile(grad[mask], 70))
    if inside.sum() < 500:
        return None
    reblur = cv2.GaussianBlur(gray, (0, 0), 1.5)
    g2 = cv2.magnitude(cv2.Sobel(reblur, cv2.CV_32F, 1, 0, 3),
                       cv2.Sobel(reblur, cv2.CV_32F, 0, 1, 3))
    a, b = grad[inside].mean(), g2[inside].mean()
    if a <= 1e-6:
        return None
    return float(max(0.0, (a - b) / a))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("video")
    parser.add_argument("--cut", required=True,
                        help="matte PNG dir; its alpha separates subject from background")
    parser.add_argument("--out", required=True)
    parser.add_argument("--samples", type=int, default=12)
    args = parser.parse_args()

    frames = sorted(glob.glob(str(Path(args.cut) / "frame_*.png")))
    if not frames:
        raise SystemExit(f"no matte frames in {args.cut}")
    step = max(1, len(frames) // args.samples)
    frames = frames[::step][: args.samples]

    cap = cv2.VideoCapture(args.video)
    sigmas = np.array([0.4, 0.8, 1.3, 2.0, 3.0, 4.5, 6.5, 9.0, 13.0])
    ratios = []

    for path in frames:
        index = int(Path(path).stem.split("_")[1])
        cap.set(cv2.CAP_PROP_POS_FRAMES, index)
        ok, frame = cap.read()
        if not ok:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32)
        alpha = np.array(cv2.imread(path, cv2.IMREAD_UNCHANGED))[:, :, 3]
        subject = alpha > 200
        background = alpha < 40
        if subject.sum() < 5000 or background.sum() < 5000:
            continue

        target = sharpness(gray, background)
        if target is None:
            continue

        # Calibrate: blur the SUBJECT until it scores like the background.
        # That sigma is the background's defocus expressed in pixels of this
        # frame, which is what the graphics need to match.
        best_sigma, best_err = None, 1e9
        for s in sigmas:
            trial = cv2.GaussianBlur(gray, (0, 0), s)
            score = sharpness(trial, subject)
            if score is None:
                continue
            err = abs(score - target)
            if err < best_err:
                best_err, best_sigma = err, float(s)
        if best_sigma is not None:
            ratios.append(best_sigma)

    cap.release()
    if not ratios:
        raise SystemExit("could not measure; check the matte covers real texture")

    bg_sigma = float(np.median(ratios))
    plane = bg_sigma * PLANE_FRACTION
    result = {
        "backgroundSigmaPx": round(bg_sigma, 2),
        "samples": len(ratios),
        "heroBlurPx": round(plane, 2),
        "scatterBlurPx": [round(plane * SCATTER_SPREAD[0], 2),
                          round(plane * SCATTER_SPREAD[1], 2)],
    }
    Path(args.out).write_text(json.dumps(result, indent=1))
    print(f"background defocus ~{bg_sigma:.2f}px  (from {len(ratios)} sampled frames)")
    print(f"  hero word blur    {result['heroBlurPx']}px")
    print(f"  scatter blur      {result['scatterBlurPx'][0]}-{result['scatterBlurPx'][1]}px")
    print(f"  -> {args.out}")


if __name__ == "__main__":
    main()
