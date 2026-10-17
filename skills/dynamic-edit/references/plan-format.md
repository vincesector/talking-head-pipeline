# Edit plan format

`remotion/plan.json` is the approval gate AND the render input: `Root.tsx` imports it, so the plan the
human approves is exactly what renders. Write it with `scripts/build_plan.py` (word anchors), not by
hand; hand edits to plan.json are lost on the next rebuild.

All frames are absolute composition frames at `fps` (30 unless the source differs).

```jsonc
{
  "source": "raw.mp4",               // in remotion/public/
  "fps": 30, "width": 1920, "height": 1080, "durationInFrames": 5400,
  "sourceFrames": 5310,              // optional: source length when an end card runs past it
  "zoomHeadroom": 1.33,              // source width / timeline width
  "defocus": {"hero": 6, "scatter": [3, 11]},   // px blur for sandwiched graphics, per lens (effects.md)
  "cutDir": "cut",                   // matte PNG folder under public/
  "finish": {"grain": 0.08, "vignette": 0.25},
  "captions": {
    "pairing": "inter-instrument",   // lib/fontPairings.ts
    "trackedUntil": 0,               // head-tracked captions OFF
    "position": 0.87,                // optional normalized y; default from the layout profile
    "accent": "#ffb35c",             // emphasis colour
    "silence": [{"from": 900, "to": 1400}]   // screen-share ranges: no captions drawn
  },
  "events": [ /* below */ ]
}
```

## Events

Every event carries `reason`, citing the script: `"lands on 'forty percent', releases after 'every
month'; the number the argument hangs on"`. Bad: `"adds energy"`, `"opener"`, `"pizzazz"`. If an event
cannot be justified by the transcript, delete it rather than reword it.

| type | fields | notes |
|---|---|---|
| `punch` | `at` (LANDING frame), `hold`, `preset` micro/standard/hard/cut/sustain/accent, `scale?` | scale about the tracked face. A per-entry `scale` overrides the preset: leave it out unless there is a stated reason |
| `reframe` | `at`, `hold`, `subjectSide` left/right, `targetX?`, `scale?`, `cards?` [{label, value}] | 16:9 only. Cards reveal at 82% of the move |
| `side` | `from`, `to`, `subject` left/right, `scale?` (1.18), `cards` [{kind, at, props, punches?}] | 16:9 only. `kind` in layouts/cards.tsx (stat, list, compare, image). `punches` [{at, until, ox?, oy?, s?}] |
| `screen` | `from`, `to`, `page` (screen/pages.tsx: image, video, example), `props`, `url`, `tabTitle`, `tabIcon`, `backgroundSrc?`, `zoom` [{at, scale, x, y, dur?}], `cursor` [{at, to, click?}], `targets` {name: {x, y}} | 16:9 design space 1920x1080. A zoom key is ARRIVED AT on its frame; moves take `dur` (16) frames |
| `roto` | `from`, `to` | frames that get a matte; everything "behind" renders only inside these |
| `bigWord` | `at`, `hold`, `text`, `lines?`, `face?`, `size?` (fraction of height), `y?` | must sit inside a roto window |
| `scatter` | `at`, `hold`, `items` [{src, x, y, size, ...}] | behind the subject, inside roto |
| `logo` | `from`, `to`, `logos`, `side?`, `x?`, `y?` | world space beside the subject |
| `hero3d` | `at`, `until`, `seq` {dir, f0, f1}, `x`, `y`, `w`, `h`, `behind?` | PNG frames from tools/render3d; box centre and size in comp px |
| `asset3d` | `at`, `until`, `seq`, `x`, `y`, `size`, `behind?` | rendered 3D logo/object; fades in ending on `at` |
| `scene` | `from`, `to`, `comp` (depth, clip, stage), `props`, `transition` fadeblur/fade, `transitionFrames` | full screen, subject leaves |
| `endcard` | `from`, `src`, `frames`, `volume?` | after the last word: whole-frame dip to black, then the clip |
| `sfx` | `at` (file START frame), `src`, `volume` | written by add_sfx.py: fires at beat minus the file's peak |

## Validation before showing the plan

| Check | Rule |
|---|---|
| Anchors | every event's entry and exit come from words (build_plan.py refuses typed frames) |
| Punch spacing | landing at least ~3 s after the previous release; never two inside 2 s |
| One-word punch | a punch whose hold covers one word is a twitch: extend to the sentence or drop it |
| Roto budget | 15 s default, warn > 30 s, ask > 60 s |
| bigWord / behind | inside a roto window |
| Reframe cost | min scale <= zoomHeadroom, else state the upscale % |
| Orientation | no `reframe`, `side`, `screen` when width < height |
| Spans a cut | no punch, reframe or bigWord crosses a shot boundary; no landing within 4 frames of one |
| Full-frame windows | no punch, reframe, bigWord or roto inside a `scene` or `screen` window |
| Face first | nothing covers the face before ~2.5 s |
| Dead air | more than ~12 s with no event: re-read that stretch; if it is flat, leave it flat |

## What to show the human

A table, not the JSON:

```
  0:00.0-0:06.0   ROTO      hero word passes behind
  0:03.2          BIGWORD   "BROKEN"        lands on "broken", the turn
  0:04.0-0:06.5   PUNCH     sustain         lands on "the whole trick", releases after "tells you"
  0:40.1-0:52.0   SIDE      stat, list      three numbers to hold while explained
  1:00.2-1:15.0   SCREEN    dashboard       the walkthrough; zooms on "this number"

  Roto: 6.0 s of 4:12 (matting ~1.2 min) | punches 6 | longest gap 9.4 s | 3D renders: 1 hero
```

Then wait.
