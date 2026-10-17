#!/usr/bin/env python3
"""Snap every content-cut edge in plan.json to real silence and cut the noises between phrases.

    snap_edges.py <workdir> [--dry-run]

Why: cuts decided from transcript word times
left fragments ("sá-", a leaked "já", the tail of a dropped "você") and throat/lip noises between
phrases. CrisperWhisper's word edges drift 200-400 ms on fast takes, and the verbatim
text itself can be wrong on a triple restart, so words cannot place a cut. The waveform can: on a gated
mic, silence is true digital silence and every sound is a run of energy.

Three passes, all on audio.wav (the synced timeline plan.json uses):
1. Head and tail: the video starts on the run that holds the first real word and ends after the run
   that holds the last one. Mic checks, throat clears and room noise outside them go.
2. Edges: a content-cut edge that lands inside a sound run moves to that run's boundary. The run
   goes to whichever side holds most of it (a dropped word's tail leaves with the dropped word, a
   kept word's clipped onset comes back).
3. Noises between phrases: bracket tokens ([UH], [UM], [lipsmack], [throatclearing], [laughter],
   [breath] ...) inside a kept range with >= 0.4 s between the neighbouring words are cut from the
   silence after the previous word's run to the silence before the next one, leaving 0.1 s of air
   on each side.
Edges listed in _meta.pinned_edges (hand-checked against the waveform) are never moved.
Every changed edge is added to _meta.content_cuts so the cutter pins it and the removed-span audit
treats it as approved. Verify afterwards by re-transcribing the render (see skills/autocut/SKILL.md, "Verify the cut").
"""
import argparse, json, re, wave
import numpy as np

TH_DB = -45.0      # speech/noise floor; a gated mic sits at digital silence between words
MERGE_GAP = 0.04   # quieter dips shorter than this stay inside one run
AIR = 0.10         # silence left on each side of a cut
GUARD = 0.05       # minimum distance from an edge to the sound it removes (frame grid is 33 ms)
TAIL = 0.20        # kept after the last sound of a kept word (soft endings decay below TH_DB)
LEAD = 0.12        # kept before the first sound of a kept word
NOISE = re.compile(r"^\[(uh|um|hmm|ah|er|eh|lipsmack|throatclearing|laughter|breath|breathing|cough|sigh|noise|click)\][.,?!]*$", re.I)


def energy(wav_path):
    w = wave.open(wav_path)
    sr, ch = w.getframerate(), w.getnchannels()
    x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(float) / 32768
    if ch > 1:
        x = x.reshape(-1, ch).mean(1)
    hop = sr // 100
    n = len(x) // hop
    return 20 * np.log10(np.sqrt((x[: n * hop].reshape(n, hop) ** 2).mean(1)) + 1e-9)


def runs_of(e):
    loud = e > TH_DB
    runs, i, n = [], 0, len(e)
    while i < n:
        if loud[i]:
            j = i
            while j < n and loud[j]:
                j += 1
            runs.append([i / 100, j / 100])
            i = j
        else:
            i += 1
    merged = []
    for r in runs:
        if merged and r[0] - merged[-1][1] < MERGE_GAP:
            merged[-1][1] = r[1]
        else:
            merged.append(r)
    return merged


def run_at(runs, t):
    for a, b in runs:
        if a < t < b:
            return a, b
    return None


def flat_words(x, out):
    if isinstance(x, dict):
        if ("word" in x or "text" in x) and "start" in x and "end" in x and not any(k in x for k in ("segments", "words")):
            out.append(x)
            return
        for y in x.values():
            flat_words(y, out)
    elif isinstance(x, list):
        for y in x:
            flat_words(y, out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("workdir")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    wd = args.workdir
    plan = json.load(open(f"{wd}/plan.json"))
    e = energy(f"{wd}/audio.wav")
    runs = runs_of(e)
    words = []
    flat_words(json.load(open(f"{wd}/verbatim.json")), words)
    text = lambda w: (w.get("word") or w.get("text")).strip()
    real = [w for w in words if not text(w).startswith("[")]
    keep = [list(k) for k in plan["keep"]]
    pinned = plan.get("_meta", {}).get("pinned_edges", [])  # hand-verified edges, never moved
    is_pinned = lambda t: any(abs(t - q) < 0.005 for q in pinned)
    log = []

    def inside(t):
        return any(a <= t <= b for a, b in keep)

    # 1. head and tail
    kept_real = [w for w in real if inside((w["start"] + w["end"]) / 2)]
    first, last = kept_real[0], kept_real[-1]
    r = run_at(runs, first["start"] + 0.02) or next(((a, b) for a, b in runs if a >= first["start"] - 0.3), None)
    head = max(0.0, (r[0] if r else first["start"]) - AIR)
    if head > keep[0][0] + 0.05:
        log.append(f"head   {keep[0][0]:.2f} -> {head:.2f} (before '{text(first)}')")
        while keep and keep[0][1] <= head:
            keep.pop(0)
        keep[0][0] = max(keep[0][0], head)  # trimming only; never reach back into a removed take
    r = run_at(runs, last["end"] - 0.02) or next(((a, b) for a, b in reversed(runs) if b <= last["end"] + 0.3), None)
    tail = (r[1] if r else last["end"]) + 0.3
    if tail < keep[-1][1] - 0.05:
        log.append(f"tail   {keep[-1][1]:.2f} -> {tail:.2f} (after '{text(last)}')")
        while keep and keep[-1][0] >= tail:
            keep.pop()
        keep[-1][1] = min(keep[-1][1], tail)

    # 2. content-cut edges out of sound runs
    for i in range(len(keep) - 1):
        for side in (1, 0):
            k = keep[i] if side == 1 else keep[i + 1]
            t = k[side]
            r = run_at(runs, t)
            if not r or is_pinned(t):
                continue
            a, b = r
            if side == 1:   # piece ends inside a run: keep the run if most of it is kept, else drop it
                new = b + AIR if (t - a) >= (b - t) else a - AIR / 2
            else:           # piece starts inside a run
                new = a - AIR if (b - t) >= (t - a) else b + AIR / 2
            k[side] = round(new, 3)
            log.append(f"edge   {'end ' if side else 'start'} {t:.2f} -> {new:.2f} (sound run {a:.2f}-{b:.2f})")

    # 2b. every edge sits inside a silence, >= GUARD from the sound on the removed side (the cutter
    # rounds edges to the 33 ms frame grid, so an edge touching a run leaks its onset or tail) and
    # with TAIL after the last kept sound / LEAD before the next, so words keep their decay and the
    # pause between sentences keeps its rhythm (0.1 s of air made "parece magia. Então" run together)
    for i in range(len(keep) - 1):
        for side in (1, 0):
            k = keep[i] if side == 1 else keep[i + 1]
            t = k[side]
            if run_at(runs, t) or is_pinned(t):
                continue
            g0 = max([b for a, b in runs if b <= t], default=0.0)
            g1 = min([a for a, b in runs if a >= t], default=t + 1.0)
            lo, hi = (g0 + TAIL, g1 - GUARD) if side == 1 else (g0 + GUARD, g1 - LEAD)
            new = (g0 + g1) / 2 if lo > hi else min(max(t, lo), hi)
            if abs(new - t) > 0.005:
                k[side] = round(new, 3)
                log.append(f"guard  {'end ' if side else 'start'} {t:.2f} -> {new:.2f} (silence {g0:.2f}-{g1:.2f})")

    # 3. noises between phrases
    for j, w in enumerate(words):
        if not NOISE.match(text(w)) or not inside((w["start"] + w["end"]) / 2):
            continue
        prev = next((u for u in reversed(words[:j]) if not text(u).startswith("[")), None)
        nxt = next((u for u in words[j + 1:] if not text(u).startswith("[")), None)
        if not prev or not nxt or nxt["start"] - prev["end"] < 0.4:
            continue
        pr = run_at(runs, prev["end"] - 0.03)
        nr = run_at(runs, nxt["start"] + 0.03)
        a = (pr[1] if pr else prev["end"]) + TAIL
        b = (nr[0] if nr else nxt["start"]) - LEAD
        if b - a < 0.15:
            continue
        out = []
        for k0, k1 in keep:
            if b <= k0 or a >= k1:
                out.append([k0, k1])
                continue
            if a > k0:
                out.append([k0, round(a, 3)])
            if b < k1:
                out.append([round(b, 3), k1])
        keep = out
        log.append(f"noise  {a:.2f}-{b:.2f} {text(w)} between '{text(prev)}' and '{text(nxt)}'")

    keep = [k for k in keep if k[1] - k[0] > 0.12]
    merged = []
    for k in sorted(keep):
        if merged and k[0] <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], k[1])
        else:
            merged.append(k)
    keep = merged
    print("\n".join(log) or "nothing to snap")
    print(f"{len(log)} changes, {len(plan['keep'])} -> {len(keep)} keep ranges, "
          f"{sum(b - a for a, b in plan['keep']):.2f}s -> {sum(b - a for a, b in keep):.2f}s kept")
    if args.dry_run:
        return
    json.dump(plan, open(f"{wd}/plan.pre-snap.json", "w"), indent=2, ensure_ascii=False)
    plan["keep"] = keep
    gaps, prev = [], None
    for a, b in keep:
        if prev is not None:
            gaps.append({"from": prev, "to": a, "reason": "snapped to silence"})
        prev = b
    plan["_meta"]["content_cuts"] = gaps
    json.dump(plan, open(f"{wd}/plan.json", "w"), indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
