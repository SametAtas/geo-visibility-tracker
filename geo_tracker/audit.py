"""GEO content audit: per post, the signals that research links to visibility in AI answers.

Aggarwal et al., "GEO: Generative Engine Optimization" (KDD 2024) found that adding cited sources,
statistics and quotations raised visibility in generative engine answers by up to about 40%,
while keyword stuffing did not help. This module counts those signals; it does not judge quality.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from .textnorm import host_of, strip_html

# A number with a unit. Years such as "2025 年" are dates, not statistics, so they are excluded.
STAT_RE = re.compile(r"(?<![\d.])(?!(?:19|20)\d\d\s*年)\d[\d,]*(?:\.\d+)?\s*(?:%|％|萬|億|倍|元|美元|人|次|年)")
FAQ_RE = re.compile(r"FAQ|常見問題|Q\s*&\s*A", re.I)
HREF_RE = re.compile(r"""href=["'](https?://[^"']+)["']""", re.I)
HEAD_RE = re.compile(r"<h[23][^>]*>([\s\S]*?)</h[23]>", re.I)


@dataclass
class PostSignals:
    id: int
    title: str
    link: str
    chars: int                 # Chinese has no spaces: count characters, not words
    headings: int
    has_faq: bool
    external_sources: int      # distinct external domains linked
    statistics: int
    quotes: int
    tables: int
    days_since_update: int


def post_signals(post: dict, own_domain: str, now: datetime | None = None) -> PostSignals:
    now = now or datetime.now(timezone.utc)
    html = (post.get("content") or {}).get("rendered", "")
    text = strip_html(html)
    headings = [strip_html(h) for h in HEAD_RE.findall(html)]
    own = own_domain.lower().removeprefix("www.")
    hosts = {h for h in (host_of(u) for u in HREF_RE.findall(html)) if h and not (h == own or h.endswith("." + own))}
    # modified_gmt is UTC; "modified" is the site's local time (8 hours off for a Taiwanese blog)
    modified = datetime.fromisoformat(post.get("modified_gmt") or post["modified"]).replace(tzinfo=timezone.utc)
    return PostSignals(
        id=post["id"],
        title=strip_html((post.get("title") or {}).get("rendered", "")),
        link=post.get("link", ""),
        chars=len(re.sub(r"\s", "", text)),
        headings=len(headings),
        has_faq=any(FAQ_RE.search(h) for h in headings),
        external_sources=len(hosts),
        statistics=len(STAT_RE.findall(text)),
        quotes=len(re.findall(r"<blockquote", html, re.I)) + text.count("「"),
        tables=len(re.findall(r"<table", html, re.I)),
        days_since_update=(now - modified).days,
    )


def summarize(rows: list[PostSignals]) -> dict:
    n = len(rows)
    if not n:
        return {"posts": 0}

    def pct(cond: Callable[[PostSignals], bool]) -> str:
        return f"{sum(1 for r in rows if cond(r)) / n:.0%}"

    chars = sorted(r.chars for r in rows)
    return {
        "posts": n,
        "median_chars": chars[n // 2],
        "with_any_external_source": pct(lambda r: r.external_sources > 0),
        "with_3plus_statistics": pct(lambda r: r.statistics >= 3),
        "with_quotes": pct(lambda r: r.quotes > 0),
        "with_faq_section": pct(lambda r: r.has_faq),
        "updated_in_last_180_days": pct(lambda r: r.days_since_update <= 180),
    }


def as_dicts(rows: list[PostSignals]) -> list[dict]:
    return [asdict(r) for r in rows]
