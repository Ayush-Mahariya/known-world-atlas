# Attribution

This is a non-commercial fan project. The world of *A Song of Ice and Fire*, its
places and its history are the intellectual property of **George R. R. Martin**.

## Map geometry — CC BY-NC-SA 3.0

All coastlines, regions, roads, rivers, islands and place positions derive from
the ASOIAF GIS shapefiles by **cadaei**, built on the cartography of
**theMountainGoat** and **Tear** of the Cartographer's Guild, extended in part
from the speculative world map by **Werthead**, with some locations positioned
from maps by **Other-in-Law**. Fixed and re-released by **Patrick Triest** (2017).

Licensed under [Creative Commons Attribution-NonCommercial-ShareAlike 3.0
Unported](https://creativecommons.org/licenses/by-nc-sa/3.0/).

Changes made: converted from shapefile to GeoJSON; attributes cleaned and
normalised; scale calibrated against canonical distances; rasterised to a
terrain grid; an elevation model synthesised from terrain classes; two missing
canonical places (Casterly Rock, Bear Island) added by hand.

The original `LICENSE.txt` and `README.txt` are preserved in
`data/raw/game_of_thrones_shapes/`.

## Article text — CC BY-SA

Place summaries, descriptions and histories are drawn from:

- **[A Wiki of Ice and Fire](https://awoiaf.westeros.org/)** — book canon, read
  from the community XML dump archived at
  [archive.org](https://archive.org/details/wiki-awoiafwesterosorg) (2015-07-09)
- **[A Song of Ice and Fire Wiki](https://iceandfire.fandom.com/)** — book canon
- **[Game of Thrones Wiki](https://gameofthrones.fandom.com/)** — screen canon

All three are licensed [CC BY-SA](https://creativecommons.org/licenses/by-sa/3.0/).
Every place panel in the app links to the specific articles it draws on.

Changes made: wikitext converted to plain text; lead, description and history
sections extracted; sources merged with book canon taking precedence over screen
canon.

## Reference material (downloaded, not rendered)

- **Known World map** by Adam Whitehead —
  [Atlas of Ice and Fire](https://atlasoficeandfireblog.wordpress.com/2019/12/23/a-new-song-of-ice-and-fire-game-of-thrones-world-map/)
- **Westeros map** — [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Westeros_Map.png)

## Software

[MapLibre GL JS](https://maplibre.org/) (BSD-3-Clause),
[Vite](https://vite.dev/) (MIT), [pyshp](https://github.com/GeospatialPython/pyshp) (MIT).
