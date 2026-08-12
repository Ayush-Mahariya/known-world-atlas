# Data sources, provenance and licensing

**Read this before publishing anything.** The geometry this project is built on
is licensed **non-commercially**, and that constrains what you can do with the
result.

## Summary

| Source | What it gives | Licence | Commercial use |
|--------|---------------|---------|----------------|
| cadaei ASOIAF shapefiles | All geometry: coastlines, regions, roads, rivers, places | CC BY-NC-SA 3.0 | **No** |
| A Wiki of Ice and Fire | Book-canon article text (215 places) | CC BY-SA | Yes, with attribution + share-alike |
| A Song of Ice and Fire Wiki (Fandom) | Book-canon article text | CC BY-SA | Yes, with attribution + share-alike |
| Game of Thrones Wiki (Fandom) | Screen-canon article text | CC BY-SA | Yes, with attribution + share-alike |
| Atlas of Ice and Fire world map | Reference raster (not used in the app) | Fan work, posted for download | Ask first |
| The underlying world | — | © George R. R. Martin | — |

**Net effect: this is a non-commercial fan project.** The CC BY-NC-SA geometry is
load-bearing — remove it and there is no map — and its share-alike term means
any derivative must carry the same licence. Do not put ads on it, do not sell
access, do not fold it into anything commercial. That is a licence obligation,
not a style preference.

---

## 1. Geometry — the cadaei shapefiles

The spine of the project. Eleven layers: `Continents`, `Islands`, `Lakes`,
`Land`, `Landscape`, `Locations`, `Political`, `Regions`, `Rivers`, `Roads`,
`Wall`.

**Provenance chain**, as stated in the bundled README:

1. **Tear** of the Cartographer's Guild drew the original map of Westeros.
2. **theMountainGoat** updated it in 2012 and extended it to Essos, Sothoryos,
   Ibben and the Summer Isles, based partly on the speculative world map by
   **Werthead**.
3. Some locations were positioned from maps by **Other-in-Law**.
4. **cadaei** built the GIS files from that work in QGIS.
5. **Patrick Triest** re-released a fixed revision in 2017 for *Atlas of
   Thrones*, which is the copy we download.

Obtained from `https://cdn.patricktriest.com/shapefiles/game_of_thrones_shapes.zip`
(364 KB), vendored to `data/raw/game_of_thrones_shapes/` with its `LICENSE.txt`
and `README.txt` intact. **Do not delete those two files** — the licence
requires them to travel with the data.

Required attribution: *cadaei, theMountainGoat and Tear; world © George R. R.
Martin.* This string is in the app's map attribution control.

Two caveats the authors state themselves and this project inherits:

- **The scale is not exact.** Their own README: *"don't use the map for distance
  measuring."* We recover a usable scale by calibration — see
  [`03-geography.md`](03-geography.md) — but every distance carries that
  uncertainty.
- **A `confirmed` flag marks inferred positions.** 50 of 241 places are
  speculative; the app surfaces this per place rather than hiding it.

## 2. Lore — three wikis

### A Wiki of Ice and Fire (primary, book canon)

The deepest ASOIAF reference, and the source for 215 of our 223 articles.

**The live site sits behind Cloudflare bot protection.** The API returns a
challenge page rather than JSON. This project does **not** attempt to work
around that — no UA spoofing, no headless-browser scraping. Instead we read the
community XML dump archived at
<https://archive.org/details/wiki-awoiafwesterosorg>.

`pipeline/05_enrich_from_awoiaf.py` streams the 1 GB dump straight out of 7-Zip
and parses it incrementally, keeping only the latest revision of pages we want.
Nothing is ever extracted to disk.

The dump is dated **2015-07-09**, which is its main limitation: it predates
*Fire & Blood* (2018), so Targaryen-era material is thinner than the live wiki's.
If you need current text, the right move is to ask the site's operators for
access, not to defeat their bot protection.

### The two Fandom wikis

`iceandfire.fandom.com` (books) and `gameofthrones.fandom.com` (screen) have
open MediaWiki APIs. `pipeline/04_fetch_lore.py` queries them 50 titles at a
time with a descriptive User-Agent and a delay between batches, and caches raw
wikitext to `data/lore/cache/` so re-extraction never touches the network.

Book canon wins where sources conflict; screen canon is kept in a separate field
and rendered under its own heading, so the two are never silently merged.

**All three are CC BY-SA**, which obliges attribution *and* share-alike. Every
place panel links its sources and states the licence.

## 3. Reference rasters (downloaded, not shipped)

`data/raw/basemaps/` holds two high-resolution maps used for eyeballing the
vector data, not rendered by the app:

- **`asoiaf-known-world-atlas-10000px.jpg`** (10000 × 8300) — the fan-made
  Known World map by Adam Whitehead, posted for download at
  [Atlas of Ice and Fire](https://atlasoficeandfireblog.wordpress.com/2019/12/23/a-new-song-of-ice-and-fire-game-of-thrones-world-map/).
- **`westeros-commons.png`** (3854 × 7400) — from
  [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Westeros_Map.png).

Neither is registered to our coordinate system, so neither can be used as a
basemap without warping. The app renders its basemap from the vector data
instead, which guarantees the map and the routing agree.

**Deliberately not used:** *The Lands of Ice and Fire* (Jonathan Roberts, 2012)
is the official cartography and is still sold as a poster set. Scans of it are
easy to find and are not in this repository.

## 4. Derived data — ours

Everything in `data/processed/` and `web/public/tiles/` is generated by the
pipeline from the above. The synthesised elevation model in particular
(`08_build_dem_tiles.py`) is **invented** — there is no canonical topography for
Westeros. It is derived from terrain classes purely so the world can be lit and
tilted, and `tiles/dem/meta.json` says so.

Because it derives from CC BY-NC-SA geometry, the derived data inherits that
licence.
