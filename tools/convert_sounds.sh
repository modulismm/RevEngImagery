#!/usr/bin/env bash
# Normalise the scraped sound bank for the browser.
#
# Commons audio is mostly Ogg Vorbis, which Safari cannot decode, and the files
# vary wildly in length and loudness. This transcodes everything to a short,
# quiet-ish mono MP3 that every browser plays.
#
# ffmpeg runs in a container, because Wintermute has none installed.
#
#   tools/convert_sounds.sh app/static/sounds/_raw app/static/sounds
set -euo pipefail

RAW="${1:-app/static/sounds/_raw}"
OUT="${2:-app/static/sounds}"
IMAGE="mwader/static-ffmpeg:7.1.1"
MAX_SECONDS=8

mkdir -p "$OUT"
RAW_ABS="$(cd "$RAW" && pwd)"
OUT_ABS="$(cd "$OUT" && pwd)"

shopt -s nullglob
for src in "$RAW_ABS"/*.{ogg,wav,mp3,flac,m4a}; do
  base="$(basename "${src%.*}")"
  echo "  $base"
  docker run --rm \
    -v "$RAW_ABS":/in:ro -v "$OUT_ABS":/out \
    "$IMAGE" \
    -hide_banner -loglevel error -y \
    -i "/in/$(basename "$src")" \
    -t "$MAX_SECONDS" \
    -ac 1 -ar 44100 \
    -af "loudnorm=I=-18:TP=-2:LRA=11,afade=t=out:st=$((MAX_SECONDS-1)):d=1" \
    -codec:a libmp3lame -b:a 96k \
    "/out/$base.mp3"
done

echo
ls -lh "$OUT_ABS"/*.mp3 | awk '{printf "  %-34s %s\n", $9, $5}'
