# The Known World in time: eras, sources, and what the map should show

The atlas is currently a *single-era* map — it shows the world roughly as it
stands at the opening of *A Game of Thrones*. That is a choice the data forced
on us, not a design goal, and this document is the reference for changing it.

The short version: geography barely moves across the sagas, but **who holds
what** changes constantly, and **which places exist** changes across eight
thousand years. A map that ignores time will misdate about a third of what it
shows.

---

## 1. The published works, and what each one contributes

### The main novels — *A Song of Ice and Fire*

| # | Title | Published | Coverage |
|---|-------|-----------|----------|
| 1 | *A Game of Thrones* | 1996 | Winterfell, the kingsroad, King's Landing, the Wall, the Dothraki sea |
| 2 | *A Clash of Kings* | 1998 | War of the Five Kings; Renly's and Stannis's camps; Qarth |
| 3 | *A Storm of Swords* | 2000 | Riverlands campaign, the Twins, Slaver's Bay |
| 4 | *A Feast for Crows* | 2005 | Dorne, the Iron Islands, Oldtown, Braavos |
| 5 | *A Dance with Dragons* | 2011 | Meereen, the road east, the North under the Boltons |
| 6 | *The Winds of Winter* | unpublished | — |
| 7 | *A Dream of Spring* | unpublished | — |

The novels are the primary canon and the reason most of the gazetteer exists.
Their span is short — roughly **298–300 AC** — so for mapping purposes the five
published novels are effectively one instant in time.

### The histories

- ***Fire & Blood*** (2018) — the Targaryen dynasty from Aegon's Conquest
  (1 AC) to the Regency (roughly 136 AC), written as a maester's history. This
  is the source for the Dance of the Dragons and therefore for *House of the
  Dragon*.
- ***The World of Ice & Fire*** (2014) — a world encyclopaedia covering the Dawn
  Age, the Long Night, the Andal invasion, Valyria, and the regions of Essos and
  Sothoryos. Most of the deep-time history in the place panels traces back here.
- ***The Rise of the Dragon*** (2022) — an illustrated retelling of the same
  Targaryen history; adds little new geography.

### The Dunk and Egg novellas — *A Knight of the Seven Kingdoms*

*The Hedge Knight* (1998), *The Sworn Sword* (2003) and *The Mystery Knight*
(2010), collected as *A Knight of the Seven Kingdoms* (2015). Set around
**209–212 AC**, roughly ninety years before the novels and ninety years after
the Dance. Ser Duncan the Tall and "Egg" travel the Reach and the riverlands on
foot and by mule, which makes these novellas unusually valuable to this project:
they are the closest thing in the canon to a travelogue with **stated travel
times over known roads**, and they are the best future source of routing
anchors.

### The screen adaptations

| Series | Aired | In-world period | Adapts |
|--------|-------|-----------------|--------|
| *Game of Thrones* | 2011–2019 | ~298–305 AC | The novels, then beyond them |
| *House of the Dragon* | 2022– | ~101–130 AC | *Fire & Blood* — the Dance of the Dragons |
| *A Knight of the Seven Kingdoms* | 2025– | ~209 AC | The Dunk and Egg novellas |

The screen canon diverges from the books in detail (and, after season five of
*Game of Thrones*, in substance). The pipeline keeps the two apart rather than
merging them: a place panel shows book history first and screen history in a
separate **On screen** section, so you can always tell which canon you are
reading.

---

## 2. The eras a time-aware atlas would need

Ordered from deep past to present. The "map impact" column is what actually
changes on screen.

| Era | Dates | Map impact |
|-----|-------|------------|
| **Dawn Age / Age of Heroes** | ~12,000–6,000 BC | No Wall, no Andal castles. The Children of the Forest hold the continent. Almost nothing in our gazetteer exists yet. |
| **The Long Night** | ~8,000 BC | The Wall is raised; the Night's Watch founded; Winterfell built by Brandon the Builder. |
| **Andal invasion** | ~6,000–4,000 BC | The Vale, Riverlands, Reach and Westerlands take the shape we know. Most castles date from here. |
| **Valyrian Freehold** | to 102 BC | Essos is the interesting continent: Valyria intact, its roads and colonies (Volantis, Lys, Myr) founded. |
| **The Doom of Valyria** | 102 BC | Valyria shatters into the Smoking Sea. The single largest permanent change to the world map. |
| **Aegon's Conquest** | 1 AC | Harrenhal burned, King's Landing founded, the Seven Kingdoms unified. **Six of seven realms change hands at once.** |
| **The Dance of the Dragons** | 129–131 AC | *House of the Dragon*. Realm splits Green/Black — a political map that cuts across the usual regional borders. |
| **Dunk and Egg** | 209–212 AC | *A Knight of the Seven Kingdoms*. Ashford, Whitewalls, Standfast. Blackfyre rebellions. |
| **Robert's Rebellion** | 282–283 AC | Targaryen → Baratheon. The Trident, Storm's End, the Tower of Joy. |
| **The novels / *Game of Thrones*** | 298–305 AC | Our current snapshot. The War of the Five Kings redraws holdings yearly. |

---

## 3. What this means for the data — and the known problem

The source GIS data carries **one** political layer: eleven regions with a
single `claimedby` field each. Inspect it and the era is ambiguous:

| Region | claimedby |
|--------|-----------|
| The North | Stark |
| The Vale | Arryn |
| Riverlands | Tully |
| The Iron Islands | Greyjoy |
| The Westerlands | Lannister |
| The Reach | Tyrell |
| Stormlands | Baratheon |
| Dorne | Martell |
| Crownsland | **Targaryen** |
| The Gift | Night's Watch |
| — (beyond the Wall) | Wildlings |

Everything says 298 AC except the crownlands, which say Targaryen — a holding
that ended in 283 AC. **This is why King's Landing currently reports "held by
House Targaryen" in the app.** It is faithfully reporting the source data, and
the source data is internally inconsistent.

There are two honest fixes, and they are different projects:

1. **Cheap:** patch the crownlands to Baratheon in `data/custom/`, and label the
   map explicitly as "circa 298 AC". One line of data, no code.
2. **Right:** make the political layer time-aware — give each region a list of
   `{from, to, house}` intervals and add an era slider to the UI. Every other
   layer (coastlines, rivers, mountains) is genuinely timeless and needs no
   change; only `political`, and the `existsFrom`/`ruinedFrom` fields on places,
   would gain a time dimension.

Option 2 is the interesting version of this project and is the headline item in
`06-roadmap.md`. Note what it buys: Harrenhal whole before 1 AC and a ruin
after; Valyria intact before the Doom; the Dance's Green/Black split as a real
map rather than a diagram; and Dunk and Egg's Westeros with the Blackfyre
holdings marked.

---

## 4. Where the story actually happens

Useful for prioritising which places deserve hand-written enrichment beyond what
the wikis give us. Roughly ranked by page-time across the five published novels:

1. **King's Landing** — the political centre; the Red Keep, the Great Sept, Flea Bottom
2. **Winterfell and the kingsroad** — the spine of the North, and our best-attested road
3. **The Wall and beyond** — Castle Black, the Haunted Forest, the Frostfangs
4. **The riverlands** — Riverrun, the Twins, Harrenhal; the war's grinding ground
5. **Slaver's Bay** — Astapor, Yunkai, Meereen; Daenerys's arc from *ASOS* on
6. **The Free Cities** — Pentos, Braavos, Volantis
7. **Dorne and the Reach** — Sunspear, Oldtown, Highgarden; opens up in *AFFC*
8. **The Iron Islands** — Pyke, Lordsport; *AFFC* onward

The gazetteer's `size` field (1–5) roughly tracks this already, which is why it
drives both label priority and marker size in the app.

---

## 5. Sources for this document

Facts here come from the published novels and companion volumes listed above,
cross-checked against [A Wiki of Ice and Fire](https://awoiaf.westeros.org/)
(CC BY-SA). Dates in the Westerosi calendar (AC = After the Conquest, BC =
Before the Conquest) follow the wiki's reconciliation of the sources; George R.
R. Martin has never published an authoritative chronology, and dates before
Aegon's Conquest are explicitly in-world guesswork by maesters.
