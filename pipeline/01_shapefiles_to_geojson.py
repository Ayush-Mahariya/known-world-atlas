#!/usr/bin/env python3
"""Convert the cadaei ASOIAF shapefiles into clean GeoJSON layers.

Input : data/raw/game_of_thrones_shapes/*.shp   (CC BY-NC-SA 3.0, see NOTICE.md)
Output: data/processed/layers/*.geojson

Pure format conversion and attribute cleanup — scale calibration is the next
stage (02_calibrate_scale.py).
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import shapefile  # pyshp

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    PROCESSED,
    SHAPES,
    feature_collection,
    slugify,
    write_json,
)

warnings.filterwarnings("ignore", category=shapefile.PossiblyCorruptFileHeader)

# layer -> (output name, which raw fields to keep as ints)
LAYERS = {
    "Continents": ("continents", {"id"}),
    "Islands": ("islands", {"id"}),
    "Lakes": ("lakes", {"id"}),
    "Land": ("land", {"id"}),
    "Landscape": ("landscape", {"id", "size"}),
    "Locations": ("locations", {"size", "confirmed"}),
    "Political": ("political", {"id"}),
    "Regions": ("regions", {"id", "size"}),
    "Rivers": ("rivers", {"id", "size"}),
    "Roads": ("roads", {"id", "size"}),
    "Wall": ("wall", {"id"}),
}

# The Roads layer leaves most segments unnamed. These are the named highways of
# Westeros; unnamed segments keep a generic label so the UI never shows blanks.
ROAD_FALLBACK = "Unnamed road"


def coerce(value, key: str, int_fields: set[str]):
    if isinstance(value, bytes):
        value = value.decode("utf-8", "replace")
    if isinstance(value, str):
        value = value.strip()
    if key in int_fields and value not in ("", None):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None
    return value if value != "" else None


def convert(src: Path, out_name: str, int_fields: set[str]) -> dict:
    reader = shapefile.Reader(str(src))
    fields = [f[0] for f in reader.fields[1:]]
    features = []
    for idx, sr in enumerate(reader.iterShapeRecords()):
        # a handful of records in Locations/Islands carry NULL geometry
        if sr.shape.shapeType == shapefile.NULL:
            continue
        geom = sr.shape.__geo_interface__
        if geom.get("type") is None or not geom.get("coordinates"):
            continue
        props = {
            k: coerce(v, k, int_fields)
            for k, v in zip(fields, list(sr.record))
            # gid/__gid are QGIS bookkeeping, not content
            if k not in ("gid", "__gid")
        }
        name = props.get("name")
        if out_name == "roads" and not name:
            name = ROAD_FALLBACK
            props["name"] = name
        props["layer"] = out_name
        props["fid"] = f"{out_name}-{idx}"
        if name:
            props["slug"] = slugify(name)
        features.append({"type": "Feature", "id": props["fid"], "properties": props,
                         "geometry": geom})
    fc = feature_collection(features)
    write_json(PROCESSED / "layers" / f"{out_name}.geojson", fc)
    return fc


def main() -> None:
    if not SHAPES.exists():
        sys.exit(f"missing source shapefiles at {SHAPES} — run scripts/fetch_sources.sh")

    total = 0
    for shp_name, (out_name, int_fields) in LAYERS.items():
        src = SHAPES / f"{shp_name}.shp"
        if not src.exists():
            print(f"  ! skipping {shp_name} (not found)")
            continue
        fc = convert(src, out_name, int_fields)
        total += len(fc["features"])
        print(f"  {out_name:12} {len(fc['features']):4} features")
    print(f"\n  {total} features -> data/processed/layers/")


if __name__ == "__main__":
    main()
