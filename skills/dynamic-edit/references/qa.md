# QA gates

Run all of these before anyone sees a render. A 1 fps contact sheet is not QA: a 15-frame matte
dropout is invisible at 1 fps and glaring in playback. Report each gate with its number, never just
"QA passed". If a gate failed and was not fixed, say so and why.

## 1. Matte integrity (if any roto)

```python
import numpy as np, glob
from PIL import Image
cov = np.array([(np.array(Image.open(f))[:, :, 3] > 128).mean() for f in sorted(glob.glob('remotion/public/cut/frame_*.png'))])
print(f"dead={(cov < 0.05).sum()}  min={cov.min()*100:.2f}%  worst_jump={np.abs(np.diff(cov)).max()*100:.2f}pts")
```

Pass: `dead` = 0, `min` > 25% of the mean, `worst_jump` < 8 points. `matte_frames.py` also prints
`repaired=` (frames patched from a neighbour): ones and twos are fine, investigate above ~5.

## 2. Occlusion (if anything is sandwiched)

Count the sandwiched graphic's pixels per frame (tune a colour mask to it). A matte dropout shows as a
spike: the whole shape suddenly visible. Pass: zero frames above 1.35x the median.

## 3. Edge safety (reframes, side layout)

Do not eyeball dark corners. Temporarily set the comp background to #ff00ff, render the range, count
`(r > 170) & (b > 170) & (g < 90)`. Pass: zero magenta pixels on every frame.

## 4. Face box

For every caption, card, chip, 3D object and logo window: its box versus the face box from
track.json at every frame of the window, with margin for movement. Pass: zero overlaps (unless the
object is behind, inside roto).

## 5. Stills at every landing (look at them)

Every hero/3D landing and landing + 25, every layout entry and exit, every screen zoom key. Read every
glyph: no digit hidden behind the head, no text sliced by the frame edge or a zoom, equal padding
from the frame edges for 3D type.

## 6. Motion sweeps at 5 fps

Around every cut, transition, and layout/scene entry and exit. Mid-animation frames, not just rest.
Text inside the safe area, readable over the brightest frame behind it, no twitch (fixed-width
containers, tabular numbers), captions in their band in every layout.

## 7. Static-text jitter (code-built UI)

Frame-diff each UI scene with the camera at rest: static text must be pixel-identical frame to frame.
Jitter means a missing `textRendering: 'geometricPrecision'` or a `transform: scale` on a whole page
(Chrome re-rasterizes; zoom positioned wrappers instead).

## 8. Flicker and blank frames

A-B-A flicker detector over the whole render (grayscale 320 px; frame i flagged if diff(i,i-1) > 0.6
and diff(i+1,i) > 0.6 and diff(i+1,i-1) < half of both). Zero flickers. Blank-frame scan at 10 fps.
File size sanity: a render far smaller than expected often means silently missing textures.

## 9. Cut integrity

No silent slivers or sub-0.8 s one-word pieces between jump cuts; frames/fps equals audio duration;
lip sync checked at the start AND the end.

## 10. Sound

Every SFX tied to a visible event; levels by RMS envelope (median ~10 dB under the voice, accents at
voice level at most). Audible when you listen for it, never competing.

## 11. Final sync and delivery

After `sync_trim.sh`: |final sync| under 5 ms at both measured windows. `ffprobe` the final:
yuv420p, bt709, constant frame rate. Loudness only if requested (-14 LUFS, true peak <= -1.5 dBTP).

## 12. Numbers and words

Every number on screen equals what is said or a saved, sourced value. No em dashes on screen.
Proper nouns spelled right in the captions.
