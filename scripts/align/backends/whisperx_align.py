#!/usr/bin/env python3
"""WhisperX forced-alignment backend. Not meant to be run directly with the
system Python -- align_words.py invokes this via:

    uv run --python 3.11 --with whisperx python3 backends/whisperx_align.py \
        <audio.wav> <segments.json> <lang_code>

<segments.json> is a flat list of {"text","start","end"} taken from the
mlx-whisper baseline transcript -- WhisperX re-times the words INSIDE that
existing text, it does not re-transcribe.

Prints one JSON object to stdout: {"words": [{"word","start","end"}, ...]}.
Any word WhisperX can't place is simply omitted (align_words.py falls back
to the baseline timestamp for those).
"""
import sys
import json


def main():
    audio_path, segments_path, lang = sys.argv[1], sys.argv[2], sys.argv[3]
    segments = json.loads(open(segments_path).read())

    import whisperx

    device = "cpu"  # the wav2vec2 CTC heads are small; MPS gave no reliable win in testing
    model, metadata = whisperx.load_align_model(language_code=lang, device=device)
    audio = whisperx.load_audio(audio_path)
    result = whisperx.align(segments, model, metadata, audio, device, return_char_alignments=False)

    words = []
    for seg in result["segments"]:
        for w in seg.get("words", []):
            if w.get("start") is None or w.get("end") is None:
                continue
            words.append({"word": w.get("word"), "start": float(w["start"]), "end": float(w["end"])})

    json.dump({"words": words}, sys.stdout)


if __name__ == "__main__":
    main()
