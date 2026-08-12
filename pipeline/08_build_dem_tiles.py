#!/usr/bin/env python3
"""Synthesise an elevation model for the Known World and cut it into DEM tiles.

There is no canonical heightmap for Westeros, so we derive one: each terrain
class gets a base elevation, the result is blurred so mountains rise into their
foothills instead of standing on 8-mile cliffs, and coastlines are pushed just
below sea level. That is enough for MapLibre to light the world with real
hillshade and to extrude it in 3D.

Output is Mapbox terrain-RGB (height = -10000 + rgb * 0.1) in XYZ tiles, written
straight to the web app's public directory. PNGs are encoded by hand — no image
library needed for what is a fixed 8-bit RGB format.

Output: web/public/tiles/dem/{z}/{x}/{y}.png
"""
from __future__ import annotations

import json
import math
import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import PROCESSED, ROOT  # noqa: E402
from heightmap import BLUR_PASSES, FEET_TO_METRES, build_heightmap  # noqa: E402

OUT = ROOT / "web" / "public" / "tiles" / "dem"
TILE = 256
MIN_Z, MAX_Z = 2, 5  # z5 is ~2.9 miles/pixel, already finer than the 8-mile source grid

# A continent 3,000 miles across makes even the Mountains of the Moon look like
# a wrinkle at true scale, so the app exaggerates relief on display. The tiles
# themselves stay honest — this is only the suggested default.
SUGGESTED_EXAGGERATION = 12


def load_grid():
    meta = json.loads((PROCESSED / "terrain.json").read_text())
    data = (PROCESSED / "terrain.bin").read_bytes()
    return meta, data


def png_rgb(width: int, height: int, rows: list[bytearray]) -> bytes:
    raw = b"".join(b"\x00" + bytes(r) for r in rows)

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)  # 8-bit truecolour
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def tile_bounds(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    n = 2 ** z
    lon1 = x / n * 360.0 - 180.0
    lon2 = (x + 1) / n * 360.0 - 180.0
    lat1 = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    lat2 = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n))))
    return lon1, lat2, lon2, lat1  # west, south, east, north


def lat_to_ytile(lat: float, z: int) -> float:
    lat = max(-85.05112878, min(85.05112878, lat))
    r = math.radians(lat)
    return (1 - math.log(math.tan(r) + 1 / math.cos(r)) / math.pi) / 2 * (2 ** z)


def main() -> None:
    meta, data = load_grid()
    w, h = meta["width"], meta["height"]
    cell, min_lon, min_lat = meta["cellDeg"], meta["minLon"], meta["minLat"]
    max_lon, max_lat = min_lon + w * cell, min_lat + h * cell

    print(f"  building heightmap from {w}x{h} terrain grid "
          f"({BLUR_PASSES} blur passes)...")
    height = build_heightmap(w, h, data)
    lo, hi = min(height), max(height)
    print(f"  elevation range {lo:.0f} to {hi:.0f} ft")

    written = 0
    for z in range(MIN_Z, MAX_Z + 1):
        n = 2 ** z
        x0 = max(0, int((min_lon + 180) / 360 * n))
        x1 = min(n - 1, int((max_lon + 180) / 360 * n))
        y0 = max(0, int(lat_to_ytile(max_lat, z)))
        y1 = min(n - 1, int(lat_to_ytile(min_lat, z)))
        count = 0
        for tx in range(x0, x1 + 1):
            for ty in range(y0, y1 + 1):
                west, south, east, north = tile_bounds(z, tx, ty)
                # precompute the source column for each pixel column
                cols = []
                for px in range(TILE):
                    lon = west + (east - west) * (px + 0.5) / TILE
                    gx = int((lon - min_lon) / cell)
                    cols.append(min(w - 1, max(0, gx)))

                rows: list[bytearray] = []
                nn = 2 ** z
                for py in range(TILE):
                    # invert web mercator for this pixel row
                    yt = (ty + (py + 0.5) / TILE) / nn
                    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * yt))))
                    gy = int((lat - min_lat) / cell)
                    gy = min(h - 1, max(0, gy))
                    base = gy * w
                    row = bytearray(TILE * 3)
                    for px in range(TILE):
                        # ELEVATION is authored in feet; terrain-RGB is metres
                        v = height[base + cols[px]] * FEET_TO_METRES
                        # terrain-RGB: height = -10000 + (R<<16 | G<<8 | B) * 0.1
                        enc = int((v + 10000.0) * 10.0)
                        row[px * 3] = (enc >> 16) & 0xFF
                        row[px * 3 + 1] = (enc >> 8) & 0xFF
                        row[px * 3 + 2] = enc & 0xFF
                    rows.append(row)

                path = OUT / str(z) / str(tx) / f"{ty}.png"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(png_rgb(TILE, TILE, rows))
                count += 1
        written += count
        print(f"  z{z}: {count} tiles  (x {x0}-{x1}, y {y0}-{y1})")

    size = sum(p.stat().st_size for p in OUT.rglob("*.png"))
    print(f"\n  {written} tiles, {size / 1024 / 1024:.1f} MB -> "
          f"{OUT.relative_to(ROOT)}")
    (OUT / "meta.json").write_text(json.dumps({
        "encoding": "mapbox",
        "minzoom": MIN_Z,
        "maxzoom": MAX_Z,
        "tileSize": TILE,
        "bounds": [min_lon, min_lat, max_lon, max_lat],
        "elevationFeet": {"min": round(lo), "max": round(hi)},
        "elevationMetres": {"min": round(lo * FEET_TO_METRES),
                            "max": round(hi * FEET_TO_METRES)},
        "suggestedExaggeration": SUGGESTED_EXAGGERATION,
        "note": "Synthesised from terrain classes; not canonical topography.",
    }, indent=2))


if __name__ == "__main__":
    main()
