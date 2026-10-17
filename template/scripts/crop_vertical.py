#!/usr/bin/env python3
"""Crop a 16:9 talking-head take to 9:16 around the subject, constant frame rate.

The vertical layout profile expects a vertical source. If you record vertical
reels on the same 16:9 setup as your long-form videos (a 2560x1440 recording is
ideal: the 9:16 crop is still 810x1440), the take has to be cropped first. The crop window is fixed for the whole take (a static camera
reads as a camera, a window that follows the subject reads as a bad stabiliser) and
centred on the median tracked head x, so the subject sits in the horizontal centre.

    scripts/crop_vertical.py clean.mp4 --track track16x9.json -o raw.mp4
    scripts/crop_vertical.py clean.mp4 -o raw.mp4          # centre crop

--track is the output of track_head.py run on the 16:9 file. Without it the
crop is the frame centre. Output is 1080x1920 unless --width/--height say
otherwise, encoded libx264 crf 18 at the source frame rate, CFR.
"""
import argparse
import json
import statistics
import subprocess
from pathlib import Path


def probe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,r_frame_rate", "-of", "json", path],
        capture_output=True, text=True, check=True).stdout
    s = json.loads(out)["streams"][0]
    num, den = s["r_frame_rate"].split("/")
    return s["width"], s["height"], num, den


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--track", help="track.json from track_head.py on this (16:9) file")
    ap.add_argument("--width", type=int, default=1080)
    ap.add_argument("--height", type=int, default=1920)
    ap.add_argument("--crf", type=int, default=18)
    a = ap.parse_args()

    sw, sh, num, den = probe(a.video)
    crop_w = round(sh * a.width / a.height)
    if crop_w > sw:
        raise SystemExit(f"source {sw}x{sh} is narrower than a {a.width}x{a.height} crop of its full height")

    cx = 0.5
    if a.track:
        t = json.loads(Path(a.track).read_text())
        xs = [e["cx"] for e in t["track"] if e.get("cx") is not None and e.get("w", 0) > 0]
        if xs:
            cx = statistics.median(xs)
    x = int(round(cx * sw - crop_w / 2))
    x = max(0, min(sw - crop_w, x))
    # even x keeps the chroma grid aligned
    x -= x % 2

    vf = f"crop={crop_w}:{sh}:{x}:0,scale={a.width}:{a.height}:flags=lanczos"
    print(f"source {sw}x{sh}, head cx {cx:.3f} -> crop {crop_w}x{sh} at x={x}, scale to {a.width}x{a.height}")
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", a.video, "-vf", vf,
         "-r", f"{num}/{den}", "-fps_mode", "cfr",
         "-c:v", "libx264", "-crf", str(a.crf), "-preset", "fast", "-pix_fmt", "yuv420p",
         "-c:a", "copy", "-movflags", "+faststart", a.output],
        check=True)
    ow, oh, _, _ = probe(a.output)
    print(f"wrote {a.output} ({ow}x{oh})")


if __name__ == "__main__":
    main()
