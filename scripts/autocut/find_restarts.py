#!/usr/bin/env python3
"""Find restarts that find_stumbles.py misses: a phrase said, abandoned, and said again
after a pause or after a half sentence. Keeps the LAST take.

    find_restarts.py <workdir> [--window 12] [--min-ngram 3] [--json out.json]

Why: "expiring, exp-, expiring", "there will be a loss at
about" said three times across ~8 s, and "and under about. [4 s] and under about" all
survived the cut. find_stumbles only drops immediate repeats, so a restart with a pause
or a different tail between the takes was invisible, and the mlx-whisper transcript used
to check the cut smoothed the repeats away. This pass works on the verbatim words only.

Rule: an n-gram (>= --min-ngram normalized tokens, or a single word whose two takes are
separated only by fragments like "exp-") that occurs again within --window seconds is a
restart. The span from the first take's first word to the last take's first word is
dropped. Chains (three takes) collapse to the last one.
"""
import argparse, json, re


def norm(t):
    return re.sub(r"[^a-z0-9'-]", "", t.lower()).strip("'")


def load(workdir):
    return load_path(f"{workdir}/verbatim.json")


def load_path(path):
    v = json.load(open(path))
    w = v["words"] if isinstance(v, dict) else v
    out = []
    for x in w:
        t = x.get("word", x.get("text", ""))
        if t.startswith("["):
            continue
        out.append({"t": t, "n": norm(t), "s": x["start"], "e": x["end"], "frag": t.rstrip(".,?!").endswith("-")})
    return out


def find(words, window, nmin):
    toks = [w for w in words if not w["frag"]]
    spans = []
    i = 0
    while i < len(toks):
        best = None
        for n in range(8, nmin - 1, -1):
            if i + n > len(toks):
                continue
            g = [t["n"] for t in toks[i:i + n]]
            for j in range(i + n, len(toks) - n + 1):
                if toks[j]["s"] - toks[i]["s"] > window:
                    break
                if [t["n"] for t in toks[j:j + n]] == g:
                    best = (i, j, n)
                    break
            if best:
                break
        # single word restarted with only fragments between it and its retake
        if not best and i + 1 < len(toks) and toks[i]["n"] == toks[i + 1]["n"] and len(toks[i]["n"]) > 2:
            between = [w for w in words if toks[i]["e"] <= w["s"] < toks[i + 1]["s"]]
            if between and all(w["frag"] for w in between):
                best = (i, i + 1, 1)
        if best:
            a, j, n = best
            # follow the chain: keep jumping while the same n-gram appears again in the window
            g = [t["n"] for t in toks[a:a + n]]
            k = j
            while True:
                nxt = next((m for m in range(k + n, len(toks) - n + 1)
                            if toks[m]["s"] - toks[k]["s"] <= window and [t["n"] for t in toks[m:m + n]] == g), None)
                if nxt is None:
                    break
                k = nxt
            spans.append({"from": toks[a]["s"], "to": toks[k]["s"], "ngram": n,
                          "auto": n == 1,  # single word + fragment: safe to apply without review
                          "phrase": " ".join(t["t"] for t in toks[a:a + n]),
                          "dropped": " ".join(w["t"] for w in words if toks[a]["s"] <= w["s"] < toks[k]["s"])})
            i = k
        else:
            i += 1
    return spans


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("workdir", help="workdir holding verbatim.json, or a verbatim json file")
    ap.add_argument("--window", type=float, default=12.0)
    ap.add_argument("--min-ngram", type=int, default=3)
    ap.add_argument("--json")
    a = ap.parse_args()
    words = load_path(a.workdir) if a.workdir.endswith(".json") else load(a.workdir)
    spans = find(words, a.window, a.min_ngram)
    for s in spans:
        print(f"[{s['from']:.2f}-{s['to']:.2f}] restart on '{s['phrase']}'  drops: {s['dropped']!r}")
    if a.json:
        json.dump(spans, open(a.json, "w"), indent=1)


if __name__ == "__main__":
    main()
