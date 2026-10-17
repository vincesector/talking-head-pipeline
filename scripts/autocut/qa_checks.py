#!/usr/bin/env python3
"""Render QA that does not trust mlx-whisper (added after a cut shipped with restarts that a smoothed transcript hid).

Three checks, all appended to workdir/qa.md:

  1. Verbatim of the cut: CrisperWhisper over clean.mp4's audio -> qa/verbatim_cut.json and
     qa/verbatim_cut.txt (full text, one line per pause). mlx-whisper smooths repeats away, so a
     restart that survived the cut is invisible to it. The .txt is what a human reads end to end.
  2. Restarts still in the cut: find_restarts.py over that verbatim. Number-sequence matches
     ("nine hundred and twenty-eight" vs "thirty-nine") can be false positives; read, don't trust.
  3. Edge clipping: for every kept range edge, 5 ms RMS frames on audio.wav. Sound (> -55 dB) running
     >= 20 ms right BEFORE a start means the onset was clipped ("ex-" cut off "expiring" because the
     verbatim word time was 190 ms after the real onset); sound running >= 20 ms past an end means
     the tail was clipped. fix_starts() moves a clipped start back into the removed span and pins it.

    qa_checks.py <workdir> [--edges-only] [--fix]     (standalone; autocut.py --render runs it too)
"""
import argparse, json, subprocess, wave
from pathlib import Path

import numpy as np

import find_restarts

FRAME = 0.005
TH_DB = -55.0
MIN_RUN = 0.020
FIX_AIR = 0.03  # silence left before a restored onset


def fmt_ts(s):
    m, sec = divmod(abs(s), 60)
    return f"{'-' if s < 0 else ''}{int(m):02d}:{sec:05.2f}"


def frame_db(wav_path):
    w = wave.open(str(wav_path))
    sr, ch = w.getframerate(), w.getnchannels()
    x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(float) / 32768
    if ch > 1:
        x = x.reshape(-1, ch).mean(1)
    hop = int(round(sr * FRAME))
    n = len(x) // hop
    return 20 * np.log10(np.sqrt((x[: n * hop].reshape(n, hop) ** 2).mean(1)) + 1e-9)


def edge_scan(wav_path, ranges):
    """Returns [{"kind": "START"|"END", "t", "other", "run"}]. For START, `other` is the onset of the
    sound running up to the edge (the silence point); for END, where the sound that continues ends."""
    db = frame_db(wav_path)
    loud = db > TH_DB
    n = len(loud)
    out = []
    for i, (s, e) in enumerate(ranges):
        if i > 0:
            f = int(s / FRAME + 1e-6)  # frames [0, f) lie fully before s
            j = f
            while j > 0 and loud[j - 1]:
                j -= 1
            if (f - j) * FRAME >= MIN_RUN - 1e-9:
                out.append({"kind": "START", "t": s, "other": round(j * FRAME, 3), "run": (f - j) * FRAME})
        if i < len(ranges) - 1:
            f = int(np.ceil(e / FRAME - 1e-6))  # first frame fully after e
            j = f
            while j < n and loud[j]:
                j += 1
            if (j - f) * FRAME >= MIN_RUN - 1e-9:
                out.append({"kind": "END", "t": e, "other": round(j * FRAME, 3), "run": (j - f) * FRAME})
    return out


def fix_starts(plan, flags):
    """Move each clipped START back to its silence point when that point lies inside the removed span
    (after the previous kept range). Pins the new edge. Returns the list of (old, new)."""
    keep = plan["keep"]
    pinned = plan.get("_meta", {}).get("pinned_edges", [])  # hand-verified against the waveform: never moved
    fixed = []
    for fl in flags:
        if fl["kind"] != "START" or any(abs(fl["t"] - q) < 0.006 for q in pinned):
            continue
        for i in range(1, len(keep)):
            if abs(keep[i][0] - fl["t"]) < 0.006:
                new = round(fl["other"] - FIX_AIR, 3)
                if new > keep[i - 1][1] + 0.005 and new < keep[i][0]:
                    old = keep[i][0]
                    keep[i][0] = new
                    plan.setdefault("_meta", {}).setdefault("pinned_edges", []).append(new)
                    fixed.append((old, new))
    return fixed


def edges_section(flags, source_label, fixed=()):
    lines = ["## Edge clipping", "",
             f"Sound above {TH_DB:.0f} dB (5 ms RMS frames) running >= {MIN_RUN * 1000:.0f} ms across a cut edge, "
             f"scanned on {source_label}.", ""]
    if not flags:
        lines.append("None: no clipped onset or tail.")
    for fl in flags:
        if fl["kind"] == "START":
            lines.append(f"- FLAGGED START {fl['t']:.2f}: onset clipped, silence at {fl['other']:.2f} "
                         f"({fl['run'] * 1000:.0f} ms of sound before the edge)")
        else:
            lines.append(f"- FLAGGED END {fl['t']:.2f}: tail clipped, sound continues to {fl['other']:.2f} "
                         f"({fl['run'] * 1000:.0f} ms past the edge)")
    for old, new in fixed:
        lines.append(f"- auto-fixed before render: START {old:.2f} -> {new:.2f} (pinned in plan.json)")
    return "\n".join(lines) + "\n"


def cut_verbatim(workdir, clean, run_verbatim, lang):
    qa = Path(workdir) / "qa"
    qa.mkdir(exist_ok=True)
    wav = qa / "cut_audio.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(clean), "-ar", "16000", "-ac", "1",
                    "-c:a", "pcm_s16le", str(wav)], check=True)
    words = run_verbatim(wav, lang)
    (qa / "verbatim_cut.json").write_text(json.dumps(words, indent=2, ensure_ascii=False))
    lines, cur, last_end = [], [], None
    for w in words:
        if cur and w["start"] - last_end > 0.5:
            lines.append(cur)
            cur = []
        if not cur:
            cur_start = w["start"]
            cur = [cur_start]
        cur.append(w["word"].strip())
        last_end = w["end"]
    if cur:
        lines.append(cur)
    txt = "\n".join(f"[{fmt_ts(l[0])}] " + " ".join(l[1:]) for l in lines) + "\n"
    (qa / "verbatim_cut.txt").write_text(txt)
    return qa / "verbatim_cut.json", qa / "verbatim_cut.txt"


def restarts_section(spans, txt_path):
    lines = ["## Restarts still in the cut", "",
             f"find_restarts.py over the CrisperWhisper verbatim of the cut ({txt_path}). Number-sequence matches "
             "(e.g. 928 vs 939) can be false positives; read the text and decide.", ""]
    if not spans:
        lines.append("None found.")
    for s in spans:
        lines.append(f"- FLAGGED [{fmt_ts(s['from'])}-{fmt_ts(s['to'])}] restart on '{s['phrase']}', "
                     f"the cut contains: {s['dropped']!r} ... then the retake")
    return "\n".join(lines) + "\n"


NOTE = ("Read qa/verbatim_cut.txt end to end before showing anyone; mlx-whisper transcripts hide repeats, "
        "never use them to check a cut.")


def replace_section(content, heading, section):
    """Replace `## heading` up to the next `## ` (or append)."""
    i = content.find(heading)
    if i == -1:
        return content.rstrip() + "\n\n" + section
    j = content.find("\n## ", i + len(heading))
    tail = content[j:] if j != -1 else ""
    return content[:i] + section.rstrip() + "\n" + (("\n" + tail.lstrip("\n")) if tail else "")


def write_sections(workdir, sections):
    path = Path(workdir) / "qa.md"
    content = path.read_text() if path.exists() else f"# QA: {Path(workdir).name}\n"
    for heading, section in sections:
        content = replace_section(content, heading, section)
    if NOTE not in content:
        head, _, rest = content.partition("\n")
        content = f"{head}\n\n**{NOTE}**\n{rest}"
    path.write_text(content)


def render_edge_ranges(workdir):
    wd = Path(workdir)
    tm = wd / "timemap.json"
    if tm.exists():
        return [(e["srcStart"], e["srcEnd"]) for e in json.loads(tm.read_text())["entries"]], "the rendered pieces (timemap.json)"
    return [tuple(k) for k in json.loads((wd / "plan.json").read_text())["keep"]], "plan.json keep ranges"


def run_qa(workdir, run_verbatim=None, lang="en", edges_only=False):
    wd = Path(workdir)
    ranges, label = render_edge_ranges(wd)
    flags = edge_scan(wd / "audio.wav", ranges)
    sections = [("## Edge clipping", edges_section(flags, label))]
    spans = []
    if not edges_only:
        plan = json.loads((wd / "plan.json").read_text())
        _, txt = cut_verbatim(wd, plan["output"], run_verbatim, lang)
        spans = find_restarts.find(find_restarts.load_path(wd / "qa" / "verbatim_cut.json"), 12.0, 3)
        sections.insert(0, ("## Restarts still in the cut", restarts_section(spans, txt)))
    write_sections(wd, sections)
    print(f"edge clipping: {len(flags)} flagged")
    for fl in flags:
        print(f"  {fl['kind']} {fl['t']:.2f} -> sound edge {fl['other']:.2f}")
    if not edges_only:
        print(f"restarts in the cut: {len(spans)} flagged (read {wd / 'qa' / 'verbatim_cut.txt'})")
        for s in spans:
            print(f"  [{s['from']:.2f}-{s['to']:.2f}] '{s['phrase']}'")
    return flags, spans


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("workdir")
    ap.add_argument("--edges-only", action="store_true", help="skip the verbatim pass (no CrisperWhisper run)")
    ap.add_argument("--plan", help="scan this plan json's keep ranges instead of timemap.json (does not write qa.md)")
    a = ap.parse_args()
    if a.plan:
        keep = [tuple(k) for k in json.load(open(a.plan))["keep"]]
        for fl in edge_scan(Path(a.workdir) / "audio.wav", keep):
            print(f"FLAGGED {fl['kind']} {fl['t']:.2f}: clipped, sound edge at {fl['other']:.2f}")
        return
    if a.edges_only:
        run_qa(a.workdir, edges_only=True)
    else:
        import autocut
        wd = Path(a.workdir)
        run_qa(wd, autocut.run_verbatim, autocut.workdir_lang(wd))


if __name__ == "__main__":
    main()
