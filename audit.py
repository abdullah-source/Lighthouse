"""
audit.py - run one full audit end to end.

This is the v0 pipeline (generate -> probe -> parse) wrapped so it can be
driven by the web backend instead of the CLI. The brand row is created by
store.create_brand BEFORE this runs; we just fill it in and move the status
forward so the dashboard can poll progress.

It is a SYNC function on purpose: FastAPI runs it in a background thread, and
the async probe/parse stages run inside their own event loop via asyncio.run.
That keeps the web server's event loop free.
"""

from __future__ import annotations

import asyncio
import time
import traceback

import db as v0
import store
from panel import build_panel
from parse import parse_all
from probe import probe_all


def _build_panel_with_retry(brand_id: int, brand: str, category: str,
                            context: str | None, attempts: int = 3) -> dict:
    """Panel generation is a single API call - a transient blip here used to
    kill the whole audit. Retry with backoff before giving up."""
    last = None
    for i in range(attempts):
        try:
            return build_panel(brand_id, brand, category, context)
        except Exception as exc:  # transient API error, overload, parse miss
            last = exc
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"panel generation failed after {attempts} tries: {last}")


def _probe_parse_finalize(brand_id: int) -> None:
    """
    Probe the brand's existing (frozen) panel, parse, index for RAG, and mark
    done. Shared by run_audit and resume_audit. Only probes queries that don't
    already have responses, so resuming an orphaned run can't duplicate.
    """
    # 2. Probe every query lacking a response (async fan-out).
    store.set_status(brand_id, "probing")
    with v0.get_conn() as conn:
        qrows = conn.execute(
            "SELECT q.id, q.query_text FROM queries q "
            "WHERE q.brand_id = %s "
            "AND NOT EXISTS (SELECT 1 FROM responses r WHERE r.query_id = q.id) "
            "ORDER BY q.id",
            (brand_id,),
        ).fetchall()
        pairs = [(r["id"], r["query_text"]) for r in qrows]
    if pairs:
        # Persist + commit each answer as it arrives so /status can report a live
        # count (responses collected so far) instead of a frozen spinner.
        with v0.get_conn() as conn:
            def _save(result) -> None:
                query_id, model, raw_text, citations = result
                v0.insert_response(conn, query_id, model, raw_text, citations)
                conn.commit()
            asyncio.run(probe_all(pairs, on_result=_save))

    # 3. Parse each unparsed response into structured mentions (async fan-out).
    store.set_status(brand_id, "parsing")
    with v0.get_conn() as conn:
        unparsed = v0.fetch_unparsed_responses(conn, brand_id)
        rpairs = [(r["id"], r["raw_text"]) for r in unparsed]
    if rpairs:
        parse_results = asyncio.run(parse_all(rpairs))
        with v0.get_conn() as conn:
            for response_id, brands, positions, descriptors in parse_results:
                v0.insert_parsed(conn, response_id, brands, positions, descriptors)

    # Index the collected AI answers into the RAG store so Ask works on any
    # audited brand. Best-effort: a failure here must not fail the audit.
    try:
        import rag
        rag.index_responses(brand_id)
    except Exception as exc:
        print(f"[audit] response indexing skipped: {exc}")

    # 4. Sanity check: responses present but almost nothing parsed = transient
    # API failure, not a real 0%. Fail honestly (the colorful-shoes bug).
    with v0.get_conn() as conn:
        total_text = conn.execute(
            "SELECT COUNT(*) AS n FROM responses r JOIN queries q ON q.id=r.query_id "
            "WHERE q.brand_id=%s AND length(r.raw_text)>0",
            (brand_id,),
        ).fetchone()["n"]
        parsed_ok = conn.execute(
            "SELECT COUNT(*) AS n FROM parsed_responses p JOIN responses r ON r.id=p.response_id "
            "JOIN queries q ON q.id=r.query_id "
            "WHERE q.brand_id=%s AND p.brands_mentioned <> '[]'",
            (brand_id,),
        ).fetchone()["n"]
    if total_text > 0 and parsed_ok < max(1, total_text // 4):
        store.set_status(
            brand_id, "error",
            error=f"Parsing failed for most responses ({parsed_ok}/{total_text}). "
                  f"Likely a transient API error. Re-run the audit.",
        )
        return

    # Mark done + snapshot the headline metric for the fast list view.
    store.set_status(brand_id, "done")
    try:
        store.refresh_brand_metrics(brand_id)
    except Exception as exc:
        print(f"[audit] metric refresh skipped: {exc}")


def run_audit(brand_id: int, brand: str, category: str, context: str | None = None) -> None:
    """Build a frozen query panel, probe the models, parse, and mark done.

    If `context` is provided, the panel is GROUNDED in the brand's own customer
    language (depth-based search); otherwise it falls back to a generic panel.
    """
    try:
        # 1. Build + freeze the query panel (one Sonnet call, retried).
        store.set_status(brand_id, "generating")
        panel = _build_panel_with_retry(brand_id, brand, category, context)
        with v0.get_conn() as conn:
            for q in panel["queries"]:
                v0.insert_query(conn, brand_id, q)
        _probe_parse_finalize(brand_id)
    except Exception as exc:
        store.set_status(brand_id, "error", error=str(exc)[:300])
        print(f"[audit] brand {brand_id} failed:\n{traceback.format_exc()}")


def resume_audit(brand_id: int) -> None:
    """Resume an orphaned audit (e.g. stuck at 'probing' after a restart) from
    its already-saved panel — re-probe the queries that have no responses yet."""
    try:
        _probe_parse_finalize(brand_id)
    except Exception as exc:
        store.set_status(brand_id, "error", error=str(exc)[:300])
        print(f"[audit] resume of brand {brand_id} failed:\n{traceback.format_exc()}")
