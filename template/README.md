# Dynamic edit project

Scaffolded by the `/dynamic-edit` skill: `cp -R $THP_HOME/template <project>`. Everything is driven by
`remotion/plan.json`, so the approved plan and the render are the same artifact. The plan is written
by `scripts/build_plan.py` (copy `build_plan.example.py`) from word anchors, never typed frames.

```
remotion/plan.json             the edit (placeholder until you write yours)
remotion/public/raw.mp4        pre-cut source (from /autocut)
remotion/public/words.json     verbatim words in the cut timeline
remotion/public/track.json     head track (always generated, cheap)
remotion/public/captions.json  caption cues (build_cues.py, written by plan_common)
remotion/public/cut/           RGBA matte PNGs, only for roto windows
remotion/src/scenes/Edit.tsx   the compositor: video, sandwich, world space, layouts, captions
remotion/src/layouts/          side layout + card kinds
remotion/src/screen/           screen scene (browser + PiP + cursor) + pages
remotion/src/lib/              punches, reframes, captions, 3D sequences, Stage/World
scripts/                       tracking, matting, cues, plan writer, SFX, render + QA, patching
```

## Setup

```bash
uv venv --python 3.11 .venv          # mediapipe has no wheels past 3.12
uv pip install --python .venv/bin/python "mediapipe==0.10.21" opencv-python backgroundremover numpy pillow
scripts/download_models.sh           # MediaPipe face detector
cd remotion && pnpm install          # or npm install
```

## Run

```bash
.venv/bin/python scripts/track_head.py remotion/public/raw.mp4 --out remotion/public/track.json --cuts remotion/public/cuts.json
python3 scripts/build_plan.py        # writes plan.json + captions.json
cd remotion && npx remotion studio   # preview
npx remotion still src/index.ts Edit ../qa/f120.png --frame=120   # check stills first
cd .. && scripts/render_and_qa.sh "$PWD" v1                       # matte, render, QA sheets
```

QA gates: `skills/dynamic-edit/references/qa.md` in the pipeline repo. Then
`scripts/master/sync_trim.sh` from the repo for the final audio sync.
