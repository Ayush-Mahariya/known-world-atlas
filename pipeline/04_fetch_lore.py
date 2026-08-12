#!/usr/bin/env python3
"""Fetch the history of every place in the gazetteer from the ASOIAF wikis.

Sources (both MediaWiki, both CC BY-SA — see NOTICE.md for attribution):
  * iceandfire.fandom.com   — "A Song of Ice and Fire Wiki", book canon
  * gameofthrones.fandom.com — show canon (GoT, House of the Dragon)

A Wiki of Ice and Fire (awoiaf.westeros.org) is the richest source but sits
behind Cloudflare bot protection, so it is not scraped here. See
docs/02-data-sources.md for the offline-dump route if you want it.

Requests are batched 50 titles at a time, cached on disk, and resumable.

Input : data/processed/gazetteer.json
Output: data/processed/lore.json, data/lore/cache/<wiki>/*.json
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import LORE, PROCESSED, write_json  # noqa: E402
from wikitext import first_paragraphs, split_sections  # noqa: E402

USER_AGENT = (
    "KnownWorldAtlas/0.1 (personal fan mapping project; "
    "https://github.com/ayush/known-world-atlas)"
)

WIKIS = {
    "iceandfire": {
        "label": "A Song of Ice and Fire Wiki",
        "api": "https://iceandfire.fandom.com/api.php",
        "page": "https://iceandfire.fandom.com/wiki/",
        "canon": "books",
    },
    "gameofthrones": {
        "label": "Game of Thrones Wiki",
        "api": "https://gameofthrones.fandom.com/api.php",
        "page": "https://gameofthrones.fandom.com/wiki/",
        "canon": "screen",
    },
}

# Section headings that count as "history" for the place panel, in priority order.
HISTORY_HEADINGS = [
    "history", "recent events", "background", "recent history",
    "notable events", "events", "legends and history",
]
DESCRIPTION_HEADINGS = ["description", "geography", "layout", "the castle", "overview"]

BATCH = 50
DELAY_S = 0.4


def api_get(api: str, params: dict) -> dict:
    params = {**params, "format": "json", "formatversion": "2"}
    url = f"{api}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                               "Accept": "application/json"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            if attempt == 3:
                raise
            wait = 2 ** attempt
            print(f"    retry in {wait}s ({e})")
            time.sleep(wait)
    return {}


def fetch_batch(api: str, titles: list[str]) -> dict[str, dict]:
    """Return {requested_title: page}. Follows redirects and normalisation."""
    data = api_get(api, {
        "action": "query",
        "prop": "revisions",
        "rvprop": "content",
        "rvslots": "main",
        "redirects": "1",
        "titles": "|".join(titles),
    })
    q = data.get("query", {})
    # map every alias back to the final page title
    alias: dict[str, str] = {}
    for kind in ("normalized", "redirects"):
        for entry in q.get(kind, []):
            alias[entry["from"]] = entry["to"]

    def resolve(t: str) -> str:
        seen = set()
        while t in alias and t not in seen:
            seen.add(t)
            t = alias[t]
        return t

    pages = {p["title"]: p for p in q.get("pages", [])}
    out = {}
    for t in titles:
        page = pages.get(resolve(t))
        if page and not page.get("missing"):
            out[t] = page
    return out


def page_wikitext(page: dict) -> str | None:
    try:
        return page["revisions"][0]["slots"]["main"]["content"]
    except (KeyError, IndexError):
        return None


def extract(title: str, content: str) -> dict:
    lead, sections = split_sections(content)
    by_title = {s["title"].strip().lower(): s["text"] for s in sections}

    def pick(candidates: list[str]) -> str | None:
        for c in candidates:
            if c in by_title and len(by_title[c]) > 40:
                return by_title[c]
        return None

    history = pick(HISTORY_HEADINGS)
    if not history:
        # some articles put history in subsections only (e.g. "== Reign of X ==")
        long_bits = [s["text"] for s in sections
                     if s["level"] <= 3 and len(s["text"]) > 200
                     and s["title"].strip().lower() not in DESCRIPTION_HEADINGS]
        history = "\n\n".join(long_bits[:4]) or None

    return {
        "title": title,
        "summary": first_paragraphs(lead, 2) or None,
        "description": pick(DESCRIPTION_HEADINGS),
        "history": history,
        "sections": [s["title"] for s in sections],
    }


def cache_path(wiki_key: str, slug: str) -> Path:
    return LORE / "cache" / wiki_key / f"{slug}.json"


def main() -> None:
    force = "--force" in sys.argv
    gazetteer = json.loads((PROCESSED / "gazetteer.json").read_text())
    by_name = {p["name"]: p for p in gazetteer}
    print(f"  {len(gazetteer)} places to look up across {len(WIKIS)} wikis")

    results: dict[str, dict] = {p["slug"]: {"slug": p["slug"], "name": p["name"],
                                            "sources": {}} for p in gazetteer}

    for wiki_key, wiki in WIKIS.items():
        # The cache holds raw wikitext, so re-extraction never needs the network.
        raw: dict[str, dict] = {}
        pending: list[str] = []
        for place in gazetteer:
            cp = cache_path(wiki_key, place["slug"])
            if cp.exists() and not force:
                raw[place["slug"]] = json.loads(cp.read_text())
            else:
                pending.append(place["name"])

        print(f"\n  {wiki['label']}: {len(raw)} cached, {len(pending)} to fetch")
        for i in range(0, len(pending), BATCH):
            chunk = pending[i : i + BATCH]
            pages = fetch_batch(wiki["api"], chunk)
            for name in chunk:
                slug = by_name[name]["slug"]
                page = pages.get(name)
                content = page_wikitext(page) if page else None
                entry = {
                    "found": bool(content),
                    "title": page["title"] if page else name,
                    "wikitext": content,
                }
                raw[slug] = entry
                write_json(cache_path(wiki_key, slug), entry, compact=False)
            print(f"    [{i + len(chunk):>4}/{len(pending)}] {len(pages)}/{len(chunk)} found")
            time.sleep(DELAY_S)

        for slug, entry in raw.items():
            if not entry.get("found") or not entry.get("wikitext"):
                continue
            record = extract(entry["title"], entry["wikitext"])
            record["url"] = wiki["page"] + urllib.parse.quote(
                record["title"].replace(" ", "_"))
            record["wiki"] = wiki["label"]
            record["canon"] = wiki["canon"]
            results[slug]["sources"][wiki_key] = record

    # merge: prefer book canon for history, fall back to screen canon
    merged = []
    for place in gazetteer:
        r = results[place["slug"]]
        book = r["sources"].get("iceandfire")
        show = r["sources"].get("gameofthrones")
        primary = book or show
        if not primary:
            merged.append({"slug": place["slug"], "name": place["name"],
                           "hasLore": False, "sources": []})
            continue
        merged.append({
            "slug": place["slug"],
            "name": place["name"],
            "hasLore": True,
            "summary": (primary.get("summary") or (show or {}).get("summary")),
            "description": (primary.get("description") or (show or {}).get("description")),
            "history": (primary.get("history") or (show or {}).get("history")),
            "screenHistory": show.get("history") if (book and show) else None,
            "sources": [
                {"wiki": s["wiki"], "title": s["title"], "url": s["url"], "canon": s["canon"],
                 "license": "CC BY-SA"}
                for s in (book, show) if s
            ],
        })

    write_json(PROCESSED / "lore.json", merged, compact=False)
    with_lore = sum(1 for m in merged if m["hasLore"])
    with_hist = sum(1 for m in merged if m.get("history"))
    print(f"\n  {with_lore}/{len(merged)} places matched an article")
    print(f"  {with_hist}/{len(merged)} have a history section")
    print("  wrote data/processed/lore.json")


if __name__ == "__main__":
    main()
