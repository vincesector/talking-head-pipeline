#!/usr/bin/env python3
"""Chain the sync, transcription and cutting tools into one raw-in, clean-out pipeline.

Reimplements nothing. Every stage below is a thin wrapper around a tool that
already exists and is individually proven:

  sync    sync/detect_sync.py + sync/fix_sync.sh
  audio   ffmpeg
  words   Whisper (whisper_backend.py: mlx-whisper on Apple Silicon, faster-whisper elsewhere),
          then align/align_words.py to re-time the edges
  cuts    autocut/cut_video.py (imported for its silence detector and its
          range-shaping functions during planning, shelled out to unchanged
          for the actual render)
  retakes align/find_retakes.py
  stumbles align/find_stumbles.py, fed by a CrisperWhisper verbatim pass.
          mlx-whisper SMOOTHS repetitions out of its own transcript (a
          stumble said twice comes back as one clean sentence), so
          find_retakes.py, which compares whole segments, never sees them.
          CrisperWhisper's verbatim mode transcribes every false start and
          self-repeat with tight word timing; find_stumbles.py finds them
          in that transcript and they are cut by default.

Two-run approval gate:

  autocut.py <raw.mp4> [--lang auto|en|pt|it|es|fr|de|nl] [--offset SECONDS | --no-sync] [--workdir DIR] [--force]
      Plan mode. Runs every stage through building plan.json + plan.md, then
      stops. Nothing is rendered. Read plan.md, edit plan.json by hand if you
      want to accept a retake proposal or change what's kept, then:

  autocut.py <raw.mp4> --render [--workdir DIR] [--force] [--no-cap-pauses]
      Render mode. Re-reads plan.json from disk (not from the first run's
      memory), caps long pauses on takes over 3 min (cap_pauses.py), snaps
      every edge to the waveform (snap_edges.py) and runs cut_video.py on it,
      then QAs the result into qa.md.

Every stage writes into <raw dir>/<raw stem>_autocut/ (or --workdir) and is
skipped on re-run if its output already exists, so re-running plan mode after
you hand-edit plan.json will NOT clobber your edits (it refreshes plan.md
against whatever plan.json currently says) unless you pass --force.

Never touches the raw file.
"""
import argparse
import datetime
import importlib.util
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import audit_removed_spans
import whisper_backend
import find_restarts
import qa_checks

HERE = Path(__file__).resolve().parent
SYNC_DIR = HERE.parent / "sync"
ALIGN_DIR = HERE.parent / "align"

DETECT_SYNC_PY = SYNC_DIR / "detect_sync.py"
FIX_SYNC_SH = SYNC_DIR / "fix_sync.sh"
CUT_VIDEO_PY = HERE / "cut_video.py"
ALIGN_WORDS_PY = ALIGN_DIR / "align_words.py"
FIND_RETAKES_PY = ALIGN_DIR / "find_retakes.py"
FIND_STUMBLES_PY = ALIGN_DIR / "find_stumbles.py"
CRISPERWHISPER_BACKEND_PY = ALIGN_DIR / "backends" / "crisperwhisper_align.py"

QA_FRAME_COUNT = 8
QA_SILENCE_FLAG_S = 1.5
DETECT_SYNC_TIMEOUT_S = 1800  # ~5min/window x 2 windows (start + end drift check), generous


def fmt_ts(s):
    if s is None:
        return "?"
    sign = "-" if s < 0 else ""
    s = abs(s)
    m, sec = divmod(s, 60)
    return f"{sign}{int(m):02d}:{sec:05.2f}"


class Info:
    """Cumulative info.json: each stage reads what's there, adds its own key,
    writes the whole thing back. Lets later stages see earlier stages'
    results across a --force-less re-run without re-running them."""

    def __init__(self, path):
        self.path = Path(path)
        self.data = json.loads(self.path.read_text()) if self.path.exists() else {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        self.path.write_text(json.dumps(self.data, indent=2))


def load_cut_video():
    """Import cut_video.py as a module (not copy-pasted, not modified). Its
    `if __name__ == "__main__"` guard means importing it does not run its
    main()."""
    spec = importlib.util.spec_from_file_location("autocut_cut_video", CUT_VIDEO_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- 01 probe

def probe(raw):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(raw)],
        check=True, capture_output=True, text=True)
    data = json.loads(r.stdout)
    vstream = next(s for s in data["streams"] if s["codec_type"] == "video")
    astreams = [s for s in data["streams"] if s["codec_type"] == "audio"]
    num, den = (vstream.get("avg_frame_rate") or "0/1").split("/")
    fps = float(num) / float(den) if float(den) else 0.0
    return {
        "duration": float(data["format"]["duration"]),
        "fps": round(fps, 3),
        "width": vstream.get("width"),
        "height": vstream.get("height"),
        "audio_streams": [
            {"index": a.get("index"), "channels": a.get("channels"), "sample_rate": a.get("sample_rate")}
            for a in astreams
        ],
    }


# ----------------------------------------------------------------- 02 sync

def detect_sync(raw):
    """Returns (offset_seconds, detected_bool, extra_dict)."""
    cmd = ["python3", str(DETECT_SYNC_PY), str(raw), "--json"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=DETECT_SYNC_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return 0.0, False, {"error": f"timed out after {DETECT_SYNC_TIMEOUT_S}s"}
    except OSError as e:
        return 0.0, False, {"error": str(e)}

    try:
        summary = json.loads(r.stdout)
    except json.JSONDecodeError:
        return 0.0, False, {"error": (r.stderr or r.stdout).strip()[-2000:], "returncode": r.returncode}

    if r.returncode != 0:
        # summary may still be a valid partial result (spread/confidence check
        # failed after printing) -- record it for visibility, but don't trust it
        return 0.0, False, {
            "error": (r.stderr or "").strip()[-2000:],
            "returncode": r.returncode,
            "unreliable_median_offset_ms": summary.get("median_offset_ms"),
            "unreliable_confidence": summary.get("min_confidence"),
        }

    return summary["median_offset_ms"] / 1000.0, True, {
        "confidence": summary["min_confidence"],
        "spread_ms": summary["spread_ms"],
    }


def apply_sync(raw, offset, workdir):
    synced = workdir / "synced.mp4"
    if synced.exists() or synced.is_symlink():
        return synced
    if abs(offset) < 1e-6:
        synced.symlink_to(raw.resolve())
    else:
        subprocess.run(["bash", str(FIX_SYNC_SH), str(raw), f"{offset:.3f}", str(synced)], check=True)
    return synced


# ---------------------------------------------------------------- 03 audio

def extract_audio(synced, workdir):
    wav = workdir / "audio.wav"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(synced), "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(wav)],
        check=True)
    return wav


# ------------------------------------------------------------ 04 transcribe

def transcribe(wav, workdir):
    target = workdir / "transcript.raw.json"
    whisper_backend.transcribe(wav, target)
    return target


# ----------------------------------------------------------------- 05 align

CHECK_RE = re.compile(
    r"--check: (\d+) words, start shift median=(\d+)ms p90=(\d+)ms, end shift median=(\d+)ms p90=(\d+)ms")


def align(wav, raw_transcript, workdir, lang):
    out = workdir / "transcript.json"
    cmd = ["python3", str(ALIGN_WORDS_PY), str(wav), str(raw_transcript), "-o", str(out), "--lang", lang, "--check"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"error: align_words.py failed:\n{(r.stderr or '')[-2000:]}")
    m = CHECK_RE.search(r.stdout)
    shift = None
    if m:
        shift = {
            "n_words": int(m.group(1)),
            "start_median_ms": int(m.group(2)), "start_p90_ms": int(m.group(3)),
            "end_median_ms": int(m.group(4)), "end_p90_ms": int(m.group(5)),
        }
    return out, shift


# -------------------------------------------------------------- 06 silences

def compute_silences(cut_video_mod, synced, workdir, force):
    out = workdir / "silences.json"
    if force and out.exists():
        out.unlink()
    return cut_video_mod.detect_silences(synced, out)


# --------------------------------------------------------------- 07 retakes

def find_retakes(transcript_path, workdir):
    out = workdir / "retakes.json"
    cmd = ["uv", "run", str(FIND_RETAKES_PY), str(transcript_path), "-o", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"error: find_retakes.py failed:\n{(r.stderr or '')[-2000:]}")
    return json.loads(out.read_text())


# -------------------------------------------------------------- 07b stumbles

def run_verbatim(wav, lang):
    """CrisperWhisper in verbatim mode over the whole synced audio track --
    same invocation align_words.py uses for its per-language backend, just
    run here for its transcript rather than to re-time an existing one."""
    cmd = ["uv", "run", "--python", "3.11", "--with", "crisperwhisper[transformers]",
           "--with", "transformers<5", "--with", "ctranslate2", "python3", str(CRISPERWHISPER_BACKEND_PY), str(wav), lang, "turbo"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"error: crisperwhisper verbatim pass failed:\n{(r.stderr or '')[-2000:]}")
    return json.loads(r.stdout)["words"]


def find_stumbles(verbatim_path, workdir, lang=None):
    out = workdir / "stumbles.json"
    cmd = ["uv", "run", str(FIND_STUMBLES_PY), str(verbatim_path), "-o", str(out), "--lang", lang or "en"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"error: find_stumbles.py failed:\n{(r.stderr or '')[-2000:]}")
    return json.loads(out.read_text())


def workdir_lang(workdir):
    """Language for the verbatim pass of an existing workdir: the --lang used at plan time, else what
    mlx-whisper detected."""
    workdir = Path(workdir)
    info = json.loads((workdir / "info.json").read_text()) if (workdir / "info.json").exists() else {}
    lang = info.get("align", {}).get("lang")
    if lang in (None, "auto"):
        raw = workdir / "transcript.raw.json"
        lang = (json.loads(raw.read_text()).get("language") if raw.exists() else None) or "en"
    return lang


def split_keep_ranges(keep_ranges, spans):
    """Remove each span's [from, to) window from keep_ranges, splitting the
    range that contains it into two -- the same mechanics as hand-accepting
    a retake proposal (see the SKILL), just applied automatically."""
    ranges = [list(r) for r in keep_ranges]
    for span in spans:
        f, t = span["from"], span["to"]
        out = []
        for s, e in ranges:
            if t <= s or f >= e:
                out.append([s, e])
                continue
            if f > s:
                out.append([s, f])
            if t < e:
                out.append([t, e])
        ranges = out
    return [tuple(r) for r in ranges]


def build_filler_removals(fillers):
    out = []
    for f in fillers:
        out.append({
            "from": f["from"], "to": f["to"],
            "reason": "filler",
            "drop_text": f["drop_text"],
        })
    return out


def splice_transcript_with_verbatim(transcript_path, verbatim_words, applied_spans, workdir):
    """For each applied stumble span, replace transcript.json's words in
    [span.from - 1.0, span.to + 1.0] with the verbatim words CrisperWhisper
    found in that same window, so cut_video.py's edge snapping (which reads
    transcript.json, not the verbatim pass) sees the real word edges around
    a stumble instead of mlx-whisper's smoothed-over, stretched ones."""
    backup = workdir / "transcript.pre-stumbles.json"
    data = json.loads(Path(transcript_path).read_text())
    if not backup.exists():
        backup.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    for span in applied_spans:
        lo, hi = span["from"] - 1.0, span["to"] + 1.0
        replacement = sorted(
            ({"word": w["word"], "start": w["start"], "end": w["end"]}
             for w in verbatim_words if lo <= w["start"] <= hi),
            key=lambda w: w["start"])
        if not replacement:
            continue  # nothing to splice in beats deleting words with nothing to replace them

        touched = [(si, wi) for si, seg in enumerate(data["segments"])
                   for wi, w in enumerate(seg.get("words", [])) if lo <= w["start"] <= hi]
        if not touched:
            continue
        target_seg = touched[0][0]

        by_seg = {}
        for si, wi in touched:
            by_seg.setdefault(si, []).append(wi)
        for si, wis in by_seg.items():
            words_list = data["segments"][si]["words"]
            for wi in sorted(wis, reverse=True):
                del words_list[wi]

        words_list = data["segments"][target_seg]["words"]
        insert_at = next((idx for idx, w in enumerate(words_list) if w["start"] > lo), len(words_list))
        words_list[insert_at:insert_at] = replacement

    Path(transcript_path).write_text(json.dumps(data, indent=2, ensure_ascii=False))


# ----------------------------------------------------------------- 08 plan

def compute_gaps(original_ranges, core_ranges):
    """original_ranges minus core_ranges, as a list of (from, to) gaps. Catches
    every removed span cut_video.py's tighten/silence_tighten will produce,
    including a trim at the very start or end of a range (which a simple
    zip-consecutive-core-ranges diff misses, since there's no earlier/later
    core range to compare against there)."""
    core_sorted = sorted(core_ranges)
    gaps = []
    for os_, oe in original_ranges:
        cursor = os_
        for cs, ce in core_sorted:
            if ce <= os_ or cs >= oe:
                continue
            cs2, ce2 = max(cs, os_), min(ce, oe)
            if cs2 > cursor:
                gaps.append((cursor, cs2))
            cursor = max(cursor, ce2)
        if cursor < oe:
            gaps.append((cursor, oe))
    return gaps


def preview_ranges(cut_video_mod, keep_ranges, words, silences):
    """Mirrors cut_video.py's own main() range-shaping pipeline exactly (by
    calling its actual functions), so plan.md's numbers match what --render
    will really produce. Returns (core_ranges_no_tail, cuts)."""
    ranges = [tuple(r) for r in keep_ranges]
    merged = [list(ranges[0])]
    for s, e in ranges[1:]:
        if s <= merged[-1][1] + 0.06 and e >= merged[-1][0]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    merged = [tuple(r) for r in merged]

    tightened = cut_video_mod.tighten_ranges(merged, words, silences)
    sil_tightened = cut_video_mod.silence_tighten(tightened, silences, words)
    core = cut_video_mod.snap_ranges(sil_tightened, words)

    cuts = [{"from": f, "to": t, "seconds": t - f} for f, t in compute_gaps(merged, core)]
    return core, cuts


def tag_cut_reason(cut, silences):
    for ss, se in silences:
        overlap = min(cut["to"], se) - max(cut["from"], ss)
        if overlap > 0.3:
            return f"silence ({se - ss:.2f}s detected below -35dB)"
    return "word gap > 1.2s (no matching detected silence)"


def build_proposed_removals(retakes):
    out = []
    for c in retakes:
        drop, keep = c["drop_candidate"], c["keep"]
        out.append({
            "from": drop["start"], "to": drop["end"],
            "reason": f"retake (similarity={c['similarity']}/100): near-duplicate of a later restatement",
            "keep_instead": {"from": keep["start"], "to": keep["end"], "text": keep["text"]},
            "drop_text": drop["text"],
            "similarity": c["similarity"],
        })
    return out


def write_plan_md(path, raw, info, keep_ranges, cuts, planned_total, raw_duration, proposed_removals,
                   applied_stumbles, fillers, render_cmd, restarts=(), workdir=None):
    lines = [f"# Autocut plan: {raw.name}", ""]
    saved = raw_duration - planned_total
    lines.append(f"- Raw duration: {fmt_ts(raw_duration)} ({raw_duration:.2f}s)")
    lines.append(f"- Planned duration (preview): {fmt_ts(planned_total)} ({planned_total:.2f}s)")
    pct = (saved / raw_duration * 100) if raw_duration else 0.0
    lines.append(f"- Saved: {fmt_ts(saved)} ({saved:.2f}s, {pct:.1f}%)")

    sync = info.get("sync", {})
    if sync.get("mode") == "detected":
        lines.append(
            f"- Sync offset used: {sync['offset']:+.3f}s (detected, confidence {sync.get('confidence')}, "
            f"spread {sync.get('spread_ms')}ms)")
    elif sync.get("mode") == "manual":
        lines.append(f"- Sync offset used: {sync['offset']:+.3f}s (--offset, manual)")
    elif sync.get("mode") == "detect-failed":
        lines.append(f"- Sync offset used: 0.000s (detection FAILED, see info.json sync.error; not applied)")
    else:
        lines.append("- Sync offset used: 0.000s (--no-sync)")

    align_info = info.get("align", {})
    shift = align_info.get("shift")
    if shift:
        lines.append(
            f"- Alignment shift (lang={align_info.get('lang')}, {shift['n_words']} words): "
            f"start median {shift['start_median_ms']}ms / p90 {shift['start_p90_ms']}ms, "
            f"end median {shift['end_median_ms']}ms / p90 {shift['end_p90_ms']}ms")

    lines += ["", "## Cuts (preview of what `tighten: true` will produce at render time)", ""]
    if cuts:
        lines.append("| timestamp | action | reason | seconds saved |")
        lines.append("|---|---|---|---|")
        for c in cuts:
            lines.append(f"| {fmt_ts(c['from'])}-{fmt_ts(c['to'])} | cut | {c['reason']} | {c['seconds']:.2f}s |")
        lines.append("")
        cuts_total = sum(c['seconds'] for c in cuts)
        lines.append(f"Totals: {len(cuts)} cut(s), {cuts_total:.2f}s removed. "
                      f"(raw - cuts total = planned duration minus the 0.5s breathing-room tail "
                      f"cut_video.py adds to the final piece: {raw_duration:.2f} - {cuts_total:.2f} = "
                      f"{raw_duration - cuts_total:.2f}, planned - 0.5 = {planned_total - 0.5:.2f})")
    else:
        lines.append("No cuts: no silence or word gap over threshold found in the current `keep` ranges.")

    lines += ["", "## Stumbles (applied by default, remove a span from `keep` splits to put it back)", ""]
    lines.append(
        "False starts and self-repeats CrisperWhisper's verbatim pass found that mlx-whisper's own "
        "transcript smoothed away (mlx-whisper's decoder favors the fluent reading, so a line said "
        "twice comes back as one clean sentence with no trace of the abandoned first take). These are "
        "already cut out of the `keep` ranges below.")
    lines.append("")
    if applied_stumbles:
        lines.append("| span | dropped | kept instead |")
        lines.append("|---|---|---|")
        for s in applied_stumbles:
            lines.append(f"| [{fmt_ts(s['from'])}-{fmt_ts(s['to'])}] | {s['kind']} {s['drop_text']!r} "
                          f"| {s['keep_text']!r} |")
    else:
        lines.append("None found.")

    lines += ["", "### Not applied: fillers and possible restarts (kind shown; move a span into the cuts to apply it)", ""]
    lines.append("Um, uh, hmm and the like -- flagged for a human ear, never cut automatically.")
    lines.append("")
    if fillers:
        lines.append("| span | kind | text |")
        lines.append("|---|---|---|")
        for f in fillers:
            lines.append(f"| [{fmt_ts(f['from'])}-{fmt_ts(f['to'])}] | {f.get('kind', 'filler')} | {f['drop_text']!r} |")
    else:
        lines.append("None found.")

    lines += ["", "## Restarts (proposed, review each)", ""]
    lines.append(
        "find_restarts.py: a phrase said, abandoned and said again within 12 s, on the verbatim words "
        "(find_stumbles only drops immediate repeats). The LAST take is kept. Single word + fragment "
        "(\"expiring exp- expiring\") is applied automatically; everything else is a proposal, because "
        "generic short n-grams in long takes produce false positives (\"nine hundred and\" twenty-eight "
        "vs thirty-nine). Listen to the context, then run the command to accept.")
    lines.append("")
    if restarts:
        lines.append("| span | status | dropped | accept with |")
        lines.append("|---|---|---|---|")
        for r in restarts:
            status = "applied automatically" if r["auto"] else ("already dropped in keep" if r.get("covered") else "PROPOSED")
            cmd = "" if r["auto"] or r.get("covered") else (
                f"`python3 {HERE / 'apply_spans.py'} {workdir} --span {r['from']:.3f}:{r['to']:.3f}`")
            lines.append(f"| [{fmt_ts(r['from'])}-{fmt_ts(r['to'])}] | {status} | {r['dropped']!r} | {cmd} |")
    else:
        lines.append("None found.")

    retake_removals = [p for p in proposed_removals if "similarity" in p]
    lines += ["", "## Retake proposals (NOT applied -- edit plan.json to apply)", ""]
    if retake_removals:
        MAX_ROWS = 30
        shown = retake_removals[:MAX_ROWS]
        spans = [p["from"] for p in retake_removals] + [p["to"] for p in retake_removals]
        window = max(spans) - min(spans) if spans else 0.0
        if len(retake_removals) > MAX_ROWS and window < 10.0:
            lines.append(
                f"find_retakes.py returned {len(retake_removals)} candidates, all inside a single "
                f"{window:.1f}s window ({fmt_ts(min(spans))}-{fmt_ts(max(spans))}). That many hits in "
                f"that little time is not {len(retake_removals)} real retakes -- it is mlx-whisper "
                f"decoder-looping (repeating the same short phrase over and over, sometimes past the "
                f"real end of the audio) which find_retakes.py faithfully flags one pair per repeat. "
                f"Full list is in retakes.json; showing the first {MAX_ROWS} rows here.")
            lines.append("")
        elif len(retake_removals) > MAX_ROWS:
            lines.append(f"{len(retake_removals)} candidates found; showing the first {MAX_ROWS} "
                          f"(full list in retakes.json).")
            lines.append("")
        lines.append("| similarity | drop candidate | keep instead |")
        lines.append("|---|---|---|")
        for p in shown:
            lines.append(
                f"| {p['similarity']} | [{fmt_ts(p['from'])}-{fmt_ts(p['to'])}] {p['drop_text']!r} "
                f"| [{fmt_ts(p['keep_instead']['from'])}-{fmt_ts(p['keep_instead']['to'])}] "
                f"{p['keep_instead']['text']!r} |")
        lines.append("")
        lines.append(
            "To accept one: edit plan.json's `keep` list to exclude the drop-candidate range "
            "(split the range that contains it into two), then run --render.")
    else:
        lines.append("None found.")

    lines += ["", "## Current keep ranges (source seconds)", ""]
    for s, e in keep_ranges:
        lines.append(f"- [{fmt_ts(s)} - {fmt_ts(e)}]")

    lines += ["", "## Render", "", "```", render_cmd, "```"]
    Path(path).write_text("\n".join(lines) + "\n")


def stage_plan(raw, workdir, lang, offset, no_sync, force):
    info = Info(workdir / "info.json")
    cut_video_mod = load_cut_video()

    t0 = time.time()
    cached = info.get("probe") is not None and not force
    if not cached:
        info.set("probe", probe(raw))
    print(f"01 probe: {'cached' if cached else 'done'} ({time.time() - t0:.2f}s)")
    raw_duration = info.get("probe")["duration"]

    t0 = time.time()
    synced = workdir / "synced.mp4"
    cached = info.get("sync") is not None and (synced.exists() or synced.is_symlink()) and not force
    if not cached:
        if offset is not None:
            off, detected, extra, mode = offset, False, {}, "manual"
        elif no_sync:
            off, detected, extra, mode = 0.0, False, {}, "no-sync"
        else:
            off, detected, extra = detect_sync(raw)
            mode = "detected" if detected else "detect-failed"
            if not detected:
                print(f"  warning: sync detection failed, using offset 0.0 -- {extra.get('error', '')[:300]}")
        info.set("sync", {"mode": mode, "offset": off, "detected": detected, **extra})
        if synced.exists() or synced.is_symlink():
            synced.unlink()
        synced = apply_sync(raw, off, workdir)
    print(f"02 sync: {'cached' if cached else 'done'} ({time.time() - t0:.2f}s) "
          f"offset={info.get('sync')['offset']:+.3f}s mode={info.get('sync')['mode']}")

    t0 = time.time()
    wav = workdir / "audio.wav"
    cached = wav.exists() and not force
    if not cached:
        wav = extract_audio(synced, workdir)
    print(f"03 audio: {'cached' if cached else 'done'} ({time.time() - t0:.2f}s)")

    t0 = time.time()
    raw_transcript = workdir / "transcript.raw.json"
    cached = raw_transcript.exists() and not force
    if not cached:
        raw_transcript = transcribe(wav, workdir)
    print(f"04 transcribe: {'cached' if cached else 'done'} ({time.time() - t0:.2f}s)")
    whisper_lang = json.loads(raw_transcript.read_text()).get("language")

    t0 = time.time()
    transcript_path = workdir / "transcript.json"
    cached = transcript_path.exists() and info.get("align") is not None and not force
    if not cached:
        transcript_path, shift = align(wav, raw_transcript, workdir, lang)
        info.set("align", {"lang": lang, "whisper_detected_lang": whisper_lang, "shift": shift})
    print(f"05 align: {'cached' if cached else 'done'} ({time.time() - t0:.2f}s)")

    t0 = time.time()
    silences_path = workdir / "silences.json"
    cached = silences_path.exists() and not force
    silences = compute_silences(cut_video_mod, synced, workdir, force) if not cached else json.loads(silences_path.read_text())
    print(f"06 silences: {'cached' if cached else 'done'} ({time.time() - t0:.2f}s) {len(silences)} found")

    t0 = time.time()
    retakes_path = workdir / "retakes.json"
    cached = retakes_path.exists() and not force
    retakes = json.loads(retakes_path.read_text()) if cached else find_retakes(transcript_path, workdir)
    print(f"07 retakes: {'cached' if cached else 'done'} ({time.time() - t0:.2f}s) {len(retakes)} candidate(s)")

    t0 = time.time()
    verbatim_path = workdir / "verbatim.json"
    cached = verbatim_path.exists() and not force
    if cached:
        verbatim = json.loads(verbatim_path.read_text())
    else:
        effective_lang = lang if lang not in (None, "auto") else (whisper_lang or "en")
        verbatim = run_verbatim(wav, effective_lang)
        verbatim_path.write_text(json.dumps(verbatim, indent=2, ensure_ascii=False))
    stumbles_path = workdir / "stumbles.json"
    cached_stumbles = stumbles_path.exists() and not force
    stumbles = json.loads(stumbles_path.read_text()) if cached_stumbles else find_stumbles(verbatim_path, workdir, lang)
    applied_stumbles = [s for s in stumbles if s["apply"]]
    fillers = [s for s in stumbles if not s["apply"]]
    print(f"07b stumbles: {'cached' if cached and cached_stumbles else 'done'} ({time.time() - t0:.2f}s) "
          f"{len(applied_stumbles)} applied, {len(fillers)} filler(s) flagged")

    t0 = time.time()
    restarts = find_restarts.find(find_restarts.load_path(verbatim_path), 12.0, 3)
    auto_restarts = [{**r, "kind": "restart", "drop_text": r["dropped"], "keep_text": r["phrase"]}
                     for r in restarts if r["auto"]]
    print(f"07c restarts: {len(restarts)} found, {len(auto_restarts)} applied automatically "
          f"(single word + fragment), {len(restarts) - len(auto_restarts)} proposed in plan.md")

    plan_path = workdir / "plan.json"
    fresh_plan = not plan_path.exists() or force
    if fresh_plan and (applied_stumbles or auto_restarts):
        splice_transcript_with_verbatim(transcript_path, verbatim, applied_stumbles + auto_restarts, workdir)
    words = cut_video_mod.load_words(transcript_path)
    if not fresh_plan:
        plan = json.loads(plan_path.read_text())
        print("08 plan: plan.json exists, preserving your edits (pass --force to regenerate from scratch)")
    else:
        keep = split_keep_ranges([(0.0, round(raw_duration, 3))], applied_stumbles + auto_restarts)
        plan = {
            "source": str(synced.resolve()),
            "transcript": str(transcript_path.resolve()),
            "output": str((workdir / "clean.mp4").resolve()),
            "keep": [list(r) for r in keep],
            "tighten": True,
            "captions": str((workdir / "captions.json").resolve()),
            "timemap": str((workdir / "timemap.json").resolve()),
            "proposed_removals": build_proposed_removals(retakes) + build_filler_removals(fillers),
        }
        plan_path.write_text(json.dumps(plan, indent=2))

    # always refresh the preview + plan.md against whatever plan.json currently
    # says (including hand edits), so re-running plan mode after a human edits the
    # plan shows him the updated picture without touching his edits
    keep_ranges = [tuple(r) for r in plan["keep"]]
    core_ranges, cuts = preview_ranges(cut_video_mod, keep_ranges, words, silences)
    for c in cuts:
        c["reason"] = tag_cut_reason(c, silences)
    planned_total = sum(e - s for s, e in core_ranges) + 0.5  # final-piece breathing tail, matches cut_video.py
    plan["_meta"] = {
        "raw_duration": raw_duration,
        "planned_duration_preview": planned_total,
        "saved_seconds_preview": raw_duration - planned_total,
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    plan_path.write_text(json.dumps(plan, indent=2))

    for r in restarts:
        r["covered"] = not any(s < r["to"] - 0.05 and e > r["from"] + 0.05 for s, e in keep_ranges)
    render_cmd = f"python3 {HERE / 'autocut.py'} {raw} --render --workdir {workdir}"
    plan_md_path = workdir / "plan.md"
    write_plan_md(plan_md_path, raw, info, keep_ranges, cuts, planned_total, raw_duration,
                  plan.get("proposed_removals", []), applied_stumbles, fillers, render_cmd, restarts, workdir)
    print(f"08 plan: done ({time.time() - t0:.2f}s)")

    print(plan_md_path)
    return plan_md_path


# --------------------------------------------------------------- render/QA

def write_qa_md(path, plan, out, dur, n_pieces, longest_silence, size_bytes, frame_paths):
    meta = plan.get("_meta", {})
    planned = meta.get("planned_duration_preview")
    lines = [f"# QA: {out.name}", ""]
    lines.append(f"- Output duration: {fmt_ts(dur)} ({dur:.2f}s)")
    if planned is not None:
        lines.append(f"- Planned duration (from plan.json _meta): {fmt_ts(planned)} ({planned:.2f}s), "
                      f"delta {dur - planned:+.2f}s")
    lines.append(f"- Pieces: {n_pieces if n_pieces is not None else '?'}")
    flag = " -- FLAGGED, exceeds 1.5s" if longest_silence > QA_SILENCE_FLAG_S else ""
    lines.append(f"- Longest internal silence: {longest_silence:.2f}s{flag}")
    lines.append(f"- File size: {size_bytes / 1e6:.1f} MB")
    lines += ["", "## Sanity frames (8 evenly spaced)", ""]
    for p in frame_paths:
        lines.append(f"- {p}")
    Path(path).write_text("\n".join(lines) + "\n")


LONG_FORM_S = 180  # raw takes longer than this get the pause cap by default


def stage_render(raw, workdir, force, cap_pauses=True):
    plan_path = workdir / "plan.json"
    if not plan_path.exists():
        sys.exit(f"error: {plan_path} not found -- run plan mode first")

    # long form: pauses over 0.65 s (every frame under -55 dB) capped to 0.30 + 0.20 s, before the
    # snapper so its clearance rules still apply
    raw_dur = json.loads(plan_path.read_text()).get("_meta", {}).get("raw_duration") or 0.0
    if cap_pauses and raw_dur > LONG_FORM_S:
        r = subprocess.run(["python3", str(Path(__file__).parent / "cap_pauses.py"), str(workdir)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            sys.exit(f"error: cap_pauses.py failed:\n{(r.stderr or '')[-3000:]}")
        print("09p pauses: " + r.stdout.strip())

    # every cut edge into real silence, noises between phrases out
    r = subprocess.run(["python3", str(Path(__file__).parent / "snap_edges.py"), str(workdir)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"error: snap_edges.py failed:\n{(r.stderr or '')[-3000:]}")
    print("09a snap: " + r.stdout.strip().splitlines()[-1])

    # onset clipping: a kept start with sound running right up to it (verbatim word times can lag the
    # real onset by 190 ms, snap_edges' -45 dB runs miss soft onsets) is moved back into the removed span
    plan = json.loads(plan_path.read_text())
    fixed = qa_checks.fix_starts(plan, qa_checks.edge_scan(workdir / "audio.wav", [tuple(k) for k in plan["keep"]]))
    if fixed:
        plan_path.write_text(json.dumps(plan, indent=2))
    for old, new in fixed:
        print(f"09b edge fix: START {old:.2f} -> {new:.2f} (onset restored, pinned)")
    plan_fixed = fixed

    t0 = time.time()
    cmd = ["python3", str(CUT_VIDEO_PY), str(plan_path)]
    if force:
        cmd.append("--force")
    r = subprocess.run(cmd, capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    if r.returncode != 0:
        sys.exit(f"error: cut_video.py failed:\n{(r.stderr or '')[-3000:]}")
    print(f"09 render: done ({time.time() - t0:.2f}s)")

    t0 = time.time()
    plan = json.loads(plan_path.read_text())  # re-read from disk, not from memory
    out = Path(plan["output"])
    cut_video_mod = load_cut_video()

    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                         "-of", "default=noprint_wrappers=1:nokey=1", str(out)],
                        check=True, capture_output=True, text=True)
    dur = float(r.stdout.strip())

    n_pieces = None
    if plan.get("timemap") and Path(plan["timemap"]).exists():
        tm = json.loads(Path(plan["timemap"]).read_text())
        n_pieces = len(tm.get("entries", []))

    qa_sil = cut_video_mod.detect_silences(out, workdir / "qa_silences.json")
    longest_silence = max((e - s for s, e in qa_sil), default=0.0)

    size_bytes = out.stat().st_size

    qa_dir = workdir / "qa"
    qa_dir.mkdir(exist_ok=True)
    frame_paths = []
    for i in range(QA_FRAME_COUNT):
        t = dur * (i + 0.5) / QA_FRAME_COUNT
        png = qa_dir / f"frame_{i:02d}_{t:.1f}s.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", str(out),
                         "-frames:v", "1", str(png)], check=True)
        frame_paths.append(png)

    qa_md_path = workdir / "qa.md"
    write_qa_md(qa_md_path, plan, out, dur, n_pieces, longest_silence, size_bytes, frame_paths)
    print(f"10 qa: done ({time.time() - t0:.2f}s)")

    t0 = time.time()
    audit_removed_spans.run_audit(workdir)
    print(f"11 removed-span audit: done ({time.time() - t0:.2f}s)")

    t0 = time.time()
    flags, spans = qa_checks.run_qa(workdir, run_verbatim, workdir_lang(workdir))
    if plan_fixed:
        qa_checks.write_sections(workdir, [("## Edge clipping", qa_checks.edges_section(flags, "the rendered pieces", plan_fixed))])
    print(f"12 verbatim-of-the-cut + edge scan: done ({time.time() - t0:.2f}s) "
          f"{len(spans)} restart(s), {len(flags)} clipped edge(s) FLAGGED. READ {workdir / 'qa' / 'verbatim_cut.txt'}")

    print(out)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("raw", nargs="?", default=None,
                     help="Raw recording. Not needed with --qa-only if --workdir is given.")
    ap.add_argument("--lang", choices=["auto", "en", "pt", "it", "es", "fr", "de", "nl"], default="auto")
    sync = ap.add_mutually_exclusive_group()
    sync.add_argument("--offset", type=float, default=None)
    sync.add_argument("--no-sync", action="store_true")
    ap.add_argument("--workdir", default=None)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--render", action="store_true")
    ap.add_argument("--no-cap-pauses", action="store_true",
                     help="Render without the long-form pause cap (cap_pauses.py), which otherwise "
                          f"runs for raw takes over {LONG_FORM_S} s.")
    ap.add_argument("--qa-only", action="store_true",
                     help="Re-run just the QA (removed-span audit, verbatim of the cut, restart and edge scans) against an existing workdir "
                          "(timemap.json, audio.wav, plan.json already there) and update "
                          "qa.md. Does not re-render, does not need the raw file.")
    args = ap.parse_args()

    if args.qa_only:
        if args.workdir:
            workdir = Path(args.workdir).resolve()
        elif args.raw:
            workdir = Path(args.raw).resolve()
        else:
            sys.exit("error: --qa-only needs --workdir (or the workdir path as the positional arg)")
        if not (workdir / "timemap.json").exists():
            sys.exit(f"error: {workdir / 'timemap.json'} not found -- run --render first")
        audit_removed_spans.run_audit(workdir)
        qa_checks.run_qa(workdir, run_verbatim, workdir_lang(workdir))
        return

    if not args.raw:
        sys.exit("error: raw recording path required")
    raw = Path(args.raw).resolve()
    if not raw.exists():
        sys.exit(f"error: {raw} not found")
    workdir = Path(args.workdir).resolve() if args.workdir else raw.parent / f"{raw.stem}_autocut"
    workdir.mkdir(parents=True, exist_ok=True)

    if args.render:
        stage_render(raw, workdir, args.force, cap_pauses=not args.no_cap_pauses)
    else:
        stage_plan(raw, workdir, args.lang, args.offset, args.no_sync, args.force)


if __name__ == "__main__":
    main()
