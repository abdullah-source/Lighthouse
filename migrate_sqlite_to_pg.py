"""
migrate_sqlite_to_pg.py - one-off: copy the old local SQLite data into Supabase.

Reads data/probe.sqlite directly (stdlib sqlite3) and inserts rows into the new
Postgres schema via db.py, preserving primary keys so foreign keys stay intact.
Idempotent (ON CONFLICT DO NOTHING); fixes each id sequence afterward so future
inserts don't collide. Embeddings (JSON text in SQLite) are converted to pgvector.

Run once:  .venv/bin/python migrate_sqlite_to_pg.py
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import db as v0           # Postgres
import store              # for _vec_literal

SQLITE_PATH = Path("data/probe.sqlite")

# (table, columns, fk-order matters). vector columns get a ::vector cast.
TABLES = [
    ("brands", ["id", "name", "category", "created_at", "status", "canonical_name", "error_message"]),
    ("brand_aliases", ["id", "canonical", "alias", "created_at"]),
    ("queries", ["id", "brand_id", "query_text", "created_at"]),
    ("responses", ["id", "query_id", "model", "raw_text", "citations", "phase", "experiment_id", "created_at"]),
    ("parsed_responses", ["id", "response_id", "brands_mentioned", "positions", "descriptors", "parsed_at"]),
    ("context_documents", ["id", "brand_id", "source_type", "title", "raw_text", "created_at"]),
    ("query_panels", ["id", "brand_id", "version", "status", "grounded", "seed_summary", "created_at", "frozen_at"]),
    ("panel_queries", ["id", "panel_id", "query_text", "intent", "created_at"]),
    ("context_chunks", ["id", "brand_id", "document_id", "chunk_text", "embedding", "kind", "created_at"]),
    ("experiments", ["id", "brand_id", "target_query", "candidate_content", "baseline_rate", "treatment_rate", "created_at"]),
]
VECTOR_COLS = {"embedding"}


def _sqlite_tables(sconn) -> set[str]:
    rows = sconn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {r["name"] for r in rows}


def migrate_table(sconn, pconn, table: str, columns: list[str]) -> int:
    src = sconn.execute(f"SELECT * FROM {table}").fetchall()
    if not src:
        print(f"  {table}: 0 rows")
        return 0
    have = set(src[0].keys())
    cols = [c for c in columns if c in have]
    ph = ["%s::vector" if c in VECTOR_COLS else "%s" for c in cols]
    sql = (f"INSERT INTO {table} ({', '.join(cols)}) "
           f"VALUES ({', '.join(ph)}) ON CONFLICT DO NOTHING")
    n = 0
    for row in src:
        vals = []
        for c in cols:
            v = row[c]
            if c == "grounded":
                v = bool(v)
            elif c == "kind":
                v = v or "context"
            elif c in VECTOR_COLS and v:
                try:
                    v = store._vec_literal(json.loads(v))
                except (ValueError, TypeError):
                    v = None
            vals.append(v)
        pconn.execute(sql, vals)
        n += 1
    print(f"  {table}: {n} rows")
    return n


def main() -> None:
    if not SQLITE_PATH.exists():
        print(f"No SQLite file at {SQLITE_PATH} — nothing to migrate.")
        return

    sconn = sqlite3.connect(SQLITE_PATH)
    sconn.row_factory = sqlite3.Row

    print("Ensuring Postgres schema...")
    v0.init_db()

    src_tables = _sqlite_tables(sconn)
    print("Migrating tables (SQLite -> Supabase):")
    with v0.get_conn() as pconn:
        for table, columns in TABLES:
            if table in src_tables:
                migrate_table(sconn, pconn, table, columns)
            else:
                print(f"  {table}: (not in SQLite, skipped)")

        # Fix sequences so future auto-inserts don't collide with migrated ids.
        print("Resetting id sequences...")
        for table, _ in TABLES:
            pconn.execute(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                f"GREATEST((SELECT COALESCE(MAX(id), 1) FROM {table}), 1))"
            )

    sconn.close()
    print("Done.")


if __name__ == "__main__":
    main()
