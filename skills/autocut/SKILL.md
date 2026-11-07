---
name: autocut
description: Turn a raw talking-head recording into a clean pre-cut file. Measures audio/video sync from the speaker's lips and fixes it, transcribes word by word, finds stumbles, false starts and restarts with a verbatim pass, removes silences, proposes retakes, renders with intact word edges and re-verifies the cut. Use when the user says "cut this", "clean this recording", "remove the silences and mistakes", "autocut", "prep this for dynamic-edit", or drops a raw recording and asks to get it ready. Plan first, render only after the human approves.
---

# /autocut

Raw recording in, clean pre-cut file out. You run every command; the human approves a plan and
watches the result. Never hand them a command line to run.

Repo root (scripts live there):

```bash
THP_HOME=${THP_HOME:-$(cat ~/.config/talking-head-pipeline/root)}
```

## Scope

| Situation | Pipeline |
|---|---|
| **Raw recording; silences, flubs and sync need fixing** | **this one** |
| Already-cut footage of a person on camera that should feel dynamic | `/dynamic-edit`, fed with this skill's `clean.mp4` |

This skill adds no effects, captions or graphics. It produces the file `/dynamic-edit` takes as
input. Chaining is the normal path: `/autocut` then `/dynamic-edit`.

## Why it works (explain it this way)

Two facts make naive auto-cutters "munch" words and drift out of sync:

1. **Wireless mics and capture software deliver audio early or late, by an amount that changes
   between sessions** (+240 ms was measured on one setup). So sync is MEASURED per file from lip
   motion (SyncNet) and applied before anything else. Never hardcoded.
2. **Whisper's word timestamps land on a real word boundary only about 2 times in 12.** Padding
   around a wrong number still clips words. So every word is re-timed with a forced aligner, and
   at render time every cut edge is snapped to the waveform itself.

And one fact makes them miss mistakes: **Whisper smooths repeats away.** "So let's talk about, so
let's talk about what happened" comes back as one clean sentence. A second, verbatim
transcription (CrisperWhisper) keeps every false start, repeat and filler; stumbles and restarts
are found in that.

## Workflow

### 1. Find the file, never touch it

Use the file the human named, or the newest recording in their capture folder (ask once where
that is). Confirm filename and duration in one line. The raw file is read-only for the whole job;
every output goes to `<raw dir>/<raw stem>_autocut/`.

### 2. Plan mode

```bash
python3 "$THP_HOME/scripts/autocut/autocut.py" "<raw.mp4>"
```

Sync detection is the slow part (about 1 minute on Apple Silicon, 3 to 10 minutes on CPU-only Linux, more on a busy machine). Say so
before you start. The rest of plan mode is about a minute once models are cached; the first run per
language downloads models (several minutes). Add `--lang en|pt|it|es|fr|de|nl` only if the detected
language is wrong. `--offset SECONDS` skips detection when the offset is already known;
`--no-sync` for screen-only footage with no face.

If detection fails (no face, low confidence) the script says so and continues at offset 0. Do not
invent a number. Tell the human it could not be measured and ask: proceed unsynced, or use a value
they give you.

### 3. Show the plan as a compact table, then STOP

Read `plan.md` from the workdir and present it (never paste the raw file):

```
  Source    take-01.mp4   01:47.9
  Sync      +240 ms (audio early), confidence 5.5, spread 0 ms
  Result    01:40.5 planned, 7.3 s removed, 5 cuts

  00:00.0-00:02.8   cut   silence 3.0 s          2.8 s
  00:23.6-00:24.9   cut   silence 2.0 s          1.3 s

  Stumbles (applied):  "so let's talk about, | so let's talk about"   keep the second take
  Restarts (proposed): 01:12.4 "there will be a loss at" x2 ...      apply_spans command listed
  Retake proposals (not applied):
  1  01:45.9-01:47.0  "and so"  ->  keep 01:47.0-01:48.1 "and so"
```

Flag in the same block: sync spread over 40 ms or confidence under 3.5; alignment start-shift p90
over 500 ms (the transcript is shaky); any retake row flagged as a Whisper decoder loop.

**Repetitions and false starts are cut by default.** That is what the word-by-word pass is for.
Precision still beats recall: a wrong cut costs a reshoot, a missed stumble costs one more cut.
Confident matches (immediate repeats, an abandonment with no punctuation between takes) are
applied; murkier ones are listed as `restart?` candidates. Read each candidate in context. Veto
anything that is a deliberate rhetorical repeat ("below 60, below 70, below 80"). Fillers (um, uh)
are listed, never auto-cut. **Keep the LAST take**; when a pause sits between two takes, the pause
marks where the second take starts.

Ask one question: approve as is, or name anything to put back. If a phrase is ambiguous, ask about
it specifically; do not guess. Nothing renders without an answer.

### 4. Apply edits from the numbers, never from memory

- Accept a retake or restart by its words, not by typed timestamps:
  ```bash
  python3 "$THP_HOME/scripts/autocut/apply_spans.py" <workdir> --drop "phrase@22.0"   # phrase nearest 22 s
  python3 "$THP_HOME/scripts/autocut/apply_spans.py" <workdir> --span 71.20:74.85     # from plan.md's listed command
  ```
  Read every context line it echoes back.
- Re-read `plan.json` from disk before rendering; the human may have edited it. A plan edited
  after a cut is re-cut automatically.
- Scripted pauses are content: a deliberate beat ("and the answer is... [pause] nothing") goes in
  `plan.json` as `keep_silences: [[s, e]]` (source seconds) so the cutter never tightens it.

### 5. Render

```bash
python3 "$THP_HOME/scripts/autocut/autocut.py" "<raw.mp4>" --render
```

What render does, so you can explain failures:
- **09p** long takes (over 3 min): caps pauses over 0.65 s to 0.30 s after the last sound + 0.20 s
  before the next. Silence here means every 5 ms frame under -55 dB. Never raise that threshold:
  word tails decay through -42..-55 dB and a higher threshold eats final consonants.
- **09a** snaps every cut edge out of sound runs and at least 50 ms clear of the sound it removes;
  trims head and tail to the first and last real word; cuts bracket noises ([UH], [lipsmack]) in
  gaps of 0.4 s or more.
- **09b** moves any kept start with sound running into it back into the silence (restores a
  clipped onset).
- The cutter drops any piece under 1 s with no sound (a "silent sliver" between two jump cuts) and
  prints `CHECK short piece with sound` for sub-1 s pieces it keeps. Listen to each one.

### 6. Verify the cut (not optional, in this order)

1. **`qa.md` `## Removed-span audit` first.** Every removed gap is checked for leftover speech
   (energy + an isolated transcription). A `FLAGGED` row means the cut is not shippable:
   investigate (loudest-window dB first, then listen to `qa/removed/spanNN.wav`), fix `keep`, and
   re-render. A lone one-word fragment with a LOW loudest-window dB is usually a click or breath,
   not speech; trust the energy number over the transcript text. `approved cut` rows are fine.
2. **Read `qa/verbatim_cut.txt` end to end, like an editor.** It is CrisperWhisper's verbatim
   transcript OF THE CUT. Look for any repeated phrase, fragment or whole-sentence retake that
   survived. **Never check a cut with a regular Whisper transcript: it hides exactly these.**
   Whole-sentence retakes said back to back after a pause are only caught this way.
3. `## Restarts still in the cut` and `## Edge clipping` in `qa.md`: resolve every FLAGGED row
   (number sequences like "928 ... 939" can be false positives; read them).
4. Checks the scripts cannot do:
   - output duration vs planned: a delta over 0.6 s is a problem;
   - sweep every join at 5 fps (frames 0.5 s either side, from `timemap.json`): no join on a
     gesture blur or a duplicated frame;
   - no internal pause over 1.0 s; no piece without a frame above -45 dB;
   - **constant frame rate**: counted frames / stream duration must equal the nominal fps
     exactly (30.0000, not 29.98). Recorders drop frames under load, and every frame-indexed tool
     downstream drifts if this is off.

Re-run just the QA without re-cutting: `autocut.py --qa-only --workdir <dir>`.

Open `clean.mp4` for the human (`open` on macOS, `xdg-open` on Linux).

### 7. Report and hand off

What was removed (table), where `clean.mp4` is, and one line: this is pre-cut input; say "make it
dynamic" to continue with `/dynamic-edit`. Captions for the next stage come from the verbatim
words, mapped into the cut timeline:

```bash
python3 "$THP_HOME/scripts/autocut/verbatim_cut_words.py" <workdir> -o words.json
```

### 8. Cleanup, only when the human says the video is done

The workdir holds `synced.mp4` (a full copy of the take) and `tmp/` render pieces. Ask before
deleting. `plan.json`, `transcript.json`, `verbatim.json` and `qa.md` are small; keep them.

## Hard rules

- **Plan gate is mandatory.** No render without the human's go.
- **Never hardcode a sync offset.** Measure it per file, or use one the human gives you.
- **The raw file is never modified.**
- **Check a cut with the verbatim transcript of the cut, never a regular Whisper transcript.**
- **Never pin an auto-generated edge.** `_meta.pinned_edges` is for edges a human checked against
  the waveform; pinning machine edges skips the snapper's clearance and eats words.
- **Silence is under -55 dB only.** Nothing between -40 and -55 dB is silence on a gated mic.
- **No stitched piece under 1 s without speech.**
- When a word or instruction is ambiguous, ask one specific question.

## Gotchas

- Whisper hallucinates empty segments on trailing room tone, with timestamps past the end of the
  file. Expected; the retake finder filters them. A thousand "retakes" in two seconds at the tail is
  a decoder loop, not real retakes, and plan.md says so.
- Sync detection needs a face on screen. Screen-recording-only footage: `--no-sync`, and say so.
- Many mics record quiet (around -30 LUFS). autocut does not normalize. Loudness belongs to the
  final master (`scripts/master/sync_trim.sh --loudnorm`); never apply it silently.

Full stage-by-stage reference: `$THP_HOME/docs/AGENT_GUIDE.md`.
