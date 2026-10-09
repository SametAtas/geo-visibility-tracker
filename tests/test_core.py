"""Unit tests: normalization, parsing, metrics, storage."""
from __future__ import annotations

import pytest

from geo_tracker import metrics as m
from geo_tracker.config import Brand
from geo_tracker.parse import parse_answer
from geo_tracker.store import Store
from geo_tracker.textnorm import host_of, jaccard, norm, urls_in

LUMI = Brand("露米診所", "lumi-clinic.example", ("Lumi Clinic",))
AURORA = Brand("晨光醫美", "aurora-aesthetics.example")


# --- textnorm -------------------------------------------------------------------------------------------
def test_norm_full_width_and_case() -> None:
    assert norm("ＳＥＯ　優化") == "seo 優化"


def test_host_of_strips_www_and_case() -> None:
    assert host_of("HTTPS://WWW.Lumi-Clinic.example/a?b=1") == "lumi-clinic.example"
    assert host_of("not a url") == ""


def test_urls_stop_at_chinese_punctuation() -> None:
    text = "見 https://a.example/x，以及（https://b.example/y）。"
    assert urls_in(text) == ["https://a.example/x", "https://b.example/y"]


def test_jaccard_ignores_punctuation() -> None:
    assert jaccard("音波拉提會痛嗎？", "音波拉提會痛嗎?") == 1.0


# --- parse ----------------------------------------------------------------------------------------------
def test_mention_and_citation_are_different_things() -> None:
    p = parse_answer("kw", "e", 1, "推薦晨光醫美，參考 https://www.lumi-clinic.example/pico", [LUMI, AURORA])
    assert p.mentioned(AURORA) and not p.cited(AURORA)      # named, not linked
    assert p.cited(LUMI) and p.mentioned(LUMI)              # the bare domain counts as a mention too


def test_subdomain_counts_as_brand_citation_but_lookalike_does_not() -> None:
    p = parse_answer("kw", "e", 1, "https://blog.lumi-clinic.example/a https://notlumi-clinic.example/b", [LUMI])
    assert p.citations == {"露米診所": 1}
    assert p.cited_domains == ["blog.lumi-clinic.example", "notlumi-clinic.example"]


def test_alias_matching_survives_full_width_text() -> None:
    p = parse_answer("kw", "e", 1, "可以考慮 ＬＵＭＩ ＣＬＩＮＩＣ 的療程", [LUMI])
    assert p.mentioned(LUMI)


@pytest.mark.parametrize("text", ["", "   ", None])
def test_empty_answer_is_flagged_not_counted_as_miss(text: str | None) -> None:
    p = parse_answer("kw", "e", 1, text, [LUMI])
    assert p.empty and not p.mentions


# --- metrics --------------------------------------------------------------------------------------------
def test_wilson_matches_reference_values() -> None:
    lo, hi = m.wilson(12, 20)
    assert round(lo, 3) == 0.387 and round(hi, 3) == 0.781
    lo, hi = m.wilson(0, 10)
    assert lo == 0.0 and 0.27 < hi < 0.28            # the naive formula would say 0% +/- 0%


def test_two_proportion_p_small_vs_large_samples() -> None:
    assert round(m.two_proportion_p(30, 100, 38, 100), 3) == 0.232      # could be noise
    assert m.two_proportion_p(300, 1000, 380, 1000) < 0.001            # real


def test_rates_exclude_empty_answers() -> None:
    answers = [parse_answer("k", "e", i, t, [LUMI]) for i, t in
               enumerate(["露米診所很好", "", "其他診所", "露米診所 https://lumi-clinic.example"], 1)]
    assert (m.mention_rate(answers, LUMI).k, m.mention_rate(answers, LUMI).n) == (2, 3)
    assert (m.citation_rate(answers, LUMI).k, m.citation_rate(answers, LUMI).n) == (1, 3)


def test_share_of_voice_sums_to_one() -> None:
    answers = [parse_answer("k", "e", 1, "露米診所 晨光醫美", [LUMI, AURORA]),
               parse_answer("k", "e", 2, "晨光醫美", [LUMI, AURORA])]
    sov = m.share_of_voice(answers, [LUMI, AURORA])
    assert sov == {"露米診所": pytest.approx(1 / 3), "晨光醫美": pytest.approx(2 / 3)}


# --- store ----------------------------------------------------------------------------------------------
def test_store_upsert_is_idempotent_and_keeps_errors() -> None:
    s = Store()
    s.save("2026-10-05", "replay", "kw", 1, "first")
    s.save("2026-10-05", "replay", "kw", 1, "second")          # re-run of the same check
    s.save("2026-10-05", "replay", "kw", 2, None, "TimeoutError: slow")
    assert s.count() == 2
    rows = s.answers("2026-10-05")
    assert rows[0][3] == "second" and rows[1][4].startswith("TimeoutError")
