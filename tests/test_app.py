"""Tests for question mining, the HTTP API, the report and the end-to-end demo."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from geo_tracker import questions, report
from geo_tracker.analysis import analyze_rows
from geo_tracker.api import app
from geo_tracker.cli import DEMO, main
from geo_tracker.config import Brand, Config, load_config


# --- question mining ------------------------------------------------------------------------------------
def test_clean_title_strips_forum_prefixes() -> None:
    assert questions.clean_title("Re: [問題] 音波拉提會痛嗎") == "音波拉提會痛嗎"
    assert questions.clean_title("【分享】音波拉提術後三個月") == "音波拉提術後三個月"


def test_mining_groups_rewordings_and_drops_non_questions() -> None:
    titles = [("[問題] 音波拉提會痛嗎？", "ptt"), ("音波拉提會很痛嗎", "dcard"), ("音波拉提會不會痛", "dcard"),
              ("[心得] 第一次皮秒雷射紀錄", "ptt"), ("皮秒雷射一次多少錢？", "dcard")]
    clusters = questions.mine(titles)
    assert [(c.size, c.intent) for c in clusters] == [(3, "informational"), (1, "transactional")]
    assert clusters[0].sources == {"ptt", "dcard"}


def test_demo_question_bank_top_question() -> None:
    top = questions.mine(questions.read_titles(DEMO / "forum_titles.csv"))[0]
    assert (top.representative, top.size, top.intent) == ("台北皮秒雷射推薦哪家", 5, "commercial")


# --- API ------------------------------------------------------------------------------------------------
client = TestClient(app)


def test_api_analyze() -> None:
    body = {"client": {"name": "露米診所", "domain": "lumi-clinic.example"},
            "competitors": [{"name": "晨光醫美", "domain": "aurora-aesthetics.example"}],
            "answers": [{"keyword": "k", "run": 1, "text": "露米診所 https://lumi-clinic.example"},
                        {"keyword": "k", "run": 2, "text": "晨光醫美"},
                        {"keyword": "k", "run": 3, "text": ""}]}
    r = client.post("/analyze", json=body)
    assert r.status_code == 200
    d = r.json()
    assert d["valid_answers"] == 2 and d["empty_answers"] == 1
    assert d["mention_rate"]["k"] == 1 and d["mention_rate"]["n"] == 2
    assert d["share_of_voice"] == {"露米診所": 0.5, "晨光醫美": 0.5}


def test_api_rejects_bad_input() -> None:
    assert client.post("/analyze", json={"client": {"name": "x"}}).status_code == 422
    assert client.post("/intent", json={"queries": []}).status_code == 422


def test_api_intent() -> None:
    r = client.post("/intent", json={"queries": ["皮秒雷射價格", "露米診所官網", "音波拉提原理"]})
    assert [x["intent"] for x in r.json()["results"]] == ["transactional", "navigational", "informational"]


# --- report ---------------------------------------------------------------------------------------------
def test_report_escapes_untrusted_text() -> None:
    evil = Brand("<script>alert(1)</script>", "evil.example")
    cfg = Config(client=evil)
    day = analyze_rows("2026-10-05", [("<b>kw</b>", "e", 1, "<script>alert(1)</script> https://evil.example", None)], [evil])
    html = report.render(cfg, day)
    assert "<script>alert" not in html and "&lt;script&gt;" in html


# --- end to end -----------------------------------------------------------------------------------------
def test_demo_end_to_end(tmp_path: Path) -> None:
    assert main(["demo", "--out", str(tmp_path)]) == 0
    s = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert s["mention_rate"] == "7/13 = 54% (95% CI 29%-77%)"
    assert s["citation_rate"] == "6/13 = 46% (95% CI 23%-71%)"
    assert s["answers_empty"] == 1 and s["collection_errors"] == 1
    assert "could be noise" in s["vs_previous"]["mention_rate"]          # 27% -> 54% on 13-15 answers is not proof
    html = (tmp_path / "report.html").read_text(encoding="utf-8")
    assert "Sample data" in html and "台北皮秒雷射推薦" in html
    assert load_config(DEMO / "config.toml").client.domain == "lumi-clinic.example"
