#!/usr/bin/env python3
"""Measure the audio/video offset of a clap-test recording.

Record about 5 seconds in OBS with your hands in frame and ONE sharp clap.
Then:

    measure_sync.py clap.mp4

It finds the audio transient, dumps the video frames around it, estimates the
visual clap frame from motion, and prints the value to enter in OBS under
Advanced Audio Properties > Sync Offset (ms) for the mic source.

Motion detection is a helper, not an oracle. Open the dumped frames folder and
confirm which frame the hands actually meet in; the printout tells you how to
correct the number by hand if it picked a neighbour.
"""
import array, math, pathlib, subprocess, sys

def sh(cmd):
    return subprocess.run(cmd, capture_output=True, check=True).stdout

def fps_of(path):
    r = sh(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
            "stream=r_frame_rate", "-of", "csv=p=0", path]).decode().strip()
    n, d = r.split("/"); return float(n) / float(d)

def audio_transient(path):
    raw = sh(["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", "48000", "-f", "s16le", "-"])
    a = array.array("h"); a.frombytes(raw[: (len(raw) // 2) * 2])
    hop = 240  # 5 ms at 48 kHz
    rms = [math.sqrt(sum(x * x for x in a[i:i + hop]) / hop) + 1e-9 for i in range(0, len(a) - hop, hop)]
    floor = sorted(rms)[len(rms) // 5]  # 20th percentile as the noise floor
    for i, v in enumerate(rms):
        if v > floor * 10:  # 20 dB above the floor
            return i * hop / 48000.0
    return None

def visual_clap(path, around, fps, outdir):
    w, h = 160, 90
    t0 = max(0.0, around - 0.4)
    raw = sh(["ffmpeg", "-v", "error", "-ss", f"{t0:.3f}", "-t", "0.8", "-i", path,
              "-vf", f"scale={w}:{h},format=gray", "-f", "rawvideo", "-"])
    n = len(raw) // (w * h)
    frames = [raw[i * w * h:(i + 1) * w * h] for i in range(n)]
    diffs = [sum(abs(p - q) for p, q in zip(frames[i], frames[i - 1])) / (w * h) for i in range(1, n)]
    peak = max(range(len(diffs)), key=lambda i: diffs[i]) + 1
    outdir.mkdir(parents=True, exist_ok=True)
    sh(["ffmpeg", "-v", "error", "-y", "-ss", f"{t0:.3f}", "-t", "0.8", "-i", path,
        "-vf", "scale=480:-1", str(outdir / "frame_%03d.png")])
    return t0 + peak / fps, peak + 1, diffs

def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    path = sys.argv[1]
    fps = fps_of(path)
    at = audio_transient(path)
    if at is None:
        sys.exit("no audio transient found; was there a clap?")
    outdir = pathlib.Path(path).with_suffix("") .parent / (pathlib.Path(path).stem + "_clapframes")
    vt, frame_no, diffs = visual_clap(path, at, fps, outdir)
    off_ms = (at - vt) * 1000.0
    print(f"video fps:              {fps:g}")
    print(f"audio transient at:     {at:8.3f} s")
    print(f"visual clap (motion) at:{vt:8.3f} s   (frame_{frame_no:03d}.png in {outdir})")
    print(f"audio minus video:      {off_ms:+7.1f} ms  ({off_ms / 1000 * fps:+.1f} frames)")
    if off_ms > 0:
        print(f"audio arrives LATE. OBS Sync Offset for the mic: {-off_ms:+.0f} ms   (fix_sync.sh offset for old files: {-off_ms/1000:+.3f})")
    else:
        print(f"audio arrives EARLY. OBS Sync Offset for the mic: {-off_ms:+.0f} ms  (fix_sync.sh offset for old files: {-off_ms/1000:+.3f})")
    print(f"one frame = {1000/fps:.1f} ms. If the true clap frame is a neighbour of the picked one, adjust by that much.")

if __name__ == "__main__":
    main()
