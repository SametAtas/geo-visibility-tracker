"""The Python audit and the WordPress plugin (PHP) share these cases: both must give the same numbers.

The PHP side runs in tests/php/test_signals.php; CI runs both, and a real WordPress check compares them on live posts.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from geo_tracker.audit import post_signals

CASES = json.loads((Path(__file__).parent / "fixtures" / "signals_cases.json").read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_signals_match_shared_cases(case: dict) -> None:
    post = {"id": 1, "link": "", "title": {"rendered": ""}, "content": {"rendered": case["html"]},
            "modified_gmt": "2026-01-01T00:00:00"}
    s = post_signals(post, case["own_domain"])
    assert {k: getattr(s, k) for k in case["expected"]} == case["expected"]
