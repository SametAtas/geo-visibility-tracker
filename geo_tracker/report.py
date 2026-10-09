"""A single self-contained HTML report (no JavaScript, no external files): easy to email or open anywhere."""
from __future__ import annotations

from html import escape

from . import metrics as m
from . import stability
from .analysis import DayAnalysis
from .config import Config
from .discover import discover

CSS = """
body{font-family:-apple-system,"Noto Sans TC","PingFang TC","Microsoft JhengHei",sans-serif;max-width:960px;margin:2rem auto;padding:0 1rem;color:#1f2328;background:#fff}
h1{font-size:1.6rem;margin-bottom:.2rem}h2{font-size:1.15rem;margin-top:2rem;border-bottom:1px solid #d0d7de;padding-bottom:.3rem}
.muted{color:#57606a;font-size:.9rem}.cards{display:flex;gap:1rem;flex-wrap:wrap}
.card{border:1px solid #d0d7de;border-radius:8px;padding:.8rem 1rem;min-width:200px;flex:1}
.big{font-size:1.8rem;font-weight:600}table{border-collapse:collapse;width:100%;font-size:.92rem;margin:.5rem 0}
th,td{border-bottom:1px solid #eaeef2;padding:.4rem .5rem;text-align:left;vertical-align:top}
.bar{position:relative;height:10px;background:#eaeef2;border-radius:5px;min-width:120px}
.ci{position:absolute;height:10px;background:#9ecbff;border-radius:5px}.pt{position:absolute;top:-3px;width:4px;height:16px;background:#0550ae;border-radius:2px}
.warn{background:#fff8c5;border:1px solid #d4a72c;border-radius:6px;padding:.6rem .8rem}
"""


def _bar(rate: m.Rate) -> str:
    lo, hi = rate.ci
    return (f'<div class="bar"><div class="ci" style="left:{lo:.0%};width:{hi - lo:.0%}"></div>'
            f'<div class="pt" style="left:calc({rate.value:.0%} - 2px)"></div></div>')


def _rate_cell(rate: m.Rate) -> str:
    lo, hi = rate.ci
    return f"{rate.k}/{rate.n} = <b>{rate.value:.0%}</b> <span class=muted>({lo:.0%}-{hi:.0%})</span>"


def _summary_cards(cfg: Config, day: DayAnalysis, previous: DayAnalysis | None) -> list[str]:
    c = cfg.client
    if c is None:
        return []
    men, cit = m.mention_rate(day.answers, c), m.citation_rate(day.answers, c)
    h = ['<div class=cards>']
    for label, r in (("Mentioned in AI answers", men), ("Cited (linked) in AI answers", cit)):
        h.append(f'<div class=card><div class=muted>{label}</div><div class=big>{r.value:.0%}</div>'
                 f'<div class=muted>{r.k}/{r.n} · 95% CI {r.ci[0]:.0%}-{r.ci[1]:.0%}</div></div>')
    if previous is not None:
        ch = m.compare(m.mention_rate(previous.answers, c), men)
        h.append(f'<div class=card><div class=muted>Mention rate vs {escape(previous.day)}</div>'
                 f'<div class=big>{ch.after.value - ch.before.value:+.0%}</div><div class=muted>{escape(ch.describe())}</div></div>')
    return h + ['</div>']


def _client_keywords(cfg: Config, day: DayAnalysis) -> list[str]:
    if cfg.client is None:
        return []
    h = ["<h2>Per keyword</h2><p class=muted>Each keyword was asked several times, because AI answers change between runs. "
         "The blue band is the 95% interval: with few runs it is wide, which is the honest answer.</p>",
         "<table><tr><th>Keyword</th><th>Mentioned</th><th></th><th>Cited</th></tr>"]
    for kw, r in m.per_keyword(day.answers, cfg.client).items():
        h.append(f"<tr><td>{escape(kw)}</td><td>{_rate_cell(r['mention'])}</td><td>{_bar(r['mention'])}</td><td>{_rate_cell(r['citation'])}</td></tr>")
    return h + ["</table>"]


def _brands(cfg: Config, day: DayAnalysis) -> list[str]:
    h = ["<h2>Brands</h2><p class=muted>Share of voice: of all mentions of tracked brands, the share each one gets.</p>"
         "<table><tr><th>Brand</th><th>Share of voice</th><th>Mentioned</th><th></th><th>Cited</th></tr>"]
    sov = m.share_of_voice(day.answers, cfg.brands)
    order = sorted(cfg.brands, key=lambda b: -sov[b.name])
    for b in order:
        men = m.mention_rate(day.answers, b)
        h.append(f"<tr><td>{escape(b.name)}{' (client)' if b == cfg.client else ''}</td><td>{sov[b.name]:.0%}</td>"
                 f"<td>{_rate_cell(men)}</td><td>{_bar(men)}</td><td>{_rate_cell(m.citation_rate(day.answers, b))}</td></tr>")
    return h + ["</table>"]


def _stability(cfg: Config, day: DayAnalysis) -> list[str]:
    st = stability.summarize(day.answers, cfg.brands)
    if not st["pairs_seen"]:
        return []
    h = [f"<h2>How stable are the answers?</h2><p>For {st['pairs_seen']} keyword-brand pairs where the brand appeared at "
         f"least once, <b>{st['pairs_flipping']} ({st['flip_share']:.0%})</b> appeared in some runs but not others. "
         f"A single check would disagree with the majority of runs <b>{st['mean_single_check_error']:.0%}</b> of the time."
         + (f" Runs of the same question named the same brands with a mean overlap of <b>{st['mean_run_overlap']:.0%}</b> (Jaccard)."
            if st["mean_run_overlap"] is not None else "") + "</p>",
         "<table><tr><th>Keyword</th><th>Overlap between runs</th></tr>"]
    h += [f"<tr><td>{escape(k)}</td><td>{v:.0%}</td></tr>" for k, v in st["run_overlap_by_keyword"].items()]
    h.append("</table><table><tr><th>Keyword</th><th>Brand</th><th>Runs mentioning it</th></tr>")
    h += [f"<tr><td>{escape(p.keyword)}</td><td>{escape(p.brand)}</td><td>{p.k}/{p.n}</td></tr>"
          for p in stability.pair_counts(day.answers, cfg.brands) if p.flips]
    return h + ["</table>"]


def _other(cfg: Config, day: DayAnalysis) -> list[str]:
    found = [d for d in discover(day.answers, day.texts, cfg.brands) if not d.tracked][:15]
    h = []
    if found:
        h.append("<h2>Other names the AI mentioned</h2><p class=muted>Not in the config. Candidates found heuristically "
                 "(bold text or list items that start a line), so a person should review them before tracking any.</p>"
                 "<table><tr><th>Name</th><th>Answers</th></tr>")
        h += [f"<tr><td>{escape(d.name)}</td><td>{d.answers} ({d.share:.0%})</td></tr>" for d in found]
        h.append("</table>")
    h.append("<h2>Most cited domains</h2><p class=muted>AI engines often cite third-party sites more than brand sites; "
             "these are the pages to earn coverage on.</p><table><tr><th>Domain</th><th>Answers citing it</th></tr>")
    cited = m.top_cited_domains(day.answers)
    h += [f"<tr><td>{escape(d)}</td><td>{n}</td></tr>" for d, n in cited]
    if not cited:
        h.append("<tr><td colspan=2 class=muted>No answer contained a link (the model answered without web search).</td></tr>")
    h.append(f"</table><h2>Data quality</h2><table><tr><td>Empty answers (not counted as 'not cited')</td><td>{day.empty}</td></tr>"
             f"<tr><td>Collection errors (stored, excluded)</td><td>{len(day.errors)}</td></tr></table>")
    return h


def _extras(audit: dict | None, questions: list | None, factcheck: dict | None) -> list[str]:
    h: list[str] = []
    if questions:
        h.append("<h2>Question bank (from forum titles)</h2><table><tr><th>Question</th><th>Asked</th><th>Intent</th><th>Sources</th></tr>")
        h += [f"<tr><td>{escape(q.representative)}</td><td>{q.size}</td><td>{q.intent}</td><td>{escape(', '.join(sorted(q.sources)))}</td></tr>"
              for q in questions[:15]]
        h.append("</table>")
    if factcheck:
        h.append(f"<h2>Fact-check: {escape(factcheck['title'])}</h2><p>{factcheck['cells']} cells · supported: "
                 f"<b>{factcheck['supported_share']}</b> of checkable cells · {escape(str(factcheck['counts']))}</p>"
                 "<table><tr><th>Entity</th><th>Attribute</th><th>Value</th><th>Status</th><th>Detail</th></tr>")
        h += [f"<tr><td>{escape(r['entity'])}</td><td>{escape(r['attribute'])}</td><td>{escape(r['value'])}</td>"
              f"<td>{r['status']}</td><td class=muted>{escape(r['detail'])}</td></tr>" for r in factcheck["needs_human"]]
        h.append("</table>")
    if audit:
        h.append("<h2>Content audit (GEO signals)</h2><table>")
        h += [f"<tr><td>{escape(k)}</td><td>{escape(str(v))}</td></tr>" for k, v in audit.items()]
        h.append("</table>")
    return h


def render(cfg: Config, day: DayAnalysis, previous: DayAnalysis | None = None,
           audit: dict | None = None, questions: list | None = None, factcheck: dict | None = None,
           sample_data: bool = False) -> str:
    """Every piece of text from answers, configs or web pages goes through html.escape (they are untrusted)."""
    engines = ", ".join(sorted({a.engine for a in day.answers})) or "-"
    h = [f"<!doctype html><html lang=zh-Hant><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
         f"<title>AI visibility: {escape(cfg.title)}</title><style>{CSS}</style>",
         f"<h1>AI visibility report: {escape(cfg.title)}</h1><p class=muted>{escape(day.day)} · engine(s): "
         f"{escape(engines)} · {len(m.valid(day.answers))} valid answers</p>"]
    if sample_data:
        h.append('<p class=warn><b>Sample data.</b> Brands, domains and answers in this report are invented (.example domains) '
                 'to demonstrate the pipeline. They are not measurements of any real company.</p>')
    h += (_summary_cards(cfg, day, previous) + _client_keywords(cfg, day) + _brands(cfg, day) + _stability(cfg, day)
          + _other(cfg, day) + _extras(audit, questions, factcheck))
    h.append("<p class=muted>Generated by geo-visibility-tracker. Rates use Wilson 95% intervals; "
             "changes are tested with a two-proportion z-test.</p></html>")
    return "\n".join(h)
