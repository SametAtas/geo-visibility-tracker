"""Fact-check an AI-generated comparison table, cell by cell, against its cited sources.

Comparison tables (clinics, products, services) are a popular GEO content format because AI engines
quote structured facts. If a model filled the table, every cell needs a source that really says it.
Each cell is classified:

  supported          evidence found on the source page, and the value's numbers appear there
  weak               evidence found only approximately (fuzzy match); a human should look
  value_not_in_source  the page was found but the value's numbers are not on it (typical hallucination)
  evidence_not_found the quoted evidence is not on the page
  no_source          the cell cites nothing
  marked_unknown     the cell honestly says "not mentioned"; fine, but counted
  unreachable        the source could not be fetched
"""
from __future__ import annotations

import json
import re
import time
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx

from .textnorm import jaccard, norm, strip_html
from .wordpress import USER_AGENT

UNKNOWN_RE = re.compile(r"未明確|未提及|未公開|不明|not (mentioned|specified|listed)|n/?a", re.I)
NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


@dataclass
class CellResult:
    entity: str
    attribute: str
    value: str
    source_url: str
    status: str
    detail: str = ""


def _numbers(s: str) -> list[str]:
    return [n.replace(",", "") for n in NUM_RE.findall(norm(s))]


def _find_evidence(evidence: str, page: str) -> tuple[str, float]:
    ev, pg = norm(evidence), norm(page)
    if not ev:
        return "none", 0.0
    if ev in pg:
        return "exact", 1.0
    width, step = len(ev), max(1, len(ev) // 4)
    best = max((jaccard(ev, pg[i:i + width]) for i in range(0, max(1, len(pg) - width + 1), step)), default=0.0)
    return ("fuzzy" if best >= 0.55 else "missing"), best


class PageCache:
    """Fetch each source once, politely; keep the text in memory."""

    def __init__(self, delay: float = 1.0, client: httpx.Client | None = None):
        self.delay, self.pages = delay, {}
        self.client = client or httpx.Client(timeout=20, headers={"User-Agent": USER_AGENT}, follow_redirects=True)
        self._last = 0.0

    def text(self, url: str) -> str | None:
        if url not in self.pages:
            wait = self.delay - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            try:
                r = self.client.get(url)
                self.pages[url] = strip_html(r.text) if r.status_code == 200 else None
            except httpx.HTTPError:
                self.pages[url] = None
        return self.pages[url]


def check_cell(cell: dict, cache: PageCache) -> CellResult:
    base = dict(entity=cell.get("entity", ""), attribute=cell.get("attribute", ""),
                value=str(cell.get("value", "")), source_url=cell.get("source_url", "") or "")
    if UNKNOWN_RE.search(base["value"]):
        return CellResult(**base, status="marked_unknown")
    if not base["source_url"]:
        return CellResult(**base, status="no_source")
    page = cache.text(base["source_url"])
    if page is None:
        return CellResult(**base, status="unreachable")
    match, score = _find_evidence(cell.get("evidence", ""), page)
    if match in ("none", "missing"):
        return CellResult(**base, status="evidence_not_found", detail=f"best similarity {score:.2f}")
    page_numbers = set(_numbers(page))
    missing = [n for n in _numbers(base["value"]) if n not in page_numbers]
    if missing:
        return CellResult(**base, status="value_not_in_source", detail="numbers not on page: " + ", ".join(missing))
    return CellResult(**base, status="supported" if match == "exact" else "weak", detail=f"evidence {match} ({score:.2f})")


def check_table(table: dict, cache: PageCache | None = None) -> dict:
    cache = cache or PageCache()
    results = [check_cell(c, cache) for c in table.get("cells", [])]
    counts = Counter(r.status for r in results)
    checked = len(results) - counts["marked_unknown"]
    return {
        "title": table.get("title", ""),
        "cells": len(results),
        "counts": dict(counts),
        "supported_share": f"{counts['supported'] / checked:.0%}" if checked else "n/a",
        "needs_human": [asdict(r) for r in results if r.status not in ("supported", "marked_unknown")],
        "results": [asdict(r) for r in results],
    }


def load_table(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))
