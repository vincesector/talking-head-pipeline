"""Plan writer: every timing in the plan is resolved from words.json BY TEXT, never typed frames.

    import sys; sys.path.insert(0, "scripts")
    from plan_common import load, write
    ws, n, (w, h) = load(project)
    write(project, ws, n, (w, h), beats, hero, rotos, events, accent, emphasis)

Anchors are "phrase@hint": the occurrence of that phrase (one or more words) nearest `hint`
seconds. A start key resolves to the first word's START, an end key to the last word's END.

beats: [(land, preset, until, reason)]
    land  = "phrase@hint": the punch ARRIVES on the start of that phrase (the move starts before it)
    until = "phrase@hint": the hold runs to the END of that phrase (the end of the sentence, the next
            pause, or the word before a softener like "but"), then the preset's release plays.
            A punch-out is a transcript decision, never a countdown.
            An int is accepted only for a hero micro-push (hold in frames).
    Every landing must be >= MIN_GAP frames after the previous release ends, or the script refuses.
hero:  None, or {"land", "hold", "lines", "size", "y", "reason", "roto": (before, after) frames, "roto_reason"}
rotos: extra roto windows [("phrase@hint", "phrase@hint", reason)]
events: extra plan events (scatter, logo, scene, side, screen, hero3d, asset3d, endcard). Keys
        "at"/"from" resolve to a word START and "to"/"until" to a word END, also inside nested
        lists (side cards' "at", screen zoom/cursor "at", card "punches"). Every event needs a
        reason and word anchors for BOTH its entry and its exit.
"""
import json, re, subprocess, sys

PRESET = {"micro": (8, 12), "standard": (8, 12), "hard": (6, 10), "sustain": (14, 18)}  # mirrors lib/punchIn.ts
MIN_HOLD, MAX_HOLD, MIN_GAP = 18, 240, 91
FPS = 30


def norm(s): return re.sub(r"[^\w]", "", s.lower())


def load(project):
    ws = json.load(open(f"{project}/remotion/public/words.json"))
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=nb_frames,width,height",
                        "-of", "json", f"{project}/remotion/public/raw.mp4"], capture_output=True, text=True, check=True)
    st = json.loads(r.stdout)["streams"][0]
    return ws, int(st["nb_frames"]), (int(st["width"]), int(st["height"]))


def find(ws, anchor):
    text, _, hint = anchor.partition("@"); hint = float(hint) if hint else 0.0
    toks = [norm(t) for t in text.split()]
    c = [i for i in range(len(ws) - len(toks) + 1) if [norm(w["text"]) for w in ws[i:i + len(toks)]] == toks]
    if not c: sys.exit(f"plan: phrase not found in words.json: {text!r}")
    i = min(c, key=lambda i: abs(ws[i]["startMs"] / 1000 - hint))
    return ws[i], ws[i + len(toks) - 1]


def start_frame(ws, anchor): return round(find(ws, anchor)[0]["startMs"] / 1000 * FPS)
def end_frame(ws, anchor): return round(find(ws, anchor)[1]["endMs"] / 1000 * FPS)


def resolve(ws, obj):
    """Resolve every word anchor in an event, recursively."""
    if isinstance(obj, list):
        return [resolve(ws, x) for x in obj]
    if not isinstance(obj, dict):
        return obj
    out = {}
    for k, v in obj.items():
        if k in ("at", "from") and isinstance(v, str): out[k] = start_frame(ws, v)
        elif k in ("to", "until", "out") and isinstance(v, str): out[k] = end_frame(ws, v)
        else: out[k] = resolve(ws, v)
    if out.get("type") == "scatter" and "until" in out:
        out["hold"] = max(1, out.pop("until") - out["at"])
    return out


def write(project, ws, nframes, size, beats, hero=None, rotos=(), events=(), accent=None, emphasis=(), lens=None):
    width, height = size
    punches, prev_release, ok = [], -10 ** 6, True
    for land, preset, until, reason in beats:
        at = start_frame(ws, land)
        if isinstance(until, int):
            hold, rel = until, f"held {until} frames (hero)"
        else:
            hold = min(MAX_HOLD, max(MIN_HOLD, end_frame(ws, until) - at)); rel = f"releases after {until.split('@')[0]!r}"
        gap = at - prev_release; ok &= gap >= MIN_GAP
        print(f"{at:5d} {at / FPS:6.2f}s {preset:8s} hold {hold:3d}  lands on {land.split('@')[0]!r}, {rel}"
              f"{'' if gap >= MIN_GAP else '  <-- ' + str(gap) + ' frames after the previous release'}")
        punches.append({"type": "punch", "at": at, "hold": hold, "preset": preset, "reason": f"{reason}; {rel}"})
        prev_release = at + hold + PRESET[preset][1]
    roto_events, big = [], []
    if hero:
        hero_at = start_frame(ws, hero["land"])
        roto_events.append({"type": "roto", "from": max(0, hero_at + hero["roto"][0]), "to": min(nframes - 1, hero_at + hero["roto"][1]),
                            "reason": hero.get("roto_reason", hero["reason"])})
        big = [{"type": "bigWord", "at": hero_at, "hold": hero["hold"], "lines": hero["lines"], "text": " ".join(hero["lines"]),
                "face": hero.get("face", "anton"), "size": hero["size"], "y": hero["y"], "reason": hero["reason"]}]
    for a, b, reason in rotos:
        roto_events.append({"type": "roto", "from": max(0, start_frame(ws, a) - 6), "to": min(nframes - 1, end_frame(ws, b) + 6), "reason": reason})
    for e in events:  # every effect enters AND leaves on a spoken word, with a reason
        ins, outs = [k for k in ("at", "from") if k in e], [k for k in ("to", "until") if k in e]
        bad = [k for k in ins + outs if not isinstance(e[k], str)]
        if not e.get("reason") or not ins or not outs or bad:
            ok = False; print(f"  <-- {e['type']} needs a reason and word anchors for entry and exit, got {ins + outs}, typed frames {bad}")
    extra = [resolve(ws, e) for e in events]
    for e in extra:  # a full-frame window (scene, screen) hides the face: no punch may land inside it
        if e["type"] in ("scene", "screen"):
            inside = [p["at"] for p in punches if e["from"] <= p["at"] <= e["to"]]
            if inside: ok = False; print(f"  <-- punch landings inside the {e['type']} window {e['from']}-{e['to']}: {inside}")
        if e.get("behind") and not any(r["from"] <= e.get("at", e.get("seq", {}).get("f0", -1)) <= r["to"] for r in roto_events):
            print(f"  note: {e['type']} has behind=true but starts outside every roto window; it will sit in front there")
    plan = {"source": "raw.mp4", "fps": FPS, "width": width, "height": height, "durationInFrames": nframes,
            "zoomHeadroom": 1.0, "lens": lens, "cutDir": "cut",
            "captions": {"pairing": "inter-instrument", "trackedUntil": 0, **({"accent": accent} if accent else {})},
            "events": roto_events + big + extra + punches}
    json.dump(plan, open(f"{project}/remotion/plan.json", "w"), indent=2, ensure_ascii=False)
    roto_s = sum(r["to"] - r["from"] for r in roto_events) / FPS
    print(f"roto {roto_s:.1f}s in {len(roto_events)} windows | punches {len(punches)} | extra {[e['type'] for e in extra]} | "
          f"spacing ok: {ok} | {width}x{height}, {nframes} frames")
    cmd = ["python3", f"{project}/scripts/build_cues.py", f"{project}/remotion/public/words.json", "--fps", str(FPS),
           "-o", f"{project}/remotion/public/captions.json"]
    for e in emphasis: cmd += ["--emphasis", e]
    print(subprocess.run(cmd, capture_output=True, text=True).stdout.strip())
    if not ok: sys.exit("plan: spacing, anchor or window violation; fix the beats")
