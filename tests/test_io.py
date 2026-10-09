"""Tests for everything that talks to the network. No real network: httpx.MockTransport plays the server."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from geo_tracker import audit, factcheck, wordpress
from geo_tracker.answers import OpenAICompatibleAdapter, ReplayAdapter, collect
from geo_tracker.cli import DEMO, local_pages_client
from geo_tracker.store import Store


# --- LLM adapter ----------------------------------------------------------------------------------------
def test_llm_adapter_retries_429_then_succeeds() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        assert request.headers["authorization"] == "Bearer test-key"
        if len(calls) == 1:
            return httpx.Response(429, headers={"retry-after": "0"})
        return httpx.Response(200, json={"choices": [{"message": {"content": "推薦露米診所"}}]})

    a = OpenAICompatibleAdapter(base_url="https://llm.example/v1", api_key="test-key", model="m",
                                min_interval=0, backoff_base=0, client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert a.ask("台北皮秒雷射推薦", 1) == "推薦露米診所"
    assert len(calls) == 2 and calls[0]["messages"] == [{"role": "user", "content": "台北皮秒雷射推薦"}]
    assert "temperature" not in calls[0]          # provider default unless configured


def test_llm_adapter_does_not_retry_client_errors() -> None:
    a = OpenAICompatibleAdapter(base_url="https://llm.example/v1", api_key="k", model="m", min_interval=0,
                                backoff_base=0, client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(401))))
    with pytest.raises(httpx.HTTPStatusError):
        a.ask("kw", 1)


def test_collect_stores_failures_instead_of_dropping_them(tmp_path: Path) -> None:
    f = tmp_path / "a.jsonl"
    f.write_text('{"keyword": "k1", "run": 1, "text": "ok"}\n{"keyword": "k1", "run": 2, "text": ""}\n', encoding="utf-8")
    store = Store()
    stats = collect(ReplayAdapter(f), ["k1"], 3, store, "2026-10-05")
    assert (stats.asked, stats.saved, stats.errors, stats.empty) == (3, 2, 1, 1)
    assert store.answers("2026-10-05")[2][4].startswith("KeyError")


# --- WordPress REST API ---------------------------------------------------------------------------------
def test_wordpress_follows_total_pages_header() -> None:
    posts = [{"id": i, "link": f"https://blog.example/{i}", "date": "2026-01-01T00:00:00",
              "modified": "2026-01-01T00:00:00", "title": {"rendered": f"t{i}"}, "content": {"rendered": ""}} for i in range(5)]
    seen_pages = []

    def handler(request: httpx.Request) -> httpx.Response:
        page, per = int(request.url.params["page"]), int(request.url.params["per_page"])
        seen_pages.append(page)
        return httpx.Response(200, json=posts[(page - 1) * per: page * per], headers={"X-WP-TotalPages": "3"})

    got = wordpress.fetch_posts("https://blog.example/", per_page=2, delay=0,
                                client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert [p["id"] for p in got] == [0, 1, 2, 3, 4] and seen_pages == [1, 2, 3]


def test_audit_signals() -> None:
    post = {"id": 1, "link": "x", "modified": "2026-10-01T00:00:00", "title": {"rendered": "SEO &amp; GEO"},
            "content": {"rendered": "<h2>常見問題</h2><p>2025 年點擊率從 15% 降到 8%，超過 3 萬人。</p>"
                                    "<blockquote>專家說</blockquote><a href='https://arxiv.org/a'>a</a>"
                                    "<a href='https://www.blog.example/b'>internal</a><a href='https://arxiv.org/c'>same domain</a>"}}
    s = audit.post_signals(post, "blog.example", now=datetime(2026, 10, 9, tzinfo=timezone.utc))
    assert s.title == "SEO & GEO"
    assert s.statistics == 3                 # 15%, 8%, 3 萬; "2025 年" is a date, not a statistic
    assert s.external_sources == 1           # arxiv.org once; the internal www link is excluded
    assert s.has_faq and s.quotes == 1 and s.days_since_update == 8


# --- fact-check -----------------------------------------------------------------------------------------
@pytest.fixture
def demo_cache() -> factcheck.PageCache:
    return factcheck.PageCache(delay=0, client=local_pages_client(DEMO / "pages"))


def test_factcheck_classifies_every_case(demo_cache: factcheck.PageCache) -> None:
    result = factcheck.check_table(factcheck.load_table(DEMO / "comparison_table.json"), demo_cache)
    status = {(r["entity"], r["attribute"]): r["status"] for r in result["results"]}
    assert status[("露米診所", "價格")] == "supported"
    assert status[("露米診所", "營業時間")] == "weak"                    # paraphrased evidence
    assert status[("晨光醫美", "價格")] == "value_not_in_source"         # 7,500 appears nowhere: invented
    assert status[("晨光醫美", "醫師人數")] == "no_source"
    assert status[("貝拉診所", "營業時間")] == "evidence_not_found"      # contradicts the page
    assert status[("貝拉診所", "醫師人數")] == "marked_unknown"
    assert status[("貝拉診所", "地址")] == "unreachable"
    assert result["supported_share"] == "44%"                             # 4 of 9 checkable cells


def test_factcheck_fetches_each_source_once() -> None:
    hits = []

    def handler(request: httpx.Request) -> httpx.Response:
        hits.append(str(request.url))
        return httpx.Response(200, text="<p>價格 1,000 元</p>")

    cache = factcheck.PageCache(delay=0, client=httpx.Client(transport=httpx.MockTransport(handler)))
    cells = [{"entity": "a", "attribute": "價格", "value": "1,000 元", "source_url": "https://s.example/p", "evidence": "價格 1,000 元"}] * 3
    assert factcheck.check_table({"cells": cells}, cache)["counts"] == {"supported": 3}
    assert hits == ["https://s.example/p"]
