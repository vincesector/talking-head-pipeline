#!/usr/bin/env python3
"""Font outlines -> SVG paths for the 3D renderer, shaped with HarfBuzz so kerning is the font's own.

    uv run --with uharfbuzz --with fonttools glyphs.py --font fonts/Sora.ttf --weight 800 \
        --out paths.json "SAVE" "50%"

Writes {text: {d, bbox}, "_cap": cap height}, font units scaled to em = 1000, y down.
Variable fonts are instanced at --weight (static fonts ignore it). Use an OFL font you are allowed
to ship in a video (Google Fonts is the easy source: fetch_font.sh).
"""
import argparse, io, json
import uharfbuzz as hb
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.boundsPen import BoundsPen

ap = argparse.ArgumentParser()
ap.add_argument("texts", nargs="+")
ap.add_argument("--font", required=True)
ap.add_argument("--weight", type=float, default=800)
ap.add_argument("--out", default="paths.json")
a = ap.parse_args()

f = TTFont(a.font)
if "fvar" in f:
    axes = {ax.axisTag for ax in f["fvar"].axes}
    f = instantiateVariableFont(f, {"wght": a.weight} if "wght" in axes else {})
f.flavor = None
buf = io.BytesIO(); f.save(buf)
font = hb.Font(hb.Face(buf.getvalue()))
upm = f["head"].unitsPerEm
gs = f.getGlyphSet()
s = 1000 / upm
out = {}
for text in a.texts:
    b = hb.Buffer(); b.add_str(text); b.guess_segment_properties()
    hb.shape(font, b, {"kern": True, "liga": False})
    pen, bp, x = SVGPathPen(gs), BoundsPen(gs), 0
    for info, pos in zip(b.glyph_infos, b.glyph_positions):
        name = f.getGlyphName(info.codepoint)
        t = (s, 0, 0, -s, x * s, 0)
        gs[name].draw(TransformPen(pen, t)); gs[name].draw(TransformPen(bp, t))
        x += pos.x_advance
    if bp.bounds is None:
        raise SystemExit(f"no outlines for {text!r} in {a.font}")
    out[text] = {"d": pen.getCommands(), "bbox": bp.bounds}
cap = getattr(f["OS/2"], "sCapHeight", 0) or 700 * upm / 1000
out["_cap"] = cap * 1000 / upm
json.dump(out, open(a.out, "w"))
for k, v in out.items():
    if k != "_cap":
        print(f"{k!r}: bbox {[round(n) for n in v['bbox']]}")
print("cap height", round(out["_cap"]), "->", a.out)
