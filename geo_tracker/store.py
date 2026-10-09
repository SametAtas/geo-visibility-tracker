"""SQLite storage. Raw answers are kept as-is; metrics are always recomputed from them.

Re-running a collection for the same (date, engine, keyword, run) overwrites that row instead of
duplicating it (an upsert on a unique key), so a crashed run can simply be re-run.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS answer (
    id            INTEGER PRIMARY KEY,
    collected_on  TEXT NOT NULL,          -- ISO date of the run (Asia/Taipei)
    engine        TEXT NOT NULL,          -- model name (e.g. gemini-3.8-flash) or 'replay'
    keyword       TEXT NOT NULL,
    run           INTEGER NOT NULL,       -- repeat number: answers vary, so each keyword is asked several times
    text          TEXT,                   -- raw answer, exactly as received
    error         TEXT,                   -- set when collection failed; never silently dropped
    asked_at      TEXT,                   -- UTC time of the request (provenance; a batch can span two days)
    UNIQUE (collected_on, engine, keyword, run)
);
CREATE INDEX IF NOT EXISTS ix_answer_day ON answer (collected_on, engine);
"""


class Store:
    def __init__(self, path: str | Path = ":memory:"):
        self.db = sqlite3.connect(str(path))
        self.db.executescript(SCHEMA)
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(answer)")}
        if "asked_at" not in columns:                        # databases created before the column existed
            self.db.execute("ALTER TABLE answer ADD COLUMN asked_at TEXT")

    def save(self, collected_on: str, engine: str, keyword: str, run: int,
             text: str | None, error: str | None = None) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.db.execute(
            """INSERT INTO answer (collected_on, engine, keyword, run, text, error, asked_at) VALUES (?,?,?,?,?,?,?)
               ON CONFLICT (collected_on, engine, keyword, run)
               DO UPDATE SET text = excluded.text, error = excluded.error, asked_at = excluded.asked_at""",
            (collected_on, engine, keyword, run, text, error, now),
        )
        self.db.commit()

    def answers(self, collected_on: str, engine: str | None = None) -> list[tuple[str, str, int, str | None, str | None]]:
        sql = "SELECT keyword, engine, run, text, error FROM answer WHERE collected_on = ?"
        args: list = [collected_on]
        if engine:
            sql += " AND engine = ?"
            args.append(engine)
        return self.db.execute(sql + " ORDER BY keyword, run", args).fetchall()

    def done(self, collected_on: str, engine: str) -> set[tuple[str, int]]:
        """(keyword, run) pairs already answered without error: a resumed run skips these."""
        rows = self.db.execute("SELECT keyword, run FROM answer WHERE collected_on = ? AND engine = ? AND error IS NULL",
                               (collected_on, engine))
        return {(kw, run) for kw, run in rows}

    def days(self) -> list[str]:
        return [r[0] for r in self.db.execute("SELECT DISTINCT collected_on FROM answer ORDER BY 1")]

    def count(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM answer").fetchone()[0]
