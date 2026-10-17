#!/usr/bin/env python3
"""CrisperWhisper 2.0 backend. Not meant to be run directly with the system
Python -- align_words.py invokes this via:

    uv run --python 3.11 --with "crisperwhisper[transformers]" --with "transformers<5" --with ctranslate2 \
        python3 backends/crisperwhisper_align.py <audio.wav> <lang_code> [model_size]

Unlike the WhisperX backend, this is a full re-transcription (CrisperWhisper
is its own ASR model with much tighter native word timing), not a re-timing
of an existing transcript. align_words.py fuzzy-matches its word list back
onto the baseline transcript's words by normalized text.

ctranslate2 is listed as an extra --with because crisperwhisper's transformers
codepath imports a loop-detection helper from its ctranslate2-backend module
at call time even when running pure PyTorch -- without it the import fails.
`backend="transformers"` is forced explicitly: with ctranslate2 installed,
CrisperWhisperModel's "auto" backend picks the CTranslate2 engine, which
doesn't support Apple Silicon's mps device.

Prints one JSON object to stdout: {"words": [{"word","start","end"}, ...]}.
"""
import sys
import json


def main():
    audio_path, lang = sys.argv[1], sys.argv[2]
    model_size = sys.argv[3] if len(sys.argv) > 3 else "turbo"

    import crisperwhisper as cw

    model_name = cw.OFFICIAL_MODELS.get(model_size, model_size)
    device = "mps" if _mps_available() else "cpu"
    model = cw.CrisperWhisperModel(model_name, backend="transformers", device=device, compute_type="float16")
    result = model.transcribe(audio_path, language=lang, mode="verbatim", word_timestamps=True)

    words = []
    chunks = getattr(result, "chunks", None)
    chunk_words_present = chunks and any(getattr(c, "words", None) for c in chunks)
    if chunks and chunk_words_present:
        for c in chunks:
            for w in getattr(c, "words", []) or []:
                words.append(_word_dict(w))
    else:
        # longform audio (>30s): per-chunk word lists aren't populated, use
        # the flat top-level list instead
        for w in getattr(result, "words", []) or []:
            words.append(_word_dict(w))

    json.dump({"words": words}, sys.stdout)


def _word_dict(w):
    if hasattr(w, "__dict__"):
        return {"word": w.word, "start": w.start, "end": w.end}
    return w


def _mps_available():
    try:
        import torch
        return torch.backends.mps.is_available()
    except Exception:
        return False


if __name__ == "__main__":
    main()
