"""SQL layer: derived tables and views over the raw answers, for analysts, dashboards and ad-hoc questions.

The raw `answer` table stays the source of truth. `refresh()` parses every answer once (same parser as
the reports) and rebuilds the derived tables; the views then answer the usual questions in plain SQL:

    brand_rate         mentions and citations per period, engine and brand
    mention_rate_ci    the same with a 95% Wilson interval, computed in SQL
    mention_change     change vs the previous period (window function LAG)
    share_of_voice     each brand's share of all tracked-brand mentions (window SUM)
    keyword_brand      per keyword: in how many runs each brand appeared (stability)
    cited_domain_count most cited domains per period

Answer status (valid / empty / error) is decided in Python, by the same rule the reports use,
so SQL and Python can never disagree about which answers count.
"""
from __future__ import annotations

import math
import sqlite3

from .config import Brand
from .parse import parse_answer
from .store import Store

DERIVED = """
CREATE TABLE IF NOT EXISTS brand (
    name       TEXT PRIMARY KEY,
    domain     TEXT NOT NULL,
    is_client  INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS answer_status (
    answer_id  INTEGER PRIMARY KEY REFERENCES answer(id),
    status     TEXT NOT NULL CHECK (status IN ('valid', 'empty', 'error'))
);
CREATE TABLE IF NOT EXISTS mention (
    answer_id  INTEGER NOT NULL REFERENCES answer(id),
    brand      TEXT NOT NULL REFERENCES brand(name),
    first_pos  INTEGER NOT NULL,                 -- character offset of the first mention
    PRIMARY KEY (answer_id, brand)
);
CREATE TABLE IF NOT EXISTS citation (
    answer_id  INTEGER NOT NULL REFERENCES answer(id),
    brand      TEXT NOT NULL REFERENCES brand(name),
    rank       INTEGER NOT NULL,                 -- 1 = the first domain the answer cited
    PRIMARY KEY (answer_id, brand)
);
CREATE TABLE IF NOT EXISTS cited_domain (
    answer_id  INTEGER NOT NULL REFERENCES answer(id),
    domain     TEXT NOT NULL,
    PRIMARY KEY (answer_id, domain)
);
"""

VIEWS = """
DROP VIEW IF EXISTS valid_answer;
CREATE VIEW valid_answer AS
    SELECT a.* FROM answer a JOIN answer_status s ON s.answer_id = a.id WHERE s.status = 'valid';

DROP VIEW IF EXISTS brand_rate;
CREATE VIEW brand_rate AS
    WITH period AS (
        SELECT collected_on, engine, COUNT(*) AS n FROM valid_answer GROUP BY collected_on, engine
    )
    SELECT p.collected_on, p.engine, b.name AS brand, b.is_client,
           COUNT(m.answer_id) AS mentioned, COUNT(c.answer_id) AS cited, p.n
    FROM period p
    CROSS JOIN brand b
    JOIN valid_answer v ON v.collected_on = p.collected_on AND v.engine = p.engine
    LEFT JOIN mention m ON m.answer_id = v.id AND m.brand = b.name
    LEFT JOIN citation c ON c.answer_id = v.id AND c.brand = b.name
    GROUP BY p.collected_on, p.engine, b.name, b.is_client, p.n;

DROP VIEW IF EXISTS mention_rate_ci;
CREATE VIEW mention_rate_ci AS
    WITH r AS (SELECT *, mentioned * 1.0 / n AS p, 3.841458820694124 AS z2 FROM brand_rate)   -- z2 = 1.96^2
    SELECT collected_on, engine, brand, is_client, mentioned, n, ROUND(p, 4) AS rate,
           ROUND(MAX(0.0, (p + z2 / (2 * n) - SQRT(z2 * (p * (1 - p) / n + z2 / (4.0 * n * n)))) / (1 + z2 / n)), 4) AS ci_low,
           ROUND(MIN(1.0, (p + z2 / (2 * n) + SQRT(z2 * (p * (1 - p) / n + z2 / (4.0 * n * n)))) / (1 + z2 / n)), 4) AS ci_high
    FROM r;

DROP VIEW IF EXISTS mention_change;
CREATE VIEW mention_change AS
    SELECT collected_on, engine, brand, is_client, mentioned, n,
           ROUND(mentioned * 1.0 / n, 4) AS rate,
           LAG(collected_on) OVER w AS previous_on,
           ROUND(mentioned * 1.0 / n - LAG(mentioned * 1.0 / n) OVER w, 4) AS change
    FROM brand_rate
    WINDOW w AS (PARTITION BY engine, brand ORDER BY collected_on);

DROP VIEW IF EXISTS share_of_voice;
CREATE VIEW share_of_voice AS
    SELECT collected_on, engine, brand, is_client, mentioned,
           ROUND(mentioned * 1.0 / NULLIF(SUM(mentioned) OVER (PARTITION BY collected_on, engine), 0), 4) AS share
    FROM brand_rate;

DROP VIEW IF EXISTS keyword_brand;
CREATE VIEW keyword_brand AS
    SELECT v.collected_on, v.engine, v.keyword, b.name AS brand,
           COUNT(m.answer_id) AS runs_mentioning, COUNT(*) AS runs,
           CASE WHEN COUNT(m.answer_id) BETWEEN 1 AND COUNT(*) - 1 THEN 1 ELSE 0 END AS flips
    FROM valid_answer v
    CROSS JOIN brand b
    LEFT JOIN mention m ON m.answer_id = v.id AND m.brand = b.name
    GROUP BY v.collected_on, v.engine, v.keyword, b.name;

DROP VIEW IF EXISTS cited_domain_count;
CREATE VIEW cited_domain_count AS
    SELECT v.collected_on, v.engine, d.domain, COUNT(*) AS answers
    FROM cited_domain d JOIN valid_answer v ON v.id = d.answer_id
    GROUP BY v.collected_on, v.engine, d.domain;
"""


def _ensure_sqrt(db: sqlite3.Connection) -> None:
    """SQLite's math functions are optional at compile time (some Windows builds lack them)."""
    try:
        db.execute("SELECT SQRT(4.0)")
    except sqlite3.OperationalError:
        db.create_function("SQRT", 1, math.sqrt, deterministic=True)


def refresh(store: Store, brands: list[Brand], client: Brand | None = None) -> dict[str, int]:
    """Rebuild the derived tables from the raw answers. Safe to run any number of times."""
    db = store.db
    _ensure_sqrt(db)
    db.executescript(DERIVED)
    with db:                                   # one transaction: readers never see a half-built state
        for table in ("mention", "citation", "cited_domain", "answer_status", "brand"):
            db.execute(f"DELETE FROM {table}")   # noqa: S608 - fixed table names, no user input
        db.executemany("INSERT INTO brand (name, domain, is_client) VALUES (?, ?, ?)",
                       [(b.name, b.domain, int(client is not None and b == client)) for b in brands])
        rows = db.execute("SELECT id, keyword, engine, run, text, error FROM answer").fetchall()
        for answer_id, keyword, engine, run, text, error in rows:
            if error:
                db.execute("INSERT INTO answer_status VALUES (?, 'error')", (answer_id,))
                continue
            p = parse_answer(keyword, engine, run, text, brands)
            db.execute("INSERT INTO answer_status VALUES (?, ?)", (answer_id, "empty" if p.empty else "valid"))
            db.executemany("INSERT INTO mention VALUES (?, ?, ?)", [(answer_id, b, pos) for b, pos in p.mentions.items()])
            db.executemany("INSERT INTO citation VALUES (?, ?, ?)", [(answer_id, b, r) for b, r in p.citations.items()])
            db.executemany("INSERT INTO cited_domain VALUES (?, ?)", [(answer_id, d) for d in p.cited_domains])
    db.executescript(VIEWS)
    return {t: db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]   # noqa: S608 - fixed table names
            for t in ("answer", "answer_status", "mention", "citation", "cited_domain")}


def query(store: Store, sql: str, params: tuple = ()) -> tuple[list[str], list[tuple]]:
    """Run one SELECT and return (column names, rows)."""
    cur = store.db.execute(sql, params)
    return [d[0] for d in cur.description or ()], cur.fetchall()
