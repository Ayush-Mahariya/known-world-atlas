# Architecture

## Shape of the thing

```
raw sources ──> pipeline (Python) ──> data/processed ──> web/public ──> app (TS)
  shapefiles        8 ordered            geojson,           static        MapLibre
  wiki dump         scripts              gazetteer,         copy          + A* router
  wiki APIs                              lore, terrain,
                                         DEM tiles
```

Two deliberate properties:

**The app is fully static.** No server, no database, no API. Every byte it needs
is a file under `web/public/`. It builds to a folder you can drop on Cloudflare
Pages, GitHub Pages, or a USB stick. Routing runs in the browser in ~2 ms.

**The app is fully offline.** No external basemap, no tile server, no font
server, no CDN. The parchment cartography is drawn from our own GeoJSON; the
hillshading comes from our own DEM tiles; place labels are HTML markers
specifically so we don't need a glyph endpoint.

## The pipeline

Each stage is a standalone script. Run all of them with
`scripts/run-pipeline.sh`, or any one on its own.

| Stage | Does | Reads | Writes |
|-------|------|-------|--------|
| `01_shapefiles_to_geojson.py` | Format conversion, attribute cleanup | `data/raw/game_of_thrones_shapes/` | `layers/*.geojson` |
| `02_calibrate_scale.py` | Fits miles-per-degree against canon distances | layers | `world.json` |
| `03_build_gazetteer.py` | Joins places to realm/region/terrain/road; patches missing places | layers, `data/custom/places.json` | `gazetteer.json` |
| `04_fetch_lore.py` | Two Fandom wikis, batched + cached | `gazetteer.json` | `lore.json`, `data/lore/cache/` |
| `05_enrich_from_awoiaf.py` | Streams the AWOIAF XML dump | `awoiaf-dump.7z` | `lore.json` (merged) |
| `06_build_terrain_grid.py` | Scanline-rasterises the world | layers | `terrain.bin`, `terrain.json` |
| `07_validate_routing.py` | Checks travel times against canon | terrain, gazetteer | `route-fixtures.json` |
| `08_build_dem_tiles.py` | Cuts terrain-RGB XYZ tiles from the elevation model | terrain grid | `web/public/tiles/dem/` |
| `09_build_satellite_tiles.py` | Renders the satellite basemap | terrain grid | `web/public/tiles/satellite/` |

`heightmap.py` holds the synthesised elevation model that stages 08 and 09
share — the imagery has to be lit by the same relief the 3D view uses, or hills
would be shaded from one direction and lit from another.

Dependencies are almost nothing: **pyshp** and the standard library. PNG
encoding, 7-Zip streaming, wiki fetching, polygon rasterisation and A* are all
hand-rolled rather than pulled in — partly to keep the install trivial, mostly
because each one is 40 lines and understanding it matters more than the
dependency would.

## Key data structures

### `gazetteer.json` — one record per place

Spatial joins are done **at build time**, not at runtime, so the app never does
point-in-polygon work:

```jsonc
{
  "slug": "winterfell", "name": "Winterfell", "type": "Castle", "size": 4,
  "confirmed": true, "source": "shapefile",
  "lon": 15.79, "lat": 32.42,
  "continent": "Westeros", "continentSource": "polygon",
  "politicalRegion": "The North", "claimedBy": "Stark",
  "regions": ["The Barrowlands"], "terrain": [],
  "nearestRoad": "Kingsroad", "milesToRoad": 3.2
}
```

### `terrain.bin` — the routing substrate

A raw `uint8` array, one byte per cell, row-major south-to-north. 745 × 745 =
555,025 bytes, which gzips to **12 KB**. `terrain.json` carries the header
(origin, cell size, legend, cost table). The browser fetches both and wraps them
in a `TerrainGrid` — no parsing, no graph construction, just an indexed array.

### Tiles

Two XYZ pyramids, z2–z5, 168 tiles each, both written by a hand-rolled PNG
encoder (~40 lines of zlib and CRC — no image library):

- **`dem/`** ~1 MB, Mapbox terrain-RGB. Elevation is synthesised from terrain
  classes, blurred nine times to hide the 8-mile cell edges, and written in
  **metres** (honest data); the app exaggerates ×12 on display, because a
  continent 3,000 miles wide makes real mountains invisible.
- **`satellite/`** ~3.5 MB, plain RGB. Biome colour per cell, lit by the relief,
  tinted by latitude, whitened above a snowline that falls as you go north, and
  shaded by depth at sea. Colours are computed once per terrain cell and
  bilinearly interpolated across each tile — faster than per-pixel biome logic,
  and the blur between biomes reads like a real ecotone rather than a
  cartographic hard edge.

Both sources declare `bounds`, which matters more than it sounds: without it
MapLibre requests tiles outside our coverage, a dev server answers with its SPA
fallback, and the decoder fails on HTML-served-as-PNG.

z5 is ~2.9 miles/pixel — already finer than the 8-mile source grid — so beyond
that MapLibre overzooms and the imagery softens. That is the right trade at
this data resolution.

## The web app

```
web/src/
  main.ts               app wiring: map, markers, declutter, search, routing
  lib/router.ts         A* over the terrain grid — the port of travel.py
  lib/router.parity.ts  pins the port to the Python reference
  lib/style.ts          the parchment MapLibre style
  lib/types.ts
  ui/placePanel.ts      geography + history for one place
  ui/routePanel.ts      five modes, ranked by time
  style/app.css
```

Three things worth knowing:

**Labels are HTML markers, not symbol layers.** Symbol layers would give free
collision avoidance but require a glyph server. Instead `declutter()` in
`main.ts` does it in screen space on each frame: walk places biggest-first,
keep a list of occupied boxes, hide anything that intersects one. A village
never suppresses a capital.

Realm labels go through `sizeRealmLabels()` first and hand their boxes to
`declutter()` as already-occupied space. Each realm label is scaled to fit its
realm's projected width — fixed-size type overruns badly ("THE WESTERLANDS" is
wider than the Westerlands at low zoom) — then a second pass drops any that
still collide, largest realm winning. Realm bounding boxes genuinely overlap
(the Reach wraps around the stormlands), so sizing alone is not enough.

**Anything that mutates layers goes through `whenStyleReady()`.** The view
controls exist before the style finishes loading, and MapLibre throws "Style is
not done loading" if you set a layout property early. Calls made before load are
queued and flushed by the `load` handler.

**Routing is synchronous on the UI thread.** At ~2 ms a query that is fine, and
it keeps the code simple. The parity test asserts a 250 ms budget; if a future
change blows through it, move to a worker.

**Two route line layers, not one.** `line-dasharray` takes no data expressions,
so ground routes and the dragon's straight flight are separate layers filtered
on the same source.

## Testing

| Command | Checks |
|---------|--------|
| `.venv/bin/python pipeline/07_validate_routing.py` | Travel times against canon; connectivity invariants |
| `cd web && npm run test:parity` | TS router matches Python to 0.1%; performance budget |
| `cd web && npm run typecheck` | Strict TypeScript |
| `cd web && npm run build` | Typecheck + production bundle |

The parity test reads generated fixtures rather than hand-copied constants, so
changing the cost model shows up as a real diff instead of a stale expectation.
