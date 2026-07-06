-- Migration 001 — retrieval-simulation page cache.
-- Run ONCE in the Supabase SQL Editor as the `postgres` role. The app runtime
-- role (app_user) is least-privilege and cannot run DDL, so schema changes go
-- through an admin here. app_user already has default DML privileges on new
-- public tables, so no extra GRANT is needed.

CREATE TABLE IF NOT EXISTS retrieval_cache (
    url            TEXT PRIMARY KEY,
    domain         TEXT,
    text           TEXT,
    published_date TEXT,
    fetched_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Match the security posture of the rest of the schema.
ALTER TABLE retrieval_cache ENABLE ROW LEVEL SECURITY;
