"""From stored raw answers to one analysis object (used by the report, the CLI and the API)."""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from . import metrics as m
from . import stability
from .config import Brand
from .discover import discover
from .parse import ParsedAnswer, parse_answer


@dataclass
class DayAnalysis:
    day: str
    answers: list[ParsedAnswer]
    errors: list[tuple[str, int, str]] = field(default_factory=list)   # (keyword, run, error)
    texts: dict[tuple[str, int], str] = field(default_factory=dict)     # (keyword, run) -> raw answer

    @property
    def empty(self) -> int:
        return sum(a.empty for a in self.answers)


Row = tuple[str, str, int, str | None, str | None]


def analyze_rows(day: str, rows: Iterable[Row], brands: list[Brand]) -> DayAnalysis:
    """rows: (keyword, engine, run, text, error) tuples, as returned by Store.answers()."""
    answers, errors, texts = [], [], {}
    for keyword, engine, run, text, error in rows:
        if error:
            errors.append((keyword, run, error))
            continue
        answers.append(parse_answer(keyword, engine, run, text, brands))
        texts[(keyword, run)] = text or ""
    return DayAnalysis(day, answers, errors, texts)


def brand_table(day: DayAnalysis, brands: list[Brand]) -> dict[str, dict]:
    sov = m.share_of_voice(day.answers, brands)
    return {b.name: {"mention_rate": str(m.mention_rate(day.answers, b)),
                     "citation_rate": str(m.citation_rate(day.answers, b)),
                     "share_of_voice": round(sov[b.name], 3)} for b in brands}


def summary(day: DayAnalysis, client: Brand | None, brands: list[Brand], previous: DayAnalysis | None = None) -> dict:
    out: dict = {
        "day": day.day,
        "engines": sorted({a.engine for a in day.answers}),
        "answers_valid": len(m.valid(day.answers)),
        "answers_empty": day.empty,
        "collection_errors": len(day.errors),
    }
    if client is not None:
        out |= {
            "client": client.name,
            "mention_rate": str(m.mention_rate(day.answers, client)),
            "citation_rate": str(m.citation_rate(day.answers, client)),
            "per_keyword": {kw: {k: str(r) for k, r in v.items()} for kw, v in m.per_keyword(day.answers, client).items()},
        }
    out |= {
        "brands": brand_table(day, brands),
        "stability": stability.summarize(day.answers, brands),
        "top_cited_domains": m.top_cited_domains(day.answers),
        "other_names_mentioned": [(d.name, d.answers) for d in discover(day.answers, day.texts, brands) if not d.tracked][:15],
    }
    if previous is not None and client is not None:
        out["vs_previous"] = {
            "previous_day": previous.day,
            "mention_rate": m.compare(m.mention_rate(previous.answers, client), m.mention_rate(day.answers, client)).describe(),
            "citation_rate": m.compare(m.citation_rate(previous.answers, client), m.citation_rate(day.answers, client)).describe(),
        }
    return out
