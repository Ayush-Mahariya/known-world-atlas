#!/usr/bin/env python3
"""Fit the world scale: how many canonical miles is one map degree?

The source geometry carries no usable scale of its own (its author warns "don't
use the map for distance measuring"). We recover one by least-squares fitting a
single MILES_PER_DEGREE against published canonical distances, then report the
per-anchor residual so the error is visible rather than assumed.

Input : data/processed/layers/*.geojson
Output: data/processed/world.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    PROCESSED,
    bbox_of,
    degrees_between,
    line_length_miles,
    write_json,
)

LAYERS = PROCESSED / "layers"

# Canonical / widely-accepted distances used as fitting anchors.
# `weight` downgrades anchors that are fan-derived rather than stated in text.
ANCHORS = [
    # (label, kind, spec, canonical miles, weight, source)
    ("The Wall, end to end", "feature", "wall", 300, 1.0,
     "AGOT — the Wall is 300 miles long"),
    ("Wall to the southern tip of Dorne", "meridian", None, 3000, 1.0,
     "GRRM — Westeros is roughly 3,000 miles north to south"),
    ("King's Landing to Winterfell", "places", ("King's Landing", "Winterfell"), 1500, 1.0,
     "kingsroad journey, ~1,400-1,600 miles by common reckoning"),
    ("Winterfell to Castle Black", "places", ("Winterfell", "Castle Black"), 600, 1.0,
     "AGOT — roughly 600 miles up the kingsroad"),
    ("King's Landing to Oldtown", "places", ("King's Landing", "Oldtown"), 1000, 1.0,
     "roseroad journey, ~1,000 miles"),
    ("King's Landing to Storm's End", "places", ("King's Landing", "Storm's End"), 400, 0.5,
     "kingsroad/stormlands, approximate"),
    ("Pentos to Dragonstone", "places", ("Pentos", "Dragonstone"), 600, 0.25,
     "fan-derived from sailing times; Essos placement is speculative"),
]


def load(name: str) -> list[dict]:
    return json.loads((LAYERS / f"{name}.geojson").read_text())["features"]


def main() -> None:
    locations = {
        f["properties"]["name"]: tuple(f["geometry"]["coordinates"][:2])
        for f in load("locations")
        if f["properties"].get("name")
    }
    wall = load("wall")[0]["geometry"]["coordinates"]
    wall_lat = sum(c[1] for c in wall) / len(wall)
    westeros = next(f for f in load("continents") if f["properties"]["name"] == "Westeros")
    _, south_lat, _, _ = bbox_of(westeros["geometry"])

    rows = []
    for label, kind, spec, canon, weight, source in ANCHORS:
        if kind == "feature":
            deg = line_length_miles(wall, mpd=1.0)  # mpd=1 -> raw degrees
        elif kind == "meridian":
            deg = wall_lat - south_lat
        else:
            a, b = spec
            if a not in locations or b not in locations:
                print(f"  ! skipping {label} (missing place)")
                continue
            deg = degrees_between(locations[a], locations[b])
        rows.append({"label": label, "degrees": deg, "canonMiles": canon,
                     "weight": weight, "source": source})

    # weighted least squares through the origin
    num = sum(r["weight"] * r["degrees"] * r["canonMiles"] for r in rows)
    den = sum(r["weight"] * r["degrees"] ** 2 for r in rows)
    mpd = num / den

    print(f"{'anchor':36}{'canon':>8}{'fitted':>8}{'error':>9}")
    worst = 0.0
    for r in rows:
        fitted = mpd * r["degrees"]
        err = (fitted - r["canonMiles"]) / r["canonMiles"] * 100
        r["fittedMiles"] = round(fitted, 1)
        r["errorPct"] = round(err, 1)
        r["degrees"] = round(r["degrees"], 4)
        worst = max(worst, abs(err))
        print(f"{r['label']:36}{r['canonMiles']:8.0f}{fitted:8.0f}{err:+8.1f}%")

    world = {
        "milesPerDegree": round(mpd, 4),
        "model": "planar",
        "modelNote": (
            "Source geometry is a flat map given WGS84 degrees (plate carree). "
            "Distance = hypot(dLon, dLat) * milesPerDegree. Do NOT use haversine: "
            "it squashes east-west distances by cos(lat)."
        ),
        "worstAnchorErrorPct": round(worst, 1),
        "anchors": rows,
        "geometrySource": "cadaei / theMountainGoat / Tear — CC BY-NC-SA 3.0",
    }
    write_json(PROCESSED / "world.json", world, compact=False)
    print(f"\n  MILES_PER_DEGREE = {mpd:.4f}  (worst anchor error {worst:.1f}%)")


if __name__ == "__main__":
    main()
