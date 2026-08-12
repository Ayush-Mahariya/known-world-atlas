#!/usr/bin/env bash
# Rebuild every derived artefact from the raw sources, in order.
#
# Stages are independent scripts so you can re-run one without the rest; this
# just runs the lot. The lore stage is cached on disk, so a second run is fast
# and makes no network requests.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PY="${PY:-$ROOT/.venv/bin/python}"
if [[ ! -x "$PY" ]]; then
  echo "no venv at $PY — create one with:" >&2
  echo "  python3 -m venv .venv && .venv/bin/pip install -r pipeline/requirements.txt" >&2
  exit 1
fi

stage() { printf '\n\033[1m== %s\033[0m\n' "$1"; }

stage "01 shapefiles -> geojson";      "$PY" pipeline/01_shapefiles_to_geojson.py
stage "02 calibrate world scale";      "$PY" pipeline/02_calibrate_scale.py
stage "03 build gazetteer";            "$PY" pipeline/03_build_gazetteer.py
stage "04 fetch lore (wikis)";         "$PY" pipeline/04_fetch_lore.py
stage "05 enrich from AWOIAF dump";    "$PY" pipeline/05_enrich_from_awoiaf.py
stage "06 rasterise terrain grid";     "$PY" pipeline/06_build_terrain_grid.py
stage "07 validate routing";           "$PY" pipeline/07_validate_routing.py
stage "08 build DEM tiles";            "$PY" pipeline/08_build_dem_tiles.py
stage "09 render satellite tiles";     "$PY" pipeline/09_build_satellite_tiles.py
stage "sync to web";                   bash scripts/sync-web-data.sh

printf '\n\033[1mpipeline complete\033[0m\n'
