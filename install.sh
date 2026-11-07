#!/usr/bin/env bash
# install.sh [--dry-run] [--copy] [--force] [--uninstall]
#
# Links skills/autocut and skills/dynamic-edit into ~/.claude/skills (Claude Code), records the repo
# location in ~/.config/talking-head-pipeline/root (the skills and scripts read it as THP_HOME),
# checks the tools the pipeline calls, and prints how to wire the same skills into Codex.
#   --dry-run    print what would happen, change nothing
#   --copy       copy the skills instead of symlinking (symlinks keep them updated with git pull)
#   --force      replace an existing autocut / dynamic-edit skill that is not this repo's
#   --uninstall  remove the links and the config file
set -euo pipefail
REPO=$(cd "$(dirname "$0")" && pwd)
DRY=0; COPY=0; UN=0; FORCE=0
for a in "$@"; do case $a in --dry-run) DRY=1;; --copy) COPY=1;; --force) FORCE=1;; --uninstall) UN=1;; -h|--help) sed -n 2,10p "$0"; exit 0;; *) echo "unknown flag $a"; exit 1;; esac; done
run() { if [ $DRY = 1 ]; then echo "  would run: $*"; else "$@"; fi; }
SK="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"; CFG="$HOME/.config/talking-head-pipeline"

if [ $UN = 1 ]; then
  for s in autocut dynamic-edit; do
    if [ "$(readlink "$SK/$s" 2>/dev/null)" = "$REPO/skills/$s" ]; then run rm -f "$SK/$s"; else echo "  $SK/$s is not this repo's link; left alone"; fi
  done
  run rm -rf "$CFG"; echo "uninstalled"; exit 0
fi

echo "repo: $REPO"
run mkdir -p "$SK" "$CFG"
if [ $DRY = 1 ]; then echo "  would write $CFG/root = $REPO"; else printf '%s\n' "$REPO" > "$CFG/root"; fi
for s in autocut dynamic-edit; do
  if { [ -e "$SK/$s" ] || [ -L "$SK/$s" ]; } && [ "$(readlink "$SK/$s" 2>/dev/null)" != "$REPO/skills/$s" ] && [ $FORCE = 0 ]; then
    echo "  $SK/$s already exists (another skill with this name); left alone. --force replaces it"; continue
  fi
  run rm -rf "$SK/$s"
  if [ $COPY = 1 ]; then run cp -R "$REPO/skills/$s" "$SK/$s"; else run ln -s "$REPO/skills/$s" "$SK/$s"; fi
  echo "  skill $s -> $SK/$s"
done
run chmod +x "$REPO"/scripts/*/*.sh "$REPO"/scripts/master/*.py "$REPO"/template/scripts/*.sh "$REPO"/tools/render3d/*.sh

echo
echo "tools:"
miss=0
for t in ffmpeg ffprobe python3 uv node git; do
  if command -v $t >/dev/null; then printf '  %-8s ok\n' $t; else printf '  %-8s MISSING\n' $t; miss=1; fi
done
command -v pnpm >/dev/null && echo "  pnpm     ok" || echo "  pnpm     not found (optional: npm works, pnpm saves disk across projects)"
command -v magick >/dev/null && echo "  magick   ok" || echo "  magick   not found (optional: QA contact sheets)"
case "$(uname -s)-$(uname -m)" in
  Darwin-arm64) echo "  whisper  mlx-whisper (Apple Silicon), fetched on first use by uvx";;
  *)            echo "  whisper  faster-whisper (CPU, or CUDA when present), fetched on first use by uv";;
esac
[ -x "$HOME/.local/share/talking-head-pipeline/syncnet/venv/bin/python" ] && echo "  syncnet  ok" \
  || echo "  syncnet  not set up yet: run scripts/sync/setup_syncnet.sh once (~150 MB weights), or always pass --offset"
echo "  matte    RVM (GPL-3.0, not shipped): add torch torchvision opencv-contrib-python to each project venv;"
echo "           model code + weights are fetched into ~/.cache/rvm/ on the first matte run"
[ $miss = 1 ] && echo && echo "install the MISSING tools first (docs/SETUP.md)."

cat <<MSG

Claude Code: restart it; /autocut and /dynamic-edit are now available.

Codex: Codex reads AGENTS.md, not skills folders. Either
  1. add to ~/.codex/AGENTS.md (all projects) or to your project's AGENTS.md:

     ## Talking-head video pipeline
     For raw recordings follow $REPO/skills/autocut/SKILL.md.
     For dynamic edits of pre-cut footage follow $REPO/skills/dynamic-edit/SKILL.md.
     Read the SKILL.md fully before the first command. THP_HOME=$REPO

  2. or, if your Codex build supports skills, link them the same way:
     ln -s $REPO/skills/autocut ~/.codex/skills/autocut
     ln -s $REPO/skills/dynamic-edit ~/.codex/skills/dynamic-edit

Next: docs/SETUP.md (models, macOS vs Linux), then hand your agent a raw recording.
MSG
