#!/usr/bin/env python3
"""English main transcript with NVIDIA Parakeet TDT 0.6B v3, plus the language check that routes to it.

Parakeet TDT 0.6B v3 (NVIDIA, CC-BY-4.0, run through parakeet-mlx, Apache-2.0) is more accurate than
Whisper on English takes and does not smooth restarts away or drop whole sentences. It is NOT used for
Portuguese: its Portuguese is European and it drifts into English mid-sentence. So:

    en           -> this module (Parakeet)
    anything else, or unknown -> mlx-whisper, the original path

Two rules the code below exists to enforce (measured 2026-11-07, see skills/autocut/SKILL.md):

  * NEVER one pass over the whole file. Full attention silently left 35 to 94 s of speech without a word
    on 6 to 10 min takes and peaked at 24 to 27 GB. The audio is cut into windows of at most MAX_WINDOW_S
    seconds, cut only inside real silences, each window is transcribed on its own, and the MLX buffer
    cache is capped at 512 MB (3.5 GB peak instead of 12 to 17 GB, same text).
  * Output is the mlx-whisper JSON shape, so align_words, find_retakes, cut_video, snap_edges, captions
    and everything else read it unchanged:
      {"text", "language": "en", "engine", "segments": [{"id","start","end","text","words":[{"word","start","end","probability"}]}]}

Library use (from autocut.py):
    parakeet_asr.detect_language(wav)            -> (lang, probability)
    parakeet_asr.transcribe(wav, out_json)       -> out_json

Workers (internal, run in an isolated env by the functions above):
    parakeet_asr.py --worker-transcribe <wav> <out.json>
    parakeet_asr.py --worker-detect <wav>
"""
import json
import platform
import re
import subprocess
import sys
from pathlib import Path

PARAKEET_MODEL = "mlx-community/parakeet-tdt-0.6b-v3"
WHISPER_MODEL = "mlx-community/whisper-large-v3-turbo"
MAX_WINDOW_S = 30.0
MIN_WINDOW_S = 0.2
CACHE_LIMIT_BYTES = 512 * 1024 * 1024
# silence settings tried in order when looking for a place to cut; the first that gives every
# window <= MAX_WINDOW_S wins. The first is the gated-mic case (pauses are digital zero).
SILENCE_PASSES = [(-45, 0.25), (-38, 0.12), (-32, 0.06)]
DETECT_MIN_PROB = 0.7  # English share needed in auto mode before Parakeet is used


def available():
    """parakeet-mlx runs on MLX, so Apple Silicon only."""
    return sys.platform == "darwin" and platform.machine() == "arm64"


# ------------------------------------------------------------ silence windows

def silences(wav, noise_db, min_d):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(wav), "-af", f"silencedetect=n={noise_db}dB:d={min_d}",
                        "-f", "null", "-"], capture_output=True, text=True).stderr
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", r)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r)]
    dur = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r)
    total = int(dur.group(1)) * 3600 + int(dur.group(2)) * 60 + float(dur.group(3))
    if len(starts) > len(ends):
        ends.append(total)
    return list(zip(starts, ends)), total


def plan_windows(sils, total, max_s=MAX_WINDOW_S):
    """Greedy cuts at silence midpoints: each window ends at the latest silence that keeps it <= max_s.
    Returns None when some stretch has no silence inside max_s (the caller then tries looser settings)."""
    mids = [(s + e) / 2 for s, e in sils if 0 < (s + e) / 2 < total]
    cuts, start = [], 0.0
    while total - start > max_s:
        ok = [m for m in mids if start + MIN_WINDOW_S < m <= start + max_s]
        if not ok:
            return None
        start = ok[-1]
        cuts.append(start)
    edges = [0.0] + cuts + [total]
    return list(zip(edges[:-1], edges[1:]))


def windows_for(wav, max_s=MAX_WINDOW_S):
    sils, total = None, None
    for noise_db, min_d in SILENCE_PASSES:
        sils, total = silences(wav, noise_db, min_d)
        w = plan_windows(sils, total, max_s)
        if w is not None:
            return w
    # no silence at all in some stretch: fixed windows are the last resort (clips a word at most per window)
    n = int(total // max_s) + 1
    return [(i * total / n, (i + 1) * total / n) for i in range(n)]


# ---------------------------------------------------------------- transcription

def tokens_to_words(tokens):
    """Parakeet emits sub-word tokens; a token with a leading space starts a new word."""
    words = []
    for t in tokens:
        txt = t["text"]
        if not words or txt.startswith(" "):
            words.append({"word": txt.strip(), "start": t["start"], "end": t["end"]})
        else:
            words[-1]["word"] += txt
            words[-1]["end"] = t["end"]
    return [w for w in words if w["word"]]


def _worker_transcribe(wav, out_json):
    import mlx.core as mx
    from parakeet_mlx import from_pretrained
    from parakeet_mlx.audio import get_logmel, load_audio

    mx.set_cache_limit(CACHE_LIMIT_BYTES)
    model = from_pretrained(PARAKEET_MODEL)
    sr = model.preprocessor_config.sample_rate
    audio = load_audio(Path(wav), sr, mx.bfloat16)
    segments = []
    for a, b in windows_for(wav):
        chunk = audio[int(a * sr):int(b * sr)]
        if len(chunk) < sr * MIN_WINDOW_S:
            continue
        res = model.generate(get_logmel(chunk, model.preprocessor_config))[0]
        for s in res.sentences:
            toks = [{"text": t.text, "start": round(t.start + a, 3), "end": round(t.start + a + t.duration, 3)}
                    for t in s.tokens]
            words = tokens_to_words(toks)
            if not words:
                continue
            segments.append({
                "id": len(segments), "start": words[0]["start"], "end": words[-1]["end"], "text": " " + s.text.strip(),
                "words": [{"word": " " + w["word"], "start": w["start"], "end": w["end"], "probability": 1.0}
                          for w in words],
            })
    Path(out_json).write_text(json.dumps({
        "text": " ".join(s["text"].strip() for s in segments), "language": "en",
        "engine": "parakeet-tdt-0.6b-v3", "segments": segments}, ensure_ascii=False))


def transcribe(wav, out_json):
    """Parakeet transcript of wav, written in the mlx-whisper JSON shape. Exits non-zero text on failure."""
    wav, out_json = Path(wav), Path(out_json)
    cmd = ["uv", "run", "--no-project", "--with", "parakeet-mlx", "python3", str(Path(__file__).resolve()),
           "--worker-transcribe", str(wav), str(out_json)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not out_json.exists():
        raise RuntimeError(f"parakeet failed on {wav.name}:\n{(r.stderr or '')[-2000:]}")
    return out_json


# ------------------------------------------------------------ language routing

def _worker_detect(wav):
    """Whisper's own language detector on up to three 30 s samples of real speech (10%, 45%, 80% in),
    probabilities averaged. Prints one JSON line {"lang","prob"}."""
    import mlx_whisper
    import mlx.core as mx
    import numpy as np
    from mlx_whisper.audio import N_SAMPLES, SAMPLE_RATE, load_audio, log_mel_spectrogram, pad_or_trim
    from mlx_whisper.decoding import detect_language
    from mlx_whisper.load_models import load_model
    from mlx_whisper.tokenizer import get_tokenizer

    audio = load_audio(str(wav))
    total = len(audio) / SAMPLE_RATE
    sils, _ = silences(wav, -45, 0.25)
    speech = []  # starts of speech after each silence
    cur = 0.0
    for s, e in sils:
        if s - cur > 1.0:
            speech.append(cur)
        cur = e
    if total - cur > 1.0:
        speech.append(cur)
    if not speech:
        speech = [0.0]
    model = load_model(WHISPER_MODEL, dtype=mx.float16)
    tok = get_tokenizer(model.is_multilingual, num_languages=model.num_languages)
    probs_sum, n = {}, 0
    for frac in (0.10, 0.45, 0.80):
        t0 = next((s for s in speech if s >= frac * total), speech[-1])
        chunk = audio[int(t0 * SAMPLE_RATE):int(t0 * SAMPLE_RATE) + N_SAMPLES]
        if len(chunk) < SAMPLE_RATE * 3:
            continue
        mel = log_mel_spectrogram(pad_or_trim(chunk, N_SAMPLES), n_mels=model.dims.n_mels)
        _, probs = detect_language(model, mel[None], tok)
        for k, v in probs[0].items():
            probs_sum[k] = probs_sum.get(k, 0.0) + float(v)
        n += 1
    if not n:
        print(json.dumps({"lang": None, "prob": 0.0}))
        return
    lang = max(probs_sum, key=probs_sum.get)
    print(json.dumps({"lang": lang, "prob": probs_sum[lang] / n}))


def detect_language(wav):
    """(language code or None, probability) from Whisper's detector; (None, 0.0) if anything goes wrong."""
    cmd = ["uv", "run", "--no-project", "--with", "mlx-whisper", "python3", str(Path(__file__).resolve()),
           "--worker-detect", str(wav)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        return None, 0.0
    try:
        line = next(l for l in reversed(r.stdout.splitlines()) if l.startswith("{"))
        d = json.loads(line)
        return d["lang"], d["prob"]
    except (StopIteration, ValueError, KeyError):
        return None, 0.0


def route(lang_arg, wav):
    """('parakeet' | 'whisper', detected_language, probability).
    --lang en -> Parakeet. --lang anything else -> Whisper. auto -> Whisper's detector decides, and
    anything but a confident English goes to Whisper (the original path)."""
    if not available():
        return "whisper", None, 0.0
    if lang_arg == "en":
        return "parakeet", "en", 1.0
    if lang_arg not in (None, "auto"):
        return "whisper", lang_arg, 1.0
    lang, prob = detect_language(wav)
    if lang == "en" and prob >= DETECT_MIN_PROB:
        return "parakeet", lang, prob
    return "whisper", lang, prob


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "--worker-transcribe":
        _worker_transcribe(sys.argv[2], sys.argv[3])
    elif len(sys.argv) >= 3 and sys.argv[1] == "--worker-detect":
        _worker_detect(sys.argv[2])
    else:
        print(__doc__)
        print("Parakeet available on this machine:", available())
