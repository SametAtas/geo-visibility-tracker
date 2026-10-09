"""Turn one AI answer into structured facts: who is mentioned, who is cited, in what order.

A *mention* is the brand's name (or alias) appearing in the text.
A *citation* is a link to the brand's domain. They are different things and are counted separately:
an AI can recommend a brand without linking to it, or cite a page without naming the brand.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .config import Brand
from .textnorm import host_of, norm, urls_in


@dataclass
class ParsedAnswer:
    keyword: str
    engine: str
    run: int
    empty: bool
    cited_domains: list[str] = field(default_factory=list)
    mentions: dict[str, int] = field(default_factory=dict)        # brand name -> first position (char offset)
    citations: dict[str, int] = field(default_factory=dict)       # brand name -> rank among cited domains (1-based)

    def mentioned(self, brand: Brand) -> bool:
        return brand.name in self.mentions

    def cited(self, brand: Brand) -> bool:
        return brand.name in self.citations


def _first_mention(text_norm: str, brand: Brand) -> int | None:
    positions = [text_norm.find(norm(n)) for n in brand.all_names if norm(n)]
    positions = [p for p in positions if p >= 0]
    return min(positions) if positions else None


def _owns(domain: str, brand_domain: str) -> bool:
    return domain == brand_domain or domain.endswith("." + brand_domain)


def parse_answer(keyword: str, engine: str, run: int, text: str | None, brands: list[Brand]) -> ParsedAnswer:
    text = text or ""
    if not text.strip():
        # An empty answer is a collection problem, not "brand not cited". Keep it visible, never count it.
        return ParsedAnswer(keyword, engine, run, empty=True)
    domains = list(dict.fromkeys(d for d in (host_of(u) for u in urls_in(text)) if d))
    t = norm(text)
    p = ParsedAnswer(keyword, engine, run, empty=False, cited_domains=domains)
    for b in brands:
        pos = _first_mention(t, b)
        if pos is not None:
            p.mentions[b.name] = pos
        rank = next((i + 1 for i, d in enumerate(domains) if _owns(d, b.domain)), None)
        if rank is not None:
            p.citations[b.name] = rank
    return p
