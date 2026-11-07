# Agent guide

For the AI agent (Claude Code, Codex, or any agent with a shell) running this pipeline for a human.
Read this once end to end, then follow `skills/autocut/SKILL.md` and `skills/dynamic-edit/SKILL.md`
for the commands.

## Your job, in one paragraph

The human records themselves talking. You turn that raw file into a finished, dynamic video. You run
every command; the human never has to touch a terminal. You stop at **three gates** and show them
something concrete each time, and you never present work that has not passed QA. When something is
ambiguous, ask one specific question. When the plan is approved, re-read it from disk, then build.

```
raw.mp4
  |  /autocut plan mode  ............................  GATE 1: the cut plan (table)
  |  /autocut --render + verbatim re-check  .........  shows: clean.mp4
  |  /dynamic-edit plan  ............................  GATE 2: the edit plan (table)
  |  build: roto, 3D, cards, screens, SFX; stills first
  |  render + QA + sync trim  .......................  GATE 3: the final video
  v
final.mp4
```

Some humans pre-approve the cut and only want to see the final; ask once at the start, then follow
what they said.

## Set-up checks before the first job

```bash
THP_HOME=${THP_HOME:-$(cat ~/.config/talking-head-pipeline/root)}
python3 "$THP_HOME/scripts/autocut/whisper_backend.py"      # which Whisper this machine uses
ls ~/.local/share/talking-head-pipeline/syncnet/venv/bin/python || echo "run $THP_HOME/scripts/sync/setup_syncnet.sh"
```

Missing pieces: `docs/SETUP.md`. First-ever runs download several GB of models; say so up front.

## What to ask the human (and when)

Ask at the start, once:
- Where are recordings saved, and where should video projects live? (Never write deliverables to the
  Desktop or into the recordings folder.)
- Output: 16:9, 9:16, or both? Platform (YouTube, Shorts/Reels/TikTok, X, LinkedIn)?
- Do they want to approve the cut, or only the final?
- Brand: accent colour, caption font preference, logo/end card file, a series font for 3D type.
- Lens and aperture, if they want depth-matched graphics (one word beats any estimate).

Ask during the job, only when needed:
- An ambiguous stumble ("is the repeat at 1:12 deliberate?").
- A proper noun the transcript may have mangled ("is it 'Acme Labs' or 'Akme'?").
- A number on screen you cannot source from what they said.
- Whether a full-screen animation is wanted at all (default: none unless asked).

Never ask them to run a command, open a JSON file, or choose between technical options they cannot
judge. Translate: "the audio was 240 ms ahead of your lips; fixed".

## Stage reference: /autocut

Workdir: `<raw dir>/<raw stem>_autocut/`. Every stage is cached and skipped on re-run unless `--force`.

| Stage | What | Output | Cost |
|---|---|---|---|
| 01 probe | ffprobe | info.json | instant |
| 02 sync | SyncNet on 2 windows (start, end) -> offset; ffmpeg shift | synced.mp4 (or a link if 0) | ~1 min on Apple Silicon, 3-10 min CPU-only (skip with --offset) |
| 03 audio | 16 kHz mono | audio.wav | instant |
| 04 transcribe | Whisper, word timestamps | transcript.raw.json | ~10 s for a 2 min take on Apple Silicon |
| 05 align | forced aligner re-times word edges | transcript.json | ~25 s on first run per language + model download |
| 06 silences | ffmpeg silencedetect | silences.json | seconds |
| 07 retakes | near-duplicate lines close in time | retakes.json | instant |
| 07b stumbles | CrisperWhisper verbatim + repeats/false starts/fillers | verbatim.json, stumbles.json | 20-40 s |
| 07c restarts | phrase said, abandoned, said again within 12 s | plan.md section | instant |
| 08 plan | keep ranges + report | plan.json, plan.md | instant |
| 09p pauses | long takes: cap pauses over 0.65 s | plan.json `_meta` | seconds |
| 09a snap | every edge into real silence; noises cut | plan.json | seconds |
| 09b onsets | restore clipped word starts | plan.json pinned edges | seconds |
| 09 render | per-piece CFR encode + concat, 30 ms fades | clean.mp4, timemap.json, captions.json | under half realtime |
| 10 qa | duration, silences, frames | qa.md, qa/*.png | seconds |
| 11 audit | every removed span: energy + isolated transcription | qa.md, qa/removed/ | ~30 s + per span |
| 12 verbatim | CrisperWhisper of the CUT; restarts still in it; edge clipping | qa/verbatim_cut.txt | 20-40 s |

## Stage reference: /dynamic-edit

| Step | Command | Output |
|---|---|---|
| scaffold | `cp -R $THP_HOME/template <P>`; venv; `download_models.sh`; `pnpm install` | project |
| words | `verbatim_cut_words.py <workdir> -o remotion/public/words.json` | words in cut timeline |
| cuts | `scripts/detect_cuts.py` | cuts.json (add missed boundaries by hand) |
| track | `scripts/track_head.py --cuts` | track.json (`detectionRate` >= 0.9) |
| plan | `scripts/build_plan.py` (from build_plan.example.py) | plan.json, captions.json |
| 3D | `tools/render3d` stills then `--clip` | public/<dir>/f####.png |
| SFX | `scripts/add_sfx.py <P> sfx_map.json` | sfx events in plan.json |
| stills | `npx remotion still src/index.ts Edit out.png --frame=N` | PNGs to look at |
| render | `scripts/render_and_qa.sh <P> <name>` | renders/<name>.mp4, qa_frames/ |
| sync trim | `scripts/master/sync_trim.sh render raw out [--loudnorm -14]` | final |
| patch | `scripts/patch_render.sh --base --replace --render --out` | fixed final in seconds |

## Planning the edit (how to think)

1. **Read the transcript like an editor.** Mark: the hook, the claim, each number, each turn, each
   reveal, the payoff, the moments that are better shown than said, the screen walkthrough if any.
2. **Assign tools to beats**, sparingly. Most sentences get nothing. See the toolbox in the
   dynamic-edit SKILL.md and the rules in `STYLE_RULES.md`.
3. **Name why / in / out for every event** from the words. The plan writer enforces anchors.
4. **Check the geometry before promising it**: zoom headroom for reframes, the face box for anything
   placed beside the head, the caption band for anything near the bottom, platform safe zones on 9:16.
5. **Budget the expensive things**: roto seconds (~2 min GPU time per footage minute, plus the QA pass), 3D frames,
   full renders. Say the cost in the plan.
6. **Present a table**, wait, then re-read plan.json from disk.

## QA checklist (before any gate shows a video)

Cut (autocut):
- [ ] Removed-span audit: zero unresolved FLAGGED rows
- [ ] `qa/verbatim_cut.txt` read end to end: no repeat, fragment or whole-sentence retake
- [ ] Restarts and edge-clipping sections clean
- [ ] Every join swept at 5 fps; no pause over 1.0 s; no silent sub-1 s piece
- [ ] Constant frame rate (frames / duration == nominal fps)
- [ ] Duration within 0.6 s of planned

Edit (dynamic-edit, `skills/dynamic-edit/references/qa.md` has the scripts):
- [ ] Matte: dead = 0, worst jump < 8 points (if roto)
- [ ] Occlusion: zero spikes (if anything sandwiched)
- [ ] Edge safety over magenta: zero pixels (if reframe/side)
- [ ] Face box: nothing over the face at any frame of any window
- [ ] Stills at every landing (+25): every glyph readable, equal edge padding, nothing sliced
- [ ] 5 fps sweeps around every cut, transition and layout change
- [ ] Static UI text pixel-identical frame to frame (no jitter)
- [ ] Zero A-B-A flickers; no blank frames
- [ ] Captions: same band in every layout, phrases emphasised whole, proper nouns right, digits
- [ ] Every on-screen number verified
- [ ] SFX tied to visible events, subtle
- [ ] Final sync |offset| < 5 ms at start and end; yuv420p bt709; plays in QuickTime/VLC

Report gates with their numbers. Then open the file for the human (`open` / `xdg-open`).

## Common failure modes and fixes

| Symptom | Cause | Fix |
|---|---|---|
| Words clipped at cuts ("ex-" missing) | edge placed from transcript times | let snap_edges run (never pin machine edges); stage 09b restores onsets; check `## Edge clipping` |
| A repeat survived the cut | checked with regular Whisper, or a whole-sentence retake after a pause | read `qa/verbatim_cut.txt`; drop the first take by exact words with `apply_spans.py --drop` |
| Thousands of "retakes" at the end | Whisper decoder loop on room tone | ignore; plan.md flags it; silence cutting handles the tail |
| "0.5 s frame with no audio" between jump cuts | two touching silence spans | the cutter drops silent sub-1 s pieces; re-render |
| Final syllables eaten on a long take | pause threshold above -55 dB or pinned machine edges | keep -55 dB; remove machine pins |
| Lips out of sync | offset not measured, or render audio delay | re-run sync detection; always `sync_trim.sh` the final |
| Effects drift late by the end | variable frame rate source | re-cut (cut_video encodes CFR); check frames/duration |
| Caption slides after every camera angle change | tracking without `--cuts` | re-track with `--cuts`; add missed boundaries |
| Graphic in front of the matte | a layer not wrapped in its own AbsoluteFill | wrap it |
| Matte holes / a sign fused to the silhouette | matting on a squashed frame, bright object touching the subject | the default RVM engine rarely does this; use `--track` region filtering, `--exclude` for a static sign |
| `mp.solutions` AttributeError / Metal "Service is unavailable" | MediaPipe 1.0+ | `mediapipe==0.10.21`, Python 3.11 |
| WebGL scene black or render fails headless | GL backend | keep `setChromiumOpenGlRenderer('angle')` |
| Render plays blank in QuickTime | yuvj420p output | re-encode to yuv420p bt709 |
| One Chrome tab doing all the work, 40+ min renders | no GL flag / low concurrency | `--concurrency=4-6`, ANGLE |
| Single frames at the wrong layout in a zoomed UI | `transform: scale` on a whole page | zoom a positioned wrapper or rebuild the region |
| Static UI text shimmering | subpixel text rendering | `textRendering: 'geometricPrecision'` on the stage |
| Hero digit hidden behind the head | word placed at head height | raise it (`y` about -0.2) and check landing + 25 |
| 3D render all transparent | object outside the frame, or `in` never reached | stills at in, in+10; check x/y and `f0`/`f1` |
| 3D render very slow on Linux | SwiftShader fallback | set `RENDER3D_GL_ARGS` for your GPU; lower `spp` |
| SFX too loud | first-pass levels | start at volumes ~0.01-0.05; RMS check vs the voice |
| Fix requested after delivery | | `patch_render.sh` the affected range; never re-render the whole video |

## Speed (where the hours actually go)

Rendering itself is not the slow part. The time goes to: re-rendering a whole video for a local fix
(use `patch_render.sh`), re-encoding the full source for a small change (encode only the stretch you
need), judging plans by renders instead of stills, and PNG frames on opaque output (the template uses
JPEG frames). Nice and lock long jobs so a machine stays usable; kill every background process you
start (studio servers, browsers, renders) before you finish.

## Files that matter

- `<workdir>/plan.json` (cut), `plan.md`, `qa.md`, `qa/verbatim_cut.txt`, `timemap.json`, `verbatim.json`
- `<project>/scripts/build_plan.py` (the edit, as code), `remotion/plan.json` (generated)
- `<project>/remotion/public/{raw.mp4, words.json, track.json, captions.json, cut/, <3d dirs>/, sfx/}`
- `<project>/renders/`, `qa_frames/`
