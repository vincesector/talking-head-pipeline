---
name: dynamic-edit
description: Build a dynamic talking-head edit in Remotion from pre-cut footage. Punch-ins chosen from the transcript, a side layout with content cards, a screen scene with a camera picture-in-picture, rotoscoped depth (hero words and objects passing behind the speaker), path-traced 3D hero type and 3D logos, fixed captions with phrase emphasis, subtle SFX tied to visible events, then a measured audio sync trim. Use when the user asks to make a talking head "more dynamic", add punch-ins or zooms, put graphics beside or behind them, show a screen walkthrough, or "edit this like a pro". Expects PRE-CUT footage (a raw take goes to /autocut first). Proposes a plan for approval before rendering anything expensive.
---

# /dynamic-edit

A talking head that never moves is dead on arrival; one that moves for no reason is worse. This
pipeline decides which effect earns its place on which word, writes that down as a plan the human
can veto, and only then spends compute.

Repo root:

```bash
THP_HOME=${THP_HOME:-$(cat ~/.config/talking-head-pipeline/root)}
```

Read before planning: `$THP_HOME/docs/STYLE_RULES.md` (the craft rules), `$THP_HOME/docs/LAYOUTS.md`
(geometry and caption safe zones), `references/plan-format.md` (the schema), `references/qa.md`
(the gates). 3D: `$THP_HOME/docs/3D.md`.

**Input contract: the footage is already cut.** No silence removal, no filler pass here. A raw take
goes to `/autocut` first; come back with its `clean.mp4` and its workdir (for verbatim words).

**Never skip the plan step.** Rotoscoping costs about 12 minutes per minute of footage and a full
render tens of minutes. A wrong guess caught in a text plan costs nothing.

## Workflow

### 1. Scaffold the project

```bash
P=<projects dir>/<slug>                 # ask where the human keeps video projects; never the Desktop
cp -R "$THP_HOME/template" "$P"
cd "$P"
uv venv --python 3.11 .venv            # mediapipe has no wheels past 3.12
uv pip install --python .venv/bin/python "mediapipe==0.10.21" opencv-python backgroundremover numpy pillow
scripts/download_models.sh             # MediaPipe face detector (not shipped in the repo)
(cd remotion && pnpm install)          # or npm install
cp "<autocut workdir>/clean.mp4" remotion/public/raw.mp4
python3 "$THP_HOME/scripts/autocut/verbatim_cut_words.py" "<autocut workdir>" -o remotion/public/words.json
```

Vertical reel from a 16:9 take: `scripts/prep_vertical.sh "<autocut workdir>" "$P"` instead of the
last two lines (static 9:16 crop on the median head x, never a follow-crop).

### 2. Inventory, cuts, track

```bash
ffprobe -v error -select_streams v:0 -show_entries stream=width,height,r_frame_rate,nb_frames \
  -show_entries format=duration -of default=nw=1 remotion/public/raw.mp4
.venv/bin/python scripts/detect_cuts.py remotion/public/raw.mp4 --out remotion/public/cuts.json
.venv/bin/python scripts/track_head.py remotion/public/raw.mp4 --out remotion/public/track.json --cuts remotion/public/cuts.json
```

- **Zoom headroom** = source width / timeline width (2560 into 1920 = 1.33x free). Past it you upscale.
- Aspect is auto-detected from plan width/height (`lib/layouts.ts` profiles). One engine, never a fork.
- Read `detectionRate` in track.json. Under ~0.9, face-anchored moves are unreliable; say so.
- Cut detection misses gradual changes (an animated switch to a screen share). Sample one frame per
  segment and add missed boundaries to cuts.json by hand. Screen-share segments get no punch-ins,
  no captions drawn over them, no cards (set `captions.silence` to those ranges).

### 3. Proofread the words

Grep `words.json` for every proper noun, brand, ticker and person the script names. Whisper-family
models mangle them and the sentence still reads fluently, so review never catches it. Fix the words
file (merging two tokens into one is fine), never the render. Numbers as digits.

### 4. Write the plan, then STOP

1. Read the whole transcript first. Find the beats the narrative actually has: hook, claim, number,
   turn, reveal, payoff, the moment better shown than said.
2. Choose a tool per beat from **Choosing effects** below. Many beats get nothing.
3. Copy `scripts/build_plan.example.py` to `scripts/build_plan.py` and write the beats there with
   word anchors (`"phrase@seconds"`). It writes `remotion/plan.json` and the captions. It refuses
   events without a reason, without word anchors for entry AND exit, or punches spaced too tight.
4. Show the human a table, one row per event: time, effect, "lands on X, leaves after Y, because Z".
   Plus: roto seconds (and the matting time that implies), any reframe beyond zoom headroom, any
   stretch over ~12 s with no event, and the 3D renders needed.
5. **Wait for approval.** Then re-read `plan.json` from disk; the human may have edited it.

If the human named a specific effect at a specific moment, that is the plan for that beat.

### 5. Build what the plan needs, nothing more

- **Roto windows:** `scripts/render_and_qa.sh` mattes them; or `scripts/matte_frames.py` per window.
- **3D hero type / 3D assets:** `tools/render3d` (see docs/3D.md). Stills first (`--stills`), look at
  them, then `--clip --dir=remotion/public/<name>`. Put the same in/out frames in the shot as the
  plan event's `at`/`until`.
- **Side cards:** kinds in `remotion/src/layouts/cards.tsx`; add a kind there when needed.
- **Screen scene pages:** `remotion/src/screen/pages.tsx`. Rebuild UI in code for anything you zoom
  into; a screenshot goes soft at 2x.
- **Full-screen scenes:** `scenes/fullscreen/registry.ts` (`depth`, `clip`, `stage`).
- **SFX:** after the plan is final, `scripts/add_sfx.py "$P" sfx_map.json --library <dir>`.

### 6. Check with stills, then render

Stills cost seconds; a render costs the afternoon:

```bash
cd remotion && npx remotion still src/index.ts Edit ../qa/landing.png --frame=<N>
```

Check every hero landing (and landing + 25), every layout entry, every transition, every 3D
arrival. Then:

```bash
scripts/render_and_qa.sh "$P" <name>        # mattes roto windows, renders, writes QA sheets
```

Renders: `--concurrency` 4-6, `nice` the process, and keep `Config.setChromiumOpenGlRenderer('angle')`
(already in remotion.config.ts) or WebGL scenes fail headless. Deliver yuv420p bt709; a yuvj420p
file plays blank in QuickTime.

### 7. QA (references/qa.md), then sync trim

Run every gate in `references/qa.md` before anyone sees it. Then measure and trim the render's audio
delay against the source (Remotion renders run a few tens of ms late; measured, never assumed):

```bash
"$THP_HOME/scripts/master/sync_trim.sh" renders/<name>.mp4 remotion/public/raw.mp4 renders/<name>_final.mp4 [--loudnorm -14]
```

Target |final sync| under 5 ms. Loudness normalization only if the human wants it (social default
-14 LUFS). Open the final for the human.

### 8. Fixes after delivery: patch the range, never re-render the video

```bash
scripts/patch_render.sh --base renders/prev.mp4 --replace 0-1049 --render 0-887 --out renders/next.mp4
```

`--replace` is the old render's range to throw away, `--render` the current plan's range that
replaces it (they differ when the source was re-cut). Only the patch is encoded; head and tail are
stream-copied on keyframes; the frame count is verified. When a stumble has to come out of the
source after the plan exists, rebuild the plan from anchors (build_plan.py) so every effect moves
with its word.

### 9. Cleanup, only when the human says the video is done

Ask first. `scripts/cleanup.sh` deletes matte PNGs, frame dumps, QA sheets, drafts, the venv and
node_modules; it keeps the plan, source, track, captions and final render. Regenerating a matte costs
~12 min per footage minute, so never run it unprompted.

## Choosing effects (a toolbox, not a running order)

There is no formula. A video with no hero word, no roto, no 3D is a valid plan. A straight piece to
camera may be punch-ins and captions only. Every effect is earned by something in the script, and
every event names **why** (its narrative job), **in** (the word it lands on; the move starts
before it so it ARRIVES on it) and **out** (the word it leaves after: end of that thought, the next
real pause, the word before a softener). Never a fixed hold, never "it was quiet for a while".

- **Face first.** The first 2-3 s are the speaker's face, frame 0 already a readable hook image (not a
  fade from black). No full-screen graphic before ~2.5 s: autoplay is muted and a stats-first open
  reads as an infographic and gets scrolled.
- **Punch-in** (the workhorse): sentence-long, few, purposeful. It lands as the key sentence builds,
  holds through it, releases on its last word. Never a one-word punch; never spaced by a timer.
  Roughly one per 30-45 s of talking head on long form; tighter on shorts only if the script earns
  it. Anchored on the tracked face. Two linked phrases: punch the half that carries the story.
  Nested accent (sustain + a small accent on the key phrase) instead of three punches in a sentence.
- **Side layout** (16:9): when a number, list or comparison should stay on screen while it is
  explained. Subject slides to one side, a content-sized card on the other, cards swap on their
  words and punch on the number being said. Most info beats in long form want this.
- **Screen scene** (16:9): the "here is how it looks" walkthrough. Use once or twice per video, not
  for every mention. One-to-one with the real UI if it recreates a product; only the data changes,
  and the data is real.
- **Offset reframe with cards:** a lighter version of side, inside the zoom headroom.
- **Roto (behind the subject):** openers and hero moments only. Default budget 15 s per video;
  warn above 30 s; above 60 s ask. Anything passing behind must be worth occluding.
- **Hero word behind the subject:** a hook, a hard turn, the named idea. Above the head, every glyph
  readable (check a still at landing + 25). One per video unless two land far apart.
- **3D hero type:** a big claim or number beside the head or across the chest, equal padding from
  every frame edge (at least ~90 px at 1080 wide), never on the face.
- **3D asset:** a logo or object the speaker names, spinning in empty space beside the face, roto
  behind if it overlaps.
- **Full-screen scene:** only when showing clearly beats saying, at most two, fade+blur in and out.
- **Captions:** fixed lower third, same position and style everywhere (talking head, side, screen).
  Emphasis = accent typeface AND 1.22x size on whole phrases, never split across two cards.
  Head-tracked captions are off unless asked.
- **SFX:** one per visible event (transition, hero landing, hard punch, card, click), subtle.

## Hard rules

- **Nothing on the face.** No caption, card, chip, logo or 3D object over the face box at any frame
  of its window. Move it, shrink it, or put it behind with roto. Measure from track.json.
- **No boxed text chips over the speaker.** No one-sided accent lines on any card (top, left, any
  edge): use a fill tint or a full even border.
- **Whole-frame fades only.** Never fade containers while a title stays.
- **Transitions:** fade+blur (default), plain fade, or a liquid stinger. Never a zigzag/teeth shutter.
- **No text sliced by a zoom or the frame edge.** Zoomed UI fades out above the caption band
  (`World` edge fade). Captions never zoom.
- **A reframe ships in the same render as what it makes room for.** No camera move toward an empty wall.
- **Verify every number on screen** against what is said or a saved, sourced fetch. Never invent one.
- **Objects and icons are real logos or generated/sourced images.** Code draws motion, text, UI,
  charts. Arrowheads are an asset, not SVG.
- No em dashes on screen. No "comment below" / "DM me" calls to action unless the human asks.
- Every layer stacked over the video is its own `AbsoluteFill` (a static video paints below any
  absolutely positioned sibling, which silently puts graphics in front of the matte).
- Use `translate + scale`, never a shifted `transform-origin`, for reframes.

Effect parameters and measured numbers: `references/effects.md`.
