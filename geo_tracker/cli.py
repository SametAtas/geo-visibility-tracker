"""Command line: python -m geo_tracker <command> ...  (run with -h for help)"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from . import audit, factcheck, questions, report, warehouse, wordpress
from .analysis import analyze_rows, summary
from .answers import OpenAICompatibleAdapter, ReplayAdapter, collect, load_keywords
from .config import load_config
from .store import Store

DEMO = Path(__file__).resolve().parent.parent / "examples" / "demo"


def _today() -> str:
    return datetime.now(ZoneInfo("Asia/Taipei")).date().isoformat()   # weeks and days are Taipei time


def local_pages_client(pages_dir: Path) -> httpx.Client:
    """An HTTP client that serves https://<host>/<path> from pages_dir/<host>/<path>.html (offline demos/tests)."""
    def handler(request: httpx.Request) -> httpx.Response:
        rel = request.url.path.strip("/") or "index"
        f = pages_dir / request.url.host / f"{rel}.html"
        return httpx.Response(200, text=f.read_text(encoding="utf-8")) if f.exists() else httpx.Response(404)
    return httpx.Client(transport=httpx.MockTransport(handler))


def _config(a: argparse.Namespace):
    cfg = load_config(a.config)
    if getattr(a, "db", None):
        cfg.db_path = Path(a.db)          # keep data outside the code folder (e.g. next to the person's notes)
    return cfg


def cmd_collect(a: argparse.Namespace) -> int:
    cfg = _config(a)
    adapter = ReplayAdapter(a.replay) if a.replay else OpenAICompatibleAdapter(
        temperature=cfg.temperature, system_prompt=cfg.system_prompt, min_interval=cfg.min_interval)
    stats = collect(adapter, load_keywords(cfg.keywords_file), cfg.repeats, Store(cfg.db_path), a.date or _today(),
                    resume=not a.refresh, progress=lambda msg: print(msg, file=sys.stderr, flush=True))
    print(json.dumps(stats.__dict__, ensure_ascii=False))
    if stats.stopped:
        print(f"Stopped early ({stats.stopped[:120]}). Fix the cause or wait for the quota to reset, then run the same "
              "command again: answers already collected are kept and skipped.", file=sys.stderr)
        return 3
    return 1 if stats.errors and not stats.saved else 0


def cmd_export(a: argparse.Namespace) -> int:
    """Raw answers of one date as JSONL. `collect --replay` reads this back, so published data can be re-analyzed."""
    cfg = _config(a)
    rows = Store(cfg.db_path).db.execute(
        "SELECT keyword, engine, run, text, error, asked_at FROM answer WHERE collected_on = ? ORDER BY keyword, run",
        (a.date,)).fetchall()
    with open(a.out, "w", encoding="utf-8") as f:
        for keyword, engine, run, text, error, asked_at in rows:
            f.write(json.dumps({"collected_on": a.date, "engine": engine, "keyword": keyword, "run": run,
                                "asked_at": asked_at, "text": text, "error": error}, ensure_ascii=False) + "\n")
    print(f"{len(rows)} answers written to {a.out}", file=sys.stderr)
    return 0


def cmd_report(a: argparse.Namespace) -> int:
    cfg = _config(a)
    store = Store(cfg.db_path)
    engines = {r[1] for r in store.answers(a.date)}
    if len(engines) > 1 and not a.engine:
        print(f"{a.date} has answers from several engines {sorted(engines)}; pick one with --engine", file=sys.stderr)
        return 2
    day = analyze_rows(a.date, store.answers(a.date, a.engine), cfg.brands)
    prev = analyze_rows(a.previous, store.answers(a.previous, a.engine), cfg.brands) if a.previous else None
    qs = questions.mine(questions.read_titles(a.questions)) if a.questions else None
    fc = None
    if a.factcheck:
        client = local_pages_client(Path(a.pages)) if a.pages else None
        fc = factcheck.check_table(factcheck.load_table(a.factcheck), factcheck.PageCache(delay=0 if client else 1, client=client))
    Path(a.out).write_text(report.render(cfg, day, prev, questions=qs, factcheck=fc, sample_data=a.sample), encoding="utf-8")
    print(json.dumps(summary(day, cfg.client, cfg.brands, prev), ensure_ascii=False, indent=1))
    print(f"report written to {a.out}", file=sys.stderr)
    return 0


def cmd_sql(a: argparse.Namespace) -> int:
    """Rebuild the derived tables, then run a query (a .sql file or a string) and print the result."""
    cfg = _config(a)
    store = Store(cfg.db_path)
    counts = warehouse.refresh(store, cfg.brands, cfg.client)
    print(f"derived tables rebuilt: {counts}", file=sys.stderr)
    sql = Path(a.query).read_text(encoding="utf-8") if a.query.endswith(".sql") else a.query
    cols, rows = warehouse.query(store, sql)
    if a.csv:
        w = csv.writer(sys.stdout)
        w.writerow(cols)
        w.writerows(rows)
        return 0
    cells = [[str(c) for c in cols]] + [["" if v is None else str(v) for v in r] for r in rows]
    widths = [max(_width(row[i]) for row in cells) for i in range(len(cols))]
    for k, row in enumerate(cells):
        print("  ".join(v + " " * (w - _width(v)) for v, w in zip(row, widths)).rstrip())
        if k == 0:
            print("  ".join("-" * w for w in widths))
    return 0


def _width(text: str) -> int:
    """Display width: Chinese characters take two columns in a terminal."""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def cmd_audit_blog(a: argparse.Namespace) -> int:
    posts = wordpress.fetch_posts(a.site, delay=a.delay)
    own = httpx.URL(a.site).host
    rows = [audit.post_signals(p, own) for p in posts]
    if rows:
        with open(a.out, "w", newline="", encoding="utf-8-sig") as f:      # utf-8-sig: Excel shows Chinese correctly
            w = csv.DictWriter(f, fieldnames=list(audit.as_dicts(rows[:1])[0]))
            w.writeheader()
            w.writerows(audit.as_dicts(rows))
    print(json.dumps(audit.summarize(rows), ensure_ascii=False, indent=1))
    return 0


def cmd_questions(a: argparse.Namespace) -> int:
    for c in questions.mine(questions.read_titles(a.csv))[: a.top]:
        print(f"{c.size:3d}  [{c.intent:13s}] {c.representative}")
    return 0


def cmd_factcheck(a: argparse.Namespace) -> int:
    client = local_pages_client(Path(a.pages)) if a.pages else None
    result = factcheck.check_table(factcheck.load_table(a.table), factcheck.PageCache(delay=0 if client else a.delay, client=client))
    print(json.dumps({k: v for k, v in result.items() if k != "results"}, ensure_ascii=False, indent=1))
    return 0


def cmd_demo(a: argparse.Namespace) -> int:
    """Run the whole pipeline on the bundled sample data (invented brands, .example domains)."""
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    cfg = load_config(DEMO / "config.toml")
    cfg.db_path = out / "demo.db"
    if cfg.db_path.exists():
        cfg.db_path.unlink()
    store = Store(cfg.db_path)
    kws = load_keywords(cfg.keywords_file)
    for day, f in (("2026-09-28", "answers_week1.jsonl"), ("2026-10-05", "answers_week2.jsonl")):
        print(day, collect(ReplayAdapter(DEMO / f), kws, cfg.repeats, store, day).__dict__)
    week1 = analyze_rows("2026-09-28", store.answers("2026-09-28"), cfg.brands)
    week2 = analyze_rows("2026-10-05", store.answers("2026-10-05"), cfg.brands)
    qs = questions.mine(questions.read_titles(DEMO / "forum_titles.csv"))
    fc = factcheck.check_table(factcheck.load_table(DEMO / "comparison_table.json"),
                               factcheck.PageCache(delay=0, client=local_pages_client(DEMO / "pages")))
    (out / "report.html").write_text(report.render(cfg, week2, week1, questions=qs, factcheck=fc, sample_data=True), encoding="utf-8")
    s = summary(week2, cfg.client, cfg.brands, week1)
    (out / "summary.json").write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "factcheck.json").write_text(json.dumps(fc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: s[k] for k in ("mention_rate", "citation_rate", "vs_previous", "answers_empty", "collection_errors")},
                     ensure_ascii=False, indent=1))
    print(f"questions: {len(qs)} clusters; top: {qs[0].representative} ({qs[0].size}x)")
    print(f"fact-check: {fc['counts']} supported_share={fc['supported_share']}")
    print(f"open {out / 'report.html'}")
    return 0


def _data_commands(sub: argparse._SubParsersAction) -> None:
    """Commands that collect or move raw answers."""
    s = sub.add_parser("collect", help="ask each keyword N times and store raw answers")
    s.add_argument("--config", required=True)
    s.add_argument("--db", help="SQLite file to use instead of the one named in the config")
    s.add_argument("--date", help="ISO date (default: today, Asia/Taipei)")
    s.add_argument("--replay", help="JSONL of recorded answers; omit to use GEO_LLM_* (OpenAI-compatible API)")
    s.add_argument("--refresh", action="store_true", help="ask again even if an answer for this date is stored")
    s.set_defaults(func=cmd_collect)

    s = sub.add_parser("export", help="write the raw answers of one date as JSONL")
    s.add_argument("--config", required=True)
    s.add_argument("--db", help="SQLite file to use instead of the one named in the config")
    s.add_argument("--date", required=True)
    s.add_argument("--out", default="answers.jsonl")
    s.set_defaults(func=cmd_export)


def _analysis_commands(sub: argparse._SubParsersAction) -> None:
    """Commands that analyze answers, blogs, forum titles and tables."""
    s = sub.add_parser("sql", help="rebuild the SQL views and run a query (file ending in .sql, or a string)")
    s.add_argument("--config", required=True)
    s.add_argument("--db", help="SQLite file to use instead of the one named in the config")
    s.add_argument("query", help="e.g. queries/visibility.sql or \"SELECT * FROM share_of_voice\"")
    s.add_argument("--csv", action="store_true", help="print CSV instead of a table")
    s.set_defaults(func=cmd_sql)

    s = sub.add_parser("report", help="analyze a day (optionally vs a previous day) into an HTML report")
    s.add_argument("--config", required=True)
    s.add_argument("--db", help="SQLite file to use instead of the one named in the config")
    s.add_argument("--date", required=True)
    s.add_argument("--engine", help="model name, when a date has answers from more than one engine")
    s.add_argument("--previous")
    s.add_argument("--questions", help="CSV of forum titles (columns: title, source)")
    s.add_argument("--factcheck", help="comparison table JSON to fact-check")
    s.add_argument("--pages", help="serve fact-check sources from this local folder (offline)")
    s.add_argument("--sample", action="store_true", help="label the report as sample data")
    s.add_argument("--out", default="report.html")
    s.set_defaults(func=cmd_report)

    s = sub.add_parser("audit-blog", help="GEO signals for every post of a WordPress site (REST API)")
    s.add_argument("site")
    s.add_argument("--out", default="audit.csv")
    s.add_argument("--delay", type=float, default=1.0)
    s.set_defaults(func=cmd_audit_blog)

    s = sub.add_parser("questions", help="mine and cluster questions from forum titles")
    s.add_argument("csv")
    s.add_argument("--top", type=int, default=20)
    s.set_defaults(func=cmd_questions)

    s = sub.add_parser("factcheck", help="check every cell of a comparison table against its source")
    s.add_argument("table")
    s.add_argument("--pages", help="serve sources from a local folder (offline)")
    s.add_argument("--delay", type=float, default=1.0)
    s.set_defaults(func=cmd_factcheck)

    s = sub.add_parser("demo", help="run the full pipeline on bundled sample data")
    s.add_argument("--out", default="demo_output")
    s.set_defaults(func=cmd_demo)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="geo_tracker", description="Track brand visibility in AI answers, honestly.")
    sub = p.add_subparsers(dest="cmd", required=True)
    _data_commands(sub)
    _analysis_commands(sub)
    a = p.parse_args(argv)
    return a.func(a)
