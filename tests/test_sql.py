"""The SQL views must give the same numbers as the Python metrics (tested on the demo data, both weeks)."""
from __future__ import annotations

import pytest

from geo_tracker import metrics as m
from geo_tracker import stability, warehouse
from geo_tracker.analysis import analyze_rows
from geo_tracker.answers import ReplayAdapter, collect, load_keywords
from geo_tracker.cli import DEMO
from geo_tracker.config import load_config
from geo_tracker.store import Store

WEEKS = {"2026-09-28": "answers_week1.jsonl", "2026-10-05": "answers_week2.jsonl"}


@pytest.fixture(scope="module")
def demo() -> tuple:
    cfg = load_config(DEMO / "config.toml")
    store = Store()
    for day, f in WEEKS.items():
        collect(ReplayAdapter(DEMO / f), load_keywords(cfg.keywords_file), cfg.repeats, store, day)
    warehouse.refresh(store, cfg.brands, cfg.client)
    days = {day: analyze_rows(day, store.answers(day), cfg.brands) for day in WEEKS}
    return cfg, store, days


def _rows(store: Store, sql: str) -> list[dict]:
    cols, rows = warehouse.query(store, sql)
    return [dict(zip(cols, r)) for r in rows]


def test_rates_and_wilson_intervals_match_python(demo: tuple) -> None:
    cfg, store, days = demo
    sql = {(r["collected_on"], r["brand"]): r for r in _rows(store, "SELECT * FROM mention_rate_ci")}
    cited = {(r["collected_on"], r["brand"]): r["cited"] for r in _rows(store, "SELECT * FROM brand_rate")}
    assert len(sql) == len(WEEKS) * len(cfg.brands)
    for day, analysis in days.items():
        for b in cfg.brands:
            py, row = m.mention_rate(analysis.answers, b), sql[(day, b.name)]
            assert (row["mentioned"], row["n"]) == (py.k, py.n)
            assert row["ci_low"] == pytest.approx(py.ci[0], abs=1e-4) and row["ci_high"] == pytest.approx(py.ci[1], abs=1e-4)
            assert cited[(day, b.name)] == m.citation_rate(analysis.answers, b).k


def test_empty_answers_and_errors_are_not_counted(demo: tuple) -> None:
    _, store, _ = demo
    status = dict(warehouse.query(store, "SELECT status, COUNT(*) FROM answer_status GROUP BY status")[1])
    assert status == {"valid": 28, "empty": 1, "error": 1}


def test_share_of_voice_matches_python(demo: tuple) -> None:
    cfg, store, days = demo
    for r in _rows(store, "SELECT * FROM share_of_voice"):
        py = m.share_of_voice(days[r["collected_on"]].answers, cfg.brands)[r["brand"]]
        assert r["share"] == pytest.approx(py, abs=1e-4)


def test_keyword_stability_matches_python(demo: tuple) -> None:
    cfg, store, days = demo
    sql = {(r["collected_on"], r["keyword"], r["brand"]): r for r in _rows(store, "SELECT * FROM keyword_brand")}
    for day, analysis in days.items():
        for p in stability.pair_counts(analysis.answers, cfg.brands):
            row = sql[(day, p.keyword, p.brand)]
            assert (row["runs_mentioning"], row["runs"], bool(row["flips"])) == (p.k, p.n, p.flips)


def test_window_function_change_matches_python(demo: tuple) -> None:
    cfg, store, days = demo
    row = _rows(store, f"SELECT * FROM mention_change WHERE brand = '{cfg.client.name}' AND previous_on IS NOT NULL")[0]
    before, after = (m.mention_rate(days[d].answers, cfg.client) for d in WEEKS)
    assert row["change"] == pytest.approx(after.value - before.value, abs=1e-4)


def test_refresh_is_idempotent(demo: tuple) -> None:
    cfg, store, _ = demo
    assert warehouse.refresh(store, cfg.brands, cfg.client) == warehouse.refresh(store, cfg.brands, cfg.client)
