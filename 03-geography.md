# The geography we have: what is in the gazetteer, and how good it is

Everything below is generated from `data/processed/`. Regenerate the numbers
with `.venv/bin/python pipeline/03_build_gazetteer.py`.

## The world at a glance

| | |
|---|---|
| Places | **241** |
| With a wiki article | 223 (93%) |
| With a written history | 176 (73%) |
| Position confirmed by the source cartographers | 191 (79%) |
| Continents | Westeros, Essos, Sothoryos (Ulthos is off the source map) |
| Named political regions | 11 |
| Roads | 21 segments, 6 named highways |
| Rivers | 74 |
| Islands | 86 |
| Lakes | 19 |

## Places by continent and kind

| Continent | City | Town | Castle | Ruin | Landmark |
|-----------|-----:|-----:|-------:|-----:|---------:|
| Westeros | 5 | 30 | 119 | 27 | 20 |
| Essos | 16 | 4 | 2 | 12 | 2 |
| Sothoryos | — | — | — | 3 | — |

The asymmetry is real and worth understanding before you judge the data:
Westeros is a continent of **castles** (119 of them) because the novels are
written from inside a feudal aristocracy, and every minor lordling's seat gets
named. Essos is a continent of **cities** because Westerosi narrators encounter
it as a string of ports. Sothoryos is three ruins, because that is all anyone in
the books claims to know about it.

## Westeros by realm

| Realm | Places | Claimed by (per source data) |
|-------|-------:|------------------------------|
| Riverlands | 34 | Tully |
| The North | 23 | Stark |
| The Westerlands | 21 | Lannister |
| Dorne | 21 | Martell |
| The Gift | 21 | Night's Watch |
| The Reach | 20 | Tyrell |
| Stormlands | 19 | Baratheon |
| The Vale | 15 | Arryn |
| Crownsland | 11 | Targaryen — *see the caveat below* |
| The Iron Islands | 5 | Greyjoy |
| *outside any realm* | 51 | — |

Two things to note.

**The riverlands are over-represented** (34 places — more than the North, which
is many times larger). This is not an error: the riverlands are the crossroads
of Westeros, densely castled, and they are where most of the War of the Five
Kings is fought, so they are the best-documented region in the text.

**"Crownsland claimed by Targaryen" is wrong for 298 AC.** The source data mixes
eras; the crownlands passed to House Baratheon in 283 AC. The app reports the
data faithfully rather than silently correcting it. See
[`04-eras-and-story.md`](04-eras-and-story.md) §3 for the two ways to fix this.

The 51 places outside any realm are beyond the Wall, on Essos, or on islands the
political layer does not cover.

## Terrain

Rasterised at 0.125° (~8 miles) per cell, 745 × 745 = 555,025 cells.

| Terrain | Cells | Share of land |
|---------|------:|--------------:|
| Plains | 68,829 | 39% |
| Mountain | 38,108 | 22% |
| Forest | 25,010 | 14% |
| Desert | 23,910 | 14% |
| Steppe | 17,457 | 10% |
| Swamp | 1,117 | 0.6% |
| Road | 1,538 | 0.9% |
| — | | |
| Ocean | 376,250 | — |
| Lake | 2,806 | — |

**Hills is empty (0 cells)** — the class exists in the cost model but the source
`Landscape` layer only distinguishes forest, mountain, swamp and steppe, so
nothing ever paints hills. Left in deliberately: it is the natural place to hang
a future pass that softens mountain edges into foothills.

## How accurate is any of this?

Three separate questions, with three different answers.

### Position — good for the famous places, guesswork for the rest

The source cartographers flag each location as confirmed or inferred. **191 of
241 (79%) are confirmed**; the remaining 50 are positioned by inference from
text and are marked in the app with an explicit caveat in the place panel.

Two canonical places were **missing entirely** from the source data — Casterly
Rock and Bear Island — and are patched in by `data/custom/places.json`,
positioned relative to neighbours that *are* in the data (Casterly Rock just
north of Lannisport; Bear Island at its island polygon's centroid). Places added
this way are labelled as such in the UI.

### Scale — calibrated, and honest about the residual

The source geometry carries no usable scale; its own README says "don't use the
map for distance measuring". We recovered one by weighted least-squares fitting
a single miles-per-degree constant against published distances:

| Anchor | Canon | Fitted | Error |
|--------|------:|-------:|------:|
| Wall to the southern tip of Dorne | 3,000 mi | 3,005 | +0.2% |
| King's Landing → Winterfell | 1,500 mi | 1,500 | 0.0% |
| King's Landing → Oldtown | 1,000 mi | 1,004 | +0.4% |
| Winterfell → Castle Black | 600 mi | 606 | +0.9% |
| The Wall, end to end | 300 mi | 285 | −5.2% |
| King's Landing → Storm's End | 400 mi | 381 | −4.7% |
| Pentos → Dragonstone | 600 mi | 467 | **−22.1%** |

**Result: 64.93 miles per degree.** Five of seven anchors land within 1%.

The Pentos–Dragonstone outlier is the honest signal in that table: it is the
only anchor that crosses the narrow sea, and Essos's placement on this map is
explicitly speculative. It is down-weighted in the fit rather than dropped, so
its error stays visible. The same underlying problem produces the one
documented caveat in the routing validator — this map puts Dragonstone roughly
400 miles from King's Landing, where the books imply a short sail.

### Projection — the trap worth knowing about

The source shapefiles are a **flat map given WGS84 degrees** (plate carrée)
placed over Africa. They are *not* geometry on a sphere. Measuring them with
haversine squashes every east–west distance by cos(latitude), which shows up as
a clean signature: east–west anchors imply a scale factor of ×1.20 while
north–south anchors imply ×0.94 — a ratio of 1.28, almost exactly 1/cos(38°).

So: **distance is `hypot(dLon, dLat) × 64.93`, never a great-circle formula.**
This is enforced in `pipeline/common.py` and mirrored in
`web/src/lib/router.ts`, and it is the single most important thing to know
before adding any new spatial calculation to this project.
