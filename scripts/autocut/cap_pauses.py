#!/usr/bin/env python3
"""Cap long pauses inside plan.json keep ranges without touching any word edge.

    cap_pauses.py <workdir> [--max 0.65] [--tail 0.30] [--lead 0.20] [--dry-run]

Sound is any 5 ms RMS frame of audio.wav above -55 dBFS, and one such frame ends a pause (no
bridging). A pause longer than --max is cut so it keeps --tail after the last sound and --lead
before the next, about 0.5 s heard, which is a natural speaking rhythm. The head and
tail of every kept piece are trimmed the same way, so two pieces meeting at a join never stack
into a longer gap. Pauses of --max or less are left alone.

Why this shape: the first version called anything under -42 dB silence, bridged 80 ms
blips, and pinned its edges. Word tails on a gated mic decay through -42..-55 dB for 50 ms or
more at 45% of phrase ends, so it cut final S's; the bridge swallowed short onsets ("That's"); and
pinning skipped snap_edges' clearance rules. Edges here are NOT pinned: snap_edges.py runs after
this pass and still validates them. Every cut is logged in _meta.content_cuts.
"""
import argparse, json, shutil, wave
import numpy as np

SOUND_DB = -55.0
HOP = 0.005


def energy(path):
    w = wave.open(str(path))
    x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(float) / 32768
    if w.getnchannels() > 1:
        x = x.reshape(-1, w.getnchannels()).mean(1)
    h = int(w.getframerate() * HOP)
    n = len(x) // h
    return 20 * np.log10(np.sqrt((x[: n * h].reshape(n, h) ** 2).mean(1)) + 1e-9)


def cap(keep, loud, max_pause, tail, lead):
    out, cuts = [], []
    for k0, k1 in keep:
        i0 = int(np.ceil(k0 / HOP))
        idx = np.flatnonzero(loud[i0:int(k1 / HOP)]) + i0
        cur = k0
        for p, q in zip(idx, idx[1:]):
            last, nxt = (p + 1) * HOP, q * HOP
            if nxt - last > max_pause:
                ca, cb = round(last + tail, 3), round(nxt - lead, 3)
                out.append([cur, ca])
                cuts.append({"from": ca, "to": cb, "reason": "cap_pauses"})
                cur = cb
        out.append([cur, k1])

    trimmed = []
    for n, (k0, k1) in enumerate(out):
        i0 = int(np.ceil(k0 / HOP))
        idx = np.flatnonzero(loud[i0:int(k1 / HOP)]) + i0
        if not len(idx):
            cuts.append({"from": k0, "to": k1, "reason": "cap_pauses silent piece"})
            continue
        first, last = idx[0] * HOP, (idx[-1] + 1) * HOP
        n0 = round(first - lead, 3) if n > 0 and first - k0 > lead else k0
        n1 = round(last + tail, 3) if n < len(out) - 1 and k1 - last > tail else k1
        if n0 != k0:
            cuts.append({"from": k0, "to": n0, "reason": "cap_pauses join"})
        if n1 != k1:
            cuts.append({"from": n1, "to": k1, "reason": "cap_pauses join"})
        trimmed.append([n0, n1])
    return trimmed, cuts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("workdir")
    ap.add_argument("--max", type=float, default=0.65, help="longest pause left untouched (s)")
    ap.add_argument("--tail", type=float, default=0.30, help="silence kept after the last sound (s)")
    ap.add_argument("--lead", type=float, default=0.20, help="silence kept before the next sound (s)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    plan_p = f"{a.workdir}/plan.json"
    plan = json.load(open(plan_p))
    loud = energy(f"{a.workdir}/audio.wav") > SOUND_DB
    keep, cuts = cap(plan["keep"], loud, a.max, a.tail, a.lead)
    print(f"cap_pauses: {len(cuts)} cuts, pauses over {a.max}s capped to {a.tail + a.lead:.2f}s, "
          f"{sum(c['to'] - c['from'] for c in cuts):.1f}s removed")
    if a.dry_run or not cuts:
        return
    shutil.copy(plan_p, f"{a.workdir}/plan.pre-cappauses.json")
    plan["keep"] = keep
    plan.setdefault("_meta", {}).setdefault("content_cuts", []).extend(cuts)
    json.dump(plan, open(plan_p, "w"), indent=1)


if __name__ == "__main__":
    main()
