"""Robust Video Matting (RVM, ResNet50) on the Mac GPU. The shared person-matte engine.

Used by `template/scripts/matte_frames.py`. Measured on an M3 Max at 1080x1920: ~40 fps for the
model alone (15-22 fps end to end with PNG writes), ~2 GB peak. The previous u2net engine ran
at 0.3-1 fps and held up to 15 GB.

THIRD-PARTY, FETCHED AT RUNTIME, NOT INCLUDED IN THIS REPO. RVM
(https://github.com/PeterL1n/RobustVideoMatting) is GPL-3.0. This repo is MIT and does not
contain or redistribute any RVM code or weights. On first use this module downloads, into
~/.cache/rvm/ (override with $RVM_CACHE):
  - the official model code (8 small files from the upstream repo, pinned to one commit, each
    checked against a SHA-256), and
  - the ResNet50 weights from the upstream v1.0.0 release (checked by size and SHA-256).
After that, nothing touches the network. Check RVM's licence before shipping it inside a product.

RVM is recurrent: it carries a hidden state from frame to frame, and that state IS the
temporal smoothing. Rules for callers:
  - walk frames strictly in order;
  - `reset()` at every shot change, or the old silhouette ghosts into the new shot;
  - discard the first ~15 frames of a window (`WARMUP_FRAMES`), run only to settle the state.
"""
import hashlib
import importlib
import os
import sys
import urllib.request
from pathlib import Path

import numpy as np
import torch

RVM_COMMIT = "53d74c6826735f01f4406b5ca9075eee27bec094"
RAW_URL = f"https://raw.githubusercontent.com/PeterL1n/RobustVideoMatting/{RVM_COMMIT}/model/"
MODEL_FILES = {
    "__init__.py": "b0897f863332e0ef783017ab2c24211c633dc10b904a92dde1342c02c714c7ba",
    "decoder.py": "f3a8c237ddd6756bf231106d03a00e45ead3c265ae57fb2661aa6bf1f9167af5",
    "deep_guided_filter.py": "b0576d4513b6238f77bce018219bd0bbc10c628948c296024cae09f64437fece",
    "fast_guided_filter.py": "7d984c58f691eb18d1ac62c00b325714dbf7f464b59ba947e56027a876474fe4",
    "lraspp.py": "c35712af044cecca8c216d4fa28611c44df88e8f4a40aad89f2618a14cf5ee17",
    "mobilenetv3.py": "6932676d3e0cc100a48d2d2b90a37e45973fce16cefc764b26ac52cd46bc748c",
    "model.py": "d8378170659fd21d114096120f9a0ad2fed0550c4d4664927d68f2def3ccd960",
    "resnet.py": "639822fcd9469daeb9bff3b9ce24eed9c1fe6e9547d1177d7aea61783268e85b",
}

WEIGHTS_URL = "https://github.com/PeterL1n/RobustVideoMatting/releases/download/v1.0.0/rvm_resnet50.pth"
WEIGHTS_SIZE = 107905875
WEIGHTS_SHA256 = "c191a807251164c073dce5fa408e7a816070d539b882b2a3150330a9fec112ce"
CACHE_DIR = Path(os.environ.get("RVM_CACHE", Path.home() / ".cache" / "rvm"))
WEIGHTS_PATH = CACHE_DIR / "rvm_resnet50.pth"
# the package directory must be called rvm_model: the upstream files use relative imports
CODE_ROOT = CACHE_DIR / f"code-{RVM_COMMIT[:7]}"
CODE_DIR = CODE_ROOT / "rvm_model"

# Frames to run and throw away before a window so the recurrent state has settled.
WARMUP_FRAMES = 15


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_weights():
    if WEIGHTS_PATH.exists() and WEIGHTS_PATH.stat().st_size == WEIGHTS_SIZE:
        return WEIGHTS_PATH
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    part = WEIGHTS_PATH.with_suffix(".part")
    print(f"rvm: downloading rvm_resnet50.pth (108 MB) to {CACHE_DIR}", file=sys.stderr, flush=True)
    urllib.request.urlretrieve(WEIGHTS_URL, part)
    if part.stat().st_size != WEIGHTS_SIZE or _sha256(part) != WEIGHTS_SHA256:
        part.unlink()
        raise SystemExit("rvm: downloaded weights failed the size/SHA-256 check")
    part.rename(WEIGHTS_PATH)
    return WEIGHTS_PATH


def ensure_model_code():
    """Fetch the official RVM model code at the pinned commit; every file is SHA-256 checked."""
    if all((CODE_DIR / n).exists() and _sha256(CODE_DIR / n) == s for n, s in MODEL_FILES.items()):
        return CODE_ROOT
    print(f"rvm: downloading the official model code ({RVM_COMMIT[:7]}, GPL-3.0) to {CODE_DIR}",
          file=sys.stderr, flush=True)
    CODE_DIR.mkdir(parents=True, exist_ok=True)
    for name, sha in MODEL_FILES.items():
        dest = CODE_DIR / name
        if dest.exists() and _sha256(dest) == sha:
            continue
        part = dest.with_suffix(".part")
        urllib.request.urlretrieve(RAW_URL + name, part)
        if _sha256(part) != sha:
            part.unlink()
            raise SystemExit(f"rvm: {name} failed its SHA-256 check")
        part.rename(dest)
    return CODE_ROOT


def _load_network_class():
    root = str(ensure_model_code())
    if root not in sys.path:
        sys.path.insert(0, root)
    return importlib.import_module("rvm_model").MattingNetwork


def auto_downsample_ratio(h, w):
    """RVM README: 0.25 for HD/1080x1920, 0.125 for 4K. Official formula 512/max(h,w),
    snapped down to a multiple of 1/16 so 1080p lands on the measured 0.25."""
    r = min(512 / max(h, w), 1.0)
    return r if r >= 1.0 else max(1 / 16, int(r * 16) / 16)


class RVMMatter:
    """Streaming matter. `matte(rgb)` takes an HxWx3 uint8 RGB frame, returns an HxW float32
    alpha in 0..1 and advances the recurrent state."""

    def __init__(self, device=None, downsample_ratio=None):
        self.device = device or ("mps" if torch.backends.mps.is_available() else
                                 "cuda" if torch.cuda.is_available() else "cpu")
        self.downsample_ratio = downsample_ratio
        net = _load_network_class()("resnet50").eval()
        net.load_state_dict(torch.load(ensure_weights(), map_location="cpu"))
        self.net = net.to(self.device)  # fp32: fp16 gave no speedup on MPS
        self.rec = [None] * 4

    def reset(self):
        self.rec = [None] * 4

    @torch.no_grad()
    def matte(self, rgb):
        h, w = rgb.shape[:2]
        ds = self.downsample_ratio or auto_downsample_ratio(h, w)
        x = torch.from_numpy(rgb).to(self.device).permute(2, 0, 1)[None].float() / 255.0
        _, pha, *self.rec = self.net(x, *self.rec, downsample_ratio=ds)
        return pha[0, 0].clamp(0, 1).cpu().numpy().astype(np.float32)
