# Setup

Everything heavy (Whisper, CrisperWhisper, WhisperX, SyncNet, MediaPipe, the matting model, fonts,
Chrome) is **downloaded on first use or by a setup script**. Nothing third-party is shipped in this
repo. Expect a few GB of model caches after the first full run.

## 1. System tools

| Tool | Why | macOS | Linux (Debian/Ubuntu) |
|---|---|---|---|
| ffmpeg + ffprobe (with libx264) | every audio/video step | `brew install ffmpeg` | `sudo apt install ffmpeg` |
| Python 3.10+ | scripts | ships with Xcode CLT, or `brew install python` | `sudo apt install python3` |
| [uv](https://docs.astral.sh/uv/) | runs each model in its own throwaway env | `brew install uv` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Node 20+ | Remotion, the 3D renderer | `brew install node` | [nodesource](https://github.com/nodesource/distributions) or nvm |
| pnpm (optional) | one shared store: the 2nd Remotion project costs ~0 MB | `npm i -g pnpm` | same |
| git, curl | setup scripts | preinstalled | `sudo apt install git curl` |
| ImageMagick (optional) | QA contact sheets | `brew install imagemagick` | `sudo apt install imagemagick` |
| coreutils (optional, macOS) | `timeout` for the SyncNet downloader | `brew install coreutils` | preinstalled |

Then from the repo root:

```bash
./install.sh            # links the skills, records THP_HOME, checks tools, prints Codex wiring
./install.sh --dry-run  # see what it would do first
```

If you already have skills called `autocut` or `dynamic-edit`, the installer leaves them alone;
`--force` replaces them.

## 2. Models

### Whisper (transcription) - automatic

`scripts/autocut/whisper_backend.py` picks the backend per platform:

| Platform | Backend | Notes |
|---|---|---|
| macOS, Apple Silicon | `mlx-whisper`, `whisper-large-v3-turbo` (via `uvx`) | Metal, fastest |
| Linux / WSL / Intel Mac | `faster-whisper`, `large-v3-turbo` (via `uv run`) | CUDA if available, else CPU. CPU works, just several times slower than a GPU |

Force one with `WHISPER_BACKEND=mlx|faster`; pick another faster-whisper size with
`FASTER_WHISPER_MODEL=medium`. Models land in `~/.cache/huggingface` on first use.

### CrisperWhisper (verbatim pass) - automatic

The stumble/restart detector and the final cut check run CrisperWhisper 2.0 (`turbo`) through
`uv run --with crisperwhisper[transformers]`. Over 1 GB on first use. Runs on CPU or GPU. This is the
model that does NOT smooth repeats away, so it is the one that checks every cut.

**License: the CrisperWhisper weights are CC BY-NC 4.0 (non-commercial).** For commercial work,
license it from its authors or replace `scripts/align/backends/crisperwhisper_align.py` with another
verbatim-capable backend that returns the same `{"words": [{word, start, end}]}` shape.

### Forced aligner - automatic

`scripts/align/align_words.py` re-times Whisper's word edges:

| Language | Aligner | Status |
|---|---|---|
| en | WhisperX (wav2vec2) | benchmarked |
| pt | CrisperWhisper | benchmarked |
| it, es, fr, de, nl | WhisperX | works, not benchmarked: run `--check` and listen once |

Other languages: add a line to `BACKEND_FOR_LANG` in `align_words.py` (WhisperX ships align
models for many more).

### SyncNet (lip-sync offset) - one setup script

```bash
scripts/sync/setup_syncnet.sh
```

Builds a Python 3.10 venv and clones [joonson/syncnet_python](https://github.com/joonson/syncnet_python)
into `~/.local/share/talking-head-pipeline/syncnet/`, then downloads its two weight files (~145 MB)
from a Hugging Face mirror. Idempotent; re-run to resume. Runs on CPU (slow: 1.5-5 min per 20 s
window) or CUDA. Without it, autocut still works if you pass `--offset <seconds>` (measure once with
a clap: `scripts/sync/measure_sync.py`) or `--no-sync`.

### MediaPipe face detector - one command per project

```bash
<project>/scripts/download_models.sh   # blaze_face_short_range.tflite, Apache-2.0, from Google's bucket
```

Pin `mediapipe==0.10.21` in the project venv: MediaPipe 1.0 removed `mp.solutions` and 1.0.1 crashes
on some Macs with a Metal "Service is unavailable" fault. Python 3.11 (no wheels past 3.12).

### Matting model - automatic

`matte_frames.py` drives `backgroundremover` (u2net_human_seg), which downloads its weights on first
use (~170 MB). Throughput ~2.4x slower than realtime at 1080p: budget roto seconds.

### Fonts

Captions and hero words load Google Fonts (OFL) through `@remotion/google-fonts`: nothing to install.
The 3D renderer needs a font FILE for outlines:

```bash
tools/render3d/fetch_font.sh 'ofl/sora/Sora[wght].ttf' Sora.ttf
tools/render3d/fetch_font.sh 'ofl/anton/Anton-Regular.ttf'
```

Use only fonts you are licensed to use in a published video. SIL OFL fonts are.

### Chrome for the 3D renderer

`cd tools/render3d && npm install` downloads a matching Chrome through `puppeteer` (~170 MB).
`CHROME_PATH=/path/to/chrome` uses yours instead.

## 3. Sound effects (bring your own)

No SFX ship with the repo. Free sources (check each file's licence before publishing):

- [Mixkit](https://mixkit.co/free-sound-effects/) (Mixkit licence, free for commercial video)
- [Pixabay sound effects](https://pixabay.com/sound-effects/) (Pixabay content licence)
- [freesound.org](https://freesound.org) (filter by CC0)

Keep them as `.wav` in one folder (subfolders fine) and point `SFX_LIBRARY` at it. Useful set: 3-4
soft whooshes, 2-3 soft impacts, UI ticks and clicks, one ping.

## 4. macOS vs Linux, in one table

| Piece | macOS (Apple Silicon) | Linux |
|---|---|---|
| Whisper | mlx-whisper (Metal) | faster-whisper (CUDA or CPU) |
| CrisperWhisper, WhisperX, SyncNet | torch MPS/CPU | torch CUDA/CPU |
| Remotion render | Chrome headless, ANGLE | same; install Chrome deps (`npx remotion browser ensure`) |
| 3D renderer | `--use-angle=metal` (GPU) | defaults to SwiftShader (CPU, slow but works); set `RENDER3D_GL_ARGS="--use-angle=vulkan"` with a GPU |
| `open` a render | `open file.mp4` | `xdg-open file.mp4` |
| Hardware H.264 | not used (libx264 was faster for splices) | not used |

Windows: use WSL2 and follow the Linux column.

## 5. Smoke test

```bash
python3 scripts/autocut/whisper_backend.py         # prints the backend this machine will use
python3 scripts/autocut/autocut.py --help
cp -R template /tmp/thp-test && cd /tmp/thp-test/remotion && pnpm install && npx tsc --noEmit
```
