#!/usr/bin/env bash
# fetch_font.sh <path in github.com/google/fonts> [out name]
#   fetch_font.sh 'ofl/sora/Sora[wght].ttf' Sora.ttf
#   fetch_font.sh 'ofl/anton/Anton-Regular.ttf'
# Google Fonts are mostly SIL OFL: free to use in videos. Check the family's OFL.txt to be sure.
set -euo pipefail
cd "$(dirname "$0")"; mkdir -p fonts
P=$1; N=${2:-$(basename "$P" | tr -d '[]' )}
U="https://github.com/google/fonts/raw/main/$(printf '%s' "$P" | sed 's/\[/%5B/g; s/\]/%5D/g')"
curl -fL --retry 3 -o "fonts/$N" "$U"
echo "fonts/$N ($(du -k "fonts/$N" | cut -f1) KB)"
