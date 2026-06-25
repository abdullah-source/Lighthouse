"""
db.py — Postgres (Supabase) schema + helpers, with pgvector.

v2 moved off SQLite to Postgres for proper multi-tenant scale and a real vector
store. Design choices that keep the rest of the codebase nearly unchanged:

- JSON-ish columns (brands_mentioned, positions, descriptors, citations) stay
  TEXT holding json.dumps(...) strings, exactly like the SQLite version, so the
  json.loads(...) calls in store.py work identically.
- Embeddings use a native pgvector `vector(1536)` column, searched in SQL.
- A connection pool (psycopg_pool) is shared across the web + background-task
  threads. get_conn() borrows a connection; the pool commits on clean exit and
  rolls back on exception.
- Rows come back as dicts (psycopg dict_row), so row["col"] works everywhere.

The full schema lives here in one place (CREATE TABLE IF NOT EXISTS), so
init_db() is the whole migration — no ALTER dance, since this is a fresh DB.
"""

import atexit
from contextlib import contextmanager

from pgvector.psycopg import register_vector
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from config import DATABASE_URL

EMBED_DIM = 1536  # text-embedding-3-small


# --- Schema -----------------------------------------------------------------

SCHEMA = f"""
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS brands (
    id              BIGSERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    category        TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    status          TEXT,
    canonical_name  TEXT,
    error_message   TEXT,
    mention_rate    REAL,        -- denormalized headline metric for the fast list view
    total_responses INTEGER,
    key_competitor  TEXT         -- optional rival the client wants to benchmark against
);

CREATE TABLE IF NOT EXISTS queries (
    id          BIGSERIAL PRIMARY KEY,
    brand_id    BIGINT NOT NULL REFERENCES brands(id),
    query_text  TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS responses (
    id            BIGSERIAL PRIMARY KEY,
    query_id      BIGINT NOT NULL REFERENCES queries(id),
    model         TEXT NOT NULL,
    raw_text      TEXT NOT NULL,
    citations     TEXT,
    phase         TEXT DEFAULT 'baseline',
    experiment_id BIGINT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS parsed_responses (
    id                BIGSERIAL PRIMARY KEY,
    response_id       BIGINT NOT NULL UNIQUE REFERENCES responses(id),
    brands_mentioned  TEXT NOT NULL,
    positions         TEXT NOT NULL,
    descriptors       TEXT,
    parsed_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS brand_aliases (
    id          BIGSERIAL PRIMARY KEY,
    canonical   TEXT NOT NULL,
    alias       TEXT NOT NULL UNIQUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS experiments (
    id                BIGSERIAL PRIMARY KEY,
    brand_id          BIGINT NOT NULL REFERENCES brands(id),
    target_query      TEXT NOT NULL,
    candidate_content TEXT,
    baseline_rate     REAL,
    treatment_rate    REAL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS context_documents (
    id          BIGSERIAL PRIMARY KEY,
    brand_id    BIGINT NOT NULL REFERENCES brands(id),
    source_type TEXT,
    title       TEXT,
    raw_text    TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS query_panels (
    id           BIGSERIAL PRIMARY KEY,
    brand_id     BIGINT NOT NULL REFERENCES brands(id),
    version      INTEGER NOT NULL,
    status       TEXT NOT NULL,
    grounded     BOOLEAN NOT NULL DEFAULT FALSE,
    seed_summary TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    frozen_at    TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS panel_queries (
    id          BIGSERIAL PRIMARY KEY,
    panel_id    BIGINT NOT NULL REFERENCES query_panels(id),
    query_text  TEXT NOT NULL,
    intent      TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS context_chunks (
    id          BIGSERIAL PRIMARY KEY,
    brand_id    BIGINT NOT NULL REFERENCES brands(id),
    document_id BIGINT REFERENCES context_documents(id),
    chunk_text  TEXT NOT NULL,
    embedding   vector({EMBED_DIM}),
    kind        TEXT NOT NULL DEFAULT 'context',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_queries_brand_id ON queries(brand_id);
CREATE INDEX IF NOT EXISTS idx_responses_query_id ON responses(query_id);
CREATE INDEX IF NOT EXISTS idx_parsed_response_id ON parsed_responses(response_id);
CREATE INDEX IF NOT EXISTS idx_panel_queries_panel ON panel_queries(panel_id);
CREATE INDEX IF NOT EXISTS idx_query_panels_brand ON query_panels(brand_id);
CREATE INDEX IF NOT EXISTS idx_context_chunks_brand ON context_chunks(brand_id);
"""


# --- Connection pool --------------------------------------------------------

# One shared pool. configure=register_vector teaches each pooled connection the
# pgvector type so we can pass/receive Python lists for `vector` columns.
_pool: ConnectionPool | None = None


def _get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL is not set — Postgres backend requires it.")
        _pool = ConnectionPool(
            DATABASE_URL,
            min_size=1,
            max_size=5,
            kwargs={"row_factory": dict_row},
            configure=register_vector,
            open=True,
        )
    return _pool


@contextmanager
def get_conn():
    """
    Borrow a pooled connection. Commits on clean exit, rolls back on error
    (psycopg_pool's connection context manager handles that).
    """
    with _get_pool().connection() as conn:
        yield conn


def close_pool() -> None:
    """Close the pool cleanly (called at interpreter exit so scripts don't hang)."""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


atexit.register(close_pool)


def init_db() -> None:
    """Create the full schema if it doesn't exist. Idempotent."""
    with get_conn() as conn:
        conn.execute(SCHEMA)
        # Add denormalized headline columns to a pre-existing brands table.
        conn.execute("ALTER TABLE brands ADD COLUMN IF NOT EXISTS mention_rate REAL")
        conn.execute("ALTER TABLE brands ADD COLUMN IF NOT EXISTS total_responses INTEGER")
        conn.execute("ALTER TABLE brands ADD COLUMN IF NOT EXISTS key_competitor TEXT")


# --- Insert helpers (RETURNING id) ------------------------------------------


def insert_brand(conn, name: str, category: str) -> int:
    row = conn.execute(
        "INSERT INTO brands (name, category) VALUES (%s, %s) RETURNING id",
        (name, category),
    ).fetchone()
    return row["id"]


def insert_query(conn, brand_id: int, query_text: str) -> int:
    row = conn.execute(
        "INSERT INTO queries (brand_id, query_text) VALUES (%s, %s) RETURNING id",
        (brand_id, query_text),
    ).fetchone()
    return row["id"]


def insert_response(conn, query_id: int, model: str, raw_text: str,
                    citations: list | None = None) -> int:
    import json
    row = conn.execute(
        "INSERT INTO responses (query_id, model, raw_text, citations) "
        "VALUES (%s, %s, %s, %s) RETURNING id",
        (query_id, model, raw_text, json.dumps(citations or [])),
    ).fetchone()
    return row["id"]


def insert_parsed(conn, response_id: int, brands_mentioned: list[str],
                  positions: dict[str, int],
                  descriptors: dict[str, list[str]] | None = None) -> int:
    import json
    row = conn.execute(
        "INSERT INTO parsed_responses (response_id, brands_mentioned, positions, descriptors) "
        "VALUES (%s, %s, %s, %s) RETURNING id",
        (response_id, json.dumps(brands_mentioned), json.dumps(positions),
         json.dumps(descriptors or {})),
    ).fetchone()
    return row["id"]


# --- Read helpers -----------------------------------------------------------


def fetch_queries_for_brand(conn, brand_id: int):
    return conn.execute(
        "SELECT id, query_text FROM queries WHERE brand_id = %s ORDER BY id",
        (brand_id,),
    ).fetchall()


def fetch_unparsed_responses(conn, brand_id: int):
    return conn.execute(
        """
        SELECT r.id, r.raw_text
        FROM responses r
        JOIN queries q ON q.id = r.query_id
        LEFT JOIN parsed_responses p ON p.response_id = r.id
        WHERE q.brand_id = %s AND p.id IS NULL
        ORDER BY r.id
        """,
        (brand_id,),
    ).fetchall()


def fetch_citations_for_brand(conn, brand_id: int):
    return conn.execute(
        """
        SELECT r.model, r.citations
        FROM responses r
        JOIN queries q ON q.id = r.query_id
        WHERE q.brand_id = %s
          AND r.citations IS NOT NULL
          AND r.citations <> ''
          AND r.citations <> '[]'
        """,
        (brand_id,),
    ).fetchall()


def fetch_parsed_for_brand(conn, brand_id: int):
    return conn.execute(
        """
        SELECT r.id AS response_id, r.model, p.brands_mentioned, p.positions, p.descriptors
        FROM parsed_responses p
        JOIN responses r ON r.id = p.response_id
        JOIN queries q ON q.id = r.query_id
        WHERE q.brand_id = %s
        """,
        (brand_id,),
    ).fetchall()
