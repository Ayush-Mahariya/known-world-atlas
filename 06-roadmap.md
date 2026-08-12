# Roadmap

Ordered by value per unit of work. Everything in "Built" already works and is
tested; everything below it does not exist yet.

## Built

- 241 places joined to realm, region, terrain and nearest road
- History for 176 of them from three wikis, book and screen canon kept apart
- Calibrated world scale (64.93 miles/degree, 5 of 7 anchors within 1%)
- Terrain grid + A* routing across five modes, validated against ten canonical
  journeys
- Synthesised 3D terrain with hillshading; flat / tilted / globe views
- Two basemaps: parchment cartography and a synthesised satellite view
- Realm overlay: rainbow palette north to south, named realms, legend
- Decluttered labels, search, route planner
- Fully static and fully offline

## Next — high value, low effort

**1. Multi-leg journeys.** The biggest hole. You cannot ride to White Harbor and
then sail to Braavos; each mode is evaluated end to end alone. Implementation:
tag coastal places as ports, then run a small graph over
`(place, mode)` nodes with transfer edges at ports. This is what turns "no
navigable water near the destination" into a real itinerary.

**2. Fix the crownlands, label the era.** Patch `claimedby` for the crownlands to
Baratheon in `data/custom/`, and put "circa 298 AC" on the map. One line of
data; removes the project's most visible factual wart. See
[`04-eras-and-story.md`](04-eras-and-story.md) §3.

**3. Deep-link and share state.** Encode selected place, route endpoints, mode
and camera in the URL hash. Makes the atlas linkable, which is most of what
makes a map like this get used.

**4. Hills.** The terrain class exists and is wired into the cost model, but
nothing ever paints it. A buffer pass around mountain polygons would give
foothills, better relief, more believable routes through the Vale, and a less
abrupt tree line in the satellite view.

**5. Sharper satellite imagery.** The basemap tops out at z5 (~2.9 miles/pixel)
because that is already finer than the 8-mile terrain grid; zooming past it just
softens. Getting genuinely crisper imagery means synthesising sub-cell detail —
fractal noise warped by the terrain class — rather than cutting more tiles from
the same data.

## Then — the interesting one

**6. Make the map time-aware.** Coastlines and rivers are timeless; only
political control and place existence change. Give each political region a list
of `{from, to, house}` intervals, add `existsFrom` / `ruinedFrom` to places, and
put an era slider in the UI. What it unlocks:

- Harrenhal whole before 1 AC, a ruin after
- Valyria intact before the Doom, the Smoking Sea after
- The Dance of the Dragons as a real Green/Black map, not a diagram
- Dunk and Egg's Westeros, with Blackfyre holdings marked
- Robert's Rebellion and the War of the Five Kings as animated frontiers

This is the feature that would make the atlas genuinely unlike anything else
that exists for this world. It is also mostly a *data* project rather than a
code one — the schema change is small; sourcing the intervals is the work.

**7. Journeys from the books.** Plot the actual routes characters take — Ned's
ride south, Arya's flight, Brienne's search, Daenerys's khalasar — as timed
tracks. The Dunk and Egg novellas are the best source of stated travel times and
would double as new routing anchors.

## Later — bigger lifts

**8. Real 3D landmarks.** Extruded or modelled castles for the major seats.
MapLibre can do `fill-extrusion` for footprints today; actual models need a
three.js custom layer.

**9. River crossings.** Model fords and bridges so the Trident is a barrier
rather than scenery. Needs bridge locations added first, or it strands places.

**10. Seasons.** Westerosi winters last years and would plausibly double every
land travel figure. A season toggle that scales terrain costs would be cheap and
very much in the spirit of the world.

**11. Self-hosted glyphs.** Would let labels move to MapLibre symbol layers, with
proper collision avoidance and curved labels along coastlines, replacing the
hand-rolled declutter pass.

**12. Fresher AWOIAF text.** The archived dump is from 2015 and predates *Fire &
Blood*. The live site is behind bot protection that this project does not
attempt to bypass — the correct route is to ask its operators for API access.

## Explicitly not doing

- **Anything commercial.** The geometry is CC BY-NC-SA. See
  [`02-data-sources.md`](02-data-sources.md).
- **Scanning the official maps.** *The Lands of Ice and Fire* is a product still
  on sale.
- **Defeating Cloudflare on awoiaf.westeros.org.** The archived dump exists and
  is licensed for this.
