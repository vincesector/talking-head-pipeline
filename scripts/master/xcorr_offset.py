#!/usr/bin/env python3
"""xcorr_offset.py <reference> <candidate> [--at 1,20] [--len 8]
Seconds the candidate's audio runs LATE versus the reference (negative = early), averaged over
windows. Cross-correlation of 8 kHz mono slices; resolution 0.125 ms."""
import argparse, subprocess, sys, tempfile, wave
from pathlib import Path
import numpy as np

def load(src, at, length, tmp):
    out = Path(tmp) / f"{abs(hash((src, at)))}.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(at), "-t", str(length), "-i", src,
                    "-ac", "1", "-ar", "8000", str(out)], check=True)
    w = wave.open(str(out))
    return np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(float)

def lag_ms(a, b):
    n = min(len(a), len(b)); a, b = a[:n], b[:n]
    c = np.fft.irfft(np.fft.rfft(a, 2 * n) * np.conj(np.fft.rfft(b, 2 * n)))
    k = int(np.argmax(c)); k = k if k < n else k - 2 * n
    return -k / 8.0

ap = argparse.ArgumentParser()
ap.add_argument("reference"); ap.add_argument("candidate")
ap.add_argument("--at", default="1,20"); ap.add_argument("--len", type=float, default=8)
ap.add_argument("--verbose", action="store_true")
a = ap.parse_args()
with tempfile.TemporaryDirectory() as tmp:
    vals = []
    for at in [float(x) for x in a.at.split(",")]:
        ms = lag_ms(load(a.reference, at, a.len, tmp), load(a.candidate, at, a.len, tmp))
        vals.append(ms)
        if a.verbose:
            print(f"window at {at:g} s: {ms:+.1f} ms", file=sys.stderr)
print(f"{sum(vals) / len(vals) / 1000:.6f}")
