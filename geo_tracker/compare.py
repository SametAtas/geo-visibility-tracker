"""One page comparing AI engines on the same questions: which brands each engine names, how often, how stably,
and where engines really differ (tested, not eyeballed)."""
from __future__ import annotations

from html import escape
from itertools import combinations
from statistics import mean

from . import metrics as m
from . import stability
from .analysis import DayAnalysis
from .config import Brand, Config
from .report import CSS, _bar, _rate_cell


def majority_sets(day: DayAnalysis, brands: list[Brand]) -> dict[str, set[str]]:
    """Per question, the brands an engine names in more than half of its runs: its 'answer' to that question."""
    out: dict[str, set[str]] = {}
    for p in stability.pair_counts(day.answers, brands):
        out.setdefault(p.keyword, set())
        if 2 * p.k > p.n:
            out[p.keyword].add(p.brand)
    return out


def agreement(a: DayAnalysis, b: DayAnalysis, brands: list[Brand]) -> dict[str, float]:
    """Jaccard overlap of the two engines' majority sets, per question both engines answered."""
    sa, sb = majority_sets(a, brands), majority_sets(b, brands)
    return {kw: (len(sa[kw] & sb[kw]) / len(sa[kw] | sb[kw]) if sa[kw] | sb[kw] else 1.0)
            for kw in sorted(sa.keys() & sb.keys())}


def differences(days: dict[str, DayAnalysis], brands: list[Brand]) -> list[tuple[str, str, str, m.Change]]:
    """Every brand and engine pair, with a two-proportion test; largest gaps first."""
    out = []
    for b in brands:
        for e1, e2 in combinations(sorted(days), 2):
            ch = m.compare(m.mention_rate(days[e1].answers, b), m.mention_rate(days[e2].answers, b))
            out.append((b.name, e1, e2, ch))
    return sorted(out, key=lambda t: -abs(t[3].after.value - t[3].before.value))


def _cards(days: dict[str, DayAnalysis], brands: list[Brand]) -> list[str]:
    h = ["<div class=cards>"]
    for engine, day in days.items():
        st = stability.summarize(day.answers, brands)
        if st["pairs_seen"] == 0:          # no tracked brand named at all: nothing to say about stability
            flips, detail = "-", "no tracked brand was named"
        else:
            flips = f"{st['flip_share']:.0%}"
            detail = (f"of question-brand pairs changed between runs · one check disagrees with the majority "
                      f"{st['mean_single_check_error']:.0%} of the time")
        h.append(f"<div class=card><div class=muted>{escape(engine)}</div><div class=big>{flips}</div>"
                 f"<div class=muted>{detail} · {len(m.valid(day.answers))} answers</div></div>")
    return h + ["</div>"]


def _brand_table(days: dict[str, DayAnalysis], brands: list[Brand]) -> list[str]:
    engines = list(days)
    head = "".join(f"<th>{escape(e)}</th>" for e in engines)
    h = ["<h2>How often each engine names each brand</h2><p class=muted>Blue band: 95% interval. Same questions, "
         f"same number of runs for every engine.</p><table><tr><th>Brand</th>{head}</tr>"]
    avg = {b.name: mean(m.mention_rate(d.answers, b).value for d in days.values()) for b in brands}
    for b in sorted(brands, key=lambda x: -avg[x.name]):
        cells = "".join(f"<td>{_rate_cell(m.mention_rate(days[e].answers, b))}{_bar(m.mention_rate(days[e].answers, b))}</td>"
                        for e in engines)
        h.append(f"<tr><td>{escape(b.name)}</td>{cells}</tr>")
    return h + ["</table>"]


def _gaps(days: dict[str, DayAnalysis], brands: list[Brand]) -> list[str]:
    diffs = differences(days, brands)
    threshold = 0.05 / len(diffs) if diffs else 0.05       # Bonferroni: many brands x engine pairs are tested at once
    h = [f"<h2>Where the engines really differ</h2><p class=muted>A two-proportion test for every brand and engine pair "
         f"({len(diffs)} tests). Testing that many at p &lt; 0.05 would produce about {0.05 * len(diffs):.0f} false alarms, "
         f"so a difference counts as real only below p = {threshold:.4f} (Bonferroni).</p>"
         "<table><tr><th>Brand</th><th>Engines</th><th>Named in</th><th>Verdict</th></tr>"]
    for brand, e1, e2, ch in diffs[:12]:
        verdict = "<b>real difference</b>" if ch.p_value < threshold else "could be noise"
        h.append(f"<tr><td>{escape(brand)}</td><td>{escape(e1)} vs {escape(e2)}</td>"
                 f"<td>{ch.before.k}/{ch.before.n} vs {ch.after.k}/{ch.after.n}</td><td>{verdict} (p={ch.p_value:.2g})</td></tr>")
    return h + ["</table>"]


def _agreement(days: dict[str, DayAnalysis], brands: list[Brand]) -> list[str]:
    pairs = list(combinations(days, 2))
    rows = {pair: agreement(days[pair[0]], days[pair[1]], brands) for pair in pairs}
    keywords = sorted({kw for r in rows.values() for kw in r})
    head = "".join(f"<th>{escape(a)} vs {escape(b)}</th>" for a, b in pairs)
    h = ["<h2>Do the engines recommend the same brands?</h2><p class=muted>Per question: overlap (Jaccard) of the "
         f"brands each engine names in most of its runs. 100% = same list.</p><table><tr><th>Question</th>{head}</tr>"]
    for kw in keywords:
        cells = "".join(f"<td>{rows[p][kw]:.0%}</td>" if kw in rows[p] else "<td>-</td>" for p in pairs)
        h.append(f"<tr><td>{escape(kw)}</td>{cells}</tr>")
    return h + ["</table>"]


def render_comparison(cfg: Config, date: str, days: dict[str, DayAnalysis]) -> str:
    """days: engine name -> its analysis for the same date and questions. Every string is escaped."""
    brands = cfg.brands
    h = [f"<!doctype html><html lang=zh-Hant><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
         f"<title>AI engines compared: {escape(cfg.title)}</title><style>{CSS}</style>",
         f"<h1>AI engines compared: {escape(cfg.title)}</h1><p class=muted>{escape(date)} · "
         f"{len(days)} engines · each question asked the same number of times per engine</p>"]
    h += _cards(days, brands) + _brand_table(days, brands) + _gaps(days, brands) + _agreement(days, brands)
    h.append("<p class=muted>Generated by geo-visibility-tracker. Rates use Wilson 95% intervals; "
             "differences between engines use a two-proportion z-test with a Bonferroni correction.</p></html>")
    return "\n".join(h)
