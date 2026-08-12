"""Reference implementation of the multi-modal travel model.

The web app ships its own TypeScript port of this (web/src/lib/router.ts); this
module is the authority the port is validated against, and is what
07_validate_routing.py exercises against canonical journey times.

Speeds are daily marches, not sprints: a rider can gallop 60 miles in a day and
founder the horse, but a party crossing a kingdom averages far less.
"""
from __future__ import annotations

import heapq
import json
import math
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Mode:
    key: str
    label: str
    #: miles covered per day of travel on flat, maintained road
    miles_per_day: float
    #: multiplier applied to every non-road land cell, on top of terrain cost
    off_road_penalty: float = 1.0
    #: terrain classes this mode simply cannot enter
    impassable: frozenset[int] = field(default_factory=frozenset)
    #: flies point-to-point, ignoring terrain and water entirely
    flies: bool = False
    #: travels on water instead of land
    sails: bool = False
    note: str = ""


# terrain codes, mirroring 06_build_terrain_grid.py
OCEAN, PLAINS, STEPPE, FOREST, DESERT, SWAMP, HILLS, MOUNTAIN, LAKE, ROAD = range(10)

WATER = {OCEAN, LAKE}

TERRAIN_BY_NAME = {
    "ocean": OCEAN, "plains": PLAINS, "steppe": STEPPE, "forest": FOREST,
    "desert": DESERT, "swamp": SWAMP, "hills": HILLS, "mountain": MOUNTAIN,
    "lake": LAKE, "road": ROAD,
}

CONFIG_PATH = Path(__file__).resolve().parent.parent / "data" / "custom" / "travel-modes.json"


def load_modes(path: Path = CONFIG_PATH) -> dict[str, Mode]:
    """Read the tunable speed/terrain config into Mode objects."""
    cfg = json.loads(path.read_text())
    modes = {}
    for key, m in cfg["modes"].items():
        modes[key] = Mode(
            key=key,
            label=m["label"],
            miles_per_day=float(m["milesPerDay"]),
            off_road_penalty=float(m.get("offRoadPenalty", 1.0)),
            impassable=frozenset(TERRAIN_BY_NAME[t] for t in m.get("impassable", [])),
            flies=bool(m.get("flies")),
            sails=bool(m.get("sails")),
            note=m.get("note", ""),
        )
    return modes


def load_terrain_cost(path: Path = CONFIG_PATH) -> dict[int, float]:
    cfg = json.loads(path.read_text())
    return {TERRAIN_BY_NAME[k]: float(v) for k, v in cfg["terrainCost"].items()}


MODES: dict[str, Mode] = load_modes()


class TerrainGrid:
    def __init__(self, meta: dict, data: bytes):
        self.width = meta["width"]
        self.height = meta["height"]
        self.cell = meta["cellDeg"]
        self.min_lon = meta["minLon"]
        self.min_lat = meta["minLat"]
        self.mpd = meta["milesPerDegree"]
        self.land_cost = {int(k): v for k, v in meta["landCost"].items()}
        self.sea_cost = {int(k): v for k, v in meta["seaCost"].items()}
        self.data = data

    @classmethod
    def load(cls, processed: Path) -> "TerrainGrid":
        meta = json.loads((processed / "terrain.json").read_text())
        return cls(meta, (processed / "terrain.bin").read_bytes())

    def idx(self, x: int, y: int) -> int:
        return y * self.width + x

    def at(self, x: int, y: int) -> int:
        return self.data[y * self.width + x]

    def to_cell(self, lon: float, lat: float) -> tuple[int, int]:
        return (
            min(self.width - 1, max(0, int((lon - self.min_lon) / self.cell))),
            min(self.height - 1, max(0, int((lat - self.min_lat) / self.cell))),
        )

    def to_lonlat(self, x: int, y: int) -> tuple[float, float]:
        return (self.min_lon + (x + 0.5) * self.cell,
                self.min_lat + (y + 0.5) * self.cell)

    def snap(self, lon: float, lat: float, allowed: set[int], radius: int = 24):
        """Nearest cell whose terrain is in `allowed`, searched in rings."""
        cx, cy = self.to_cell(lon, lat)
        if self.at(cx, cy) in allowed:
            return cx, cy
        for r in range(1, radius + 1):
            for dx in range(-r, r + 1):
                for dy in (-r, r):
                    x, y = cx + dx, cy + dy
                    if 0 <= x < self.width and 0 <= y < self.height and self.at(x, y) in allowed:
                        return x, y
            for dy in range(-r + 1, r):
                for dx in (-r, r):
                    x, y = cx + dx, cy + dy
                    if 0 <= x < self.width and 0 <= y < self.height and self.at(x, y) in allowed:
                        return x, y
        return None


# 8-connected neighbourhood
NEIGHBOURS = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]

# How far (in cells, ~8 miles each) to hunt for a usable start/end cell.
SNAP_RADIUS_LAND = 24   # ~195 miles: covers islands drawn smaller than a cell
SNAP_RADIUS_SEA = 5     # ~40 miles: a port must actually be near the water


def passable_set(grid: TerrainGrid, mode: Mode) -> set[int]:
    if mode.sails:
        # Ocean only. Lakes are water but land-locked: snapping a port to an
        # enclosed lagoon strands the route (Braavos did exactly this).
        return {OCEAN}
    return {c for c in grid.land_cost if c not in mode.impassable}


def smooth(grid: TerrainGrid, cells: list[int], allowed: set[int],
           costs: dict[int, float], off_road: float) -> list[int]:
    """String-pull the A* path straight where the terrain allows it.

    An 8-connected grid can only step at 45 degree increments, so any route on a
    different bearing comes out as a staircase and reads ~8% long. This walks the
    path greedily, replacing runs of cells with a straight line whenever that
    line is passable and no more expensive than the steps it replaces.
    """
    if len(cells) < 3:
        return cells

    def line_cells(a: int, b: int) -> list[int] | None:
        ax, ay = a % grid.width, a // grid.width
        bx, by = b % grid.width, b // grid.width
        steps = max(abs(bx - ax), abs(by - ay))
        if steps == 0:
            return [a]
        out = []
        for s in range(steps + 1):
            t = s / steps
            x = round(ax + (bx - ax) * t)
            y = round(ay + (by - ay) * t)
            terrain = grid.at(x, y)
            if terrain not in allowed:
                return None
            out.append(y * grid.width + x)
        return out

    def run_cost(seq: list[int]) -> float:
        cell_miles = grid.cell * grid.mpd
        total = 0.0
        for i in range(1, len(seq)):
            px, py = seq[i - 1] % grid.width, seq[i - 1] // grid.width
            x, y = seq[i] % grid.width, seq[i] // grid.width
            step = cell_miles * (math.sqrt(2) if (px != x and py != y) else 1.0)
            terrain = grid.at(x, y)
            w = costs[terrain] * (off_road if terrain != ROAD else 1.0)
            total += step * w
        return total

    out = [cells[0]]
    i = 0
    while i < len(cells) - 1:
        best, best_line = i + 1, [cells[i], cells[i + 1]]
        # cap the look-ahead: quadratic in the window, and long straight shots
        # across a whole continent are rarely valid anyway
        for j in range(min(len(cells) - 1, i + 60), i + 1, -1):
            line = line_cells(cells[i], cells[j])
            if line and run_cost(line) <= run_cost(cells[i : j + 1]) + 1e-9:
                best, best_line = j, line
                break
        # keep the path densified and cell-adjacent so callers can measure it
        out.extend(best_line[1:])
        i = best
    return out


def route(grid: TerrainGrid, mode: Mode, start: tuple[float, float],
          end: tuple[float, float]) -> dict | None:
    """A* from start to end for one travel mode. Returns miles, days and path."""
    if mode.flies:
        miles = math.hypot(end[0] - start[0], end[1] - start[1]) * grid.mpd
        return {
            "mode": mode.key,
            "miles": miles,
            "days": miles / mode.miles_per_day,
            "path": [list(start), list(end)],
            "straightLine": True,
        }

    allowed = passable_set(grid, mode)
    costs = grid.sea_cost if mode.sails else grid.land_cost

    # How far we will look for a usable cell before giving up. Ships need a port:
    # if there is no navigable sea within a day's cart ride, the answer is "you
    # cannot sail from here", not a silently wrong route.
    radius = SNAP_RADIUS_SEA if mode.sails else SNAP_RADIUS_LAND
    s = grid.snap(*start, allowed=allowed, radius=radius)
    e = grid.snap(*end, allowed=allowed, radius=radius)
    if not s or not e:
        which = "origin" if not s else "destination"
        reason = "no navigable water" if mode.sails else "no passable ground"
        return {
            "mode": mode.key,
            "error": "unreachable-endpoint",
            "endpoint": which,
            "message": f"{reason} near the {which} for travel {mode.label.lower()}",
        }

    cell_miles = grid.cell * grid.mpd
    goal_idx = grid.idx(*e)

    def heuristic(x: int, y: int) -> float:
        # octile distance, scaled by the cheapest possible terrain
        dx, dy = abs(x - e[0]), abs(y - e[1])
        steps = (dx + dy) + (math.sqrt(2) - 2) * min(dx, dy)
        return steps * cell_miles * min(costs.values())

    start_idx = grid.idx(*s)
    g = {start_idx: 0.0}
    came: dict[int, int] = {}
    open_heap = [(heuristic(*s), start_idx)]
    closed = bytearray(grid.width * grid.height)

    while open_heap:
        _, current = heapq.heappop(open_heap)
        if closed[current]:
            continue
        closed[current] = 1
        if current == goal_idx:
            break
        cy, cx = divmod(current, grid.width)
        cy, cx = current // grid.width, current % grid.width
        for dx, dy in NEIGHBOURS:
            nx, ny = cx + dx, cy + dy
            if not (0 <= nx < grid.width and 0 <= ny < grid.height):
                continue
            terrain = grid.at(nx, ny)
            if terrain not in allowed:
                continue
            nidx = ny * grid.width + nx
            if closed[nidx]:
                continue
            step = cell_miles * (math.sqrt(2) if dx and dy else 1.0)
            weight = costs[terrain]
            if not mode.sails and terrain != ROAD:
                weight *= mode.off_road_penalty
            tentative = g[current] + step * weight
            if tentative < g.get(nidx, float("inf")):
                g[nidx] = tentative
                came[nidx] = current
                heapq.heappush(open_heap, (tentative + heuristic(nx, ny), nidx))

    if goal_idx not in g:
        return {
            "mode": mode.key,
            "error": "no-route",
            "message": f"no continuous {mode.label.lower()} route exists between "
                       f"these places",
        }

    path_cells = [goal_idx]
    while path_cells[-1] != start_idx:
        path_cells.append(came[path_cells[-1]])
    path_cells.reverse()

    off_road = 1.0 if mode.sails else mode.off_road_penalty
    path_cells = smooth(grid, path_cells, allowed, costs, off_road)

    # measure the smoothed path: true miles for the distance readout, weighted
    # miles (terrain-adjusted) for the duration
    miles = 0.0
    weighted = 0.0
    path = []
    for i, idx in enumerate(path_cells):
        y, x = idx // grid.width, idx % grid.width
        path.append([round(v, 5) for v in grid.to_lonlat(x, y)])
        if i:
            py, px = path_cells[i - 1] // grid.width, path_cells[i - 1] % grid.width
            step = cell_miles * (math.sqrt(2) if (px != x and py != y) else 1.0)
            terrain = grid.at(x, y)
            w = costs[terrain] * (off_road if (not mode.sails and terrain != ROAD) else 1.0)
            miles += step
            weighted += step * w

    return {
        "mode": mode.key,
        "miles": miles,
        "weightedMiles": weighted,
        "days": weighted / mode.miles_per_day,
        "path": path,
        "straightLine": False,
    }
