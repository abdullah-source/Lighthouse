"""
store.py - v1 database layer.

Sits on top of the v0 db.py (same SQLite file) and adds:
  - an idempotent migration (new columns + tables, existing data preserved)
  - brand/audit lifecycle with a status field
  - a learned brand-alias table (persists the Brooks fix over time)
  - the aggregation that powers the dashboard, with normalization applied
  - an experiments scaffold for the causal layer

Read-time normalization: we canonicalize brand mentions when we aggregate,
not when we store. That way improving brand_identity.py re-fixes old data
without re-probing.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from urllib.parse import urlparse

import db as v0
from brand_identity import BrandResolver, _norm_key


# --- Migration --------------------------------------------------------------

def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def migrate() -> None:
    """Create v0 tables, then add v1 columns/tables. Safe to run repeatedly."""
    v0.init_db()  # ensures brands/queries/responses/parsed_responses exist
    with v0.get_conn() as conn:
        bcols = _columns(conn, "brands")
        if "status" not in bcols:
            conn.execute("ALTER TABLE brands ADD COLUMN status TEXT")
        if "canonical_name" not in bcols:
            conn.execute("ALTER TABLE brands ADD COLUMN canonical_name TEXT")
        if "error_message" not in bcols:
            conn.execute("ALTER TABLE brands ADD COLUMN error_message TEXT")

        rcols = _columns(conn, "responses")
        if "phase" not in rcols:
            conn.execute("ALTER TABLE responses ADD COLUMN phase TEXT DEFAULT 'baseline'")
        if "experiment_id" not in rcols:
            conn.execute("ALTER TABLE responses ADD COLUMN experiment_id INTEGER")
        if "citations" not in rcols:
            conn.execute("ALTER TABLE responses ADD COLUMN citations TEXT")

        pcols = _columns(conn, "parsed_responses")
        if "descriptors" not in pcols:
            conn.execute("ALTER TABLE parsed_responses ADD COLUMN descriptors TEXT")

        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS brand_aliases (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                canonical   TEXT NOT NULL,
                alias       TEXT NOT NULL UNIQUE,
                created_at  TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS experiments (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                brand_id        INTEGER NOT NULL REFERENCES brands(id),
                target_query    TEXT NOT NULL,
                candidate_content TEXT,
                baseline_rate   REAL,
                treatment_rate  REAL,
                created_at      TEXT NOT NULL
            );
            -- v2 depth-based search: ingested first-party context + the frozen,
            -- versioned query panels generated (and grounded) from it.
            CREATE TABLE IF NOT EXISTS context_documents (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                brand_id    INTEGER NOT NULL REFERENCES brands(id),
                source_type TEXT,
                title       TEXT,
                raw_text    TEXT NOT NULL,
                created_at  TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS query_panels (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                brand_id     INTEGER NOT NULL REFERENCES brands(id),
                version      INTEGER NOT NULL,
                status       TEXT NOT NULL,          -- 'frozen'
                grounded     INTEGER NOT NULL DEFAULT 0,
                seed_summary TEXT,
                created_at   TEXT NOT NULL,
                frozen_at    TEXT
            );
            CREATE TABLE IF NOT EXISTS panel_queries (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                panel_id    INTEGER NOT NULL REFERENCES query_panels(id),
                query_text  TEXT NOT NULL,
                intent      TEXT,
                created_at  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_panel_queries_panel ON panel_queries(panel_id);
            CREATE INDEX IF NOT EXISTS idx_query_panels_brand ON query_panels(brand_id);
            -- RAG vector store. embedding is a JSON float array here (SQLite);
            -- this maps 1:1 onto a pgvector `vector(1536)` column when we deploy.
            CREATE TABLE IF NOT EXISTS context_chunks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                brand_id    INTEGER NOT NULL REFERENCES brands(id),
                document_id INTEGER REFERENCES context_documents(id),
                chunk_text  TEXT NOT NULL,
                embedding   TEXT NOT NULL,        -- JSON array of floats
                created_at  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_context_chunks_brand ON context_chunks(brand_id);
            """
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- Brand / audit lifecycle ------------------------------------------------

def create_brand(name: str, category: str) -> int:
    """Insert a brand row in 'pending' status. Returns brand_id."""
    canon = BrandResolver(known_brands=[name]).canonicalize(name)
    with v0.get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO brands (name, category, created_at, status, canonical_name) "
            "VALUES (?, ?, ?, ?, ?)",
            (name, category, _now(), "pending", canon),
        )
        return cur.lastrowid


def set_status(brand_id: int, status: str, error: str | None = None) -> None:
    with v0.get_conn() as conn:
        conn.execute(
            "UPDATE brands SET status = ?, error_message = ? WHERE id = ?",
            (status, error, brand_id),
        )


def get_sample_query(brand_id: int) -> str | None:
    """A representative buyer query for the brand, used to seed action artifacts."""
    with v0.get_conn() as conn:
        row = conn.execute(
            "SELECT query_text FROM queries WHERE brand_id = ? ORDER BY id LIMIT 1",
            (brand_id,),
        ).fetchone()
    return row["query_text"] if row else None


def get_brand(brand_id: int) -> sqlite3.Row | None:
    with v0.get_conn() as conn:
        return conn.execute(
            "SELECT id, name, category, created_at, status, canonical_name, error_message "
            "FROM brands WHERE id = ?",
            (brand_id,),
        ).fetchone()


def list_brands() -> list[dict]:
    """All audited brands, newest first, with a headline mention rate."""
    with v0.get_conn() as conn:
        rows = conn.execute(
            "SELECT id, name, category, created_at, COALESCE(status,'done') AS status "
            "FROM brands ORDER BY id DESC"
        ).fetchall()
    out = []
    for r in rows:
        agg = aggregate_brand(r["id"]) if r["status"] in ("done", None) else None
        out.append(
            {
                "id": r["id"],
                "name": r["name"],
                "category": r["category"],
                "created_at": r["created_at"],
                "status": r["status"],
                "mention_rate": agg["mention_rate"] if agg else None,
                "responses": agg["total_responses"] if agg else 0,
            }
        )
    return out


# --- Alias persistence ------------------------------------------------------

def load_aliases() -> dict[str, str]:
    with v0.get_conn() as conn:
        rows = conn.execute("SELECT alias, canonical FROM brand_aliases").fetchall()
    return {r["alias"]: r["canonical"] for r in rows}


def save_aliases(mapping: dict[str, str]) -> None:
    """Persist raw->canonical mappings where they actually changed something."""
    with v0.get_conn() as conn:
        for raw, canon in mapping.items():
            # Only learn a meaningful alias: a raw form that normalizes to a
            # DIFFERENT key than the canonical (e.g. "On Cloudmonster" -> "On").
            # Skip pure casing/whitespace variants ("On" vs "ON"), which would
            # poison resolution by overriding the seed casing.
            if raw and canon and _norm_key(raw) != _norm_key(canon):
                conn.execute(
                    "INSERT OR IGNORE INTO brand_aliases (canonical, alias, created_at) "
                    "VALUES (?, ?, ?)",
                    (canon, raw, _now()),
                )


# --- Context + frozen panels (v2 depth-based search) ------------------------

def save_context(brand_id: int, raw_text: str, source_type: str = "paste",
                 title: str | None = None) -> int:
    with v0.get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO context_documents (brand_id, source_type, title, raw_text, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (brand_id, source_type, title, raw_text, _now()),
        )
        return cur.lastrowid


def create_panel(brand_id: int, queries: list[dict], grounded: bool,
                 seed_summary: str = "") -> int:
    """
    Persist a frozen, versioned panel. `queries` is [{intent, query}, ...].
    Version auto-increments per brand. Returns panel_id.
    """
    now = _now()
    with v0.get_conn() as conn:
        row = conn.execute(
            "SELECT COALESCE(MAX(version), 0) AS v FROM query_panels WHERE brand_id = ?",
            (brand_id,),
        ).fetchone()
        version = (row["v"] or 0) + 1
        cur = conn.execute(
            "INSERT INTO query_panels (brand_id, version, status, grounded, seed_summary, "
            "created_at, frozen_at) VALUES (?, ?, 'frozen', ?, ?, ?, ?)",
            (brand_id, version, 1 if grounded else 0, seed_summary, now, now),
        )
        panel_id = cur.lastrowid
        for q in queries:
            conn.execute(
                "INSERT INTO panel_queries (panel_id, query_text, intent, created_at) "
                "VALUES (?, ?, ?, ?)",
                (panel_id, q["query"], q.get("intent") or "general", now),
            )
    return panel_id


def save_chunks(brand_id: int, document_id: int,
                items: list[tuple[str, list[float]]]) -> int:
    """Persist (chunk_text, embedding) pairs for the RAG store. Returns count."""
    now = _now()
    with v0.get_conn() as conn:
        for text, emb in items:
            conn.execute(
                "INSERT INTO context_chunks (brand_id, document_id, chunk_text, embedding, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (brand_id, document_id, text, json.dumps(emb), now),
            )
    return len(items)


def fetch_chunks(brand_id: int) -> list[tuple[str, list[float]]]:
    """All (chunk_text, embedding) for a brand, for in-process cosine retrieval."""
    with v0.get_conn() as conn:
        rows = conn.execute(
            "SELECT chunk_text, embedding FROM context_chunks WHERE brand_id = ?",
            (brand_id,),
        ).fetchall()
    out: list[tuple[str, list[float]]] = []
    for r in rows:
        try:
            out.append((r["chunk_text"], json.loads(r["embedding"])))
        except (ValueError, TypeError):
            continue
    return out


def get_active_panel(brand_id: int) -> dict | None:
    """The latest frozen panel for a brand, with a small summary for the UI."""
    with v0.get_conn() as conn:
        p = conn.execute(
            "SELECT id, version, grounded, seed_summary, frozen_at "
            "FROM query_panels WHERE brand_id = ? ORDER BY version DESC LIMIT 1",
            (brand_id,),
        ).fetchone()
        if p is None:
            return None
        n = conn.execute(
            "SELECT COUNT(*) AS c FROM panel_queries WHERE panel_id = ?", (p["id"],)
        ).fetchone()["c"]
    return {
        "panel_id": p["id"],
        "version": p["version"],
        "grounded": bool(p["grounded"]),
        "seed_summary": p["seed_summary"] or "",
        "query_count": n,
        "frozen_at": p["frozen_at"],
    }


# --- Source provenance (the "why": which pages the AI cites) ----------------

def _domain(url: str) -> str:
    """Bare domain for grouping: https://www.runrepeat.com/x -> runrepeat.com."""
    try:
        net = urlparse(url).netloc.lower()
    except Exception:
        return ""
    return net[4:] if net.startswith("www.") else net


def _build_provenance(rows: list[sqlite3.Row]) -> dict:
    """
    Roll up the cited sources across a brand's retrieval answers into a ranked
    list of domains. This is the off-site "why": the pages the engine trusts
    when it answers buyer questions in this category.
    """
    domain_count: dict[str, int] = {}
    domain_url: dict[str, str] = {}
    engines: set[str] = set()
    total = 0
    responses_with = 0

    for r in rows:
        try:
            cites = json.loads(r["citations"]) if r["citations"] else []
        except (ValueError, TypeError):
            cites = []
        if not cites:
            continue
        responses_with += 1
        engines.add(r["model"])
        for c in cites:
            url = c.get("url") if isinstance(c, dict) else (c if isinstance(c, str) else None)
            if not url:
                continue
            dom = _domain(url)
            if not dom:
                continue
            total += 1
            domain_count[dom] = domain_count.get(dom, 0) + 1
            domain_url.setdefault(dom, url)

    top_sources = sorted(
        ({"domain": d, "url": domain_url[d], "count": n} for d, n in domain_count.items()),
        key=lambda s: s["count"],
        reverse=True,
    )[:12]

    return {
        "total_citations": total,
        "responses_with_sources": responses_with,
        "unique_sources": len(domain_count),
        "engines": sorted(engines),
        "top_sources": top_sources,
    }


# --- Lexical environment (the "verbal vibes") -------------------------------

def _build_lexical(lex_focal: dict[str, int], lex_comp: dict[str, int]) -> dict:
    """
    Turn raw term counts into the 'verbal vibes' payload:
    - focal_top: how AI describes YOU (ranked terms)
    - you_own:   vibes where you lead competitors (the lean-in action)
    - they_own:  vibes competitors own that you don't
    """
    def ranked(d: dict[str, int], n: int = 18) -> list[dict]:
        return [{"term": t, "count": c}
                for t, c in sorted(d.items(), key=lambda kv: kv[1], reverse=True)[:n]]

    you_own = [
        {"term": t, "count": c, "lead": c - lex_comp.get(t, 0)}
        for t, c in lex_focal.items() if c >= lex_comp.get(t, 0)
    ]
    you_own.sort(key=lambda x: (x["lead"], x["count"]), reverse=True)

    they_own = [
        {"term": t, "count": c, "lead": c - lex_focal.get(t, 0)}
        for t, c in lex_comp.items() if c > lex_focal.get(t, 0)
    ]
    they_own.sort(key=lambda x: (x["lead"], x["count"]), reverse=True)

    focal_top = ranked(lex_focal)
    max_count = max([x["count"] for x in focal_top], default=0)
    return {
        "focal_top": focal_top,
        "you_own": you_own[:12],
        "they_own": they_own[:12],
        "max_count": max_count,
        "focal_term_count": len(lex_focal),
    }


# --- Aggregation (the dashboard payload) ------------------------------------

def aggregate_brand(brand_id: int) -> dict:
    """
    Compute the dashboard metrics for a brand, with brand-identity
    normalization applied. This is where the Brooks fix shows up.
    """
    brand = get_brand(brand_id)
    if brand is None:
        return {}

    with v0.get_conn() as conn:
        rows = v0.fetch_parsed_for_brand(conn, brand_id)
        citation_rows = v0.fetch_citations_for_brand(conn, brand_id)

    aliases = load_aliases()
    resolver = BrandResolver(known_brands=[brand["name"]], aliases=aliases)
    focal = resolver.canonicalize(brand["name"])
    focal_cf = focal.casefold()  # compare on a case-insensitive key, not display

    total = len(rows)
    raw_variants: set[str] = set()
    canon_brands: set[str] = set()
    focal_hits = 0
    focal_positions: list[int] = []
    total_canon_mentions = 0

    # by model
    model_total: dict[str, int] = {}
    model_focal: dict[str, int] = {}
    # competitors: canonical brand -> [responses mentioning, positions]
    comp_hits: dict[str, int] = {}
    comp_positions: dict[str, list[int]] = {}
    learned: dict[str, str] = {}
    # lexical environment ("verbal vibes"): canonical brand -> {term: count}
    lex_focal: dict[str, int] = {}
    lex_comp: dict[str, int] = {}

    for r in rows:
        model = r["model"]
        model_total[model] = model_total.get(model, 0) + 1

        raw_brands = json.loads(r["brands_mentioned"]) if r["brands_mentioned"] else []
        positions = json.loads(r["positions"]) if r["positions"] else {}
        try:
            descriptors = json.loads(r["descriptors"]) if r["descriptors"] else {}
        except (ValueError, TypeError):
            descriptors = {}
        # attribute each descriptor term to the focal brand or to competitors,
        # by canonicalizing the brand key the term was attached to.
        for raw_b, terms in (descriptors or {}).items():
            canon_b = resolver.canonicalize(raw_b)
            if not canon_b:
                continue
            bucket = lex_focal if canon_b.casefold() == focal_cf else lex_comp
            for t in terms or []:
                t = (t or "").strip().lower()
                if t:
                    bucket[t] = bucket.get(t, 0) + 1

        # canonicalize this response's mentions
        canon_to_pos: dict[str, int] = {}
        for raw in raw_brands:
            raw_variants.add(raw)
            canon = resolver.canonicalize(raw)
            if not canon:
                continue
            if raw != canon:
                learned[raw] = canon
            pos = positions.get(raw)
            if isinstance(pos, int):
                # collapse: keep the best (lowest) position per canonical brand
                if canon not in canon_to_pos or pos < canon_to_pos[canon]:
                    canon_to_pos[canon] = pos

        present = set(canon_to_pos.keys()) | {
            resolver.canonicalize(b) for b in raw_brands
        }
        present.discard("")
        canon_brands |= present
        total_canon_mentions += len(present)

        if focal_cf in {p.casefold() for p in present}:
            focal_hits += 1
            model_focal[model] = model_focal.get(model, 0) + 1
            fpos = [canon_to_pos[k] for k in canon_to_pos if k.casefold() == focal_cf]
            if fpos:
                focal_positions.append(min(fpos))

        for b in present:
            if b.casefold() == focal_cf:
                continue
            comp_hits[b] = comp_hits.get(b, 0) + 1
            if b in canon_to_pos:
                comp_positions.setdefault(b, []).append(canon_to_pos[b])

    # persist anything we learned so the fix compounds
    if learned:
        save_aliases(learned)

    def avg(xs: list[int]) -> float | None:
        return round(sum(xs) / len(xs), 2) if xs else None

    competitors = sorted(
        (
            {
                "brand": b,
                "mentions": n,
                "rate": round(n / total, 3) if total else 0,
                "avg_position": avg(comp_positions.get(b, [])),
            }
            for b, n in comp_hits.items()
        ),
        key=lambda c: c["mentions"],
        reverse=True,
    )

    by_model = [
        {
            "model": m,
            "responses": model_total[m],
            "mentions": model_focal.get(m, 0),
            "rate": round(model_focal.get(m, 0) / model_total[m], 3) if model_total[m] else 0,
        }
        for m in sorted(model_total)
    ]

    return {
        "brand_id": brand_id,
        "name": brand["name"],
        "category": brand["category"],
        "status": brand["status"] or "done",
        "focal_canonical": focal,
        "total_responses": total,
        "mention_rate": round(focal_hits / total, 3) if total else 0,
        "mentions": focal_hits,
        "avg_position": avg(focal_positions),
        "share_of_voice": round(focal_hits / total_canon_mentions, 3) if total_canon_mentions else 0,
        "by_model": by_model,
        "competitors": competitors[:8],
        "normalization": {
            "raw_variants": len(raw_variants),
            "canonical_brands": len(canon_brands),
            "merged": len(raw_variants) - len(canon_brands),
        },
        "provenance": _build_provenance(citation_rows),
        "panel": get_active_panel(brand_id),
        "lexical": _build_lexical(lex_focal, lex_comp),
    }


if __name__ == "__main__":
    migrate()
    print("migrated. brands:")
    for b in list_brands():
        print(f"  [{b['id']}] {b['name']} ({b['category']}) "
              f"status={b['status']} rate={b['mention_rate']}")
