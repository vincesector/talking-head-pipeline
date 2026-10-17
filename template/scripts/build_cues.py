#!/usr/bin/env python3
"""Word-level transcript in, caption cues out.

Every dynamic-edit project used to build `captions.json` by hand. This is the
step, written down once.

Input words: autocut's `captions.json` ([{"text","startMs","endMs"}]) or an
mlx-whisper / align_words transcript ({"segments":[{"words":[{"word","start","end"}]}]}).

Cue rules (measured on two shipped edits: median 4 tokens,
median 1.4 s):
  - a cue ends at a pause longer than --pause (default 0.35 s), at sentence
    punctuation (. ? !), at --max-tokens (default 5) or at --max-seconds (2.2)
  - a cue starts on its first word's onset and ends on its last word's end
  - emphasis is a PHRASE, never one word inside a named thing: pass each phrase
    with --emphasis "cash flow" --emphasis "ten months"; a cue never breaks
    inside an emphasised phrase (the caption rule from SKILL.md)
  - first-person "i" is capitalised (Whisper leaves it lower case)

    scripts/build_cues.py words.json --fps 30 -o remotion/public/captions.json \
        --emphasis "cash flow" --emphasis "ten months"
"""
import argparse
import json
import re
from pathlib import Path


def load_words(path):
    data = json.loads(Path(path).read_text())
    words = []
    if isinstance(data, list):  # autocut captions.json
        for w in data:
            t = w["text"].strip()
            if t:
                words.append({"w": t, "s": w["startMs"] / 1000, "e": w["endMs"] / 1000})
    else:  # whisper-style segments
        for seg in data.get("segments", []):
            for w in seg.get("words", []):
                t = w["word"].strip()
                if t:
                    words.append({"w": t, "s": w["start"], "e": w["end"]})
    for w in words:
        if w["w"] == "i":
            w["w"] = "I"
        elif w["w"].startswith("i'"):
            w["w"] = "I" + w["w"][1:]
    return words


def norm(s):
    return re.sub(r"[^\w]", "", s.lower())


def mark_emphasis(words, phrases):
    """Set e=True on every token of each phrase; return the set of indices that
    must not be followed by a cue break (inside a phrase)."""
    no_break_after = set()
    toks = [norm(w["w"]) for w in words]
    for w in words:
        w["em"] = False  # emphasis flag; "e" is the end time
    for phrase in phrases:
        p = [norm(x) for x in phrase.split()]
        n = len(p)
        for i in range(len(toks) - n + 1):
            if toks[i:i + n] == p:
                for k in range(i, i + n):
                    words[k]["em"] = True
                for k in range(i, i + n - 1):
                    no_break_after.add(k)
    return no_break_after


def build(words, fps, pause, max_tokens, max_seconds, no_break_after):
    cues, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        last = i == len(words) - 1
        nxt_gap = (words[i + 1]["s"] - w["e"]) if not last else 0
        ends_sentence = w["w"][-1] in ".?!"
        too_long = len(cur) >= max_tokens or (w["e"] - cur[0]["s"]) >= max_seconds
        if (last or nxt_gap > pause or ends_sentence or too_long) and i not in no_break_after:
            cues.append(cur)
            cur = []
    if cur:
        cues.append(cur)
    out = []
    for c in cues:
        frm = round(c[0]["s"] * fps)
        to = max(frm + 1, round(c[-1]["e"] * fps))
        if out and frm <= out[-1]["to"]:
            frm = out[-1]["to"] + 1
        out.append({"from": frm, "to": to, "tokens": [{"w": w["w"], "e": w["em"]} for w in c]})
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("words")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--fps", type=float, default=30)
    ap.add_argument("--pause", type=float, default=0.35)
    ap.add_argument("--max-tokens", type=int, default=5)
    ap.add_argument("--max-seconds", type=float, default=2.2)
    ap.add_argument("--emphasis", action="append", default=[], help="phrase to emphasise, repeatable")
    a = ap.parse_args()
    words = load_words(a.words)
    nb = mark_emphasis(words, a.emphasis)
    cues = build(words, a.fps, a.pause, a.max_tokens, a.max_seconds, nb)
    Path(a.output).write_text(json.dumps(cues, indent=1))
    hit = sum(any(t["e"] for t in c["tokens"]) for c in cues)
    print(f"{len(words)} words -> {len(cues)} cues, {hit} with emphasis -> {a.output}")
    missing = [p for p in a.emphasis if not any(norm(p).replace(' ', '') == ''.join(norm(t['w']) for t in c['tokens'] if t['e']) or norm(p) in ' '.join(norm(t['w']) for t in c['tokens']) for c in cues)]
    if missing:
        print("emphasis phrases not found in the transcript:", missing)


if __name__ == "__main__":
    main()
