# Working in this repo

An interactive 3D atlas of the Known World from *A Song of Ice and Fire*. Start
with `README.md`, then `docs/01-architecture.md`.

## Two rules that are easy to break

**Distance is planar, never great-circle.** The source geometry is a flat map
that was handed WGS84 degrees, so it is plate carrée, not geometry on a sphere.
Distance is `hypot(dLon, dLat) × milesPerDegree` (64.93). A haversine call
silently squashes every east–west distance by cos(latitude) — this was a real
bug, caught because east–west anchors implied a ×1.20 scale while north–south
anchors implied ×0.94. Use `miles_between()` in `pipeline/common.py`.

**`pipeline/travel.py` is the reference implementation** of the travel model;
`web/src/lib/router.ts` is a port of it. Change the Python first, run
`pipeline/07_validate_routing.py` (which regenerates the fixtures), then mirror
the change in TypeScript. `cd web && npm run test:parity` fails if they diverge
by more than 0.1%.

## Commands

```bash
scripts/run-pipeline.sh                            # rebuild everything
.venv/bin/python pipeline/0N_....py                # any single stage
.venv/bin/python pipeline/07_validate_routing.py   # travel times vs canon
cd web && npm run dev                              # app on :5173
cd web && npm run test:parity                      # router parity + perf budget
cd web && npm run build                            # typecheck + bundle
```

The Python venv is at `.venv/`; the only dependency is pyshp.

## Where things belong

- **Tunable travel numbers** → `data/custom/travel-modes.json`, never in code.
  They are inferred, not canonical, and are meant to be edited.
- **Canonical places missing from the source data** → `data/custom/places.json`,
  with a `positioning` note explaining how the coordinates were derived.
- **Generated files** → `data/processed/`. Never hand-edit; regenerate.
- `web/public/data/` is a disposable copy — `scripts/sync-web-data.sh` refills it.

## Conventions

- Pipeline stages are numbered, standalone, and re-runnable. Lore fetching caches
  raw wikitext to disk, so re-extraction never touches the network.
- Prefer the standard library. PNG encoding, 7z streaming, polygon rasterisation
  and A* are all hand-rolled here on purpose — each is short, and the install
  stays trivial.
- When the source data is wrong or uncertain, **surface it rather than hide it**.
  The gazetteer carries `confirmed` and `continentSource`; the app renders
  caveats per place; the routing validator separates "our bug" (CHECKS) from
  "the source map disagrees with the books" (CAVEATS).

## Licensing constraint

The geometry is **CC BY-NC-SA 3.0** and load-bearing. This project cannot be
used commercially, and derivatives must carry the same licence. Do not add
scans of *The Lands of Ice and Fire* (a product still on sale), and do not try
to bypass the Cloudflare protection on awoiaf.westeros.org — the archived dump
in `data/raw/` is the sanctioned route. See `docs/02-data-sources.md`.
