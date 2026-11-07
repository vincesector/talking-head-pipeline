#!/usr/bin/env python3
"""Example plan builder. Copy to build_plan.py in the project, rewrite the beats from YOUR transcript.

    python3 scripts/build_plan.py

Every timing is a word anchor ("phrase@seconds" = that phrase's occurrence nearest those seconds),
resolved against remotion/public/words.json. Nothing here is a typed frame, so re-cutting the
source and rebuilding the plan keeps every effect on its word. Keep hand edits HERE, not in
plan.json: this script rewrites plan.json and the captions every run.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
from plan_common import load, write

P = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ws, n, size = load(P)

# (lands on, preset, releases after, why). Sentence-long, few, purposeful: the push arrives as the
# key sentence builds, holds through it, releases on its last word. Never on a single word.
beats = [
    ("the whole trick@4.0", "sustain", "nobody tells you@6.5", "the hook: the claim the video pays off"),
    ("forty percent@31.2", "standard", "every single month@33.9", "the number the argument hangs on"),
]

# Optional hero word behind the subject (needs a roto window; roto costs ~2 min of GPU time per footage minute plus a QA pass).
hero = None
# hero = {"land": "broken@12.4", "hold": 40, "lines": ["BROKEN"], "size": 0.5, "y": -0.2,
#         "reason": "the turn of the story", "roto": (-10, 50), "roto_reason": "hero word passes behind"}

rotos = []  # extra roto windows: [("from phrase@s", "to phrase@s", "why")]

events = [
    {"type": "side", "from": "here are the numbers@40.1", "to": "and that is why@52.0", "subject": "left",
     "reason": "three numbers to hold while they are explained",
     "cards": [
         {"kind": "stat", "at": "here are the numbers@40.1", "props": {"label": "Monthly cost", "value": "$1,200"},
          "punches": [{"at": "twelve hundred@41.5", "until": "a month@42.6"}]},
         {"kind": "list", "at": "three things@46.0", "props": {"title": "What changed", "items": ["One", "Two", "Three"]}},
     ]},
    {"type": "screen", "from": "let me show you@60.2", "to": "back to me@75.0", "page": "image",
     "props": {"src": "screens/dashboard.png"}, "url": "example.com/dashboard", "tabTitle": "Dashboard", "tabIcon": "D",
     "zoom": [{"at": "this number@64.0", "scale": 1.7, "x": 1300, "y": 420}, {"at": "and then@70.0", "scale": 1, "x": 960, "y": 540}],
     "reason": "the walkthrough: showing beats saying"},
]

write(P, ws, n, size, beats, hero=hero, rotos=rotos, events=events,
      emphasis=["the whole trick", "forty percent"], lens="50mm f1.8 (ask, or estimate with measure_defocus.py)")
