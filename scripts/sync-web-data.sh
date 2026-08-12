#!/usr/bin/env bash
# Copy pipeline output into the web app's public directory.
#
# The pipeline writes to data/processed/; the app serves from web/public/data/.
# Keeping them separate means a broken pipeline run never leaves the app serving
# half-written files, and web/public/data stays disposable.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$ROOT/data/processed"
DEST="$ROOT/web/public/data"

if [[ ! -f "$SRC/gazetteer.json" ]]; then
  echo "no pipeline output at $SRC — run scripts/run-pipeline.sh first" >&2
  exit 1
fi

mkdir -p "$DEST/layers"
cp "$SRC"/gazetteer.json "$SRC"/lore.json "$SRC"/realms.json "$SRC"/world.json "$DEST/"
cp "$SRC"/route-fixtures.json "$SRC"/terrain.json "$SRC"/terrain.bin "$DEST/"
cp "$SRC"/layers/*.geojson "$DEST/layers/"
cp "$ROOT"/data/custom/travel-modes.json "$DEST/"

echo "synced to web/public/data:"
du -sh "$DEST" | sed 's/^/  /'
find "$DEST" -type f | wc -l | sed 's/^/  /;s/$/ files/'
