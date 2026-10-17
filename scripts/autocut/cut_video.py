#!/usr/bin/env python3
"""Cut mistakes + silences from an OBS recording, driven by a plan JSON.

Adapted from an earlier clip builder (the approved
pipeline). Same editorial rules: word-boundary snaps with generous padding,
silence tightening with drift-aware right edges, 30ms audio fades per join,
0.5s breathing tail with 0.3s fade on the final piece, per-range extract ->
lossless concat, output-timeline caption JSON + timemap for downstream
overlay placement.

Usage: python3 cut_video.py <plan.json> [--force]

Plan format:
{
  "source": "/abs/path/video.mp4",
  "transcript": "/abs/path/whisper.json",
  "output": "/abs/path/out.mp4",
  "keep": [[s, e], ...],          // KEEP ranges, source seconds (mistakes excluded)
  "tighten": true,                 // jump-cut silences > 1.2s inside keeps
  "keep_silences": [[s, e]],        // scripted pauses (source seconds) never tightened
  "captions": "/abs/path/captions.json",  // optional, output-timeline Caption[]
  "timemap": "/abs/path/timemap.json"     // optional, kept ranges + offsets
}
"""
import json
import math
import re
import subprocess
import sys
from pathlib import Path

PAD = 0.15
TIGHTEN_GAP = 1.2
TIGHTEN_PAD = 0.15


def load_words(transcript_path):
    data = json.loads(Path(transcript_path).read_text())
    words = []
    for seg in data["segments"]:
        for w in seg.get("words", []):
            words.append({"word": w["word"], "start": w["start"], "end": w["end"]})
    return words


def words_in_range(words, start, end):
    return [w for w in words if w["start"] >= start - 0.01 and w["end"] <= end + 0.01]


def tighten_ranges(ranges, words, silences=None):
    """Jump-cut gaps between words longer than TIGHTEN_GAP.

    A gap in the transcript is only evidence of a pause when the audio agrees.
    Whisper drops words, and a dropped phrase looks exactly like a 1 to 3 s gap.
    On one long take this function removed 17 spoken phrases that
    way ("I did a longer trade for December", "$50,000 was great"). So when
    `silences` (ffmpeg silencedetect spans) is given, a gap is cut only if at
    least 0.8 s of detected silence falls inside it, the same threshold
    silence_tighten uses. Without `silences` the old transcript-only behaviour
    remains for legacy callers, and it is unsafe."""
    if silences is not None:
        # The audio decides both eligibility and span. silence_tighten cuts each
        # detected silence with room tone kept on both sides; a transcript gap
        # adds nothing to that except the risk of spanning speech the aligner
        # mistimed ("because", "I did", "there's" were lost that way).
        return [tuple(r) for r in ranges]

    def gap_is_silent(a_end, b_start):
        return True

    out = []
    for s, e in ranges:
        ws = words_in_range(words, s, e)
        if not ws:
            out.append((s, e))
            continue
        cur_start = s
        for a, b in zip(ws, ws[1:]):
            if b["start"] - a["end"] > TIGHTEN_GAP and gap_is_silent(a["end"], b["start"]):
                out.append((cur_start, a["end"] + TIGHTEN_PAD))
                cur_start = b["start"] - TIGHTEN_PAD
        out.append((cur_start, e))
    return out


def silence_threshold_db(source):
    """Threshold relative to how loud the recording actually is.

    A fixed -35 dB treated soft word tails as silence on a wireless mic,
    which records around -33 LUFS integrated (17 dB under broadcast level), so
    "$502" lost its tail and "dollars" its last syllable. Measure integrated
    loudness and sit 15 dB under it, clamped to [-50, -30] dB."""
    res = subprocess.run(["ffmpeg", "-i", str(source), "-af", "ebur128", "-f", "null", "-"],
                         capture_output=True, text=True)
    m = re.findall(r"I:\s*(-?\d+(?:\.\d+)?) LUFS", res.stderr)
    lufs = float(m[-1]) if m else -16.0
    return max(-50.0, min(-30.0, lufs - 15.0))


def merge_silences(sil, gap=0.1):
    """silencedetect sometimes reports one pause as two spans a few ms apart
    (e.g. [95.953, 101.053] + [101.056, 102.533]). silence_tighten then
    keeps a margin on both sides of the seam and a 0.5 s piece of pure silence
    survives between two jump cuts (it plays as "a video frame with no audio",
    a silent cut sandwiched between two takes)."""
    out = []
    for s, e in sil:
        if out and s - out[-1][1] < gap:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return out


def detect_silences(source, cache_path):
    cache = Path(cache_path)
    if cache.exists():
        return merge_silences(json.loads(cache.read_text()))
    thr = silence_threshold_db(source)
    res = subprocess.run(
        ["ffmpeg", "-i", str(source),
         "-af", f"silencedetect=n={thr:.0f}dB:d=1.0", "-f", "null", "-"],
        capture_output=True, text=True)
    sil = []
    start = None
    for line in res.stderr.splitlines():
        if "silence_start:" in line:
            start = float(line.split("silence_start:")[1].strip())
        elif "silence_end:" in line and start is not None:
            end = float(line.split("silence_end:")[1].split("|")[0].strip())
            sil.append([start, end])
            start = None
    cache.write_text(json.dumps(sil))
    return merge_silences(sil)


def silence_tighten(ranges, silences, words, margin=0.25, min_piece=0.4):
    def right_edge(o_start, o_end):
        edge = o_end - margin
        nxt = next((w for w in words if w["end"] > edge), None)
        if nxt and o_start < nxt["start"] < o_end + 0.2:
            edge = min(edge, max(nxt["start"] - 0.05, o_start + 0.3))
        return edge

    out = []
    for s, e in ranges:
        pieces = [(s, e)]
        for ss, se in silences:
            new = []
            for a, b in pieces:
                o_start, o_end = max(ss, a), min(se, b)
                if o_end - o_start >= 0.8:
                    left = (a, min(b, o_start + margin))
                    right = (max(a, right_edge(o_start, o_end)), b)
                    added = False
                    if left[1] - left[0] >= min_piece:
                        new.append(left)
                        added = True
                    if right[1] - right[0] >= min_piece:
                        new.append(right)
                        added = True
                    if not added:
                        new.append((a, b))
                else:
                    new.append((a, b))
            pieces = new
        out.extend(pieces)
    return out


def snap_ranges(ranges, words, pinned=()):
    """pinned: edges that must not move. Content cuts reviewed against the
    verbatim word list are already on a word boundary; widening them by the
    aligner's idea of the neighbouring word put a whole "vamos" back into
    the 2026-09-09 terreno take."""
    out = []
    for s, e in ranges:
        pin_s = any(abs(s - x) < 1e-3 for x in pinned)
        pin_e = any(abs(e - x) < 1e-3 for x in pinned)
        inside = [w for w in words if w["start"] >= s - 0.01 and w["start"] <= e - 0.05]
        if not inside:
            out.append((s, e))
            continue
        first, last = inside[0], inside[-1]
        i0 = words.index(first)
        i1 = words.index(last)
        prev_end = words[i0 - 1]["end"] if i0 > 0 else 0.0
        next_start = words[i1 + 1]["start"] if i1 + 1 < len(words) else 1e9
        s2 = min(max(first["start"] - 0.15, prev_end + 0.02), first["start"])
        if last["end"] > e:
            e2 = e
        else:
            e2 = max(min(last["end"] + 0.20, next_start - 0.02), last["end"] + 0.06)
            # The 60 ms floor must not run into the next word: when the gap is
            # shorter than the pad, split the gap instead. A content cut on
            # "cripto, | seja" left a 150 ms "s" fragment before the join.
            if e2 > next_start - 0.02:
                e2 = max(last["end"], (last["end"] + next_start) / 2)
        # Pads may only widen a keep range. The incoming edges come from detected
        # silence (audio), the word edges come from the aligner, and the aligner
        # is wrong around pauses: it stretched "trade" across a 3.5 s gap and
        # ended "happened." 0.8 s early, so snapping to word edges here cut the
        # onset of one sentence and the tail of another on the 2026-09-08 take.
        s2 = min(s2, s)
        e2 = max(e2, e)
        if pin_s: s2 = s
        if pin_e: e2 = e
        out.append((s2, e2))
    return out


_FPS_CACHE = {}


def source_fps(source):
    """Nominal frame rate of the source as a string ffmpeg accepts (e.g. "30" or "30000/1001").

    OBS drops frames under load, so a "30 fps" recording carries slightly fewer
    frames than its duration implies (30369 over 1012.86 s on the 2026-09-08
    take). Encoding the pieces without a fixed rate preserved those gaps as
    variable frame timing, and every downstream tool that indexes by frame
    (head track, captions, punch landings) then drifted 0.55 s by the end of a
    17 min video. Pieces are therefore encoded at constant frame rate."""
    key = str(source)
    if key not in _FPS_CACHE:
        res = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                              "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0", str(source)],
                             capture_output=True, text=True)
        _FPS_CACHE[key] = (res.stdout.strip() or "30").split("\n")[0]
    return _FPS_CACHE[key]


def video_start(source):
    """First video pts. OBS starts the picture ~44 ms after the audio, so frames sit
    at v0 + k/fps, not on k/fps."""
    res = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                          "-show_entries", "stream=start_time", "-of", "csv=p=0", str(source)],
                         capture_output=True, text=True)
    try:
        return float(res.stdout.strip().split("\n")[0])
    except ValueError:
        return 0.0


def cut_range(source, start, end, out_path, fade_out=0.03, frames=None):
    dur = end - start
    fade_out_start = max(0, dur - fade_out)
    subprocess.run([
        "ffmpeg", "-v", "error", "-ss", f"{start:.6f}", "-to", f"{end:.6f}",
        "-i", str(source),
        "-af", f"afade=t=in:st=0:d=0.03,afade=t=out:st={fade_out_start:.3f}:d={fade_out}",
        "-fps_mode", "cfr", "-r", source_fps(source),
        # Exact frame count per piece. On 2026-09-24 18 of 128 pieces came out one
        # frame longer than their audio (cfr padding a grid that ignored the video
        # start offset); the concat stacked those frames and the picture ran 0.57 s
        # behind the sound by the end of a 12 min cut.
        *(["-frames:v", str(frames)] if frames else []),
        "-c:v", "libx264", "-crf", "18", "-preset", "medium",
        # PCM, not AAC: every AAC piece carried ~25 ms of encoder padding that
        # the concat kept, so the cut grew 0.22 s over 8 joins and captions
        # (timemap-exact) ran early by the end.
        # The audio is encoded once, at the concat.
        "-c:a", "pcm_s16le", "-ar", "48000",
        "-pix_fmt", "yuv420p",
        str(out_path), "-y",
    ], check=True)


class TimeMap:
    def __init__(self, ranges):
        self.entries = []
        off = 0.0
        for s, e in ranges:
            self.entries.append((s, e, off))
            off += e - s
        self.total = off

    def to_out(self, t):
        for s, e, off in self.entries:
            if s - 0.05 <= t <= e + 0.05:
                return min(max(t - s, 0), e - s) + off
        return None


SLIVER_MAX_S = 1.0     # Rule: a stitched piece under 1 s is almost always a mistake
SLIVER_SILENT_DB = -45  # ...and is dropped when nothing in it is louder than this (no speech)


def drop_silent_slivers(source, ranges):
    """Drop pieces shorter than SLIVER_MAX_S that hold no speech.

    The silence detector can split one pause into two touching spans, and the
    tightening then leaves a 0.5-0.7 s piece of pure room tone between them. With
    a gated mic that plays as a frame with no audio (a long-form take 1:01 and
    short 1 at 0:28 and 0:44, 2026-10-12; first seen 2026-09-29). A short piece
    WITH speech (a lone "So.") is kept and printed for a human to check.
    """
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(source), "-vn", "-ac", "1", "-ar", "16000",
                          "-f", "s16le", "-"], check=True, capture_output=True).stdout
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float64) / 32768.0
    hop = 160
    n = len(x) // hop
    db = 20 * np.log10(np.sqrt((x[: n * hop].reshape(n, hop) ** 2).mean(1)) + 1e-12)
    kept = []
    for s, e in ranges:
        if e - s < SLIVER_MAX_S:
            seg = db[int(s * 100): max(int(s * 100) + 1, int(e * 100))]
            peak = float(seg.max()) if len(seg) else -999.0
            if peak < SLIVER_SILENT_DB:
                print(f"dropped silent sliver {s:.2f}-{e:.2f} ({e - s:.2f}s, peak {peak:.0f} dB)")
                continue
            print(f"CHECK short piece with sound {s:.2f}-{e:.2f} ({e - s:.2f}s, peak {peak:.0f} dB)")
        kept.append((s, e))
    return kept


def main():
    plan = json.loads(Path(sys.argv[1]).read_text())
    force = "--force" in sys.argv
    source = Path(plan["source"])
    out = Path(plan["output"])
    words = load_words(plan["transcript"])
    sil_cache = out.with_suffix(".silences.json")
    silences = detect_silences(source, sil_cache)
    # pauses that are part of the script (a fill-in-the-blank beat) are never tightened
    held = plan.get("keep_silences", [])
    silences = [x for x in silences if not any(x[0] < b and a < x[1] for a, b in held)]

    ranges = [tuple(r) for r in plan["keep"]]
    merged = [list(ranges[0])]
    for s, e in ranges[1:]:
        if s <= merged[-1][1] + 0.06 and e >= merged[-1][0]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    ranges = [tuple(r) for r in merged]
    if plan.get("tighten", True):
        ranges = tighten_ranges(ranges, words, silences)
        ranges = silence_tighten(ranges, silences, words)
    pinned = [v for c in plan.get("_meta", {}).get("content_cuts", []) for v in (c["from"], c["to"])]
    ranges = snap_ranges(ranges, words, pinned)
    # Boundaries on the frame grid: a piece of 20.79 s of audio became 20.80 s of
    # video (whole frames), so audio and picture parted by a frame per join.
    num, den = (source_fps(source).split("/") + ["1"])[:2]
    fps = float(num) / float(den)
    # outward: a keep starts on the frame at or before its edge and ends on the frame at
    # or after it, so the grid never clips a word onset ("que" lost 13 ms on 2026-09-10)
    # The grid is the video's own frame times (v0 + k/fps). A grid on k/fps put every
    # boundary between two frames, and cfr then padded a duplicate into some pieces.
    v0 = video_start(source) % (1 / fps)
    ranges = [(v0 + math.floor((s - v0) * fps + 1e-6) / fps, v0 + math.ceil((e - v0) * fps - 1e-6) / fps)
              for s, e in ranges]
    ranges = [(s, e) for s, e in ranges if e - s >= 2 / fps]
    ranges = drop_silent_slivers(source, ranges)
    ranges[-1] = (ranges[-1][0], ranges[-1][1] + 0.5)

    tmap = TimeMap(ranges)
    print(f"{len(ranges)} pieces, output {tmap.total:.1f}s "
          f"(source keeps {sum(e - s for s, e in [tuple(r) for r in plan['keep']]):.1f}s)")

    # Skip only when the existing cut is newer than the plan. A plan edited after
    # the cut (reviewed stumbles, a dropped opener) used to be silently ignored
    # while timemap and captions were rewritten for the new plan: captions then
    # drifted against a stale video (seen on two vertical reels).
    plan_mtime = Path(sys.argv[1]).stat().st_mtime
    if out.exists() and not force and out.stat().st_mtime >= plan_mtime:
        print(f"{out.name}: exists and is newer than the plan, skipping cut (--force to redo)")
    else:
        tmp = out.parent / "tmp"
        tmp.mkdir(exist_ok=True)
        parts = []
        for i, (s, e) in enumerate(ranges):
            part = tmp / f"{out.stem}_part{i:03d}.mov"
            cut_range(source, s, e, part,
                      fade_out=0.3 if i == len(ranges) - 1 else 0.03,
                      frames=round((e - s) * fps))
            parts.append(part)
            print(f"  piece {i + 1}/{len(ranges)}: {s:.2f}-{e:.2f}", flush=True)
        concat_list = tmp / f"{out.stem}_concat.txt"
        concat_list.write_text("".join(f"file '{p.resolve()}'\n" for p in parts))
        subprocess.run([
            "ffmpeg", "-v", "error", "-f", "concat", "-safe", "0",
            "-i", str(concat_list), "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart",
            str(out), "-y",
        ], check=True)
        print(f"wrote {out}")

    if plan.get("timemap"):
        Path(plan["timemap"]).write_text(json.dumps({
            "total": tmap.total,
            "entries": [{"srcStart": s, "srcEnd": e, "outOffset": off}
                        for s, e, off in tmap.entries],
        }, indent=1))

    if plan.get("captions"):
        captions = []
        for ri, (s, e, off) in enumerate(tmap.entries):
            cap_end = e - 0.5 if ri == len(tmap.entries) - 1 else e
            for w in words:
                if not (w["start"] >= s - 0.01 and w["start"] <= cap_end - 0.09):
                    continue
                t0 = w["start"] - s + off
                t1 = min(w["end"], e) - s + off
                raw = w["word"] if w["word"].startswith(" ") else " " + w["word"]
                if raw.lstrip().startswith("-"):
                    raw = raw.lstrip()
                captions.append({
                    "text": raw,
                    "startMs": round(t0 * 1000),
                    "endMs": round(t1 * 1000),
                    "timestampMs": round((t0 + t1) / 2 * 1000),
                    "confidence": None,
                })
        Path(plan["captions"]).write_text(json.dumps(captions))
        print(f"wrote {len(captions)} caption tokens")


if __name__ == "__main__":
    main()
