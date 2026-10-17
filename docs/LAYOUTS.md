# Layouts

Three layouts, one compositor (`template/remotion/src/scenes/Edit.tsx`). Punches, reframes and the
side layout all resolve to ONE transform `{scale, dx, dy}` that the video, everything in world
space, the matte and the caption anchors share, so nothing drifts apart.

Geometry profiles per aspect live in `lib/layouts.ts` and are picked from the plan's width/height.
All numbers below are fractions of the frame unless they say px.

## A. Talking head

### 16:9 (1920x1080, ideally from a 2560x1440 recording: 1.33x free zoom)

```
+------------------------------------------------------------------+
|  safe 0.03                                                       |
|              world space:          +--------+                    |
|              logos, 3D assets,     |        |                    |
|              hero type beside      |  face  |   <- face box from  |
|              the head              |        |      track.json:    |
|                                    +--------+      nothing on it  |
|                                   /          \                   |
|                                                                  |
|        +------------------------------------------------+        |
|        |   caption, centred, y 0.87, width 0.78          |        |
|        +------------------------------------------------+        |
|  safe 0.04                                                       |
+------------------------------------------------------------------+
```

- Punch: scale about the tracked face (`micro` 1.07, `standard` 1.16, `hard` 1.28, `sustain` 1.10).
  Check where the head top leaves frame: `cy / (cy - top)` is the max scale.
- Offset reframe (subject to a third, cards on the other): `dx = tx - 0.5 - (fx - 0.5) * s`,
  minimum scale `tx/fx` moving right, `(1-tx)/(1-fx)` moving left. Compare against headroom.
- Hero word behind the speaker: above the head, `size` 0.45-0.62 of height, `y` about -0.2.

### 9:16 (1080x1920)

```
+---------------------------+
|  safe top 0.06            |
|   HERO WORD / 3D TYPE     |   <- the usable space is ABOVE the head
|   one word per line       |
|        +-------+          |
|        | face  |          |
|        +-------+          |
|       /         \         | right 0.12 = platform
|                           | action rail: nothing
|                           | important lives here
|  +---------------------+  |
|  | caption y 0.79      |  |
|  +---------------------+  |
|  bottom 0.15: platform UI |
+---------------------------+
```

- No offset reframes and no side layout: there is no lateral room worth the zoom.
- `size` is a fraction of frame HEIGHT everywhere, so a badge reads ~3x wider in vertical than the
  same number in 16:9. Vertical sizes are smaller for that reason alone.
- A word can fit and still look clipped: keep hero text within ~84% of the width.

## B. Side (16:9 only)

The presenter slides to one side (scale ~1.18, face centre at x 0.29 of width), a content-sized card
sits on the other (centre x 0.727, y 0.45). The uncovered room is the same footage, blurred and
darkened; the slid footage feathers into it on the card side. No letterbox, no browser frame.

```
+------------------------------------------------------------------+
|                         .                                        |
|      +--------+         .          +-------------------------+   |
|      |  face  |         .          |  LABEL                  |   |
|      |        |         .          |  42%                    |   |
|      +--------+   feathered        |  a line under it        |   |
|     /          \  edge, blurred    +-------------------------+   |
|                   room behind        card centre x 0.727W, y 0.45H|
|                                                                  |
|   +------------------------------+                               |
|   | caption under the presenter  |   never under or over the card|
|   | centre x 0.29W, width 900 px |                               |
|   +------------------------------+                               |
+------------------------------------------------------------------+
```

- Enter 8 frames before `from` over 16 frames, exit over 16 frames from `to`.
- Cards swap on their own words (`at`), slide 70 px in, 40 px out; a card can punch (~1.1x) on the
  number being said (`punches`), anchored where the number is (`ox`, `oy`).
- `subject: "right"` mirrors everything.
- Cards: `stat`, `list`, `compare`, `image` in `layouts/cards.tsx`. Full even border, fill tint for
  emphasis, never a one-sided accent bar. Sized to content.
- Most info beats in long form want this layout; keep the full screen scene for the walkthrough.

## C. Screen scene (16:9 only)

A browser window (design space 1920x1080, scaled to the comp) holding a page you build, the camera
shrinking into a rounded PiP bottom-right over 14 frames, an animated cursor and camera zooms.

```
+------------------------------------------------------------------+
|  +------------------------------------------------------------+  |
|  | o o o  [E Example x]  +                                    |  |
|  | < > C  [ example.com/dashboard                         ]   |  |
|  |                                                            |  |
|  |     page slot: screen/pages.tsx (image / video / your      |  |
|  |     React page). zoom keys arrive ON their words;          |  |
|  |     cursor glides 16 frames between named targets          |  |
|  |                                          +--------------+  |  |
|  |                                          |  camera PiP  |  |  |
|  +------------------------------------------|  384 x 372   |--+  |
|      +------------------------------+       |  radius 28   |     |
|      | caption centred, max 900 px  |       +--------------+     |
|      +------------------------------+  ends before x 1410: clear |
|   soft full-width scrim under the band, no box                   |
+------------------------------------------------------------------+
```

- One tab, a real-looking URL, a calm dark backdrop (`backgroundSrc` or the default gradient).
- The PiP may move at most once per scene. Keep the parts of the page you talk about clear of it.
- Zooms: real zooms (1.6-2.2x) centred on the element, pixel-equal margins. Never `transform:
  scale` on a whole recreated web page (Chrome reuses a cached layer and single frames render at the
  wrong layout); zoom a positioned wrapper, or rebuild the region at the zoomed size.
- Rebuild UI in code for anything you zoom into. One-to-one with the real product if it depicts
  one; only the data changes, and the data is real.
- Captions over the screen scene are fine (it is a built scene); over a raw screen recording of the
  speaker's screen share, use `captions.silence` instead.

## Caption safe zones (summary)

| Layout | Caption centre x | Box width | y |
|---|---|---|---|
| Talking head 16:9 | 0.5 | 0.78 W (1240 px at 1080p) | 0.87 |
| Side 16:9 | presenter's face x (0.29 W) | 900 px at 1080p | 0.87 |
| Screen 16:9 | 0.5 | 900 px at 1080p, clear of the PiP | 0.87 + scrim |
| Talking head 9:16 | 0.5 | 0.88 W | 0.79 (above platform UI) |
| Full-screen stage | 0.5 | layout default | band reserved: content fades above it |

Captions interpolate between these as a layout enters and exits, so the box glides with the
presenter instead of jumping.

## Full-screen stages (code-built scenes)

`lib/Stage.tsx`: `Stage` (design space scaled to the comp, moving backdrop, `geometricPrecision`
text so nothing jitters), `World` (a camera with keys `{at, s, x, y}` and the **edge fade**: zoomed
content fades out over 30 px above the caption band, so text is never sliced under the captions),
`punchKeys(at, out, s, x, y)` (arrive on a word, hold, release on the exit word), `chromeOpacity`
(fixed chrome hides while pushed in). `scenes/fullscreen/StageScene.tsx` is a working example.

## Layering order inside the transform

```
1  base video                         (AbsoluteFill)
2  sandwich: scatter, bigWord,        (AbsoluteFill, only inside roto windows)
   hero3d/asset3d with behind: true
3  world-space logos                  (in front of the video, behind the matte)
4  matte PNG of the speaker           (AbsoluteFill, only inside roto windows)
5  hero3d/asset3d in front
--- outside the transform (screen space) ---
6  side scrim + cards, reframe cards
7  full-screen scene / screen scene
8  end card, caption scrim, captions, finish (grain, vignette)
```

Every stacked layer must be its own `AbsoluteFill`: a statically positioned video paints below any
absolutely positioned sibling regardless of DOM order, which silently puts graphics in front of the
matte and looks exactly like an alpha failure.
