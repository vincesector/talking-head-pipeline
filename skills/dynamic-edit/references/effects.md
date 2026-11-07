# Effect parameters

Every number here was measured on real edits or derived, not taken from a blog.

All frame counts assume **30fps**. Double them at 60.

---

## The easing principle behind all of it

**HARD RULE: every curve eases at BOTH ends, and nothing attacks in under ~12 frames.**

The old attack was Material's decelerate curve, `bezier(0, 0, 0.2, 1)`, over 4 to
8 frames. It begins at maximum velocity. Measured on a 15 frame move it spends
41% of the travel inside the first 15% of the duration, which reads as "too fast,
but not smooth enough, and too linear". Nothing physical
starts at full speed, so a move that does reads as a glitch rather than a camera.

Quadratic ease-in-out replaces it. Its velocity profile is a triangle: constant
acceleration, then constant deceleration, which is literally what a hand on a
zoom ring produces.

**Circular ease looks like the smoothest option and is the worst of the three.**
Its derivative spikes at the midpoint. On a 15 frame move one single frame
carries 36% of the travel and it snaps in the middle. Measured shares of the
busiest frame, 15 frame move:

| Curve | Busiest frame |
|---|---|
| Circular in-out | 36%, snaps |
| Cubic in-out | 19% |
| **Quadratic in-out** | **13%, chosen** |

| Role | Curve |
|---|---|
| Attack (push in) | `Easing.inOut(Easing.quad)` |
| Release (pull out) | `Easing.inOut(Easing.sin)`, gentler still, a pull-out that gets noticed has failed |
| Reframe attack | `Easing.bezier(0.32, 0, 0.16, 1)` |
| Reframe release | `Easing.bezier(0.4, 0, 0.25, 1)` |

**Scale, and the horizontal correction.** The ladder is 1.07 micro, 1.16
standard, 1.28 hard. It was 1.04 / 1.12 / 1.22 and read as too timid in a
horizontal frame, where a wide shot leaves far more room around the subject than
a vertical one does. Verify before raising further: scaling about the tracked
face, work out at what scale the top of the head leaves frame. On one edit that was
`cy / (cy - top)`, which came to 2.05, so 1.28 had plenty of margin.

**A per-entry `scale` in plan.json overrides the preset, so it silently
undoes this.** One edit shipped with all eleven `hard` punches overridden to 1.12,
half strength, and the preset table looked correct the whole time. Let the preset
govern unless there is a stated reason not to.

---

## Emphasis spans, not emphasis words

A push anchored to one word is a twitch: it arrives and leaves before the idea
does. A push held across a whole paragraph stops reading as emphasis and just
becomes the new framing. The useful unit is a clause or a sentence.

`scripts/emphasis_spans.py` produces the candidates: it splits the transcript on
clause punctuation, merges anything under **1.6s** into its neighbour, and splits
anything over **7.0s** at its best interior comma or, failing that, at the longest
internal pause. It also names the heaviest word in each span so a lean-in has an
anchor.

The planner still chooses which spans earn a push. Not every span gets one.

**Shape: one sustained push per passage, with a nested accent.**

The rule: if a stretch has several important parts, do one
long gentle push and hold it, then push a little further on the single part that
deserves most. Three separate punches inside one sentence is the failure mode.

- `sustain` (1.10, 14f in, 18f out) carries the passage
- `accent` (1.08, 6f in, 9f out) leans in inside it
- **Punch scales compose** (deltas multiply), so a sustain plus an accent is one
  continuous move that leans in, not two moves fighting. Measured composed peak
  on a real passage: flat 1.080 for 4.5s, then 1.145 on the key phrase.
- Minimum 3s between the END of one independent push and the START of the next.
- Reserve single `standard`/`hard` punches for genuinely isolated beats.

Measured before and after on the same 88s edit: 10 separate punches at ~1s holds
became 6 independent moves at a 5.4s mean hold.

## Punch-in

**The plan timestamp is the LANDING frame.** The animation runs from
`at - inFrames`. Start the move on the emphasis word and it arrives 7 frames
late, by which point the word is gone. This matters more than the curve.

| Preset | Scale | In | Out | Use |
|---|---|---|---|---|
| `micro` | 1.07 | 8f | 12f | Keeps a long take alive. Not emphasis |
| `standard` | 1.16 | 8f | 12f | Workhorse. Lands as the key sentence builds |
| `hard` | 1.28 | 6f | 10f | A number, a name, a punchline |
| `cut` | 1.18 | 0f | 0f | No animation, scale changes on a jump cut |
| `sustain` | 1.10 | 14f | 18f | A long gentle push held across a passage |
| `accent` | 1.08 | 6f | 9f | A small extra lean INSIDE a sustain (scales compose) |

Values live in `lib/punchIn.ts`; this table mirrors them.

Hold is per-punch and content-driven. ~2s is the usual landing spot.

Scale about the **tracked face**, not the frame centre. Every guide assumes a
centred subject; an off-centre head drifts toward the edge during a centre-origin
zoom.

---

## Offset reframe

Transform is `translate(dx, dy) scale(s)` about the frame centre.

A source point at `fx` lands at `0.5 + (fx - 0.5) * s + dx`, so:

```
dx = tx - 0.5 - (fx - 0.5) * s
```

The footage must still cover the frame, which bounds the slide:

```
|dx| <= (s - 1) / 2
```

**How far you can slide is set entirely by how far you zoomed.** Minimum scale
for a given reframe:

```
s >= tx / fx             moving right
s >= (1 - tx) / (1 - fx) moving left
```

### Timing

14 frames in (467ms), 18 out (600ms). Longer than a punch because the move
travels further. One eased progress value drives both scale and translate, or
the path curves and reads as drift.

### Rules

- Lock the target to the face position on the **landing frame**. Never recompute
  per frame.
- Graphics reveal at ~82% of the move, staggered 4f apart. Nothing appears while
  the camera travels.
- Clamp `dx`/`dy` to `(s-1)/2` minus a small margin (0.004) so subpixel rounding
  cannot reveal an edge.

### Measured on one setup

Face sat at x ≈ 0.450, left of centre. Free zoom
headroom cutting 1920x1080 from 2560x1440 is 1.33x.

| Target | Min scale | Verdict |
|---|---|---|
| x = 0.333 (left third) | 1.21x | free |
| x = 0.30 | 1.27x | free |
| x = 0.25 | 1.37x | slight upscale |
| x = 0.667 (right third) | 1.48x | 11% upscale |
| x = 0.75 | 1.67x | 25% upscale |

Canvas brightness on that set:

| | Mean luma | Bright pixels (>170) |
|---|---|---|
| Left third | 152.7 | 45.2% (lit orange wall, unusable bare) |
| Right third | 73.0 | 14.5% |

So **subject-left / canvas-right** is both cheaper and cleaner there. Re-measure
per shoot; it changes with where the subject sits and how the set is lit.

Quick canvas check:

```python
g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(float)
band = g[int(h*0.25):int(h*0.85), :int(w*0.30)]   # or [int(w*0.70):]
print(band.mean(), (band > 170).mean())
```

Above ~20% bright pixels, text needs an opaque plate to survive.

---

## Depth blur on sandwiched graphics

Many creators shoot wide open. The subject is sharp, the room behind is heavily out of focus.
A razor-sharp word sitting "between" those two planes is physically impossible,
and that is exactly what makes a sandwiched graphic read as pasted onto the
frame rather than present in the room. Give it some blur and it takes its place
in the depth.

**This is not a constant.** Between a 23mm f2.5 and an 85mm f1.4,
background separation changes by a large factor. Set it per
clip in `plan.defocus`, in pixels at the comp's resolution.

Starting points, at 1080p short edge. Scale linearly with resolution:

| Lens / aperture | Separation | Hero blur | Scatter range |
|---|---|---|---|
| 85mm f1.4 | extreme | 7-9 px | 4-14 px |
| 85mm f1.8 / 50mm f1.4 | strong | 5-7 px | 3-11 px |
| 50mm f1.8 | moderate | 4-5 px | 2-8 px |
| 23mm f2.5 | mild | 2-3 px | 1-5 px |

**Ask the human which lens if it is not obvious.** One word beats any
estimate from the footage.

`scripts/measure_defocus.py` exists as an assist, but treat its output as a hint
only. It discriminates setups correctly (measured 0.99 vs 1.42 subject/background
sharpness ratio on two different shoots) but its absolute numbers are not
trustworthy on dark footage: when the backgrounds are very dark and low-texture, which
is exactly where every sharpness metric degrades. Do not present its output as a
measurement.

**Scatter blur varies with size.** Within one scatter the smaller marks read as
further away and carry more blur. Uniform blur flattens them onto one plane,
which defeats the point.

**Legibility beats realism.** If matching the background would make the word
unreadable, back off. Depth is a cue, not a simulation.

## Aspect ratios: one pipeline, two layout profiles

The engine is aspect-agnostic. Punch curves, head tracking, matting, the
world-space transform and the occlusion sandwich behave identically at any frame
size. Only geometry differs, so `lib/layouts.ts` carries two profiles and
`resolveLayout(width, height)` picks by aspect. Do not fork.

**The trap that bites first:** `size` is a fraction of frame HEIGHT everywhere.
A circular badge at size `s` is therefore `s * (height/width)` wide. On 16:9 that
is `s * 0.5625`; on 9:16 it is `s * 1.778`. The same number reads three times
wider in vertical. Vertical sizes are smaller for that reason alone.

Measured differences between the two shoots:

| | Horizontal shoot | Vertical shoot |
|---|---|---|
| Face spans x | 0.40-0.60 | **0.353-0.687** |
| Usable empty space | left/right thirds | **533px above the head**, luma 15.7, 0% bright |
| Logo placement | side, x 0.19, column | **above head, row, y 0.11** |
| Caption y | 0.87 | 0.79 |
| Safe bottom | 0.04 | **0.15** (TikTok/Reels UI) |
| Safe right | 0.03 | **0.12** (action rail) |
| Offset reframe | allowed | **disallowed**, no lateral room worth the zoom |
| Scatter | 8 marks, 0.22-0.30 | 6 marks, 0.09-0.14 |

**Enforce the safe box, do not just document it.** `LogoScatter` clamps every
mark into `layout.safe` after converting size to a width fraction. A badge that
clears the frame edge can still sit under the platform's own UI.

**A word can fit and still look clipped.** In vertical at widthLimit 0.92 the
hero word measured x 0.053-0.959, inside the frame but reading as cut. 0.84 is
the working value. Verify by measuring the rendered span, not by eye.

## Sizing in-scene graphics

**Go big. If there is real estate, fill it.** Logos and badges should be
roughly twice the size instinct suggests. Small marks in a wide
empty third read as timid and waste the frame.

Working sizes as a fraction of FRAME HEIGHT, measured on a 16:9 set:

| Element | Size |
|---|---|
| Single side logo | 0.24-0.26 |
| Stacked side logos with labels (3 up) | 0.135-0.15 each |
| Scatter badges behind the subject | 0.22-0.30, varied |

A circular badge at size `s` is `s * 0.5625` wide on 16:9. That width, not the
height, is what clips. Check both extents against the punch:

```
half-width  = s * 0.5625 / 2        (times scale)
centre_x    = 0.5 + (x - 0.5) * scale + dx
```

A punch pushes everything outward, so a mark that clears the edge at rest can
leave frame under a 1.12x push. Verify at the punch, not at rest. Same for
vertical.

Two placement traps found in practice: a badge parked dead centre sits behind
the head for the whole beat and is never seen, and a badge grazing an edge looks
clipped rather than deliberate. Both are cheap to check numerically before
rendering.

## World space vs screen space

Logos, cards and any in-scene graphic belong **inside** the transformed layer
group, alongside the video. Then a punch-in scales and translates them exactly
as it does the subject, and they read as objects sitting in the room.

Anchored in screen space they stay pinned while the camera moves, which reads as
a sticker on the lens.

Order inside the transform: base video, sandwiched graphics, **logos**, matte.
Putting logos before the matte means they fall behind the subject whenever a
roto segment is live, and in front of the base video always.

Captions are the exception and stay in screen space. They are UI, not scenery.
Head-tracked captions still project through the transform so they stay glued to
the subject, which is a different thing from living in the scene.

Watch the frame edge: a logo at x=0.19 under a 1.22x punch lands at 0.12. That
is correct behaviour, an object closer to camera drifts out of frame, but check
it does not leave.

## Head-tracked captions

Anchor off `track.json`, which stores normalized 0-1 coordinates so it survives
any render resolution.

- Offset above the head: 0.05-0.07 of frame height.
- Tracker smoothing: 9-frame centred moving average (0.3s). Less and the caption
  vibrates; much more and it lags fast head moves.
- When a punch or reframe is active, pass the same `scale` and origin into the
  caption or it slides off mid-move.
- Tracker takes the largest face and has **no identity persistence**. A second
  person entering closer to camera steals the anchor.

Fonts and caption motion: `lib/fontPairings.ts`, `lib/motionCurves.ts`, `lib/CaptionEffects.tsx`.
`inter-instrument` (Inter + Instrument Serif italic, both Google Fonts) is the default pairing.

---

## Rotoscope segments

```bash
./.venv/bin/python scripts/matte_frames.py IN.mp4 --out public/cut --from-frame A --to-frame B \
  --track public/track.json --cuts public/cuts.json
```

Writes an RGBA PNG sequence. Consume in Remotion with `Img` indexed off
`useCurrentFrame()`.

- Engine: Robust Video Matting (ResNet50) on the Mac GPU (MPS). Measured on an M3 Max at
  1080x1920: 15-22 fps end to end (about realtime), ~2 GB peak, flat however long the window is,
  because each PNG is written as it goes. The model alone does ~40 fps; PNG writes are the rest.
  The old u2net engine did 0.3-1 fps and up to 15 GB.
- RVM is GPL-3.0. Its model code and weights are fetched into `~/.cache/rvm/` on the first run
  and are not part of this repo.
- RVM is recurrent. The script resets its state at every shot in `--cuts` (always pass
  it) and starts 15 frames before `--from-frame`, discarding them, so the matte is
  settled when the window opens. `--smooth` only applies to `--engine u2net`.
- No edge hardening by default, so curls stay strands. For a bright backdrop where a
  soft strand reads as halo add `--refine` (guided filter + sigmoid, `--pivot 0.55`
  chokes inward). Needs `opencv-contrib-python`.
- It prints `low_coverage=`: frames whose mask is under 25% of the window's best. They
  are not repaired; look at them before rendering (see qa.md gate 1).
- Matte quality: curls separated, hands solid even when motion-blurred, props and desk
  dropped. People only: a held phone or mic is not guaranteed to be kept.
- `--engine u2net` is the previous engine (CPU, letterboxed 640 predict, 3-frame average,
  guided filter, sigmoid). Kept for one release, then deleted.

### Layer order

```tsx
<AbsoluteFill>{/* base video */}</AbsoluteFill>
<AbsoluteFill>{/* sandwiched graphics */}</AbsoluteFill>
<AbsoluteFill>{/* matted subject PNG */}</AbsoluteFill>
```

All three must be `AbsoluteFill`, and all three take the same transform if a
punch or reframe is active.

---

## Big word behind the subject

- Height: 60-80% of frame height. Below 50% it reads as a caption, not a moment.
- One word, and it must be a word that is said, landing on the frame it is said.
- Enter under the matte so the reveal is the occlusion itself.
- Tracking tight (-2 to -4% letter-spacing) and a heavy weight. `druk-helvetica`
  or Inter 900 from `fontPairings.ts`.
- No glow or box-shadow. They ghost badly against a matte edge.
- Once per video.

---

## Full-screen 2.5D animation (the `depth` scene)

Generated cutout images placed as planes in real 3D (three.js via @remotion/three), a camera that
travels through `stops`, gentle per-layer yaw/pitch idle so cutouts do not read as stickers.

- Design a scene as DATA in plan.json: 2-4 images at three depths (far, mid, near), an opaque textured
  backdrop plane first (a flat colour reads as "assets pasted on black"), a motivated camera move.
- Timing: element enter 12-18f with `cubic-bezier(0.22, 1, 0.36, 1)`, exit 8-12f, sibling stagger 4f.
  No overshoot or bounce on anything informational.
- Text stays 2D in screen space, on top of the depth. World-layer text goes soft.
- Check projected bounds at the END of a push, where objects are largest: a growing object must not
  eat the 2D headline.

R3F setup gotchas already solved in the template: render with the ANGLE GL backend, load textures via
`THREE.TextureLoader` wrapped in `delayRender()`/`continueRender()` (useLoader + Suspense never
resolves headless), and drive the camera from `useCurrentFrame()` in a rig component, never R3F's
`useFrame()`.
