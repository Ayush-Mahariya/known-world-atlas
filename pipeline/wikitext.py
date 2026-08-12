"""A small, dependency-free wikitext -> plain text converter.

Good enough for reading article prose out of MediaWiki dumps and API responses.
It is deliberately lossy: templates, infoboxes, files and references are dropped
rather than rendered, because we only want the narrative text.
"""
from __future__ import annotations

import re

_COMMENT = re.compile(r"<!--.*?-->", re.S)
_REF_PAIR = re.compile(r"<ref[^>/]*>.*?</ref>", re.S | re.I)
_REF_SELF = re.compile(r"<ref[^>]*/>", re.I)
_TAG = re.compile(r"</?(?:small|big|center|div|span|sup|sub|br|gallery|poem|blockquote)[^>]*>", re.I)
_DROP_LINK_PREFIX = re.compile(r"^\s*(?:File|Image|Category|Media)\s*:", re.I)
_HEADING = re.compile(r"^\s*(={2,6})\s*(.*?)\s*\1\s*$")
_BOLD_ITALIC = re.compile(r"'{2,5}")
_LIST_PREFIX = re.compile(r"^[*#:;]+\s*")
_TABLE = re.compile(r"^\s*(\{\||\|\}|\|[-+]|!|\|)")
_WS = re.compile(r"[ \t]+")
_BLANKS = re.compile(r"\n{3,}")


def _strip_braces(text: str) -> str:
    """Remove {{templates}} and {|tables|}, honouring nesting."""
    out: list[str] = []
    depth = 0
    i = 0
    n = len(text)
    while i < n:
        two = text[i : i + 2]
        if two in ("{{", "{|"):
            depth += 1
            i += 2
        elif two in ("}}", "|}") and depth:
            depth -= 1
            i += 2
        else:
            if not depth:
                out.append(text[i])
            i += 1
    return "".join(out)


def _resolve_links(text: str) -> str:
    """Resolve [[wiki links]] to their labels, dropping File/Image/Category ones.

    Written as a nesting-aware scan rather than a regex: image captions routinely
    contain their own [[links]], and a non-greedy regex leaves orphaned "]]"
    behind when it matches the inner pair first.
    """
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        if text.startswith("[[", i):
            depth, j = 1, i + 2
            while j < n and depth:
                if text.startswith("[[", j):
                    depth += 1
                    j += 2
                elif text.startswith("]]", j):
                    depth -= 1
                    j += 2
                else:
                    j += 1
            if depth:  # unterminated — emit literally and stop scanning
                out.append(text[i:])
                break
            inner = text[i + 2 : j - 2]
            if _DROP_LINK_PREFIX.match(inner):
                pass  # image/category: drop caption and all
            elif "|" in inner:
                target, _, label = inner.rpartition("|")
                out.append(_resolve_links(label) or target)
            else:
                out.append(inner)
            i = j
        else:
            out.append(text[i])
            i += 1
    text = "".join(out)
    # external links: [http://x label] -> label
    text = re.sub(r"\[(?:https?|//)\S+\s+([^\]]+)\]", r"\1", text)
    text = re.sub(r"\[(?:https?|//)\S+\]", "", text)
    return text


def clean(text: str) -> str:
    """Full wikitext -> plain text."""
    text = _COMMENT.sub("", text)
    text = _REF_PAIR.sub("", text)
    text = _REF_SELF.sub("", text)
    text = _strip_braces(text)
    text = _resolve_links(text)
    text = _TAG.sub("", text)
    text = _BOLD_ITALIC.sub("", text)

    lines = []
    for line in text.split("\n"):
        if _TABLE.match(line):
            continue
        line = _LIST_PREFIX.sub("", line)
        lines.append(_WS.sub(" ", line).strip())
    text = "\n".join(lines)
    return _BLANKS.sub("\n\n", text).strip()


def split_sections(wikitext: str) -> tuple[str, list[dict]]:
    """Split an article into (lead, [{level, title, text}, ...]).

    Text is returned already cleaned.
    """
    lead_lines: list[str] = []
    sections: list[dict] = []
    current: dict | None = None

    for line in wikitext.split("\n"):
        m = _HEADING.match(line)
        if m:
            if current:
                sections.append(current)
            current = {"level": len(m.group(1)), "title": clean(m.group(2)), "raw": []}
        elif current is not None:
            current["raw"].append(line)
        else:
            lead_lines.append(line)
    if current:
        sections.append(current)

    for s in sections:
        s["text"] = clean("\n".join(s.pop("raw")))
    return clean("\n".join(lead_lines)), [s for s in sections if s["text"]]


def first_paragraphs(text: str, limit: int = 2) -> str:
    paras = [p for p in text.split("\n\n") if p.strip()]
    return "\n\n".join(paras[:limit])
