#!/usr/bin/env python3
"""Enrich lore.json with book-canon articles from the A Wiki of Ice and Fire dump.

AWOIAF is the deepest ASOIAF reference but its live site sits behind Cloudflare
bot protection, so we read the community XML dump archived at
https://archive.org/details/wiki-awoiafwesterosorg instead (CC BY-SA).

The dump is the full revision history (~1 GB of XML), so it is streamed straight
out of 7-Zip and parsed incrementally — never extracted to disk. Only the latest
revision of pages we actually want is kept.

Input : data/raw/awoiaf-dump.7z, data/processed/gazetteer.json, lore.json
Output: data/lore/awoiaf/*.json, updated data/processed/lore.json
"""
from __future__ import annotations

import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import LORE, PROCESSED, RAW, write_json  # noqa: E402
from wikitext import first_paragraphs, split_sections  # noqa: E402

DUMP = RAW / "awoiaf-dump.7z"
WIKI_LABEL = "A Wiki of Ice and Fire"
WIKI_BASE = "https://awoiaf.westeros.org/index.php/"


def localname(tag: str) -> str:
    """MediaWiki export namespaces vary by version (0.9, 0.10, ...) — ignore them."""
    return tag.rsplit("}", 1)[-1]

HISTORY_HEADINGS = ["history", "recent events", "background", "legends", "recent history"]
DESCRIPTION_HEADINGS = ["description", "geography", "layout", "the castle", "overview"]


def wanted_titles(gazetteer: list[dict]) -> dict[str, str]:
    """Map lookup-key -> slug. Keys are lowercased titles plus a few aliases."""
    out: dict[str, str] = {}
    for p in gazetteer:
        name = p["name"]
        for key in {name.lower(), name.lower().replace("the ", "", 1)}:
            out.setdefault(key, p["slug"])
    return out


def stream_pages(dump: Path):
    """Yield (title, latest_text) for every page in the 7z-compressed dump."""
    proc = subprocess.Popen(
        ["7z", "x", "-so", str(dump), "*.xml"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    title: str | None = None
    latest: str | None = None
    try:
        for event, elem in ET.iterparse(proc.stdout, events=("end",)):
            tag = localname(elem.tag)
            if tag == "title":
                title = elem.text
            elif tag == "text":
                # revisions appear in chronological order; last one wins
                latest = elem.text
                elem.clear()
            elif tag == "page":
                if title and latest:
                    yield title, latest
                title = latest = None
                elem.clear()
    finally:
        proc.stdout.close()
        proc.wait()


def extract(title: str, content: str) -> dict:
    lead, sections = split_sections(content)
    by_title = {s["title"].strip().lower(): s["text"] for s in sections}

    def pick(candidates):
        for c in candidates:
            if c in by_title and len(by_title[c]) > 40:
                return by_title[c]
        return None

    history = pick(HISTORY_HEADINGS)
    if not history:
        long_bits = [s["text"] for s in sections
                     if s["level"] <= 3 and len(s["text"]) > 200
                     and s["title"].strip().lower() not in DESCRIPTION_HEADINGS]
        history = "\n\n".join(long_bits[:4]) or None

    return {
        "title": title,
        "wiki": WIKI_LABEL,
        "canon": "books",
        "url": WIKI_BASE + title.replace(" ", "_"),
        "summary": first_paragraphs(lead, 2) or None,
        "description": pick(DESCRIPTION_HEADINGS),
        "history": history,
        "sections": [s["title"] for s in sections],
        "license": "CC BY-SA",
        "dump": "awoiafwesterosorg-20150709",
    }


def main() -> None:
    if not DUMP.exists():
        sys.exit(f"missing {DUMP} — run scripts/fetch_sources.sh")

    gazetteer = json.loads((PROCESSED / "gazetteer.json").read_text())
    lore = {m["slug"]: m for m in json.loads((PROCESSED / "lore.json").read_text())}
    wanted = wanted_titles(gazetteer)

    found: dict[str, dict] = {}
    scanned = 0
    for title, content in stream_pages(DUMP):
        scanned += 1
        if scanned % 20000 == 0:
            print(f"    scanned {scanned:,} pages, matched {len(found)}")
        slug = wanted.get((title or "").lower())
        if not slug or slug in found:
            continue
        if content.strip().lower().startswith("#redirect"):
            continue
        record = extract(title, content)
        found[slug] = record
        write_json(LORE / "awoiaf" / f"{slug}.json", record, compact=False)

    print(f"    scanned {scanned:,} pages, matched {len(found)}")

    # AWOIAF is book canon and the deepest source: it becomes primary where present.
    gained_lore = gained_hist = 0
    for slug, record in found.items():
        entry = lore.get(slug)
        if not entry:
            continue
        if not entry.get("hasLore"):
            gained_lore += 1
        if record.get("history") and not entry.get("history"):
            gained_hist += 1
        entry["hasLore"] = True
        entry["summary"] = record.get("summary") or entry.get("summary")
        entry["description"] = record.get("description") or entry.get("description")
        entry["history"] = record.get("history") or entry.get("history")
        srcs = [s for s in entry.get("sources", []) if s["wiki"] != WIKI_LABEL]
        entry["sources"] = [{
            "wiki": WIKI_LABEL, "title": record["title"], "url": record["url"],
            "canon": "books", "license": "CC BY-SA",
        }] + srcs

    merged = [lore[p["slug"]] for p in gazetteer]
    write_json(PROCESSED / "lore.json", merged, compact=False)

    with_lore = sum(1 for m in merged if m.get("hasLore"))
    with_hist = sum(1 for m in merged if m.get("history"))
    print(f"\n  AWOIAF added {gained_lore} new articles and {gained_hist} new histories")
    print(f"  {with_lore}/{len(merged)} places have an article")
    print(f"  {with_hist}/{len(merged)} places have a history section")


if __name__ == "__main__":
    main()
