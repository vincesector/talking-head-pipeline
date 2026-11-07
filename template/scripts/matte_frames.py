#!/usr/bin/env python3
"""Matte a video to an RGBA PNG sequence, one frame at a time, in order, streaming.

Default engine: Robust Video Matting (RVM ResNet50) on the Mac GPU (MPS), via the shared
module scripts/matte/rvm_matte.py of this repo. Measured on an M3 Max at 1080x1920: 15-22 fps
end to end (the model alone does ~40), ~2 GB peak, real hair strands, no table or props.
RVM is GPL-3.0 and is fetched at runtime into ~/.cache/rvm/, not shipped in this repo.
How it is driven here:

  - frames are read in order and every PNG is written as it goes (no frame is held), so a
    60 s window peaks near 2 GB instead of growing with the clip;
  - RVM's recurrent state is the temporal smoothing. It is reset at every shot change
    (--cuts). `--smooth` does not apply. The first frame or two after a reset can show faint
    haze along a desk edge (feeding the first frame repeatedly was measured and did not
    help), so look at the frame after each cut;
  - the window starts 15 frames early (warm-up) and those frames are discarded, so the
    state has settled when the first PNG is written;
  - no edge hardening: the old guided filter + sigmoid turned curls into a smooth helmet.
    `--refine` brings it back as a choke for bright backdrops (--pivot, --gain, --radius,
    --eps only act with --refine);
  - output contract is unchanged: RGBA PNG (original frame RGB + alpha), absolute frame
    numbers, frame_NNNNN.png.

`--engine u2net` is the previous engine (u2net_human_seg via backgroundremover, CPU, ~1 fps,
15 GB on an 8 s window). Kept for one release, then removed. Its notes, kept for reference:

1. backgroundremover's own `-tv` video mode corrupts frames: it spawns parallel
   workers even when told not to, and on a 180-frame clip it wrote the RGB
   image into the alpha plane on 15 of them.
2. Its prediction runs at 320x320 and is upscaled to the frame size, so every edge is a
   wide gradient. The u2net path therefore predicts at 640 on a letterboxed square, takes a
   temporal average, a guided filter and a steep sigmoid (19% partial alpha down to 2.7%).
   The guided filter needs opencv-contrib-python (cv2.ximgproc), not plain opencv-python.
"""
import argparse
import concurrent.futures as cf
import json
import os
import resource
import sys
import threading
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

WARMUP_FRAMES = 15  # mirrors rvm_matte.WARMUP_FRAMES; kept here so --help works without torch


def find_rvm_module():
    """The shared engine lives in the repo at scripts/matte/. A project copy of this script
    finds it via $THP_HOME, ~/.config/talking-head-pipeline/root (written by install.sh), or
    the script's own location when it still sits inside the repo."""
    roots = [os.environ.get("THP_HOME")]
    cfg = Path.home() / ".config" / "talking-head-pipeline" / "root"
    if cfg.exists():
        roots.append(cfg.read_text().strip())
    roots += [str(p) for p in Path(__file__).resolve().parents]
    for r in roots:
        if r and (Path(r) / "scripts" / "matte" / "rvm_matte.py").exists():
            return str(Path(r) / "scripts" / "matte")
    raise SystemExit("matte_frames: cannot find scripts/matte/rvm_matte.py (set THP_HOME to the repo root)")


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
    import torch
    from backgroundremover.u2net import data_loader
    from torchvision import transforms

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


def load_cuts(path):
    if not path:
        return set()
    return {int(c) for c in json.loads(Path(path).read_text())["cuts"]}


def peak_rss_gb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e9  # bytes on macOS


class PngWriter:
    """Writes PNGs on worker threads (zlib releases the GIL) with a bounded queue, so the
    GPU loop never waits on disk but memory stays flat."""

    def __init__(self, workers=4, in_flight=8):
        self.pool = cf.ThreadPoolExecutor(workers)
        self.sem = threading.Semaphore(in_flight)
        self.futures = []

    def _write(self, path, rgba, level):
        try:
            Image.fromarray(rgba).save(path, compress_level=level)
        finally:
            self.sem.release()

    def submit(self, path, rgba, level):
        self.sem.acquire()
        self.futures.append(self.pool.submit(self._write, path, rgba, level))
        if len(self.futures) > 64:
            self.futures = [f for f in self.futures if not f.done()]

    def close(self):
        for f in self.futures:
            f.result()
        self.pool.shutdown()


def run_rvm(args, out, track, exclude):
    sys.path.insert(0, find_rvm_module())
    import rvm_matte

    cuts = load_cuts(args.cuts)
    start = max(0, args.from_frame - WARMUP_FRAMES)
    # Warm-up must not reach back across a shot change: start at the cut instead.
    for c in sorted(cuts):
        if start < c <= args.from_frame:
            start = c

    matter = rvm_matte.RVMMatter(downsample_ratio=args.downsample)
    cap = cv2.VideoCapture(args.video)
    writer = PngWriter()
    coverage, softness = [], []
    n = 0
    t0 = time.time()
    index = -1
    while True:
        index += 1
        if index > args.to_frame:
            break
        if index < start:
            if not cap.grab():
                break
            continue
        ok, frame = cap.read()
        if not ok:
            break
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        if index == start:
            t0 = time.time()  # fps excludes the skip-decode up to the window
        if index == start or index in cuts:
            matter.reset()
        a = matter.matte(rgb)
        if index < args.from_frame:
            continue  # warm-up frame, state only
        if args.refine:
            a = refine(a, rgb, args.radius, args.eps, args.gain, args.pivot)
        if track is not None:
            a = cleanup(a, rgb, track[min(index, len(track) - 1)], exclude)
        coverage.append(float((a > 0.5).mean()))
        solid = (a >= 0.95).sum()
        softness.append(((a > 0.05) & (a < 0.95)).sum() / max(solid, 1))
        rgba = np.empty((*rgb.shape[:2], 4), np.uint8)
        rgba[..., :3] = rgb
        rgba[..., 3] = (a * 255).astype(np.uint8)
        writer.submit(out / f"frame_{index:05d}.png", rgba, args.png_level)
        n += 1
    cap.release()
    writer.close()
    if not n:
        raise SystemExit("no frames read")
    return n, coverage, softness, time.time() - t0


def run_u2net(args, out, track, exclude):
    """Previous engine, kept behind --engine u2net for one release. Holds every frame in RAM."""
    from backgroundremover.u2net import detect

    net = detect.load_model(model_name=args.model)
    cap = cv2.VideoCapture(args.video)
    t0 = time.time()

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
    for i in range(len(masks)):
        if coverage[i] <= coverage.max() * 0.25:
            masks[i] = masks[good[np.abs(good - i).argmin()]].copy()

    if args.smooth > 1:
        half = args.smooth // 2
        # Averaging a mask across a cut ghosts the previous silhouette into the
        # new shot for a few frames. Clamp the window to the current shot.
        bounds = [0, len(masks)]
        if args.cuts:
            bounds = sorted({0, len(masks)} | {
                c - args.from_frame for c in load_cuts(args.cuts)
                if 0 < c - args.from_frame < len(masks)
            })
        shots = [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1)]
        averaged = list(masks)
        for lo_s, hi_s in shots:
            for i in range(lo_s, hi_s):
                lo, hi = max(lo_s, i - half), min(hi_s, i + half + 1)
                averaged[i] = np.mean(masks[lo:hi], axis=0)
        masks = averaged

    cov_out, softness = [], []
    for i, (rgb, mask) in enumerate(zip(frames, masks)):
        a = refine(mask, rgb, args.radius, args.eps, args.gain, args.pivot)
        if track is not None:
            a = cleanup(a, rgb, track[min(i + args.from_frame, len(track) - 1)], exclude)
        cov_out.append(float((a > 0.5).mean()))
        softness.append(((a > 0.05) & (a < 0.95)).sum() / max((a >= 0.95).sum(), 1))
        rgba = np.dstack([rgb, (a * 255).astype(np.uint8)])
        Image.fromarray(rgba).save(out / f"frame_{i + args.from_frame:05d}.png")
    return len(frames), cov_out, softness, time.time() - t0


def main():
    parser = argparse.ArgumentParser(description="Matte a video to an RGBA PNG sequence (RVM on MPS by default).")
    parser.add_argument("video")
    parser.add_argument("--out", required=True, help="output directory for PNGs")
    parser.add_argument("--engine", choices=["rvm", "u2net"], default="rvm",
                        help="rvm = Robust Video Matting on the GPU (default). u2net = the "
                        "previous CPU engine, kept for one release")
    parser.add_argument("--from-frame", type=int, default=0)
    parser.add_argument("--to-frame", type=int, default=10**9)
    parser.add_argument("--track", help="track.json, enables stray-blob removal")
    parser.add_argument("--cuts", help="cuts.json. RVM: the recurrent state is reset at each "
                        "shot change. u2net: the temporal average does not span a cut.")
    parser.add_argument("--exclude", help="static region to carve out, as "
                        "cx,cy,rx,ry normalized (e.g. a neon sign the model "
                        "keeps calling part of the person)")
    parser.add_argument("--downsample", type=float, default=None,
                        help="RVM downsample_ratio. Default: auto by resolution (0.25 at 1080p)")
    parser.add_argument("--refine", action="store_true",
                        help="RVM: apply the guided filter + sigmoid choke (--pivot, --gain, "
                        "--radius, --eps). Off by default, it flattens hair strands. "
                        "Needs opencv-contrib-python. Always on for u2net")
    parser.add_argument("--gain", type=float, default=22.0,
                        help="sigmoid steepness. higher = harder edge")
    parser.add_argument("--pivot", type=float, default=0.5,
                        help="alpha midpoint. raise to choke the edge inward")
    parser.add_argument("--radius", type=int, default=6)
    parser.add_argument("--eps", type=float, default=1e-5)
    parser.add_argument("--png-level", type=int, default=3,
                        help="PNG zlib level 0-9 (RVM path). Lower is faster, files are larger")
    # u2net only
    parser.add_argument("--model", default="u2net_human_seg", help="u2net engine only")
    parser.add_argument("--size", type=int, default=640, help="u2net engine only: input size")
    parser.add_argument("--smooth", type=int, default=3, help="u2net engine only: temporal "
                        "mask average in frames. RVM's recurrent state replaces it")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    track = None
    if args.track:
        track = json.loads(Path(args.track).read_text())["track"]
    exclude = None
    if args.exclude:
        cx, cy, rx, ry = [float(v) for v in args.exclude.split(",")]
        exclude = {"cx": cx, "cy": cy, "rx": rx, "ry": ry}

    run = run_rvm if args.engine == "rvm" else run_u2net
    n, coverage, softness, secs = run(args, out, track, exclude)

    cov = np.array(coverage)
    low = int((cov <= cov.max() * 0.25).sum())
    print(
        f"{n} frames -> {out}  engine={args.engine}  {n / secs:.1f} fps  rss={peak_rss_gb():.1f} GB  "
        f"low_coverage={low}  mean edge softness={np.mean(softness) * 100:.1f}% of solid area"
    )


if __name__ == "__main__":
    main()
