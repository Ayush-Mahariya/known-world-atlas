# The Known World Atlas

An interactive 3D atlas of Westeros and Essos — every place, its history, and
how long it takes to get there on foot, on horseback, by wheelhouse, by ship or
on dragonback.

A fan project built on George R. R. Martin's *A Song of Ice and Fire*, the
companion histories, and the three screen adaptations. **Non-commercial** — see
[licensing](#licensing).

## What it does

- **241 places** across Westeros, Essos and Sothoryos, each joined to its realm,
  ruling house, terrain and nearest road
- **Click any place for its history** — 176 places have a written history,
  pulled from three wikis, with book canon and screen canon kept separate and
  every source credited
- **Plan a journey between any two places** by foot, horse, wheelhouse, ship or
  dragon; all five compared side by side and ranked by time, with the ones that
  cannot work explaining *why* ("no navigable water near the destination")
- **Real 3D terrain** — synthesised elevation, hillshading, tilt and globe views
- **Two basemaps** — hand-styled parchment cartography, or a synthesised
  satellite view rendered from the terrain and elevation data (biomes, relief
  lighting, sea-depth gradient, and a snowline that falls as you go north)
- **Realm overlay** — the eleven political regions in a rainbow palette running
  north to south, each named on the map with its ruling house, plus a key
- **Runs entirely offline** — no server, no API, no external tiles or fonts

Travel times are validated against journeys the books give a duration for:
King's Landing to Winterfell comes out at six and a half weeks on horseback,
about twelve weeks by wheelhouse, and three days on a dragon.

## Quick start

```bash
# one-time: python environment for the pipeline
python3 -m venv .venv && .venv/bin/pip install -r pipeline/requirements.txt

# rebuild everything from the raw sources (~1 minute; lore is cached)
scripts/run-pipeline.sh

# run the app
cd web && npm install && npm run dev
```

The processed data is committed, so if you only want to run the app you can skip
the pipeline entirely.

## Deploying

```bash
bash scripts/build-site.sh    # ~25s -> web/dist (8.9 MB)
```

Needs only python3 and node — the tile builders are pure standard library, so
any CI image with Python can build it. On Cloudflare Pages set the build command
to `bash scripts/build-site.sh` and the output directory to `web/dist`; a
GitHub Pages workflow is included at `.github/workflows/deploy-pages.yml`.
Full details, including caching and the non-commercial licence constraint, in
[`docs/07-deployment.md`](docs/07-deployment.md).

## Layout

```
data/
  raw/         source shapefiles, the AWOIAF wiki dump, reference basemaps
  custom/      hand-authored patches: missing places, travel speeds
  processed/   generated: geojson layers, gazetteer, lore, terrain grid
  lore/        cached wiki responses
pipeline/      eight ordered Python scripts, raw -> processed
web/           Vite + TypeScript + MapLibre app
scripts/       run-pipeline.sh, sync-web-data.sh
docs/          the interesting reading — see below
```

## Documentation

| | |
|---|---|
| [`01-architecture.md`](docs/01-architecture.md) | How the pipeline and app fit together |
| [`02-data-sources.md`](docs/02-data-sources.md) | Provenance and licensing — **read before publishing** |
| [`03-geography.md`](docs/03-geography.md) | What is in the gazetteer and how accurate it is |
| [`04-eras-and-story.md`](docs/04-eras-and-story.md) | The books, the shows, the timeline, and making the map time-aware |
| [`05-travel-model.md`](docs/05-travel-model.md) | Speeds, terrain costs, routing, validation |
| [`06-roadmap.md`](docs/06-roadmap.md) | What to build next |
| [`07-deployment.md`](docs/07-deployment.md) | Building and shipping the static site |

## Testing

```bash
.venv/bin/python pipeline/07_validate_routing.py   # travel times vs canon
cd web && npm run test:parity                      # TS router == Python reference
cd web && npm run build                            # typecheck + bundle
```

## Two things to know before changing anything

**Distance is planar, never great-circle.** The source geometry is a flat map
that was handed WGS84 degrees. Use `hypot(dLon, dLat) × 64.93`. A haversine call
will silently squash every east–west distance by cos(latitude). Enforced in
`pipeline/common.py`, mirrored in `web/src/lib/router.ts`.

**`pipeline/travel.py` is the reference implementation** of the travel model.
`web/src/lib/router.ts` is a port. Change the Python first, re-run the validator,
then mirror it — `npm run test:parity` will catch you if you don't.

## Known limitations

- The map is a single snapshot, roughly 298 AC, and the source data's political
  layer is internally inconsistent — the crownlands are still marked Targaryen.
  See [`04-eras-and-story.md`](docs/04-eras-and-story.md) §3.
- 50 of 241 place positions are inferred rather than confirmed; the app labels
  these individually.
- No multi-leg journeys yet — you cannot ride to a port and then sail.
- The archived AWOIAF text is from 2015 and predates *Fire & Blood*.
- This map places Dragonstone ~400 miles from King's Landing; the books imply a
  much shorter sail.

## Licensing

The geometry is **CC BY-NC-SA 3.0** (cadaei, theMountainGoat, Tear) — it is
load-bearing, and its non-commercial and share-alike terms flow through to
everything derived from it. Wiki text is **CC BY-SA**. The world itself is
© George R. R. Martin.

Full attribution in [`NOTICE.md`](NOTICE.md) and
[`docs/02-data-sources.md`](docs/02-data-sources.md).
