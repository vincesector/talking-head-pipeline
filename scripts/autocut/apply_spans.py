#!/usr/bin/env python3
"""Split an autocut plan's keep ranges around drop spans defined by WORDS, not by
typed timestamps. Each span is "first dropped word @ time -> first kept word @ time",
resolved against the verbatim word list so the numbers come from the transcript.

    apply_spans.py <workdir> --span 2.50:7.76 --span 18.08:27.16 ...

A span "A:B" drops [start of the word at A, start of the word at B). Times must
match a verbatim word start within 0.15 s or the script refuses. Prints, for
each span, the words dropped and the words that now follow, then rewrites
plan.json's keep list from the raw duration minus every span.
"""
import argparse, json, sys
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("workdir"); ap.add_argument("--span", action="append", default=[])
ap.add_argument("--drop", action="append", default=[], help='"words to drop@time hint": drops that phrase occurrence nearest the hint, up to the next word')
ap.add_argument("--reset", action="store_true", help="start from a single full keep range (default: keep existing splits too)")
a = ap.parse_args()
wd = Path(a.workdir)
plan = json.loads((wd / "plan.json").read_text())
vb = json.loads((wd / "verbatim.json").read_text()); words = vb["words"] if isinstance(vb, dict) else vb
info = json.loads((wd / "info.json").read_text()); dur = info["probe"]["duration"]

def word_at(t):
    best = min(words, key=lambda w: abs(w["start"] - t))
    if abs(best["start"] - t) > 0.15: sys.exit(f"no word starts near {t}: nearest {best['word']!r} at {best['start']}")
    return best

def norm(x): return "".join(ch for ch in x.lower() if ch.isalnum())
for d in a.drop:
    text, _, hint = d.partition("@"); toks = [norm(t) for t in text.split()]; hint = float(hint) if hint else 0.0
    cands = [i for i in range(len(words) - len(toks) + 1) if [norm(w["word"]) for w in words[i:i + len(toks)]] == toks]
    if not cands: sys.exit(f"phrase not found: {text!r}")
    i = min(cands, key=lambda i: abs(words[i]["start"] - hint))
    j = i + len(toks)
    if j >= len(words): sys.exit(f"phrase {text!r} runs to the end of the transcript")
    a.span.append(f"{words[i]['start']}:{words[j]['start']}")
spans = []
for s in a.span:
    x, y = (float(v) for v in s.split(":"))
    wa, wb = word_at(x), word_at(y)
    ia, ib = words.index(wa), words.index(wb)
    dropped = " ".join(w["word"] for w in words[ia:ib]); after = " ".join(w["word"] for w in words[ib:ib + 7])
    before = " ".join(w["word"] for w in words[max(0, ia - 5):ia])
    spans.append((wa["start"], wb["start"]))
    print(f"[{wa['start']:.2f}-{wb['start']:.2f}] drop {dropped!r}\n      -> ...{before} | {after}")

keeps = [(0.0, dur)] if a.reset else [tuple(k) for k in plan["keep"]]
for x, y in sorted(spans):
    out = []
    for k0, k1 in keeps:
        if y <= k0 or x >= k1: out.append((k0, k1)); continue
        if x > k0: out.append((k0, x))
        if y < k1: out.append((y, k1))
    keeps = out
plan["keep"] = [[round(k0, 3), round(k1, 3)] for k0, k1 in keeps]
# content_cuts = every gap between the keep ranges (plus the leading gap), so earlier
# reviewed cuts keep their pinned edges and their "approved" audit status.
gaps = []
prev = 0.0
for k0, k1 in plan["keep"]:
    if k0 - prev > 1e-3: gaps.append((prev, k0))
    prev = k1
plan.setdefault("_meta", {})["content_cuts"] = [{"from": round(x, 3), "to": round(y, 3), "reason": "stumble, reviewed"} for x, y in gaps]
(wd / "plan.json").write_text(json.dumps(plan, indent=2))
print("keep:", plan["keep"]); print("removed by spans: %.2f s" % sum(y - x for x, y in spans))
