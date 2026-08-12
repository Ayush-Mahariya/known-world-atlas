# The travel model

How the atlas answers "how long does it take to get from here to there, and by
what means".

## Where the numbers live

All tunable figures are in **`data/custom/travel-modes.json`**, not in code.
They are the softest part of the project — Martin never publishes a rate table
— so they are meant to be argued with. Edit, then run:

```bash
.venv/bin/python pipeline/07_validate_routing.py
```

which re-checks them against journeys the books give a duration for, and
regenerates the fixtures the TypeScript port is tested against.

## Modes

| Mode | Miles/day | Off-road penalty | Cannot enter | Notes |
|------|----------:|-----------------:|--------------|-------|
| On foot | 20 | ×1.0 | — | A party walking. An army with a baggage train makes less. |
| On horseback | 35 | ×1.0 | — | Sustained daily march, not a gallop. Couriers with remounts do far more. |
| By wheelhouse | 20 | ×1.9 | swamp, mountain | Road-bound and slow — Robert's wheelhouse held the royal progress to a crawl. |
| By ship | 120 | — | land | ~5 knots averaged over a day including nights at anchor. Ocean only. |
| By dragon | 500 | — | — | Straight line over anything. Ignores the terrain graph entirely. |

## Terrain cost

Multipliers on straight-line distance. A road is the only thing *faster* than
open ground, because it is maintained, bridged and signposted.

| Terrain | Cost |
|---------|-----:|
| Road | 1.00 |
| Steppe | 1.45 |
| Plains | 1.55 |
| Hills | 2.00 |
| Forest | 2.20 |
| Desert | 2.40 |
| Swamp | 3.00 |
| Mountain | 3.60 |

Duration is `Σ(segment miles × terrain cost × off-road penalty) ÷ miles per day`.
The **distance** shown in the UI is the unweighted path length; the **time** uses
the weighted one. That is why 1,637 miles of kingsroad takes a rider six and a
half weeks while the same distance across the Mountains of the Moon would not.

## How routing works

Road-network routing was tried first and abandoned: the source data has only 21
road segments, and just 49 of 241 places sit within 15 miles of one. Everything
else would have been unreachable.

Instead the whole world is rasterised into a **terrain grid** — 745 × 745 cells
at 0.125° (~8 miles) — and A* runs over it, 8-connected, one node per cell.
Roads are burned into the grid as cheap cells layered on top of whatever they
cross. This makes every place reachable from every other place that *should* be
reachable, and it makes the answer sensitive to what the ground is actually like.

Three details that matter:

**Path smoothing.** An 8-connected grid can only step at 45° increments, so a
route on any other bearing comes out as a staircase and reads several percent
long. A string-pulling pass replaces runs of cells with a straight line wherever
that line is passable and costs no more than the steps it replaces.

**Snapping.** Endpoints snap to the nearest usable cell — up to ~195 miles for
land modes (some islands are smaller than one cell), but only ~40 miles for
ships. That asymmetry is deliberate: it is what makes the atlas say *"no
navigable water near the origin"* for Winterfell rather than inventing a port.

**Landlocked water.** The source `Regions` layer paints some inland basins as
ocean. Left alone, a coastal city snaps into an enclosed lagoon and the route
strands — Braavos did exactly this. The grid builder floods the open sea inward
from the map border and demotes anything it cannot reach to a lake.

## Validation against canon

`pipeline/07_validate_routing.py` is the honesty check on the whole pipeline.
All ten checks currently pass:

| Journey | Mode | Miles | Time | Expected |
|---------|------|------:|-----:|---------:|
| King's Landing → Winterfell | horse | 1,637 | 46.8 d | 30–55 |
| King's Landing → Winterfell | wheelhouse | 1,637 | 81.9 d | 55–110 |
| King's Landing → Winterfell | foot | 1,637 | 81.9 d | 55–100 |
| Winterfell → Castle Black | horse | 663 | 19.3 d | 12–25 |
| King's Landing → Oldtown | horse | 1,177 | 33.6 d | 22–45 |
| King's Landing → Casterly Rock | horse | 889 | 25.8 d | 15–35 |
| King's Landing → Riverrun | horse | 700 | 20.3 d | 12–30 |
| King's Landing → Storm's End | horse | 435 | 12.4 d | 8–20 |
| King's Landing → Braavos | ship | 1,171 | 9.8 d | 5–20 |
| Dragonstone → Winterfell | dragon | 1,420 | 2.8 d | 2–6 |

The script keeps two other sections deliberately separate from the checks:

- **Caveats** — where the *source map* disagrees with the books, not where our
  model is wrong. Currently one: this map places Dragonstone ~400 miles from
  King's Landing, so every route to it reads long.
- **Connectivity probes** — invariants about what should and should not be
  reachable. Pyke must be unreachable on horseback (it is an island) and
  Winterfell must be unreachable by ship (it is inland); both are asserted, so a
  future change that quietly makes them routable will fail the build.

## Two implementations, kept in step

`pipeline/travel.py` is the reference. `web/src/lib/router.ts` is the port that
actually runs in the browser. They are pinned together by
`web/src/lib/router.parity.ts`, which reads
`data/processed/route-fixtures.json` — generated by the Python validator, never
hand-edited — and fails if the two disagree by more than 0.1%.

```bash
cd web && npm run test:parity
```

The test also asserts a performance budget: a continent-crossing query must stay
under 250 ms, since routing runs on the UI thread. It currently takes **~2 ms**.

## Known limits

- **No multi-leg journeys.** You cannot ride to White Harbor and then sail. Each
  mode is evaluated end to end on its own, which is why the panel says "no
  navigable water near the destination" instead of routing you overland first.
  This is the most-requested-sounding gap and the top item on the roadmap.
- **Rivers are not barriers.** Crossing the Trident costs the same as walking a
  field. Modelling fords and bridges would be more faithful but risks stranding
  places, so it needs the bridge locations added first.
- **No seasons or weather.** Westerosi winters last years and would plausibly
  double every land figure. Nothing in the model knows about them.
- **Terrain classes are coarse.** Eight classes over 8-mile cells. A mountain
  pass and a sheer cliff are the same cell.
