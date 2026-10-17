#!/usr/bin/env python3
"""Place sound effects into plan.json from a sound-design map. Run AFTER the plan is written (writing
the plan again drops them).

    add_sfx.py <project> <sfx_map.json> [--library DIR]      (or set SFX_LIBRARY)

Every sound is tied to something that VISIBLY happens. Generic cues on a piece to camera read as cheap,
and an edit with no sound at all reads as unfinished. Each file fires at (beat - its measured peak time)
so its loudest moment lands on the beat. Files are copied into remotion/public/sfx/.
Mix onto an existing render without re-rendering with mix_sfx.py.

sfx_map.json, every entry [file relative to the library, linear volume]; omit a key to skip it:
    {
      "transition": ["whoosh/soft-01.wav", 0.016],   in and out of every scene / screen window
      "hero":       ["impact/soft-02.wav", 0.02],    a bigWord or hero3d landing
      "hard_punch": ["whoosh/light-03.wav", 0.012],  punches with preset "hard"
      "card":       ["ui/tick-01.wav", 0.011],       each side card arriving
      "click":      ["ui/click-02.wav", 0.011],      each cursor click in a screen scene
      "asset":      ["impact/soft-01.wav", 0.016],   each asset3d arrival
      "extra": [{"frame": 412, "file": "ui/ping.wav", "volume": 0.011, "reason": "chip appears"}]
    }
Levels: subtle. Audible when you listen for them, never competing with the voice. Starting points above
are for a voice normalized to about -14 LUFS; check by RMS envelope (median ~10 dB under the voice).
Free libraries: see docs/SETUP.md (Mixkit, Pixabay, freesound CC0). Check each file's licence.
"""
import argparse, json, os, shutil, wave
import numpy as np


def peak_s(path):
    w = wave.open(path)
    sr, ch = w.getframerate(), w.getnchannels()
    x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(float)
    if ch > 1:
        x = x.reshape(-1, ch).mean(1)
    hop = sr // 100
    n = len(x) // hop
    return int(np.argmax(np.sqrt((x[: n * hop].reshape(n, hop) ** 2).mean(1)))) / 100


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project"); ap.add_argument("sfx_map")
    ap.add_argument("--library", default=os.environ.get("SFX_LIBRARY"))
    a = ap.parse_args()
    if not a.library:
        raise SystemExit("set --library or SFX_LIBRARY to your folder of .wav sound effects")
    m = json.load(open(a.sfx_map))
    plan_path = f"{a.project}/remotion/plan.json"
    plan = json.load(open(plan_path))
    fps = plan.get("fps", 30)
    events = [e for e in plan["events"] if e["type"] != "sfx"]
    peaks, out = {}, []

    def add(frame_on_beat, spec, reason):
        if not spec:
            return
        rel, vol = spec
        if rel not in peaks:
            peaks[rel] = peak_s(f"{a.library}/{rel}")
            os.makedirs(os.path.dirname(f"{a.project}/remotion/public/sfx/{rel}"), exist_ok=True)
            shutil.copy(f"{a.library}/{rel}", f"{a.project}/remotion/public/sfx/{rel}")
        at = max(0, frame_on_beat - round(peaks[rel] * fps))
        out.append({"type": "sfx", "at": at, "src": f"sfx/{rel}", "volume": vol, "reason": reason, "_beat": frame_on_beat})

    for e in events:
        t = e["type"]
        if t in ("scene", "screen"):
            add(e["from"] + 4, m.get("transition"), f"transition into {t}")
            add(e["to"] - 4, m.get("transition"), f"transition out of {t}")
            for c in e.get("cursor", []) if t == "screen" else []:
                if c.get("click"):
                    add(c["at"], m.get("click"), "cursor click")
        elif t in ("bigWord", "hero3d"):
            add(e["at"], m.get("hero"), f"hero lands: {e.get('text', e.get('seq', {}).get('dir'))}")
        elif t == "punch" and e.get("preset") == "hard":
            add(e["at"], m.get("hard_punch"), "hard punch")
        elif t == "side":
            for c in e["cards"]:
                add(c["at"], m.get("card"), f"card {c['kind']}")
        elif t == "asset3d":
            add(e["at"], m.get("asset"), f"asset arrives: {e['seq']['dir']}")
    for x in m.get("extra", []):
        add(x["frame"], [x["file"], x["volume"]], x.get("reason", "extra"))

    out.sort(key=lambda s: s["_beat"])
    kept = []
    for s in out:  # two sounds on the same beat read as one mistake
        if kept and s["_beat"] - kept[-1]["_beat"] < 3:
            continue
        kept.append(s)
    for s in kept:
        s.pop("_beat")
    plan["events"] = events + kept
    json.dump(plan, open(plan_path, "w"), indent=2, ensure_ascii=False)
    print(f"{len(kept)} sfx placed ({len(out) - len(kept)} dropped as same-beat duplicates)")


if __name__ == "__main__":
    main()
