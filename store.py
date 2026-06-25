"""
store.py - the v2 database layer (Postgres + pgvector via db.py).

Adds on top of db.py's schema:
  - brand/audit lifecycle with a status field
  - a learned brand-alias table (persists the Brooks fix over time)
  - context ingestion + frozen, versioned query panels (depth-based search)
  - a pgvector-backed RAG chunk store (context + collected AI responses)
  - read-time aggregation that powers the dashboard, with normalization,
    off-site provenance, and the lexical "verbal vibes"

Read-time normalization: we canonicalize brand mentions when we aggregate,
not when we store, so improving brand_identity.py re-fixes old data.
"""

from __future__ import annotations

import json
from urllib.parse import urlparse

import db as v0
from brand_identity import BrandResolver, _norm_key


# --- Migration --------------------------------------------------------------

def migrate() -> None:
    """Create the full schema if needed. (db.py holds the canonical schema.)"""
    v0.init_db()


# --- Brand / audit lifecycle ------------------------------------------------

def create_brand(name: str, category: str) -> int:
    """Insert a brand row in 'pending' status. Returns brand_id."""
    canon = BrandResolver(known_brands=[name]).canonicalize(name)
    with v0.get_conn() as conn:
        row = conn.execute(
            "INSERT INTO brands (name, category, status, canonical_name) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (name, category, "pending", canon),
        ).fetchone()
        return row["id"]


def set_status(brand_id: int, status: str, error: str | None = None) -> None:
    with v0.get_conn() as conn:
        conn.execute(
            "UPDATE brands SET status = %s, error_message = %s WHERE id = %s",
            (status, error, brand_id),
        )


def get_sample_query(brand_id: int) -> str | None:
    """A representative buyer query for the brand, used to seed action artifacts."""
    with v0.get_conn() as conn:
        row = conn.execute(
            "SELECT query_text FROM queries WHERE brand_id = %s ORDER BY id LIMIT 1",
            (brand_id,),
        ).fetchone()
    return row["query_text"] if row else None


def get_brand(brand_id: int) -> dict | None:
    with v0.get_conn() as conn:
        return conn.execute(
            "SELECT id, name, category, created_at, status, canonical_name, error_message "
            "FROM brands WHERE id = %s",
            (brand_id,),
        ).fetchone()


def list_brands() -> list[dict]:
    """
    All audited brands, newest first, with the denormalized headline metric.
    One cheap query — we read mention_rate/total_responses straight off the
    brand row (set by refresh_brand_metrics at audit time) instead of running
    the full aggregate per brand (which is an N+1 explosion over a remote DB).
    """
    with v0.get_conn() as conn:
        rows = conn.execute(
            "SELECT id, name, category, created_at, COALESCE(status,'done') AS status, "
            "mention_rate, total_responses FROM brands ORDER BY id DESC"
        ).fetchall()
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "category": r["category"],
            "created_at": r["created_at"],
            "status": r["status"],
            "mention_rate": r["mention_rate"],
            "responses": r["total_responses"] or 0,
        }
        for r in rows
    ]


def refresh_brand_metrics(brand_id: int) -> None:
    """Recompute and store the headline metric on the brand row (called when an
    audit finishes, and by the backfill). Keeps list_brands O(1) per row."""
    agg = aggregate_brand(brand_id)
    if not agg:
        return
    with v0.get_conn() as conn:
        conn.execute(
            "UPDATE brands SET mention_rate = %s, total_responses = %s WHERE id = %s",
            (agg.get("mention_rate"), agg.get("total_responses"), brand_id),
        )


# --- Alias persistence ------------------------------------------------------

def load_aliases() -> dict[str, str]:
    with v0.get_conn() as conn:
        rows = conn.execute("SELECT alias, canonical FROM brand_aliases").fetchall()
    return {r["alias"]: r["canonical"] for r in rows}


def save_aliases(mapping: dict[str, str]) -> None:
    """
    Persist raw->canonical mappings where they actually changed something.
    Batched into one executemany round-trip (this runs in the read path, so
    a per-row loop over a remote DB was the dashboard's slow point).
    """
    # Only learn meaningful aliases: a raw form that normalizes to a DIFFERENT
    # key than the canonical (e.g. "On Cloudmonster" -> "On"). Skip pure
    # casing/whitespace variants ("On" vs "ON").
    rows = [
        (canon, raw) for raw, canon in mapping.items()
        if raw and canon and _norm_key(raw) != _norm_key(canon)
    ]
    if not rows:
        return
    with v0.get_conn() as conn:
        conn.cursor().executemany(
            "INSERT INTO brand_aliases (canonical, alias) VALUES (%s, %s) "
            "ON CONFLICT (alias) DO NOTHING",
            rows,
        )


# --- Context + frozen panels (v2 depth-based search) ------------------------

def save_context(brand_id: int, raw_text: str, source_type: str = "paste",
                 title: str | None = None) -> int:
    with v0.get_conn() as conn:
        row = conn.execute(
            "INSERT INTO context_documents (brand_id, source_type, title, raw_text) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (brand_id, source_type, title, raw_text),
        ).fetchone()
        return row["id"]


def create_panel(brand_id: int, queries: list[dict], grounded: bool,
                 seed_summary: str = "") -> int:
    """
    Persist a frozen, versioned panel. `queries` is [{intent, query}, ...].
    Version auto-increments per brand. Returns panel_id.
    """
    with v0.get_conn() as conn:
        row = conn.execute(
            "SELECT COALESCE(MAX(version), 0) AS v FROM query_panels WHERE brand_id = %s",
            (brand_id,),
        ).fetchone()
        version = (row["v"] or 0) + 1
        prow = conn.execute(
            "INSERT INTO query_panels (brand_id, version, status, grounded, seed_summary, frozen_at) "
            "VALUES (%s, %s, 'frozen', %s, %s, now()) RETURNING id",
            (brand_id, version, grounded, seed_summary),
        ).fetchone()
        panel_id = prow["id"]
        for q in queries:
            conn.execute(
                "INSERT INTO panel_queries (panel_id, query_text, intent) VALUES (%s, %s, %s)",
                (panel_id, q["query"], q.get("intent") or "general"),
            )
    return panel_id


def get_active_panel(brand_id: int) -> dict | None:
    """The latest frozen panel for a brand, with a small summary for the UI."""
    with v0.get_conn() as conn:
        p = conn.execute(
            "SELECT id, version, grounded, seed_summary, frozen_at "
            "FROM query_panels WHERE brand_id = %s ORDER BY version DESC LIMIT 1",
            (brand_id,),
        ).fetchone()
        if p is None:
            return None
        n = conn.execute(
            "SELECT COUNT(*) AS c FROM panel_queries WHERE panel_id = %s", (p["id"],)
        ).fetchone()["c"]
    return {
        "panel_id": p["id"],
        "version": p["version"],
        "grounded": bool(p["grounded"]),
        "seed_summary": p["seed_summary"] or "",
        "query_count": n,
        "frozen_at": p["frozen_at"],
    }


# --- RAG chunk store (pgvector) ---------------------------------------------

def _vec_literal(emb: list[float]) -> str:
    """Render an embedding as a pgvector text literal: [0.1,0.2,...]."""
    return "[" + ",".join(repr(float(x)) for x in emb) + "]"


def save_chunks(brand_id: int, document_id: int | None,
                items: list[tuple[str, list[float]]], kind: str = "context") -> int:
    """
    Persist (chunk_text, embedding) pairs. `kind` is 'context' (first-party) or
    'response' (collected AI answers). Embeddings go into a pgvector column.
    """
    with v0.get_conn() as conn:
        for text, emb in items:
            conn.execute(
                "INSERT INTO context_chunks (brand_id, document_id, chunk_text, embedding, kind) "
                "VALUES (%s, %s, %s, %s::vector, %s)",
                (brand_id, document_id, text, _vec_literal(emb), kind),
            )
    return len(items)


def delete_chunks(brand_id: int, kind: str) -> None:
    """Drop a brand's chunks of one kind (so re-indexing is idempotent)."""
    with v0.get_conn() as conn:
        conn.execute("DELETE FROM context_chunks WHERE brand_id = %s AND kind = %s", (brand_id, kind))


def search_chunks(brand_id: int, query_vec: list[float], k: int = 6,
                  kinds: list[str] | None = None) -> list[str]:
    """
    pgvector cosine search: top-k chunk texts nearest the query embedding.
    kinds=None searches everything (Ask); ['context'] = first-party only.
    """
    sql = "SELECT chunk_text FROM context_chunks WHERE brand_id = %s AND embedding IS NOT NULL"
    params: list = [brand_id]
    if kinds:
        sql += " AND kind = ANY(%s)"
        params.append(kinds)
    sql += " ORDER BY embedding <=> %s::vector LIMIT %s"
    params += [_vec_literal(query_vec), k]
    with v0.get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [r["chunk_text"] for r in rows]


def fetch_response_texts(brand_id: int) -> list[str]:
    """The raw AI answers collected for a brand (for RAG over what engines said)."""
    with v0.get_conn() as conn:
        rows = conn.execute(
            "SELECT r.raw_text FROM responses r JOIN queries q ON q.id = r.query_id "
            "WHERE q.brand_id = %s AND length(r.raw_text) > 0",
            (brand_id,),
        ).fetchall()
    return [r["raw_text"] for r in rows]


# --- Source provenance (the "why": which pages the AI cites) ----------------

def _domain(url: str) -> str:
    """Bare domain for grouping: https://www.runrepeat.com/x -> runrepeat.com."""
    try:
        net = urlparse(url).netloc.lower()
    except Exception:
        return ""
    return net[4:] if net.startswith("www.") else net


def _build_provenance(rows: list) -> dict:
    """
    Roll up the cited sources across a brand's retrieval answers into a ranked
    list of domains. This is the off-site "why": the pages the engine trusts.
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

        # Defensive: the model can occasionally return a non-conforming shape
        # (a string instead of a list/object). Coerce to the expected types so
        # one odd response never 500s the whole dashboard.
        try:
            raw_brands = json.loads(r["brands_mentioned"]) if r["brands_mentioned"] else []
        except (ValueError, TypeError):
            raw_brands = []
        if not isinstance(raw_brands, list):
            raw_brands = []
        try:
            positions = json.loads(r["positions"]) if r["positions"] else {}
        except (ValueError, TypeError):
            positions = {}
        if not isinstance(positions, dict):
            positions = {}
        try:
            descriptors = json.loads(r["descriptors"]) if r["descriptors"] else {}
        except (ValueError, TypeError):
            descriptors = {}
        if not isinstance(descriptors, dict):
            descriptors = {}
        # attribute each descriptor term to the focal brand or to competitors,
        # by canonicalizing the brand key the term was attached to.
        for raw_b, terms in descriptors.items():
            canon_b = resolver.canonicalize(raw_b)
            if not canon_b:
                continue
            bucket = lex_focal if canon_b.casefold() == focal_cf else lex_comp
            for t in (terms if isinstance(terms, list) else []):
                t = (t or "").strip().lower() if isinstance(t, str) else ""
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
