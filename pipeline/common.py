"""Shared helpers and world constants for the Known World Atlas pipeline."""
from __future__ import annotations

import json
import math
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
LORE = ROOT / "data" / "lore"
SHAPES = RAW / "game_of_thrones_shapes"

# --- world scale -----------------------------------------------------------
# The source GIS files were drawn as a flat rectangular map and then given WGS84
# degrees, so the coordinates are plate carree: one degree of longitude covers
# the same map distance as one degree of latitude. Measuring them with a real
# spherical formula therefore squashes all east-west distances by cos(lat) --
# which is exactly the anisotropy 02_calibrate_scale.py found (E-W anchors
# implied x1.20, N-S anchors x0.94). We use planar degrees instead, scaled by a
# single MILES_PER_DEGREE fitted against canonical distances.
DEFAULT_MILES_PER_DEGREE = 65.183

EARTH_RADIUS_MILES = 3958.7613  # only used to explain the legacy measurement
WALL_CANON_MILES = 300.0

# Written by 02_calibrate_scale.py, read by everything downstream.
WORLD_FILE = PROCESSED / "world.json"


def slugify(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s or "unnamed"


def degrees_between(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Planar distance between two [lon, lat] points, in map degrees."""
    return math.hypot(b[0] - a[0], b[1] - a[1])


def miles_between(
    a: tuple[float, float], b: tuple[float, float], mpd: float = DEFAULT_MILES_PER_DEGREE
) -> float:
    """Canonical Westerosi miles between two [lon, lat] points."""
    return degrees_between(a, b) * mpd


def line_length_miles(coords: list[list[float]], mpd: float = DEFAULT_MILES_PER_DEGREE) -> float:
    return sum(
        miles_between(coords[i], coords[i + 1], mpd) for i in range(len(coords) - 1)
    )


def load_world() -> dict:
    if not WORLD_FILE.exists():
        return {"milesPerDegree": DEFAULT_MILES_PER_DEGREE}
    return json.loads(WORLD_FILE.read_text())


def miles_per_degree() -> float:
    return load_world().get("milesPerDegree", DEFAULT_MILES_PER_DEGREE)


def write_json(path: Path, obj, *, compact: bool = True) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if compact:
        path.write_text(json.dumps(obj, separators=(",", ":"), ensure_ascii=False))
    else:
        path.write_text(json.dumps(obj, indent=2, ensure_ascii=False))
    return path


def feature_collection(features: list[dict]) -> dict:
    return {"type": "FeatureCollection", "features": features}


# --- point-in-polygon (ray casting), good enough for this flat-ish data -----

def _ring_contains(ring: list[list[float]], pt: tuple[float, float]) -> bool:
    x, y = pt
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[(i + 1) % n][0], ring[(i + 1) % n][1]
        if (y1 > y) != (y2 > y):
            xin = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < xin:
                inside = not inside
    return inside


def polygon_contains(geometry: dict, pt: tuple[float, float]) -> bool:
    """True if `pt` ([lon, lat]) falls inside a GeoJSON Polygon/MultiPolygon."""
    polys = (
        geometry["coordinates"]
        if geometry["type"] == "MultiPolygon"
        else [geometry["coordinates"]]
    )
    for poly in polys:
        if not poly:
            continue
        if _ring_contains(poly[0], pt) and not any(
            _ring_contains(hole, pt) for hole in poly[1:]
        ):
            return True
    return False


def bbox_of(geometry: dict) -> tuple[float, float, float, float]:
    xs: list[float] = []
    ys: list[float] = []

    def walk(c):
        if c and isinstance(c[0], (int, float)):
            xs.append(c[0])
            ys.append(c[1])
        else:
            for sub in c:
                walk(sub)

    walk(geometry["coordinates"])
    return min(xs), min(ys), max(xs), max(ys)
