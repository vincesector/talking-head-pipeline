#!/usr/bin/env python3
"""Matte a video to an RGBA PNG sequence, one frame at a time, in order.

Two problems this solves.

1. backgroundremover's own `-tv` video mode corrupts frames: it spawns parallel
   workers even when told not to, and on a 180-frame clip it wrote the RGB
   image into the alpha plane on 15 of them. Those frames render as a fully
   transparent subject, so anything sandwiched behind pops in front.

2. Its prediction runs at 320x320 and is then upscaled to the frame size. At
   1080p that is a 5.6x upscale of the mask, which turns every edge into a wide
   gradient. Composite a bright graphic behind that and the subject wears a
   halo. Measured on this footage: 19% of the subject area was partial alpha,
   with ramps up to 240px wide.

The fix is a three-stage edge pipeline:
  predict at 640  ->  temporal average  ->  guided filter  ->  steep sigmoid

640 is deliberate. U2NET is fully convolutional so it accepts any size, but it
was trained at 320 and degrades out of distribution. Measured partial-alpha
area on the same frame: 16.6% at 320, 5.1% at 640, 24.0% at 960.

The guided filter uses the frame itself as guide, so the matte snaps to real
image edges instead of being blurred across them. The sigmoid then collapses
what is left of the ramp. Together: 19% partial alpha down to 2.7%.
"""
import argparse
from pathlib import Path

import cv2
import numpy as np
import torch
from backgroundremover.u2net import data_loader, detect
from PIL import Image
from torchvision import transforms


def predict_at(net, image, size):
    """U2NET forward pass at an arbitrary input size.

    RescaleT resizes to size x size, so a 9:16 frame gets squashed to 56% of
    its width before the model ever sees it. On this footage that distortion
    made u2net_human_seg classify a whole column of shelving above the head as
    "person", fused to his silhouette so connected-component filtering kept it,
    and the hero word behind him had a hole punched through it.

    Measured on frame 45, alpha above y=0.22 (well clear of his hair):
      squashed 640   18.4% phantom, 54.9% coverage
      squashed 1024   2.5% phantom, 32.2% coverage (now losing his body)
      squashed 1280   0.0% phantom, 18.0% coverage (lost his body)
      LETTERBOXED 640 0.2% phantom, 53.9% coverage

    So pad to square instead of raising the input size: it keeps the 640 sweet
    spot the edge pipeline was tuned around and fixes the aspect at the source.
    """
    h, w = image.shape[:2]
    side = max(h, w)
    y0, x0 = (side - h) // 2, (side - w) // 2
    if h != w:
        square = np.zeros((side, side, 3), image.dtype)
        square[y0:y0 + h, x0:x0 + w] = image
    else:
        square = image

    label = np.zeros(square.shape[0:2])[:, :, np.newaxis]
    tf = transforms.Compose(
        [data_loader.RescaleT(size), data_loader.ToTensorLab(flag=0)]
    )
    sample = tf({"imidx": np.array([0]), "image": square, "label": label})
    x = torch.FloatTensor(sample["image"].unsqueeze(0).float())
    param = next(net.parameters())
    x = x.to(param.device, dtype=param.dtype)
    with torch.no_grad():
        d1 = net(x)[0]
    pred = d1[:, 0, :, :]
    pred = (pred - pred.min()) / (pred.max() - pred.min())
    mask = pred.squeeze().cpu().numpy().astype(np.float32)
    mask = cv2.resize(mask, (side, side), interpolation=cv2.INTER_LINEAR)
    return mask[y0:y0 + h, x0:x0 + w]


def cleanup(alpha, rgb, track_frame, exclude):
    """Drop what u2net wrongly called 'person'.

    Two distinct failures on a lit set:
      - detached blobs (a bright doorway, a poster) that are not him at all
      - a bright object FUSED to his silhouette. Here a neon sign merged
        into his arm, so the hero word passed behind the neon as if the sign
        were part of him. Erosion up to 36px never broke the bridge, so
        connected-component filtering alone cannot fix it.

    So: keep only the component containing the tracked face, then subtract a
    static region gated on the pixel actually being lit neon. The gate matters.
    A plain region cut carves a hole out of him whenever he stands in front of
    the sign, which he does during the walk-in.
    """
    h, w = alpha.shape
    binary = (alpha > 0.5).astype(np.uint8)
    if binary.sum() == 0:
        return alpha

    n, lab, stats, _ = cv2.connectedComponentsWithStats(binary, 8)
    seed = (
        min(w - 1, max(0, int(track_frame["cx"] * w))),
        min(h - 1, max(0, int(track_frame["cy"] * h))),
    )
    lid = lab[seed[1], seed[0]]
    if lid == 0:
        lid = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    alpha = alpha * (lab == lid)

    if exclude is None:
        return alpha

    region = np.zeros((h, w), np.uint8)
    cv2.ellipse(
        region,
        (int(exclude["cx"] * w), int(exclude["cy"] * h)),
        (int(exclude["rx"] * w), int(exclude["ry"] * h)),
        0, 0, 360, 255, -1,
    )
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    hue = hsv[:, :, 0].astype(int) * 2
    sat = hsv[:, :, 1].astype(int)
    val = hsv[:, :, 2].astype(int)
    lit = (
        (hue >= exclude.get("hue0", 30))
        & (hue <= exclude.get("hue1", 75))
        & (sat > exclude.get("sat", 150))
        & (val > exclude.get("val", 120))
    ).astype(np.uint8) * 255
    lit = cv2.dilate(lit, np.ones((25, 25), np.uint8))
    cut = cv2.GaussianBlur(cv2.bitwise_and(region, lit), (41, 41), 0)
    return alpha * (1.0 - np.clip(cut.astype(np.float32) / 255.0 * 1.6, 0, 1))


def refine(alpha, guide_rgb, radius, eps, gain, pivot):
    guide = guide_rgb.astype(np.float32) / 255.0
    a = cv2.ximgproc.guidedFilter(
        guide=guide, src=alpha.astype(np.float32), radius=radius, eps=eps
    )
    a = 1.0 / (1.0 + np.exp(-gain * (a - pivot)))
    return np.clip(a, 0.0, 1.0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("video")
    parser.add_argument("--out", required=True, help="output directory for PNGs")
    parser.add_argument("--model", default="u2net_human_seg")
    parser.add_argument("--from-frame", type=int, default=0)
    parser.add_argument("--to-frame", type=int, default=10**9)
    parser.add_argument("--size", type=int, default=640,
                        help="U2NET input size. 640 is the measured sweet spot")
    parser.add_argument("--smooth", type=int, default=3,
                        help="temporal mask average in frames, applied BEFORE "
                             "edge refinement so it steadies without softening")
    parser.add_argument("--gain", type=float, default=22.0,
                        help="sigmoid steepness. higher = harder edge")
    parser.add_argument("--pivot", type=float, default=0.5,
                        help="alpha midpoint. raise to choke the edge inward")
    parser.add_argument("--track", help="track.json, enables stray-blob removal")
    parser.add_argument("--cuts", help="cuts.json. The temporal average must not "
                        "span a shot change or the matte ghosts across the cut.")
    parser.add_argument("--exclude", help="static region to carve out, as "
                        "cx,cy,rx,ry normalized (e.g. a neon sign the model "
                        "keeps calling part of the person)")
    parser.add_argument("--radius", type=int, default=6)
    parser.add_argument("--eps", type=float, default=1e-5)
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    track = None
    if args.track:
        import json
        track = json.loads(Path(args.track).read_text())["track"]
    exclude = None
    if args.exclude:
        cx, cy, rx, ry = [float(v) for v in args.exclude.split(",")]
        exclude = {"cx": cx, "cy": cy, "rx": rx, "ry": ry}

    net = detect.load_model(model_name=args.model)
    cap = cv2.VideoCapture(args.video)

    masks, frames = [], []
    index = -1
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        index += 1
        if index < args.from_frame:
            continue
        if index > args.to_frame:
            break
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        masks.append(predict_at(net, rgb, args.size))
        frames.append(rgb)
    cap.release()

    if not frames:
        raise SystemExit("no frames read")

    # A frame whose mask covers almost nothing is a model failure, not a person
    # leaving the shot. Replace it before smoothing so one bad frame does not
    # drag its neighbours down.
    coverage = np.array([(m > 0.5).mean() for m in masks])
    good = np.where(coverage > coverage.max() * 0.25)[0]
    repaired = 0
    for i in range(len(masks)):
        if coverage[i] <= coverage.max() * 0.25:
            masks[i] = masks[good[np.abs(good - i).argmin()]].copy()
            repaired += 1

    if args.smooth > 1:
        half = args.smooth // 2
        # Averaging a mask across a cut ghosts the previous silhouette into the
        # new shot for a few frames. Clamp the window to the current shot.
        bounds = [0, len(masks)]
        if args.cuts:
            import json as _json
            raw_cuts = _json.loads(Path(args.cuts).read_text())["cuts"]
            bounds = sorted({0, len(masks)} | {
                int(c) - args.from_frame for c in raw_cuts
                if 0 < int(c) - args.from_frame < len(masks)
            })
        shots = [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1)]
        # NB: do not name this `out`; that shadows the output directory.
        averaged = list(masks)
        for lo_s, hi_s in shots:
            for i in range(lo_s, hi_s):
                lo, hi = max(lo_s, i - half), min(hi_s, i + half + 1)
                averaged[i] = np.mean(masks[lo:hi], axis=0)
        masks = averaged

    softness = []
    for i, (rgb, mask) in enumerate(zip(frames, masks)):
        a = refine(mask, rgb, args.radius, args.eps, args.gain, args.pivot)
        if track is not None:
            a = cleanup(a, rgb, track[min(i + args.from_frame, len(track) - 1)], exclude)
        partial = ((a > 0.05) & (a < 0.95)).sum()
        solid = (a >= 0.95).sum()
        softness.append(partial / max(solid, 1))
        rgba = np.dstack([rgb, (a * 255).astype(np.uint8)])
        Image.fromarray(rgba, mode="RGBA").save(
            out / f"frame_{i + args.from_frame:05d}.png"
        )

    print(
        f"{len(frames)} frames -> {out}  repaired={repaired}  "
        f"mean edge softness={np.mean(softness) * 100:.1f}% of solid area "
        f"(was ~19% at 320px)"
    )


if __name__ == "__main__":
    main()
