#!/usr/bin/env python3
"""One Whisper call for every platform.

macOS on Apple Silicon: mlx-whisper (fast, Metal) through `uvx`.
Everything else (Linux, Intel Mac, WSL): faster-whisper through `uv run --with faster-whisper`.
Force one with WHISPER_BACKEND=mlx|faster. Both write the same JSON shape mlx-whisper writes:

    {"text", "language", "segments": [{"start", "end", "text", "words": [{"word", "start", "end", "probability"}]}]}

so nothing downstream knows which backend ran.

    whisper_backend.py --worker <wav> <out.json> [--language xx] [--no-words]   (internal, faster-whisper side)
"""
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MLX_MODEL = "mlx-community/whisper-large-v3-turbo"
FASTER_MODEL = os.environ.get("FASTER_WHISPER_MODEL", "large-v3-turbo")


def backend():
    forced = os.environ.get("WHISPER_BACKEND")
    if forced in ("mlx", "faster"):
        return forced
    return "mlx" if sys.platform == "darwin" and platform.machine() == "arm64" else "faster"


def transcribe(wav, out_json, language=None, words=True):
    """Transcribe wav to out_json (mlx-whisper JSON shape). Loop guards on: without them Whisper
    repeats a short phrase for 20+ s over room tone and swallows real speech."""
    wav, out_json = Path(wav), Path(out_json)
    if backend() == "mlx":
        cmd = ["uvx", "--from", "mlx-whisper", "mlx_whisper", str(wav), "--model", MLX_MODEL,
               "--word-timestamps", "True" if words else "False",
               "--condition-on-previous-text", "False", "--output-format", "json",
               "--output-dir", str(out_json.parent)]
        if words:
            cmd += ["--hallucination-silence-threshold", "2"]
        if language:
            cmd += ["--language", language]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            sys.exit(f"error: mlx_whisper failed on {wav.name}:\n{(r.stderr or '')[-2000:]}")
        produced = out_json.parent / f"{wav.stem}.json"
        if not produced.exists():
            sys.exit(f"error: expected mlx_whisper output {produced} not found")
        if produced != out_json:
            produced.replace(out_json)
    else:
        cmd = ["uv", "run", "--python", "3.11", "--with", "faster-whisper>=1.1", "python3", str(Path(__file__)),
               "--worker", str(wav), str(out_json)]
        if language:
            cmd += ["--language", language]
        if not words:
            cmd += ["--no-words"]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            sys.exit(f"error: faster-whisper failed on {wav.name}:\n{(r.stderr or '')[-2000:]}")
    return out_json


def transcribe_text(wav, out_dir, language=None):
    """Plain text of a short clip (the removed-span audit)."""
    out = Path(out_dir) / f"{Path(wav).stem}.json"
    transcribe(wav, out, language=language, words=False)
    text = json.loads(out.read_text()).get("text", "").strip()
    out.with_suffix(".txt").write_text(text + "\n")
    return text


def _worker(argv):
    from faster_whisper import WhisperModel

    wav, out = argv[0], argv[1]
    language = argv[argv.index("--language") + 1] if "--language" in argv else None
    words = "--no-words" not in argv
    model = WhisperModel(FASTER_MODEL, device="auto", compute_type="auto")  # CUDA when present, else CPU
    kw = dict(language=language, word_timestamps=words, condition_on_previous_text=False)
    if words:
        kw["hallucination_silence_threshold"] = 2
    segs, info = model.transcribe(wav, **kw)
    out_segs = []
    for s in segs:
        seg = {"id": s.id, "start": s.start, "end": s.end, "text": s.text}
        if words:
            seg["words"] = [{"word": w.word, "start": w.start, "end": w.end, "probability": w.probability}
                            for w in (s.words or [])]
        out_segs.append(seg)
    Path(out).write_text(json.dumps({"text": "".join(s["text"] for s in out_segs),
                                     "language": info.language, "segments": out_segs}))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        _worker(sys.argv[2:])
    else:
        print(__doc__)
        print("backend on this machine:", backend())
