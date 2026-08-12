#!/usr/bin/env python3
"""Render a satellite-style basemap for a world that has no satellites.

There is no orbital imagery of Westeros, so we synthesise it from the same two
things the 3D view uses: the terrain classification and the elevation field.
Each cell gets a biome colour, then we light it with the relief, cool it toward
the poles, whiten the peaks and the far north, and shade the seas by depth.

The shading uses the *same* heightmap as the DEM tiles (pipeline/heightmap.py),
so the imagery and the 3D relief agree — otherwise hills would be lit from one
direction and shadowed from another.

Colours are computed once per terrain cell, then bilinearly interpolated across
each tile. That is both much faster than per-pixel biome logic and better
looking: the blur between biomes reads like a real ecotone instead of a
cartographic hard edge.

Output: web/public/tiles/satellite/{z}/{x}/{y}.png
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
from heightmap import build_heightmap  # noqa: E402
from travel import (  # noqa: E402
    DESERT, FOREST, HILLS, LAKE, MOUNTAIN, OCEAN, PLAINS, ROAD, STEPPE, SWAMP,
)

OUT = ROOT / "web" / "public" / "tiles" / "satellite"
TILE = 256
MIN_Z, MAX_Z = 2, 5

# Base biome colours, chosen to read as orbital imagery rather than as a map.
BIOME = {
    PLAINS:   (104, 118, 68),
    STEPPE:   (144, 138, 84),
    FOREST:   (54, 78, 44),
    DESERT:   (196, 170, 112),
    SWAMP:    (72, 86, 58),
    HILLS:    (118, 116, 78),
    MOUNTAIN: (116, 106, 92),
    ROAD:     (140, 126, 92),
    LAKE:     (36, 74, 96),
}
SEA_SHALLOW = (44, 106, 132)
SEA_DEEP = (10, 34, 58)
SNOW = (238, 242, 246)

# Latitude band, in map degrees, over which flat ground turns to snow. The Wall
# sits at ~35; everything well beyond it should read as the frozen north.
SNOW_LAT_START, SNOW_LAT_FULL = 32.0, 46.0

# The snowline falls as you go north, exactly as it does on Earth: a 4,000ft
# peak in Dorne is bare rock, the same peak past the Wall is under ice. Without
# this the Essos mountains at mid-latitude come out as implausible ice sheets.
SNOWLINE_WARM_FT = 6500.0   # snowline in the far south
SNOWLINE_COLD_FT = 1500.0   # snowline in the far north
SNOWLINE_LAT_LO, SNOWLINE_LAT_HI = -5.0, 40.0
SNOW_ELEV_BAND = 1800.0     # feet from bare ground to full cover

# Relief lighting: from the north-west, as cartographic convention expects.
LIGHT = (-0.6, 0.8)
SHADE_STRENGTH = 0.00055  # tuned against the foot-scale of the height field
SHADE_RANGE = (0.62, 1.32)


def clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if v < lo else hi if v > hi else v


def mix(a, b, t: float):
    return (a[0] + (b[0] - a[0]) * t,
            a[1] + (b[1] - a[1]) * t,
            a[2] + (b[2] - a[2]) * t)


def cell_noise(x: int, y: int) -> float:
    """Deterministic value noise in [-1, 1], for mottling the biomes."""
    n = (x * 374761393 + y * 668265263) & 0xFFFFFFFF
    n = ((n ^ (n >> 13)) * 1274126177) & 0xFFFFFFFF
    return (((n ^ (n >> 16)) & 0xFFFF) / 32767.5) - 1.0


def build_colours(w: int, h: int, terrain: bytes, height: list[float],
                  min_lat: float, cell: float) -> tuple[bytearray, bytearray, bytearray]:
    """One RGB triple per terrain cell, fully lit and tinted."""
    r_ch, g_ch, b_ch = bytearray(w * h), bytearray(w * h), bytearray(w * h)

    for y in range(h):
        lat = min_lat + (y + 0.5) * cell
        # cool the palette toward the north; warm it toward Dorne
        cold = clamp((lat - 8.0) / 30.0)
        warm = clamp((6.0 - lat) / 22.0)
        snow_lat = clamp((lat - SNOW_LAT_START) / (SNOW_LAT_FULL - SNOW_LAT_START))
        # snowline for this latitude
        chill = clamp((lat - SNOWLINE_LAT_LO) / (SNOWLINE_LAT_HI - SNOWLINE_LAT_LO))
        snowline = SNOWLINE_WARM_FT + (SNOWLINE_COLD_FT - SNOWLINE_WARM_FT) * chill
        row = y * w

        for x in range(w):
            i = row + x
            code = terrain[i]
            elev = height[i]

            if code == OCEAN:
                # the blurred field is most negative far from land, which gives
                # a depth gradient for free
                depth = clamp(-elev / 600.0)
                colour = mix(SEA_SHALLOW, SEA_DEEP, depth ** 0.65)
                # ice over the northernmost water
                colour = mix(colour, (206, 220, 228), snow_lat * 0.55)
                shade = 1.0
            else:
                colour = BIOME.get(code, BIOME[PLAINS])

                snow_elev = clamp((elev - snowline) / SNOW_ELEV_BAND)
                snow = max(snow_lat * 0.9, snow_elev)
                if code == LAKE:
                    snow *= 0.4
                colour = mix(colour, SNOW, snow)

                # temperature tint, damped where snow already dominates
                tint = 1.0 - snow
                colour = mix(colour, (108, 128, 140), cold * 0.20 * tint)
                colour = mix(colour, (198, 168, 104), warm * 0.22 * tint)

                # relief shading from the local gradient
                xm = x - 1 if x > 0 else 0
                xp = x + 1 if x < w - 1 else w - 1
                ym = y - 1 if y > 0 else 0
                yp = y + 1 if y < h - 1 else h - 1
                dzdx = height[row + xp] - height[row + xm]
                dzdy = height[yp * w + x] - height[ym * w + x]
                shade = 1.0 + (dzdx * LIGHT[0] + dzdy * LIGHT[1]) * SHADE_STRENGTH
                shade = clamp(shade, *SHADE_RANGE)

                # mottling, so flat biomes are not flat colour. Quantised to a
                # few levels: continuous noise wrecks PNG compression.
                grain = round(cell_noise(x, y) * 3.0) / 3.0
                shade *= 1.0 + grain * 0.045

            r_ch[i] = int(clamp(colour[0] * shade, 0, 255))
            g_ch[i] = int(clamp(colour[1] * shade, 0, 255))
            b_ch[i] = int(clamp(colour[2] * shade, 0, 255))

    return r_ch, g_ch, b_ch


def png_rgb(width: int, height: int, rows: list[bytearray]) -> bytes:
    raw = b"".join(b"\x00" + bytes(r) for r in rows)

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def tile_bounds(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    n = 2 ** z
    lon1 = x / n * 360.0 - 180.0
    lon2 = (x + 1) / n * 360.0 - 180.0
    lat1 = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    lat2 = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n))))
    return lon1, lat2, lon2, lat1


def lat_to_ytile(lat: float, z: int) -> float:
    lat = max(-85.05112878, min(85.05112878, lat))
    r = math.radians(lat)
    return (1 - math.log(math.tan(r) + 1 / math.cos(r)) / math.pi) / 2 * (2 ** z)


def main() -> None:
    meta = json.loads((PROCESSED / "terrain.json").read_text())
    terrain = (PROCESSED / "terrain.bin").read_bytes()
    w, h = meta["width"], meta["height"]
    cell, min_lon, min_lat = meta["cellDeg"], meta["minLon"], meta["minLat"]
    max_lon, max_lat = min_lon + w * cell, min_lat + h * cell

    print(f"  lighting {w}x{h} cells...")
    height = build_heightmap(w, h, terrain)
    r_ch, g_ch, b_ch = build_colours(w, h, terrain, height, min_lat, cell)

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

                # bilinear source column per pixel column, precomputed
                cols: list[tuple[int, int, float]] = []
                for px in range(TILE):
                    lon = west + (east - west) * (px + 0.5) / TILE
                    fx = (lon - min_lon) / cell - 0.5
                    x0i = math.floor(fx)
                    tfx = fx - x0i
                    xa = min(w - 1, max(0, x0i))
                    xb = min(w - 1, max(0, x0i + 1))
                    cols.append((xa, xb, tfx))

                rows: list[bytearray] = []
                for py in range(TILE):
                    yt = (ty + (py + 0.5) / TILE) / n
                    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * yt))))
                    fy = (lat - min_lat) / cell - 0.5
                    y0i = math.floor(fy)
                    tfy = fy - y0i
                    ya = min(h - 1, max(0, y0i)) * w
                    yb = min(h - 1, max(0, y0i + 1)) * w

                    row = bytearray(TILE * 3)
                    for px in range(TILE):
                        xa, xb, tfx = cols[px]
                        w00 = (1 - tfx) * (1 - tfy)
                        w10 = tfx * (1 - tfy)
                        w01 = (1 - tfx) * tfy
                        w11 = tfx * tfy
                        ia, ib, ic, idx = ya + xa, ya + xb, yb + xa, yb + xb
                        o = px * 3
                        row[o] = int(r_ch[ia] * w00 + r_ch[ib] * w10
                                     + r_ch[ic] * w01 + r_ch[idx] * w11)
                        row[o + 1] = int(g_ch[ia] * w00 + g_ch[ib] * w10
                                         + g_ch[ic] * w01 + g_ch[idx] * w11)
                        row[o + 2] = int(b_ch[ia] * w00 + b_ch[ib] * w10
                                         + b_ch[ic] * w01 + b_ch[idx] * w11)
                    rows.append(row)

                path = OUT / str(z) / str(tx) / f"{ty}.png"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(png_rgb(TILE, TILE, rows))
                count += 1
        written += count
        print(f"  z{z}: {count} tiles")

    size = sum(p.stat().st_size for p in OUT.rglob("*.png"))
    (OUT / "meta.json").write_text(json.dumps({
        "minzoom": MIN_Z,
        "maxzoom": MAX_Z,
        "tileSize": TILE,
        "bounds": [min_lon, min_lat, max_lon, max_lat],
        "note": ("Synthesised from terrain classes and the invented elevation "
                 "model. There is no canonical imagery of this world."),
    }, indent=2))
    print(f"\n  {written} tiles, {size / 1024 / 1024:.1f} MB -> "
          f"{OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
