"""Real-measurement features: resume, daily quota, retry delays, export/replay, stability, discovery."""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from geo_tracker import stability
from geo_tracker.analysis import analyze_rows, summary
from geo_tracker.answers import OpenAICompatibleAdapter, QuotaExhausted, ReplayAdapter, collect
from geo_tracker.cli import main
from geo_tracker.config import Brand, load_config
from geo_tracker.discover import candidates, discover
from geo_tracker.store import Store

A, B, C = Brand("蝦皮購物", "shopee.tw", ("蝦皮",)), Brand("momo購物網", "momoshop.com.tw", ("momo",)), Brand("博客來", "books.com.tw")


def _adapter(handler, **kw) -> OpenAICompatibleAdapter:
    return OpenAICompatibleAdapter(base_url="https://llm.example/v1beta/openai/", api_key="k", model="m", min_interval=0,
                                   backoff_base=0, client=httpx.Client(transport=httpx.MockTransport(handler)), **kw)


# --- collection -----------------------------------------------------------------------------------------
def test_daily_quota_stops_without_retrying_and_resume_continues() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if len(calls) == 3:   # Gemini-style daily quota error
            return httpx.Response(429, text='{"error":{"details":[{"quotaId":"GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}}')
        return httpx.Response(200, json={"choices": [{"message": {"content": f"answer {len(calls)}"}}]})

    store = Store()
    first = collect(_adapter(handler), ["k1", "k2"], 2, store, "2026-10-09")
    assert first.stopped.startswith("daily quota") and first.saved == 2 and len(calls) == 3   # no retries on a daily quota
    assert calls[0] == "/v1beta/openai/chat/completions"                                       # trailing slash handled
    second = collect(_adapter(handler), ["k1", "k2"], 2, store, "2026-10-09")
    assert (second.skipped, second.saved, second.stopped) == (2, 2, "")
    assert store.count() == 4


def test_minute_rate_limit_uses_gemini_retry_delay_from_body() -> None:
    a = _adapter(lambda r: httpx.Response(429, text='{"error":{"details":[{"retryDelay":"7s"}]}}'))
    assert a._retry_delay(httpx.Response(429, text='[{"retryDelay": "7s"}]'), attempt=0) == 7.0
    assert a._retry_delay(httpx.Response(429, headers={"retry-after": "1.5"}), attempt=0) == 1.5
    assert a._retry_delay(httpx.Response(503), attempt=2) == 0.0          # backoff_base=0 in tests
    slow = OpenAICompatibleAdapter(base_url="https://x", api_key="k", model="m")
    assert [slow._retry_delay(httpx.Response(503), i) for i in range(7)] == [2, 4, 8, 16, 32, 60, 60]


def test_temperature_and_system_prompt_only_sent_when_configured() -> None:
    bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "x"}}]})

    _adapter(handler, temperature=0.2, system_prompt="sys").ask("q", 1)
    assert bodies[0]["temperature"] == 0.2 and bodies[0]["messages"][0] == {"role": "system", "content": "sys"}


def test_run_stops_after_three_errors_in_a_row() -> None:
    store = Store()
    stats = collect(_adapter(lambda r: httpx.Response(401)), ["k1", "k2", "k3"], 2, store, "2026-10-09")
    assert stats.errors == 3 and stats.asked == 3 and stats.stopped.startswith("3 errors in a row")
    assert store.count() == 3 and not store.done("2026-10-09", "m")      # errors are stored, and retried on resume


def test_quota_error_is_not_stored_so_resume_can_fill_it() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="PerDay")
    with pytest.raises(QuotaExhausted):
        _adapter(handler).ask("q", 1)


def test_export_then_replay_reproduces_the_same_rows(tmp_path: Path) -> None:
    cfg = tmp_path / "config.toml"
    (tmp_path / "kw.txt").write_text("q1\nq2\n", encoding="utf-8")
    cfg.write_text('[[brands]]\nname = "蝦皮購物"\ndomain = "shopee.tw"\n[run]\nkeywords_file = "kw.txt"\nrepeats = 2\n',
                   encoding="utf-8")
    store = Store(tmp_path / "geo.db")
    store.save("2026-10-09", "gemini-x", "q1", 1, "推薦蝦皮")
    store.save("2026-10-09", "gemini-x", "q1", 2, "")
    store.save("2026-10-09", "gemini-x", "q2", 1, None, "HTTPStatusError: 503")
    store.save("2026-10-09", "gemini-x", "q2", 2, "momo")
    store.db.close()
    out = tmp_path / "answers.jsonl"
    assert main(["export", "--config", str(cfg), "--date", "2026-10-09", "--out", str(out)]) == 0
    replay = ReplayAdapter(out)
    assert replay.name == "gemini-x"                       # engine survives the round trip
    copy = Store()
    stats = collect(replay, ["q1", "q2"], 2, copy, "2026-10-09")
    assert (stats.saved, stats.errors, stats.empty) == (3, 1, 1)
    assert copy.answers("2026-10-09")[2][4].endswith("HTTPStatusError: 503")


def test_config_without_client_is_a_market_study(tmp_path: Path) -> None:
    f = tmp_path / "c.toml"
    f.write_text('[[brands]]\nname = "A"\ndomain = "a.example"\n[[brands]]\nname = "B"\ndomain = "b.example"\n'
                 '[run]\nmin_interval = 6.5\n', encoding="utf-8")
    cfg = load_config(f)
    assert cfg.client is None and [b.name for b in cfg.brands] == ["A", "B"] and cfg.min_interval == 6.5
    day = analyze_rows("d", [("q", "e", 1, "A and B", None), ("q", "e", 2, "A", None)], cfg.brands)
    s = summary(day, cfg.client, cfg.brands)
    assert "mention_rate" not in s and s["brands"]["A"]["mention_rate"].startswith("2/2")


# --- analysis -------------------------------------------------------------------------------------------
def test_stability_counts_flips_and_single_check_error() -> None:
    rows = [("q", "e", 1, "蝦皮 momo", None), ("q", "e", 2, "蝦皮", None), ("q", "e", 3, "蝦皮 momo 博客來", None),
            ("q", "e", 4, "蝦皮", None)]
    day = analyze_rows("d", rows, [A, B, C])
    st = stability.summarize(day.answers, [A, B, C])
    # 蝦皮 4/4 (stable), momo 2/4 (flips, error 0.5), 博客來 1/4 (flips, error 0.25)
    assert (st["pairs_seen"], st["pairs_flipping"]) == (3, 2)
    assert st["mean_single_check_error"] == round((0 + 0.5 + 0.25) / 3, 3)
    assert 0 < st["mean_run_overlap"] < 1


def test_discovery_finds_untracked_names_and_skips_labels() -> None:
    text = ("以下是推薦：\n1. **蝦皮購物**：商品多\n2. **PChome 24h購物（PChome）**：到貨快\n- 樂天市場：點數回饋\n"
            "**優點**：方便\n**總結**\n**NT$399**")
    assert candidates(text) == {"蝦皮購物", "PChome 24h購物", "樂天市場"}
    day = analyze_rows("d", [("q", "e", 1, text, None), ("q", "e", 2, "**樂天市場** 也不錯", None)], [A])
    found = {d.name: d for d in discover(day.answers, day.texts, [A])}
    assert found["樂天市場"].answers == 2 and found["蝦皮購物"].tracked and not found["樂天市場"].tracked


def test_report_refuses_to_mix_engines(tmp_path: Path) -> None:
    cfg = tmp_path / "c.toml"
    cfg.write_text('[[brands]]\nname = "A"\ndomain = "a.example"\n[run]\ndb_path = "g.db"\n', encoding="utf-8")
    store = Store(tmp_path / "g.db")
    store.save("2026-10-09", "gemini-x", "q", 1, "A")
    store.save("2026-10-09", "step-y", "q", 1, "B")
    store.db.close()
    out = tmp_path / "r.html"
    assert main(["report", "--config", str(cfg), "--date", "2026-10-09", "--out", str(out)]) == 2
    assert main(["report", "--config", str(cfg), "--date", "2026-10-09", "--engine", "step-y", "--out", str(out)]) == 0
    assert "step-y" in out.read_text(encoding="utf-8")


def test_published_real_run_reproduces_the_numbers_in_the_readme() -> None:
    """experiments/ecommerce_tw: the README's numbers must come out of the raw answers committed next to it."""
    exp = Path(__file__).parent.parent / "experiments" / "ecommerce_tw"
    cfg = load_config(exp / "config.toml")
    store = Store()
    replay = ReplayAdapter(exp / "answers_2026-10-09_step-5-preview.jsonl")
    assert replay.name == "stepfun/step-5-preview"
    assert collect(replay, [l.strip() for l in (exp / "keywords.txt").read_text(encoding="utf-8").splitlines()
                            if l.strip() and not l.startswith("#")], 5, store, "2026-10-09").saved == 30
    day = analyze_rows("2026-10-09", store.answers("2026-10-09"), cfg.brands)
    s = summary(day, None, cfg.brands)
    assert s["brands"]["蝦皮購物"]["mention_rate"].startswith("30/30")
    assert (s["stability"]["pairs_seen"], s["stability"]["pairs_flipping"]) == (53, 32)
    assert s["stability"]["mean_single_check_error"] == 0.166 and s["stability"]["mean_run_overlap"] == 0.641
    coupang = next(p for p in stability.pair_counts(day.answers, cfg.brands)
                   if p.brand == "酷澎" and p.keyword.startswith("網購想要隔天到貨"))
    assert (coupang.k, coupang.n) == (1, 5)
