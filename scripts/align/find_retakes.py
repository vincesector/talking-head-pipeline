#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["rapidfuzz"]
# ///
"""Flag likely retakes in an aligned (or raw mlx-whisper) transcript.

A "retake" here means: the speaker flubbed a line, restated it, and kept going --
two segments close together in time with near-identical text. This never
deletes anything. It writes a candidates JSON and a human-readable list of
timestamps for a human (or a later, separate cutting step) to act on.

Definition used: two segments are "nearby" if their start times are within
20s of each other, and "similar" if rapidfuzz.fuzz.ratio on their normalized
text is >= 75 (0-100 scale). For each match, the LATER segment is proposed
as the keeper (the usual pattern: restate and continue), the earlier one
as the drop candidate.

Usage:
    uv run find_retakes.py <aligned.json> [-o candidates.json]
"""
import argparse
import json
import re
import sys
from pathlib import Path

from rapidfuzz import fuzz

NEARBY_S = 20.0
SIMILARITY_THRESHOLD = 75.0  # rapidfuzz ratio is 0-100


def norm(text):
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def load_segments(path):
    data = json.loads(Path(path).read_text())
    segs = []
    for i, seg in enumerate(data["segments"]):
        text = seg["text"].strip()
        # Whisper hallucinates empty or zero-length segments on trailing room tone,
        # sometimes past the end of the file. Two empty strings match at 100%, so
        # they must never reach the comparison.
        if not norm(text) or seg["end"] - seg["start"] < 0.15:
            continue
        segs.append({"index": i, "start": seg["start"], "end": seg["end"], "text": text})
    return segs


def find_candidates(segments):
    candidates = []
    for i in range(len(segments)):
        for j in range(i + 1, len(segments)):
            a, b = segments[i], segments[j]
            if b["start"] - a["start"] > NEARBY_S:
                break  # segments are ordered by start, nothing further is nearby either
            sim = fuzz.ratio(norm(a["text"]), norm(b["text"]))
            if sim >= SIMILARITY_THRESHOLD:
                candidates.append({
                    "keep": b,
                    "drop_candidate": a,
                    "similarity": round(sim, 1),
                })
    return collapse_loops(candidates)


def collapse_loops(candidates):
    """A real retake is one repeat. The same short phrase repeated 3+ times in
    a row is a Whisper decoder loop, not a real retake; keep one row for it and
    say so, instead of one row per repeat."""
    counts = {}
    for c in candidates:
        counts[norm(c["drop_candidate"]["text"])] = counts.get(norm(c["drop_candidate"]["text"]), 0) + 1
    out, seen = [], set()
    for c in candidates:
        key = norm(c["drop_candidate"]["text"])
        if counts[key] >= 3:
            if key in seen:
                continue
            seen.add(key)
            c = dict(c, note=f"'{c['drop_candidate']['text']}' repeats {counts[key]} times in a row, likely a Whisper decoder loop on room tone; check the audio rather than trusting the transcript")
        out.append(c)
    return out


def fmt_ts(s):
    m, s = divmod(s, 60)
    return f"{int(m):02d}:{s:05.2f}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("transcript")
    ap.add_argument("-o", "--output", default=None, help="candidates JSON path (default: <transcript>.retakes.json)")
    args = ap.parse_args()

    segments = load_segments(args.transcript)
    candidates = find_candidates(segments)

    out_path = args.output or str(Path(args.transcript).with_suffix("")) + ".retakes.json"
    Path(out_path).write_text(json.dumps(candidates, indent=2, ensure_ascii=False))

    if not candidates:
        print(f"no likely retakes found ({len(segments)} segments checked)")
        print(f"wrote empty candidate list to {out_path}")
        return

    print(f"{len(candidates)} likely retake pair(s) found ({len(segments)} segments checked):\n")
    for c in candidates:
        a, b = c["drop_candidate"], c["keep"]
        print(f"  similarity={c['similarity']}")
        print(f"    drop?  [{fmt_ts(a['start'])}-{fmt_ts(a['end'])}] {a['text']!r}")
        print(f"    keep   [{fmt_ts(b['start'])}-{fmt_ts(b['end'])}] {b['text']!r}")
        print()
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
