#!/usr/bin/env python3
"""Re-time a mlx-whisper transcript's word boundaries with a forced aligner.

Why this exists: mlx-whisper's own word timestamps are only accurate to
roughly +/-100-500ms at word edges (it estimates them from cross-attention,
not from the audio's actual phoneme boundaries). cut_video.py and
build_clips.py pad and fade correctly, but they're padding around a
mistimed edge, which is what causes "munched words" -- a cut or caption
that clips the first or last consonant of a word. This script fixes the
INPUT, not the cutting logic: it re-runs a real forced aligner against the
audio and writes out the identical JSON shape the existing scripts already
read, with tighter start/end times.

Winner per language (benchmark summary in docs/SETUP.md):
  en -> WhisperX (wav2vec2 CTC forced alignment)
  pt -> CrisperWhisper 2.0 (its own ASR, re-matched onto the baseline words)
  it -> WhisperX (same architecture as en; not benchmarked on Italian audio,
        treat as provisional until checked against a real Italian clip)

Usage:
    python3 align_words.py <audio.wav> <mlx_whisper.json> -o <aligned.json> [--lang en|pt|it|auto]
    python3 align_words.py <audio.wav> <mlx_whisper.json> -o <aligned.json> --check

Each aligner runs in its own ephemeral environment via `uv run --with`, the
same pattern the rest of this repo uses for mlx-whisper (`uvx --from
mlx-whisper`) -- nothing gets installed into your system or project Python.
First run per aligner downloads its model (see README); after that it's
cached and fast.
"""
import argparse
import json
import re
import shutil
import statistics
import subprocess
import sys
import difflib
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKENDS = HERE / "backends"

LANG_NAMES = {"en": "English", "pt": "Portuguese", "it": "Italian", "es": "Spanish", "fr": "French", "de": "German", "nl": "Dutch"}

# language -> (backend name, uv-run args to install that backend's deps)
BACKEND_FOR_LANG = {
    "en": "whisperx",
    "it": "whisperx",
    "pt": "crisperwhisper",
    # Not benchmarked: WhisperX ships default wav2vec2 align models for these. Run --check first.
    "es": "whisperx",
    "fr": "whisperx",
    "de": "whisperx",
    "nl": "whisperx",
}


def norm(word):
    word = word.strip().lower()
    word = re.sub(r"[^\w]", "", word)
    word = re.sub(r"^\[.*\]$", "", word)  # CrisperWhisper disfluency tags like [UH]
    return word


def flatten_baseline(data):
    words = []
    for si, seg in enumerate(data["segments"]):
        for wi, w in enumerate(seg.get("words", [])):
            words.append({"seg": si, "idx": wi, "word": w["word"], "start": w["start"], "end": w["end"]})
    return words


def run_whisperx(audio_path, baseline, lang):
    segments = [{"text": seg["text"], "start": seg["start"], "end": seg["end"]} for seg in baseline["segments"]]
    seg_file = HERE / ".tmp_segments.json"
    seg_file.write_text(json.dumps(segments))
    try:
        cmd = ["uv", "run", "--python", "3.11", "--with", "whisperx", "python3",
               str(BACKENDS / "whisperx_align.py"), str(audio_path), str(seg_file), lang]
        out = subprocess.run(cmd, capture_output=True, text=True)
        if out.returncode != 0:
            sys.exit(f"error: whisperx backend failed:\n{out.stderr[-2000:]}")
        # whisperx logs warnings (e.g. an empty segment) to stdout, so read only the JSON line
        json_line = next(l for l in reversed(out.stdout.splitlines()) if l.startswith("{"))
        return json.loads(json_line)["words"]
    finally:
        seg_file.unlink(missing_ok=True)


def run_crisperwhisper(audio_path, lang, model_size="turbo"):
    cmd = ["uv", "run", "--python", "3.11", "--with", "crisperwhisper[transformers]",
           "--with", "transformers<5", "--with", "ctranslate2", "python3",
           str(BACKENDS / "crisperwhisper_align.py"), str(audio_path), lang, model_size]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit(f"error: crisperwhisper backend failed:\n{out.stderr[-2000:]}")
    return json.loads(out.stdout)["words"]


def match_words(baseline_words, candidate_words):
    """Match candidate words onto baseline words by normalized text
    (difflib), same approach whether the candidate is a true 1:1
    re-alignment (WhisperX) or an independent re-transcription
    (CrisperWhisper). Returns {baseline_index: candidate_word}."""
    base_norm = [norm(w["word"]) for w in baseline_words]
    cand_norm = [norm(w["word"]) for w in candidate_words]
    sm = difflib.SequenceMatcher(None, base_norm, cand_norm, autojunk=False)
    matched = {}
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag != "equal":
            continue
        for k in range(i2 - i1):
            bi, cj = i1 + k, j1 + k
            if base_norm[bi] == "":
                continue
            matched[bi] = candidate_words[cj]
    return matched


def detect_lang(baseline):
    lang = baseline.get("language")
    if not lang:
        sys.exit("error: input JSON has no top-level \"language\" key, pass --lang explicitly")
    return lang


def align(audio_path, baseline_path, lang_arg):
    baseline = json.loads(Path(baseline_path).read_text())
    lang = detect_lang(baseline) if lang_arg in (None, "auto") else lang_arg

    backend = BACKEND_FOR_LANG.get(lang)
    if backend is None:
        sys.exit(f"error: no aligner configured for language {lang!r} "
                 f"(supported: {sorted(BACKEND_FOR_LANG)})")

    if lang not in ("en", "pt"):
        print(f"warning: {LANG_NAMES.get(lang, lang)} uses the WhisperX backend by default but was not "
              "benchmarked directly -- run with --check and spot-listen before trusting it.",
              file=sys.stderr)

    print(f"aligning with {backend} ({LANG_NAMES.get(lang, lang)})...", file=sys.stderr)

    if backend == "whisperx":
        candidate_words = run_whisperx(audio_path, baseline, lang)
    elif backend == "crisperwhisper":
        candidate_words = run_crisperwhisper(audio_path, lang)
    else:
        sys.exit(f"error: unknown backend {backend!r}")

    baseline_words = flatten_baseline(baseline)
    matched = match_words(baseline_words, candidate_words)

    n_aligned = 0
    for i, bw in enumerate(baseline_words):
        seg, idx = bw["seg"], bw["idx"]
        target = baseline["segments"][seg]["words"][idx]
        if i in matched:
            c = matched[i]
            target["start"] = float(c["start"])
            target["end"] = float(c["end"])
            target["aligned"] = True
            n_aligned += 1
        else:
            target["aligned"] = False

    print(f"{n_aligned}/{len(baseline_words)} words re-timed by {backend}, "
          f"{len(baseline_words) - n_aligned} kept baseline timestamps (aligned=false)",
          file=sys.stderr)
    return baseline


def print_check(before_path, after):
    before = json.loads(Path(before_path).read_text())
    before_words = flatten_baseline(before)
    after_words = flatten_baseline(after)
    d_start, d_end = [], []
    for bw, aw in zip(before_words, after_words):
        d_start.append(abs(aw["start"] - bw["start"]) * 1000)
        d_end.append(abs(aw["end"] - bw["end"]) * 1000)

    def stats(xs):
        if not xs:
            return (0.0, 0.0)
        xs = sorted(xs)
        median = statistics.median(xs)
        p90 = xs[min(len(xs) - 1, int(round(0.9 * (len(xs) - 1))))]
        return median, p90

    ms, ps = stats(d_start)
    me, pe = stats(d_end)
    print(f"--check: {len(before_words)} words, start shift median={ms:.0f}ms p90={ps:.0f}ms, "
          f"end shift median={me:.0f}ms p90={pe:.0f}ms")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("audio")
    ap.add_argument("transcript", help="mlx-whisper JSON (word timestamps)")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--lang", default="auto", choices=["en", "pt", "it", "es", "fr", "de", "nl", "auto"])
    ap.add_argument("--check", action="store_true", help="print median/p90 shift vs the input and exit")
    args = ap.parse_args()

    if shutil.which("uv") is None:
        sys.exit("error: uv not found on PATH (needed to run aligners in isolated envs)")

    aligned = align(args.audio, args.transcript, args.lang)
    Path(args.output).write_text(json.dumps(aligned, indent=2, ensure_ascii=False))
    print(f"wrote {args.output}", file=sys.stderr)

    if args.check:
        print_check(args.transcript, aligned)


if __name__ == "__main__":
    main()
