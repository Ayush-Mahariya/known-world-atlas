#!/usr/bin/env bash
# Build the deployable site from a fresh checkout.
#
# This is the command a CI builder runs. It deliberately does NOT run the whole
# pipeline: stages 01-07 need the source shapefiles and the wiki dump, and their
# output (data/processed/) is committed. All that is missing from a clean clone
# is the derived tiles and the copy of the data the app serves.
#
# Requirements: python3 (standard library only — the tile stages import nothing
# external) and node. No pip install, no network.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PY="${PY:-python3}"

if [[ ! -f data/processed/terrain.bin ]]; then
  echo "data/processed/terrain.bin is missing." >&2
  echo "It should be committed. To regenerate it you need the raw sources:" >&2
  echo "  scripts/fetch-sources.sh && scripts/run-pipeline.sh" >&2
  exit 1
fi

stage() { printf '\n\033[1m== %s\033[0m\n' "$1"; }

stage "DEM tiles";        "$PY" pipeline/08_build_dem_tiles.py
stage "satellite tiles";  "$PY" pipeline/09_build_satellite_tiles.py
stage "sync app data";    bash scripts/sync-web-data.sh

stage "web build"
cd web
if [[ -f package-lock.json ]]; then npm ci; else npm install; fi
npm run build

cd "$ROOT"
printf '\n\033[1mready to deploy: web/dist\033[0m\n'
du -sh web/dist | sed 's/^/  /'
find web/dist -type f | wc -l | sed 's/^/  /;s/$/ files/'
