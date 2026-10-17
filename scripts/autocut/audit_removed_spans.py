#!/usr/bin/env python3
"""Removed-span audit: catch cut spans that actually contained speech.

Born from 2026-09-08: four renders were needed on one recording because
`tighten_ranges`/`silence_tighten` removed spans that had real words in them,
caught only by a human listening to every gap by hand. This automates that
manual check and writes it into `qa.md` so a bad cut can't ship silently.

For every removed span (the gap between two consecutive `timemap.json`
entries, in source seconds of `synced.mp4`):

  1. Extract the span's audio from `audio.wav`.
  2. Energy check: the loudest 100ms RMS window in dBFS. Flagged if it's
     louder than the recording's own silence threshold + 12dB -- a real
     silence shouldn't have a window that hot.
  3. Whisper check: transcribe the span in isolation with the same
     mlx-whisper settings the pipeline already uses. Flagged unless the
     result is empty or pure filler ("um", "you", "thank you", ...).

A span is flagged if either check fires, unless it matches an entry in
`plan.json`'s `_meta.content_cuts` (a removal a human already approved by hand),
in which case it's reported as "approved cut" instead of "FLAGGED".

Importable (`run_audit(workdir)`) so `autocut.py --render` runs it as part of
its own QA stage, and standalone (`--qa-only` / running this file directly)
so it can be re-run against an existing workdir without re-rendering.
"""
import argparse
import json
import math
import re
import struct
import subprocess
import sys
import wave
from pathlib import Path

import whisper_backend

HERE = Path(__file__).resolve().parent
CUT_VIDEO_PY = HERE / "cut_video.py"

MIN_SPAN_S = 0.3
ENERGY_MARGIN_DB = 12
OVERLAP_EPS = 0.05
WINDOW_MS = 100

# Filler tokens a span can be made of and still count as clean. "so" and
# "yeah" only count when they are the ENTIRE span, not part of a longer line.
BASE_FILLERS = {"you", "um", "uh", "hmm", "mm", "mhm", "ah", "oh"}
SOLO_FILLERS = {"so", "yeah"}


def fmt_ts(s):
    sign = "-" if s < 0 else ""
    s = abs(s)
    m, sec = divmod(s, 60)
    return f"{sign}{int(m):02d}:{sec:05.2f}"


def load_cut_video():
    import importlib.util
    spec = importlib.util.spec_from_file_location("autocut_cut_video", CUT_VIDEO_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def find_removed_spans(timemap):
    """(idx, srcStart-of-gap, srcEnd-of-gap) for every gap between two
    consecutive timemap entries, 1-indexed in original order. Includes gaps
    under MIN_SPAN_S -- those are still listed, just not audio-checked."""
    entries = timemap["entries"]
    spans = []
    for i in range(len(entries) - 1):
        gap_start = entries[i]["srcEnd"]
        gap_end = entries[i + 1]["srcStart"]
        if gap_end > gap_start:
            spans.append((i + 1, gap_start, gap_end))
    return spans


def overlaps_content_cut(start, end, content_cuts):
    for c in content_cuts:
        if min(end, c["to"]) - max(start, c["from"]) > -OVERLAP_EPS:
            return True
    return False


def extract_span_wav(audio_wav, start, end, out_path):
    subprocess.run([
        "ffmpeg", "-v", "error", "-y", "-i", str(audio_wav),
        "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
        "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(out_path),
    ], check=True)


def loudest_window_dbfs(wav_path, window_ms=WINDOW_MS):
    """Loudest window_ms RMS window in the clip, in dBFS. Pure Python over the
    s16le samples (prefix sum of squares, so each window is O(1)); no numpy."""
    with wave.open(str(wav_path), "rb") as w:
        assert w.getsampwidth() == 2, "expected s16le"
        n = w.getnframes()
        sr = w.getframerate()
        raw = w.readframes(n)
    count = len(raw) // 2
    if count == 0:
        return -99.0
    samples = struct.unpack(f"<{count}h", raw[:count * 2])

    window = max(1, int(sr * window_ms / 1000))
    window = min(window, count)

    prefix = [0] * (count + 1)
    for i, s in enumerate(samples):
        prefix[i + 1] = prefix[i] + s * s

    best_sumsq = 0
    hop = max(1, window // 4)
    for start in range(0, count - window + 1, hop):
        sumsq = prefix[start + window] - prefix[start]
        if sumsq > best_sumsq:
            best_sumsq = sumsq

    if best_sumsq <= 0:
        return -99.0
    rms = math.sqrt(best_sumsq / window)
    return 20 * math.log10(rms / 32768.0)


def normalize_text(text):
    t = text.strip().lower()
    t = re.sub(r"[^\w\s]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def is_clean_transcript(normalized):
    if not normalized:
        return True
    if normalized == "thank you":
        return True
    if normalized in SOLO_FILLERS:
        return True
    tokens = normalized.split()
    return bool(tokens) and all(t in BASE_FILLERS for t in tokens)


def transcribe_span(wav_path, language, out_dir):
    return whisper_backend.transcribe_text(wav_path, out_dir, language=language)


def audit_span(idx, start, end, audio_wav, language, threshold_db, content_cuts, removed_dir):
    dur = end - start
    approved = overlaps_content_cut(start, end, content_cuts)

    if dur < MIN_SPAN_S:
        return {
            "idx": idx, "start": start, "end": end, "dur": dur,
            "loudest_db": None, "text": "", "approved": approved,
            "verdict": "clean", "note": f"< {MIN_SPAN_S}s, not analyzed",
        }

    span_wav = removed_dir / f"span{idx:02d}.wav"
    extract_span_wav(audio_wav, start, end, span_wav)

    loudest_db = loudest_window_dbfs(span_wav)
    energy_flag = loudest_db > (threshold_db + ENERGY_MARGIN_DB)

    text = transcribe_span(span_wav, language, removed_dir)
    whisper_flag = not is_clean_transcript(normalize_text(text))

    would_flag = energy_flag or whisper_flag
    if not would_flag:
        verdict = "clean"
    elif approved:
        verdict = "approved cut"
    else:
        verdict = "FLAGGED"

    return {
        "idx": idx, "start": start, "end": end, "dur": dur,
        "loudest_db": loudest_db, "text": text, "approved": approved,
        "verdict": verdict, "note": "",
    }


def render_section(rows):
    lines = ["## Removed-span audit", ""]
    lines.append(
        "Every gap `tighten`/`silence_tighten` removed, checked in isolation for "
        "leftover speech. Read this table before showing `qa.md` to anyone -- a "
        "FLAGGED row means the cut is not shippable.")
    lines.append("")
    lines.append("| span | source range | duration | loudest 100ms window | whisper text | verdict |")
    lines.append("|---|---|---|---|---|---|")
    for r in rows:
        rng = f"{fmt_ts(r['start'])}-{fmt_ts(r['end'])}"
        db = f"{r['loudest_db']:.1f} dB" if r["loudest_db"] is not None else "n/a"
        text = repr(r["text"]) if r["text"] else (f"({r['note']})" if r["note"] else "(empty)")
        lines.append(f"| span{r['idx']:02d} | {rng} | {r['dur']:.2f}s | {db} | {text} | {r['verdict']} |")
    lines.append("")
    return "\n".join(lines) + "\n"


def update_qa_md(qa_md_path, section_text):
    path = Path(qa_md_path)
    if path.exists():
        content = path.read_text()
    else:
        content = "# QA (audit only, no render section)\n"
    marker = "## Removed-span audit"
    idx = content.find(marker)
    content = (content[:idx] if idx != -1 else content).rstrip() + "\n\n"
    content += section_text
    path.write_text(content)


def run_audit(workdir):
    workdir = Path(workdir)
    timemap = json.loads((workdir / "timemap.json").read_text())
    plan = json.loads((workdir / "plan.json").read_text())
    audio_wav = workdir / "audio.wav"
    synced = Path(plan["source"])
    raw_transcript_path = workdir / "transcript.raw.json"
    language = None
    if raw_transcript_path.exists():
        language = json.loads(raw_transcript_path.read_text()).get("language")
    content_cuts = plan.get("_meta", {}).get("content_cuts", [])

    cut_video_mod = load_cut_video()
    threshold_db = cut_video_mod.silence_threshold_db(synced)

    removed_dir = workdir / "qa" / "removed"
    removed_dir.mkdir(parents=True, exist_ok=True)

    spans = find_removed_spans(timemap)
    rows = [
        audit_span(idx, start, end, audio_wav, language, threshold_db, content_cuts, removed_dir)
        for idx, start, end in spans
    ]

    section = render_section(rows)
    update_qa_md(workdir / "qa.md", section)

    flagged = [r for r in rows if r["verdict"] == "FLAGGED"]
    print(f"removed-span audit: {len(rows)} spans, {len(flagged)} flagged")
    print(f"  (energy flag line: {threshold_db + ENERGY_MARGIN_DB:.1f}dB = "
          f"silence threshold {threshold_db:.1f}dB + {ENERGY_MARGIN_DB}dB)")
    for r in flagged:
        print(f"  span{r['idx']:02d} [{fmt_ts(r['start'])}-{fmt_ts(r['end'])}] "
              f"{r['loudest_db']:.1f}dB: {r['text']!r}")

    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("workdir")
    args = ap.parse_args()
    run_audit(Path(args.workdir).resolve())


if __name__ == "__main__":
    main()
