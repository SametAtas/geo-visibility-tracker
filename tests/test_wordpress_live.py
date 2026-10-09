"""Against a real WordPress (tests/wordpress/setup_wordpress.sh): the Python audit, read through the core REST API,
and the PHP plugin's own endpoint must report the same numbers for every post. Also checks pagination,
drafts, freshness with a non-UTC site timezone, the admin column, and recomputation on save.

Skipped unless GEO_WP_URL is set, e.g. GEO_WP_URL=http://127.0.0.1:8899 pytest tests/test_wordpress_live.py
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import asdict
from pathlib import Path

import httpx
import pytest

from geo_tracker import audit, wordpress

URL = os.environ.get("GEO_WP_URL", "")
pytestmark = pytest.mark.skipif(not URL, reason="needs a running WordPress (GEO_WP_URL)")
SIGNALS = ("chars", "headings", "has_faq", "external_sources", "statistics", "quotes", "tables")


def _plugin_posts() -> list[dict]:
    out, page, pages = [], 1, 1
    while page <= pages:
        r = httpx.get(f"{URL}/wp-json/geo-signals/v1/posts", params={"per_page": 10, "page": page})
        r.raise_for_status()
        pages = int(r.headers["x-wp-totalpages"])
        out += r.json()
        page += 1
    return out


def test_core_rest_api_paginates_published_posts_only() -> None:
    posts = wordpress.fetch_posts(URL, per_page=10, delay=0)
    assert len(posts) == 23 and len({p["id"] for p in posts}) == 23          # 3 pages, no duplicates
    assert not any("Draft" in p["title"]["rendered"] for p in posts)


def test_python_audit_and_php_plugin_agree_on_every_post() -> None:
    host = httpx.URL(URL).host
    py = {r.id: asdict(r) for r in (audit.post_signals(p, host) for p in wordpress.fetch_posts(URL, delay=0))}
    php = {p["id"]: p for p in _plugin_posts()}
    assert py.keys() == php.keys()
    for pid, row in py.items():
        assert {k: row[k] for k in SIGNALS} == php[pid]["signals"], f"post {pid}: {row['title']}"
        assert row["days_since_update"] == php[pid]["days_since_update"]


def test_blog_summary_is_identical() -> None:
    host = httpx.URL(URL).host
    rows = [audit.post_signals(p, host) for p in wordpress.fetch_posts(URL, delay=0)]
    assert audit.summarize(rows) == httpx.get(f"{URL}/wp-json/geo-signals/v1/summary").json()


def test_old_post_is_not_fresh_and_timezone_is_handled() -> None:
    old = next(p for p in _plugin_posts() if p["title"] == "Old post")
    assert old["days_since_update"] == 400          # stored 400 days ago in GMT; site timezone is Asia/Taipei


def test_admin_posts_screen_shows_the_column() -> None:
    with httpx.Client(base_url=URL, follow_redirects=True) as c:
        c.get("/wp-login.php")                                            # sets the test cookie
        c.post("/wp-login.php", data={"log": "admin", "pwd": "test-password-123", "rememberme": "forever",
                                      "redirect_to": f"{URL}/wp-admin/", "testcookie": "1"})
        typical = c.get("/wp-admin/edit.php", params={"s": "typical"}).text          # the first fixture case
        no_source = c.get("/wp-admin/edit.php", params={"s": "Old post"}).text
    # 5 sources, not 3 as in the unit case: here the site is 127.0.0.1, so lumi-clinic.example links are external too
    assert "GEO signals" in typical and "<span>Sources 5 · Stats 4 · Quotes 2 · FAQ</span>" in typical
    assert '<span style="color:#b32d2e">Sources 0 · Stats 1 · Quotes 0 · No FAQ</span>' in no_source   # flagged red


def test_signals_are_recomputed_when_a_post_is_saved() -> None:
    site = Path(os.environ.get("GEO_WP_DIR", Path(__file__).parent.parent / ".wp-test" / "site"))
    target = next(p for p in _plugin_posts() if p["title"] == "Filler 1")
    php = (f"require '{site}/wp-load.php'; wp_update_post(['ID' => {target['id']}, 'post_content' => "
           "'<p><a href=\"https://a.example\">a</a> <a href=\"https://b.example\">b</a> 5% 6% 7%</p>']);")
    subprocess.run(["php", "-r", php], check=True, capture_output=True)
    after = next(p for p in _plugin_posts() if p["id"] == target["id"])
    assert (after["signals"]["external_sources"], after["signals"]["statistics"]) == (2, 3)
