"""Read a WordPress site through its public REST API instead of scraping HTML.

GET {site}/wp-json/wp/v2/posts?per_page=100&page=N, stopping at the X-WP-TotalPages header.
One request per second by default.
"""
from __future__ import annotations

import time

import httpx

USER_AGENT = "geo-visibility-tracker/0.1 (+https://github.com/SametAtas/geo-visibility-tracker)"
FIELDS = "id,link,date,modified,modified_gmt,title,content"


def fetch_posts(site: str, per_page: int = 100, delay: float = 1.0, max_pages: int = 50,
                client: httpx.Client | None = None) -> list[dict]:
    site = site.rstrip("/")
    own = client is None
    client = client or httpx.Client(timeout=30, headers={"User-Agent": USER_AGENT}, follow_redirects=True)
    posts: list[dict] = []
    page, total_pages = 1, 1
    try:
        while page <= min(total_pages, max_pages):
            r = client.get(f"{site}/wp-json/wp/v2/posts",
                           params={"per_page": per_page, "page": page, "_fields": FIELDS})
            r.raise_for_status()
            total_pages = int(r.headers.get("x-wp-totalpages", "1"))  # httpx headers are case-insensitive
            posts.extend(r.json())
            page += 1
            if page <= total_pages:
                time.sleep(delay)
    finally:
        if own:
            client.close()
    return posts
