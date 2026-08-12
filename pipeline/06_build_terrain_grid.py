#!/usr/bin/env python3
"""Rasterise the world into a terrain grid — the substrate for route finding.

Routing on the road network alone is useless here: the source data has only 21
road segments and just 49 of 239 places sit within 15 miles of one. So we burn
the whole world into a regular lattice of cells, tag each with a terrain class,
and let the client run A* over it. Roads become cheap cells layered on top.

Rasterisation is scanline fill (even-odd), not per-point containment: at this
resolution a point-in-polygon sweep would be ~10^9 operations, while scanline is
O(rows x edges) and finishes in seconds.

Input : data/processed/layers/*.geojson, world.json
Output: data/processed/terrain.bin  (uint8 grid, row-major, south-to-north)
        data/processed/terrain.json (header + legend + costs)
"""
from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import PROCESSED, miles_per_degree, write_json  # noqa: E402
from travel import (  # noqa: E402
    DESERT, FOREST, HILLS, LAKE, MOUNTAIN, OCEAN, PLAINS, ROAD, STEPPE, SWAMP,
    load_terrain_cost,
)

LAYERS = PROCESSED / "layers"

CELL_DEG = 0.125  # ~8 canonical miles per cell

LEGEND = {
    OCEAN: "ocean", PLAINS: "plains", STEPPE: "steppe", FOREST: "forest",
    DESERT: "desert", SWAMP: "swamp", HILLS: "hills", MOUNTAIN: "mountain",
    LAKE: "lake", ROAD: "road",
}

WATER = {OCEAN, LAKE}

# Cost multipliers per terrain class, applied to straight-line distance. Single
# source of truth is data/custom/travel-modes.json so the numbers stay tunable.
LAND_COST = load_terrain_cost()
SEA_COST = {OCEAN: 1.0}

# Source layer "type" values -> terrain class.
LANDSCAPE_TYPES = {"forest": FOREST, "mountain": MOUNTAIN, "swamp": SWAMP, "stepp": STEPPE}
REGION_TYPES = {"forest": FOREST, "mountain": MOUNTAIN, "desert": DESERT, "water": OCEAN}


def load(name: str) -> list[dict]:
    return json.loads((LAYERS / f"{name}.geojson").read_text())["features"]


def rings_of(geometry: dict) -> list[list[list[float]]]:
    """All linear rings of a Polygon/MultiPolygon, holes included."""
    if geometry["type"] == "Polygon":
        return list(geometry["coordinates"])
    if geometry["type"] == "MultiPolygon":
        return [ring for poly in geometry["coordinates"] for ring in poly]
    return []


class Grid:
    def __init__(self, min_lon, min_lat, max_lon, max_lat, cell):
        self.cell = cell
        self.min_lon = min_lon
        self.min_lat = min_lat
        self.width = int((max_lon - min_lon) / cell) + 1
        self.height = int((max_lat - min_lat) / cell) + 1
        self.data = bytearray(self.width * self.height)  # OCEAN == 0

    def lon_of(self, x: int) -> float:
        return self.min_lon + (x + 0.5) * self.cell

    def lat_of(self, y: int) -> float:
        return self.min_lat + (y + 0.5) * self.cell

    def index_of(self, lon: float, lat: float) -> tuple[int, int]:
        return (
            min(self.width - 1, max(0, int((lon - self.min_lon) / self.cell))),
            min(self.height - 1, max(0, int((lat - self.min_lat) / self.cell))),
        )

    def fill_polygons(self, features, value_for, *, only_over=None):
        """Scanline even-odd fill. `value_for(feature)` returns a class or None."""
        painted = 0
        buckets: dict[int, list] = {}
        for feat in features:
            value = value_for(feat)
            if value is None:
                continue
            buckets.setdefault(value, []).extend(rings_of(feat["geometry"]))

        for value, rings in buckets.items():
            edges = []
            for ring in rings:
                for i in range(len(ring) - 1):
                    (x1, y1), (x2, y2) = ring[i][:2], ring[i + 1][:2]
                    if y1 != y2:
                        edges.append((min(y1, y2), max(y1, y2), x1, y1, x2, y2))
            if not edges:
                continue
            edges.sort(key=lambda e: e[0])

            for y in range(self.height):
                lat = self.lat_of(y)
                xs = []
                for ylo, yhi, x1, y1, x2, y2 in edges:
                    if ylo > lat:
                        break
                    if ylo <= lat < yhi:
                        xs.append(x1 + (lat - y1) * (x2 - x1) / (y2 - y1))
                if not xs:
                    continue
                xs.sort()
                row = y * self.width
                for i in range(0, len(xs) - 1, 2):
                    xa, _ = self.index_of(xs[i], lat)
                    xb, _ = self.index_of(xs[i + 1], lat)
                    for x in range(xa, xb + 1):
                        if only_over is None or self.data[row + x] in only_over:
                            self.data[row + x] = value
                            painted += 1
        return painted

    def reclass_landlocked_ocean(self) -> int:
        """Flood the open sea inward from the map border; demote the rest to lake.

        The border is padded 1 degree beyond any coastline, so every edge cell is
        genuinely open water and makes a safe seed.
        """
        from collections import deque

        w, h, data = self.width, self.height, self.data
        open_sea = bytearray(w * h)
        q: deque[int] = deque()

        def seed(x: int, y: int) -> None:
            i = y * w + x
            if data[i] == OCEAN and not open_sea[i]:
                open_sea[i] = 1
                q.append(i)

        for x in range(w):
            seed(x, 0)
            seed(x, h - 1)
        for y in range(h):
            seed(0, y)
            seed(w - 1, y)

        while q:
            i = q.popleft()
            x, y = i % w, i // w
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h:
                    seed(nx, ny)

        demoted = 0
        for i in range(w * h):
            if data[i] == OCEAN and not open_sea[i]:
                data[i] = LAKE
                demoted += 1
        return demoted

    def stroke_lines(self, features, value, *, only_over):
        """Burn line features into the grid (Bresenham-ish, cell-dense)."""
        painted = 0
        for feat in features:
            geom = feat["geometry"]
            parts = (geom["coordinates"] if geom["type"] == "MultiLineString"
                     else [geom["coordinates"]])
            for part in parts:
                for i in range(len(part) - 1):
                    (lon1, lat1), (lon2, lat2) = part[i][:2], part[i + 1][:2]
                    steps = max(
                        1,
                        int(max(abs(lon2 - lon1), abs(lat2 - lat1)) / (self.cell * 0.5)),
                    )
                    for s in range(steps + 1):
                        t = s / steps
                        x, y = self.index_of(lon1 + (lon2 - lon1) * t,
                                             lat1 + (lat2 - lat1) * t)
                        idx = y * self.width + x
                        if self.data[idx] in only_over:
                            self.data[idx] = value
                            painted += 1
        return painted


def main() -> None:
    continents = load("continents")
    islands = load("islands")
    lakes = load("lakes")
    landscape = load("landscape")
    regions = load("regions")
    roads = load("roads")

    lons, lats = [], []
    for feat in continents + islands:
        for ring in rings_of(feat["geometry"]):
            for c in ring:
                lons.append(c[0])
                lats.append(c[1])
    pad = 1.0
    grid = Grid(min(lons) - pad, min(lats) - pad, max(lons) + pad, max(lats) + pad, CELL_DEG)
    print(f"  grid {grid.width} x {grid.height} = {grid.width * grid.height:,} cells "
          f"@ {CELL_DEG}deg (~{CELL_DEG * miles_per_degree():.1f} miles)")

    # 1. base land
    n = grid.fill_polygons(continents, lambda f: PLAINS)
    n += grid.fill_polygons(islands, lambda f: PLAINS)
    print(f"  land        {n:>8,} cells painted")

    # 2. broad regions, then the more specific landscape polygons on top
    n = grid.fill_polygons(
        regions,
        lambda f: REGION_TYPES.get((f["properties"].get("type") or "").lower()),
        only_over={PLAINS},
    )
    print(f"  regions     {n:>8,}")
    n = grid.fill_polygons(
        landscape,
        lambda f: LANDSCAPE_TYPES.get((f["properties"].get("type") or "").lower()),
        only_over={PLAINS, STEPPE, FOREST, DESERT, HILLS},
    )
    print(f"  landscape   {n:>8,}")

    # 3. inland water is impassable to land travel
    n = grid.fill_polygons(lakes, lambda f: LAKE)
    print(f"  lakes       {n:>8,}")

    # 4. roads win over whatever they cross (they are the maintained route)
    land_classes = set(LAND_COST) - {ROAD}
    n = grid.stroke_lines(roads, ROAD, only_over=land_classes)
    print(f"  roads       {n:>8,}")

    # 5. Some inland basins get painted ocean by the Regions layer, and a coastal
    # city can then snap into a pocket with no way out to sea (Braavos' lagoon
    # did exactly this). Anything not connected to the open sea becomes a lake.
    n = grid.reclass_landlocked_ocean()
    print(f"  landlocked  {n:>8,} ocean cells -> lake")

    counts = {LEGEND[c]: grid.data.count(c) for c in LEGEND}
    total_land = sum(v for k, v in counts.items() if k not in ("ocean", "lake"))

    out_bin = PROCESSED / "terrain.bin"
    out_bin.write_bytes(bytes(grid.data))
    gz = gzip.compress(bytes(grid.data), 9)
    (PROCESSED / "terrain.bin.gz").write_bytes(gz)

    write_json(PROCESSED / "terrain.json", {
        "width": grid.width,
        "height": grid.height,
        "cellDeg": CELL_DEG,
        "minLon": round(grid.min_lon, 6),
        "minLat": round(grid.min_lat, 6),
        "milesPerDegree": miles_per_degree(),
        "rowOrder": "south-to-north, west-to-east, row-major",
        "legend": {str(k): v for k, v in LEGEND.items()},
        "landCost": {str(k): v for k, v in LAND_COST.items()},
        "seaCost": {str(k): v for k, v in SEA_COST.items()},
        "water": sorted(WATER),
        "counts": counts,
        "binary": "terrain.bin (uint8, one byte per cell)",
    }, compact=False)

    print(f"\n  {counts}")
    print(f"  {total_land:,} traversable land cells")
    print(f"  terrain.bin {len(grid.data) / 1024:.0f} KB  ->  gzip {len(gz) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
