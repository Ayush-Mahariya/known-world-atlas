#!/usr/bin/env python3
"""Build the gazetteer: one enriched record per named place in the world.

Joins each point location against the political, region, landscape and continent
polygons so the UI can answer "where is this, who claims it, what is around it"
without any runtime spatial work.

Also emits realms.json: one label anchor and colour per political region, for
the realm overlay.

Input : data/processed/layers/*.geojson
Output: data/processed/gazetteer.json, data/processed/realms.json
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    PROCESSED,
    ROOT,
    bbox_of,
    miles_between,
    miles_per_degree,
    polygon_contains,
    slugify,
    write_json,
)

LAYERS = PROCESSED / "layers"

# The Islands layer spells Sothoryos two ways.
ISLAND_CONTINENT_FIX = {"Sothyrios": "Sothoryos"}

# Coastal cities sometimes sit a hair outside the continent polygon (the
# coastline is drawn from a hand-traced map). Anything within this many miles of
# a continent's outline is assigned to it rather than left unplaced.
COAST_SNAP_MILES = 120.0


def load(name: str) -> list[dict]:
    return json.loads((LAYERS / f"{name}.geojson").read_text())["features"]


def load_custom_places() -> list[dict]:
    """Canonical places the source shapefiles omit (Casterly Rock, Bear Island...).

    Shaped like locations.geojson features so the rest of the join is unchanged.
    """
    path = ROOT / "data" / "custom" / "places.json"
    if not path.exists():
        return []
    entries = json.loads(path.read_text()).get("places", [])
    out = []
    for i, e in enumerate(entries):
        out.append({
            "type": "Feature",
            "properties": {
                "name": e["name"],
                "type": e.get("type", "Other"),
                "size": e.get("size", 3),
                "confirmed": 1 if e.get("confirmed", True) else 0,
                "layer": "locations",
                "fid": f"custom-{i}",
                "source": "custom",
                "positioning": e.get("positioning"),
            },
            "geometry": {"type": "Point", "coordinates": [e["lon"], e["lat"]]},
        })
    print(f"  + {len(out)} custom places patched in")
    return out


class PolygonIndex:
    """Tiny bbox-prefiltered point-in-polygon index."""

    def __init__(self, features: list[dict]):
        self.entries = [(bbox_of(f["geometry"]), f) for f in features]

    def find(self, pt: tuple[float, float]) -> dict | None:
        lon, lat = pt
        for (minx, miny, maxx, maxy), feat in self.entries:
            if minx <= lon <= maxx and miny <= lat <= maxy:
                if polygon_contains(feat["geometry"], pt):
                    return feat
        return None

    def find_all(self, pt: tuple[float, float]) -> list[dict]:
        lon, lat = pt
        hits = []
        for (minx, miny, maxx, maxy), feat in self.entries:
            if minx <= lon <= maxx and miny <= lat <= maxy:
                if polygon_contains(feat["geometry"], pt):
                    hits.append(feat)
        return hits


def _iter_coords(geometry: dict):
    def walk(c):
        if c and isinstance(c[0], (int, float)):
            yield c
        else:
            for sub in c:
                yield from walk(sub)

    yield from walk(geometry["coordinates"])


def nearest_feature_miles(pt: tuple[float, float], features: list[dict], mpd: float):
    """Distance to the closest vertex of the closest feature, in miles."""
    best_d, best_f = float("inf"), None
    for feat in features:
        for c in _iter_coords(feat["geometry"]):
            d = miles_between(pt, (c[0], c[1]), mpd)
            if d < best_d:
                best_d, best_f = d, feat
    return best_d, best_f


def label_anchor(geometry: dict) -> tuple[float, float]:
    """A point well inside the polygon — its pole of inaccessibility, roughly.

    A centroid is no good for realms like Dorne or the Vale: they are concave
    enough that the average of their vertices can land in the sea. Instead we
    grid-search for the interior point furthest from any edge, then refine once
    around the winner.
    """
    minx, miny, maxx, maxy = bbox_of(geometry)
    rings: list[list[list[float]]] = []
    polys = (geometry["coordinates"] if geometry["type"] == "MultiPolygon"
             else [geometry["coordinates"]])
    for poly in polys:
        rings.extend(poly)

    def clearance(pt: tuple[float, float]) -> float:
        if not polygon_contains(geometry, pt):
            return -1.0
        best = float("inf")
        for ring in rings:
            for c in ring:
                d = (c[0] - pt[0]) ** 2 + (c[1] - pt[1]) ** 2
                if d < best:
                    best = d
        return best

    def search(x0, y0, x1, y1, steps):
        best_pt, best_score = ((x0 + x1) / 2, (y0 + y1) / 2), -1.0
        for i in range(steps + 1):
            for j in range(steps + 1):
                pt = (x0 + (x1 - x0) * i / steps, y0 + (y1 - y0) * j / steps)
                score = clearance(pt)
                if score > best_score:
                    best_pt, best_score = pt, score
        return best_pt, best_score

    coarse, score = search(minx, miny, maxx, maxy, 40)
    if score < 0:
        return ((minx + maxx) / 2, (miny + maxy) / 2)
    span_x = (maxx - minx) / 40
    span_y = (maxy - miny) / 40
    fine, _ = search(coarse[0] - span_x, coarse[1] - span_y,
                     coarse[0] + span_x, coarse[1] + span_y, 10)
    return fine


def hsl_to_hex(h: float, s: float, l: float) -> str:
    """h in degrees, s/l in 0..1."""
    c = (1 - abs(2 * l - 1)) * s
    x = c * (1 - abs((h / 60.0) % 2 - 1))
    m = l - c / 2
    seg = int(h // 60) % 6
    rgb = [(c, x, 0), (x, c, 0), (0, c, x), (0, x, c), (x, 0, c), (c, 0, x)][seg]
    return "#" + "".join(f"{int(round((v + m) * 255)):02x}" for v in rgb)


def build_realms(political: list[dict]) -> list[dict]:
    """Label anchors plus a rainbow palette spread north to south."""
    realms = []
    for feat in political:
        source_name = (feat["properties"].get("name") or "").strip()
        # the one unnamed polygon is the land beyond the Wall
        name = source_name or "Beyond the Wall"
        lon, lat = label_anchor(feat["geometry"])
        minx, miny, maxx, maxy = bbox_of(feat["geometry"])
        realms.append({
            "name": name,
            # the app scales each label to fit its realm's on-screen width, so a
            # small realm gets small type instead of overrunning its neighbours
            "bbox": [round(minx, 4), round(miny, 4), round(maxx, 4), round(maxy, 4)],
            # exact value of the source `name` field, so the map style can match
            # on it — including the empty string
            "sourceName": source_name,
            "claimedBy": feat["properties"].get("claimedby"),
            "lon": round(lon, 5),
            "lat": round(lat, 5),
            "slug": slugify(name),
        })

    # Rainbow ordered by latitude, so the spectrum sweeps down the continent
    # rather than jumping about at random.
    realms.sort(key=lambda r: -r["lat"])
    n = len(realms)
    for i, realm in enumerate(realms):
        hue = 300.0 * i / max(1, n - 1)
        realm["hue"] = round(hue, 1)
        realm["colour"] = hsl_to_hex(hue, 0.62, 0.48)
        realm["labelColour"] = hsl_to_hex(hue, 0.72, 0.30)
    return realms


def main() -> None:
    mpd = miles_per_degree()

    locations = load("locations")
    locations += load_custom_places()
    continent_features = load("continents")
    continents = PolygonIndex(continent_features)
    political_features = load("political")
    political = PolygonIndex(political_features)
    regions = PolygonIndex(load("regions"))
    landscape = PolygonIndex(load("landscape"))
    islands = PolygonIndex(load("islands"))
    roads = load("roads")

    seen_slugs: Counter[str] = Counter()
    gazetteer = []

    for feat in locations:
        props = feat["properties"]
        name = props.get("name")
        if not name:
            continue
        lon, lat = feat["geometry"]["coordinates"][:2]
        pt = (lon, lat)

        slug = slugify(name)
        seen_slugs[slug] += 1
        if seen_slugs[slug] > 1:  # duplicate place names do exist (e.g. ruins)
            slug = f"{slug}-{seen_slugs[slug]}"

        cont = continents.find(pt)
        island = islands.find(pt)
        continent = cont["properties"]["name"] if cont else None
        placement = "polygon" if continent else None
        if not continent and island:
            raw = island["properties"].get("continent")
            continent = ISLAND_CONTINENT_FIX.get(raw, raw)
            placement = "island"
        if not continent:
            # coastal city just outside the traced outline — snap to the nearest
            near_d, near_f = nearest_feature_miles(pt, continent_features, mpd)
            if near_d <= COAST_SNAP_MILES:
                continent = near_f["properties"]["name"]
                placement = "coast-snap"

        pol = political.find(pt)
        region_hits = regions.find_all(pt)
        land_hits = landscape.find_all(pt)
        road_dist, road_feat = nearest_feature_miles(pt, roads, mpd)

        gazetteer.append(
            {
                "slug": slug,
                "name": name,
                "type": props.get("type") or "Other",
                # size 1..5 in the source data; drives label priority and icon size
                "size": props.get("size") or 1,
                "confirmed": bool(props.get("confirmed")),
                "source": props.get("source") or "shapefile",
                "lon": round(lon, 6),
                "lat": round(lat, 6),
                "continent": continent,
                "continentSource": placement,
                "island": island["properties"].get("name") if island else None,
                "politicalRegion": pol["properties"].get("name") if pol else None,
                "claimedBy": pol["properties"].get("claimedby") if pol else None,
                "regions": sorted(
                    {r["properties"]["name"] for r in region_hits if r["properties"].get("name")}
                ),
                "terrain": sorted({l["properties"].get("type") for l in land_hits if l["properties"].get("type")}),
                "nearestRoad": (road_feat["properties"]["name"] if road_feat else None),
                "milesToRoad": round(road_dist, 1),
            }
        )

    gazetteer.sort(key=lambda p: (-p["size"], p["name"]))
    write_json(PROCESSED / "gazetteer.json", gazetteer, compact=False)

    realms = build_realms(political_features)
    write_json(PROCESSED / "realms.json", realms, compact=False)
    print(f"  {len(realms)} realms with label anchors:")
    for r in realms:
        held = f"House {r['claimedBy']}" if r["claimedBy"] else "—"
        print(f"    {r['colour']}  {r['name']:20} {held}")

    by_type = Counter(p["type"] for p in gazetteer)
    by_cont = Counter(p["continent"] or "unplaced" for p in gazetteer)
    print(f"  {len(gazetteer)} places")
    print("  by type     :", dict(by_type.most_common()))
    print("  by continent:", dict(by_cont.most_common()))
    print(f"  on/near a road (<15mi): {sum(1 for p in gazetteer if p['milesToRoad'] < 15)}")


if __name__ == "__main__":
    main()
