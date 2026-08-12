"""The synthesised elevation model, shared by the DEM and satellite tile builders.

There is no canonical topography for the Known World, so we invent one: each
terrain class gets a base elevation and the result is blurred until mountains
rise into believable foothills rather than standing on 8-mile cliffs.

Both consumers need the *same* heights — the satellite imagery is lit by the
same relief the 3D terrain uses, or the shading would not line up.
"""
from __future__ import annotations

from travel import (
    DESERT, FOREST, HILLS, LAKE, MOUNTAIN, OCEAN, PLAINS, ROAD, STEPPE, SWAMP,
)

# Base elevation in feet per terrain class.
ELEVATION: dict[int, float] = {
    OCEAN: -600.0,
    LAKE: -20.0,
    SWAMP: 15.0,
    PLAINS: 220.0,
    ROAD: 200.0,
    STEPPE: 350.0,
    FOREST: 420.0,
    DESERT: 500.0,
    HILLS: 1100.0,
    MOUNTAIN: 4200.0,
}

# Each cell is ~8 miles across, so the raw heightmap is a staircase. Enough box
# blur to hide the cell edges at the zooms we ship, not so much that mountain
# ranges melt into the plains.
BLUR_PASSES = 9
FEET_TO_METRES = 0.3048


def build_heightmap(width: int, height: int, terrain: bytes) -> list[float]:
    """Terrain classes -> a blurred field of elevations in feet."""
    field = [ELEVATION[b] for b in terrain]

    for _ in range(BLUR_PASSES):
        tmp = [0.0] * (width * height)
        for y in range(height):
            row = y * width
            for x in range(width):
                a = field[row + (x - 1 if x > 0 else 0)]
                b = field[row + x]
                c = field[row + (x + 1 if x < width - 1 else width - 1)]
                tmp[row + x] = (a + b + c) / 3.0
        for x in range(width):
            for y in range(height):
                a = tmp[(y - 1 if y > 0 else 0) * width + x]
                b = tmp[y * width + x]
                c = tmp[(y + 1 if y < height - 1 else height - 1) * width + x]
                field[y * width + x] = (a + b + c) / 3.0
    return field
