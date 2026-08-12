#!/usr/bin/env python3
"""Check the travel model against journeys the books give us a duration for.

This is the honesty check on the whole pipeline. If the grid, the scale and the
cost model are right, riding the kingsroad from King's Landing to Winterfell
should take about a month and a half, not a week and not a season.

Two sections, deliberately kept apart:
  CHECKS   — assertions about our model. A failure here is our bug.
  CAVEATS  — places where the *source map* disagrees with the books. Reported
             every run so they stay visible, but they do not fail the build.

Run: ./.venv/bin/python pipeline/07_validate_routing.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import PROCESSED, write_json  # noqa: E402
from travel import MODES, TerrainGrid, route  # noqa: E402

# (from, to, mode, low days, high days, why)
CHECKS = [
    ("King's Landing", "Winterfell", "horse", 30, 55,
     "the length of the kingsroad; a month and a half for a mounted party"),
    ("King's Landing", "Winterfell", "carriage", 55, 110,
     "the royal progress, held to a crawl by Robert's wheelhouse"),
    ("Winterfell", "Castle Black", "horse", 12, 25,
     "~600 miles up the kingsroad"),
    ("King's Landing", "Oldtown", "horse", 22, 45,
     "~1,000 miles down the roseroad"),
    ("King's Landing", "Storm's End", "horse", 8, 20, "~400 miles"),
    ("King's Landing", "Riverrun", "horse", 12, 30, "up the river road"),
    ("King's Landing", "Casterly Rock", "horse", 15, 35, "down the goldroad"),
    ("Dragonstone", "Winterfell", "dragon", 2, 6,
     "the length of Westeros on the wing"),
    ("King's Landing", "Braavos", "ship", 5, 20, "across the narrow sea"),
    ("King's Landing", "Winterfell", "foot", 55, 100, "the same road, walking"),
]

# Journeys where the map itself is the problem, not the model.
CAVEATS = [
    ("King's Landing", "Dragonstone", "dragon",
     "The books put Dragonstone a short sail from King's Landing. This map "
     "places it far out in Blackwater Bay, so every route to it reads long."),
]

# (from, to, mode, should a route exist?)
CONNECTIVITY = [
    ("King's Landing", "Sunspear", "horse", True),
    ("Winterfell", "The Eyrie", "horse", True),
    ("Pentos", "Vaes Dothrak", "horse", True),
    ("Oldtown", "Braavos", "ship", True),
    # Pyke is on the Iron Islands: no land route should exist, and the app is
    # expected to fall back to ship or dragon when a mode strands the traveller.
    ("Winterfell", "Pyke", "horse", False),
    ("Winterfell", "Pyke", "dragon", True),
    # Winterfell is inland — you cannot sail from it, but White Harbor is the
    # North's port and reaches the Iron Islands the long way round Westeros.
    ("Winterfell", "Pyke", "ship", False),
    ("White Harbor", "Pyke", "ship", True),
    ("Lannisport", "Pyke", "ship", True),
]


def main() -> None:
    grid = TerrainGrid.load(PROCESSED)
    places = {p["name"]: (p["lon"], p["lat"])
              for p in json.loads((PROCESSED / "gazetteer.json").read_text())}

    print(f"  grid {grid.width}x{grid.height} @ {grid.cell} deg, "
          f"{grid.mpd:.2f} miles/degree")
    print(f"  modes: " + ", ".join(f"{m.key} {m.miles_per_day:g}mi/day"
                                   for m in MODES.values()) + "\n")

    def run(a, b, mode_key):
        """-> (result, error_message). result is None when no route exists."""
        if a not in places or b not in places:
            return None, f"{a} or {b} not in gazetteer"
        r = route(grid, MODES[mode_key], places[a], places[b])
        if r and r.get("error"):
            return None, r["message"]
        return r, None if r else "no route found"

    failures = []
    # Full-precision results, consumed by the TypeScript parity test so the two
    # implementations are compared against generated numbers rather than
    # hand-copied ones.
    fixtures: list[dict] = []

    print(f"  CHECKS")
    print(f"  {'journey':42}{'mode':10}{'miles':>7}{'days':>7}  expected")
    for a, b, mode_key, lo, hi, _why in CHECKS:
        r, err = run(a, b, mode_key)
        label = f"{a} -> {b}"
        if err:
            print(f"  {label:42}{mode_key:10}{'—':>7}{'—':>7}  {err.upper()}")
            failures.append(f"{label} ({mode_key}): {err}")
            continue
        ok = lo <= r["days"] <= hi
        print(f"  {label:42}{mode_key:10}{r['miles']:7.0f}{r['days']:7.1f}  "
              f"{lo}-{hi} {'ok' if ok else '<-- OUT OF RANGE'}")
        if not ok:
            failures.append(f"{label} ({mode_key}): {r['days']:.1f} days, "
                            f"expected {lo}-{hi}")
        fixtures.append({
            "from": a, "to": b, "mode": mode_key,
            "miles": r["miles"], "days": r["days"],
            "pathPoints": len(r["path"]), "straightLine": r["straightLine"],
        })

    print(f"\n  CAVEATS (source map vs books — reported, not failed)")
    for a, b, mode_key, why in CAVEATS:
        r, err = run(a, b, mode_key)
        got = f"{r['miles']:.0f} mi / {r['days']:.1f} days" if r else (err or "—")
        print(f"  {a} -> {b} ({mode_key}): {got}")
        print(f"      {why}")

    print(f"\n  CONNECTIVITY")
    for a, b, mode_key, should_reach in CONNECTIVITY:
        r, err = run(a, b, mode_key)
        label = f"{a} -> {b} ({mode_key})"
        if r and should_reach:
            print(f"  {label}: {r['miles']:.0f} mi, {r['days']:.1f} days")
        elif not r and not should_reach:
            print(f"  {label}: unreachable, as expected")
        elif r and not should_reach:
            print(f"  {label}: reachable but should NOT be")
            failures.append(f"{label}: found a route where none should exist")
        else:
            print(f"  {label}: {(err or 'unreachable').upper()}")
            failures.append(f"{label}: {err or 'unreachable'}")

    blocked = [{"from": a, "to": b, "mode": m}
               for a, b, m, should in CONNECTIVITY if not should]
    write_json(PROCESSED / "route-fixtures.json",
               {"generatedBy": "pipeline/07_validate_routing.py",
                "note": "Reference results for web/src/lib/router.parity.ts. "
                        "Regenerate whenever the cost model or grid changes.",
                "routes": fixtures, "blocked": blocked},
               compact=False)
    print(f"\n  wrote {len(fixtures)} reference routes to "
          f"data/processed/route-fixtures.json")

    if failures:
        print(f"\n  {len(failures)} failure(s):")
        for f in failures:
            print(f"    - {f}")
        sys.exit(1)
    print(f"\n  all {len(CHECKS)} checks and {len(CONNECTIVITY)} probes passed")


if __name__ == "__main__":
    main()
