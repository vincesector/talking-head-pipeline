#!/usr/bin/env python3
"""Turn a word-level transcript into candidate emphasis SPANS.

A push anchored to a single word is a twitch: it arrives and leaves before the
idea does. A push anchored to a whole paragraph overstays: a minute of held zoom
stops reading as emphasis and just becomes the new framing. The useful unit is
in between, a clause or a sentence, which is also how speech is actually
grouped.

This produces the candidate spans. The planner still chooses which ones earn a
push and which are left flat; nothing here says every span must be used.

Rules:
  - split on clause punctuation first, because that is where a speaker breathes
  - a span shorter than MIN merges forward into its neighbour
  - a span longer than MAX splits at its best interior comma, or failing that at
    its longest internal pause
  - the accent word inside a span is its highest-weight token, so the planner
    can nest a lean-in without hunting for it
"""
import argparse
import json
import re
from pathlib import Path

MIN_SEC = 1.6   # below this a push reads as a twitch
MAX_SEC = 7.0   # above this it stops being emphasis and becomes framing
CLAUSE_END = re.compile(r"[.,!?;:]$")


def load_words(transcript, offset):
    words = []
    for seg in json.loads(Path(transcript).read_text())["segments"]:
        for w in seg.get("words", []):
            text = w["word"].strip()
            if text:
                words.append({"t": text, "s": w["start"] - offset, "e": w["end"] - offset})
    return [w for w in words if w["e"] > 0]


def split_on_clauses(words):
    spans, cur = [], []
    for w in words:
        cur.append(w)
        if CLAUSE_END.search(w["t"]):
            spans.append(cur)
            cur = []
    if cur:
        spans.append(cur)
    return spans


def duration(span):
    return span[-1]["e"] - span[0]["s"]


def split_long(span):
    """Halve an overlong span at its best interior break."""
    if duration(span) <= MAX_SEC or len(span) < 6:
        return [span]
    interior = range(2, len(span) - 2)
    commas = [i for i in interior if CLAUSE_END.search(span[i]["t"])]
    if commas:
        mid = min(commas, key=lambda i: abs(i - len(span) / 2))
    else:
        # longest silence between words is where he actually took a breath
        mid = max(interior, key=lambda i: span[i]["s"] - span[i - 1]["e"])
    return split_long(span[: mid + 1]) + split_long(span[mid + 1:])


def merge_short(spans):
    out = []
    for span in spans:
        if out and duration(span) < MIN_SEC:
            out[-1] = out[-1] + span
        else:
            out.append(span)
    # a lone short span at the head has nothing before it to merge into
    while len(out) > 1 and duration(out[0]) < MIN_SEC:
        out[0] = out[0] + out.pop(1)
    return out


def weight(token, emphasis):
    bare = re.sub(r"[^\w'-]", "", token).lower()
    if bare in emphasis:
        return 3
    if any(c.isdigit() for c in bare):
        return 2
    if len(bare) > 7:
        return 1
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("transcript")
    parser.add_argument("--out", required=True)
    parser.add_argument("--offset", type=float, default=0.0,
                        help="seconds trimmed off the head of the source")
    parser.add_argument("--fps", type=float, default=30)
    parser.add_argument("--emphasis", default="",
                        help="comma-separated words that carry weight in this script")
    args = parser.parse_args()

    emphasis = {w.strip().lower() for w in args.emphasis.split(",") if w.strip()}
    words = load_words(args.transcript, args.offset)

    # Split and merge fight each other: merging a short clause into its
    # neighbour can push the result back over MAX. Iterate until stable, or a
    # 14s span survives a 7s ceiling.
    spans = split_on_clauses(words)
    for _ in range(6):
        before = len(spans)
        spans = [s for c in spans for s in split_long(c)]
        spans = merge_short(spans)
        if len(spans) == before:
            break
    # End on a merge, never a split. A span slightly over MAX is a push that
    # runs a beat long; a 0.6s fragment is the twitch this filter exists to
    # prevent. Prefer the former.
    spans = merge_short(spans)

    out = []
    for span in spans:
        best = max(span, key=lambda w: (weight(w["t"], emphasis), len(w["t"])))
        out.append({
            "fromFrame": max(0, int(span[0]["s"] * args.fps)),
            "toFrame": int(span[-1]["e"] * args.fps),
            "seconds": round(duration(span), 2),
            "text": " ".join(w["t"] for w in span),
            "accentWord": best["t"],
            "accentFrame": int(best["s"] * args.fps),
            "weight": sum(weight(w["t"], emphasis) for w in span),
        })

    Path(args.out).write_text(json.dumps(out, indent=1))
    lens = [s["seconds"] for s in out]
    print(f"{len(out)} spans -> {args.out}")
    print(f"  duration min {min(lens):.1f}s  mean {sum(lens)/len(lens):.1f}s  max {max(lens):.1f}s")
    print(f"  (filter targets {MIN_SEC}-{MAX_SEC}s)")
    print("\n  top spans by weight:")
    for s in sorted(out, key=lambda s: -s["weight"])[:8]:
        print(f"    w{s['weight']:2d}  {s['seconds']:4.1f}s  f{s['fromFrame']:5d}-{s['toFrame']:5d}  "
              f"accent '{s['accentWord']}'  {s['text'][:52]}")


if __name__ == "__main__":
    main()
