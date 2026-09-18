#!/usr/bin/env bash
# Nightly backup of everything Imagery holds: database, uploads, session secret.
#
#   tools/backup.sh [destination]
#
# Default destination follows the standing rule of keeping bulk data off the
# root disk. Add to cron:
#   15 3 * * *  /home/fpop/git/RevEngImagery/tools/backup.sh >> /var/log/imagery-backup.log 2>&1
set -euo pipefail

VOLUME="${IMAGERY_VOLUME:-imagery_data}"
DEST="${1:-/media/fpop/b0a10632-e09f-4153-ac08-337cc316f4f1/backups/imagery}"
KEEP_DAYS="${KEEP_DAYS:-30}"

mkdir -p "$DEST"
STAMP="$(date +%Y-%m-%d-%H%M)"
OUT="$DEST/imagery-$STAMP.tar.gz"

# Read the volume through a throwaway container: the data never has to be
# readable from the host, and this works the same wherever it is deployed.
docker run --rm \
  -v "$VOLUME":/data:ro \
  -v "$DEST":/backup \
  alpine:3 \
  tar czf "/backup/$(basename "$OUT")" -C /data .

if [ ! -s "$OUT" ]; then
  echo "backup produced nothing -- is the volume named '$VOLUME'?" >&2
  exit 1
fi

# Verify the archive rather than trusting that tar exited zero.
docker run --rm -v "$DEST":/backup:ro alpine:3 tar tzf "/backup/$(basename "$OUT")" >/dev/null

echo "$(date -Is)  ok  $OUT  ($(du -h "$OUT" | cut -f1))"

find "$DEST" -name 'imagery-*.tar.gz' -mtime "+$KEEP_DAYS" -print -delete
