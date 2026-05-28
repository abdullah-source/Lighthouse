"""
db.py — SQLite schema and helpers.

Why no ORM:
- SQLAlchemy adds a learning curve and indirection we don't need at v0.
- Raw SQL teaches you the data model directly.
- When we move to Postgres in v1, the migration is straightforward because
  we never relied on ORM features.

Why SQLite for v0:
- Single file, zero setup, ships with Python's stdlib.
- Handles thousands of rows trivially.
- One process, one writer — perfect for a CLI script.

SQLite quirks worth knowing:
- Datatype affinity is permissive. We use TEXT for JSON blobs because
  SQLite stores them as strings anyway.
- Parameterized queries (the `?` placeholders) are mandatory. Never
  f-string user input into SQL — that's how SQL injection happens.
- Foreign keys are OFF by default. We enable them per-connection.
"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from config import DB_PATH


# --- Schema -----------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS brands (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    category    TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS queries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    brand_id    INTEGER NOT NULL REFERENCES brands(id),
    query_text  TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS responses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    query_id    INTEGER NOT NULL REFERENCES queries(id),
    model       TEXT NOT NULL,         -- e.g. 'gpt-5' or 'claude-sonnet-4-6'
    raw_text    TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS parsed_responses (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    response_id         INTEGER NOT NULL UNIQUE REFERENCES responses(id),
    brands_mentioned    TEXT NOT NULL,  -- JSON array: ["Allbirds", "Hoka"]
    positions           TEXT NOT NULL,  -- JSON object: {"Allbirds": 3, "Hoka": 1}
    parsed_at           TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_queries_brand_id ON queries(brand_id);
CREATE INDEX IF NOT EXISTS idx_responses_query_id ON responses(query_id);
CREATE INDEX IF NOT EXISTS idx_parsed_response_id ON parsed_responses(response_id);
"""


# --- Connection helper ------------------------------------------------------


@contextmanager
def get_conn():
    """
    Open a SQLite connection with sensible defaults.

    `with get_conn() as conn:` ensures commit + close happen even if
    something raises. Skipping context managers is a common source of
    "where did my data go?" bugs.

    row_factory = sqlite3.Row makes results behave like both tuples AND
    dicts: row[0] or row['name']. Much nicer than raw tuples.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")  # SQLite disables FK enforcement by default
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """Create tables and indexes if they don't already exist. Idempotent."""
    with get_conn() as conn:
        conn.executescript(SCHEMA)


# --- Insert helpers ---------------------------------------------------------


def _now() -> str:
    """ISO-8601 UTC timestamp. SQLite stores it as TEXT and we can ORDER BY it."""
    return datetime.now(timezone.utc).isoformat()


def insert_brand(conn: sqlite3.Connection, name: str, category: str) -> int:
    cur = conn.execute(
        "INSERT INTO brands (name, category, created_at) VALUES (?, ?, ?)",
        (name, category, _now()),
    )
    return cur.lastrowid


def insert_query(conn: sqlite3.Connection, brand_id: int, query_text: str) -> int:
    cur = conn.execute(
        "INSERT INTO queries (brand_id, query_text, created_at) VALUES (?, ?, ?)",
        (brand_id, query_text, _now()),
    )
    return cur.lastrowid


def insert_response(conn: sqlite3.Connection, query_id: int, model: str, raw_text: str) -> int:
    cur = conn.execute(
        "INSERT INTO responses (query_id, model, raw_text, created_at) VALUES (?, ?, ?, ?)",
        (query_id, model, raw_text, _now()),
    )
    return cur.lastrowid


def insert_parsed(
    conn: sqlite3.Connection,
    response_id: int,
    brands_mentioned: list[str],
    positions: dict[str, int],
) -> int:
    """
    Store the parser's output. JSON-encode the list and dict so we can
    fit them into TEXT columns. SQLite has JSON1 functions if we later
    want to query inside them, but for v0 we just deserialize at read time.
    """
    cur = conn.execute(
        "INSERT INTO parsed_responses (response_id, brands_mentioned, positions, parsed_at) "
        "VALUES (?, ?, ?, ?)",
        (response_id, json.dumps(brands_mentioned), json.dumps(positions), _now()),
    )
    return cur.lastrowid


# --- Read helpers -----------------------------------------------------------


def fetch_queries_for_brand(conn: sqlite3.Connection, brand_id: int) -> list[sqlite3.Row]:
    """All queries for a brand, ordered by id (insertion order)."""
    return conn.execute(
        "SELECT id, query_text FROM queries WHERE brand_id = ? ORDER BY id",
        (brand_id,),
    ).fetchall()


def fetch_unparsed_responses(conn: sqlite3.Connection, brand_id: int) -> list[sqlite3.Row]:
    """
    Responses that don't yet have a parsed_responses row. Used by parse.py
    so a re-run doesn't re-parse what we already did.
    """
    return conn.execute(
        """
        SELECT r.id, r.raw_text
        FROM responses r
        JOIN queries q ON q.id = r.query_id
        LEFT JOIN parsed_responses p ON p.response_id = r.id
        WHERE q.brand_id = ? AND p.id IS NULL
        ORDER BY r.id
        """,
        (brand_id,),
    ).fetchall()


def fetch_parsed_for_brand(conn: sqlite3.Connection, brand_id: int) -> list[sqlite3.Row]:
    """All parsed responses for a brand. Used by report.py to aggregate."""
    return conn.execute(
        """
        SELECT r.id AS response_id, r.model, p.brands_mentioned, p.positions
        FROM parsed_responses p
        JOIN responses r ON r.id = p.response_id
        JOIN queries q ON q.id = r.query_id
        WHERE q.brand_id = ?
        """,
        (brand_id,),
    ).fetchall()
