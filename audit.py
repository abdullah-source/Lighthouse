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

        # 2. Probe every query against the available models (async fan-out).
        store.set_status(brand_id, "probing")
        with v0.get_conn() as conn:
            qrows = v0.fetch_queries_for_brand(conn, brand_id)
            pairs = [(r["id"], r["query_text"]) for r in qrows]
        probe_results = asyncio.run(probe_all(pairs))
        with v0.get_conn() as conn:
            for query_id, model, raw_text, citations in probe_results:
                v0.insert_response(conn, query_id, model, raw_text, citations)

        # 3. Parse each response into structured mentions (async fan-out).
        store.set_status(brand_id, "parsing")
        with v0.get_conn() as conn:
            unparsed = v0.fetch_unparsed_responses(conn, brand_id)
            rpairs = [(r["id"], r["raw_text"]) for r in unparsed]
        parse_results = asyncio.run(parse_all(rpairs))
        with v0.get_conn() as conn:
            for response_id, brands, positions, descriptors in parse_results:
                v0.insert_parsed(conn, response_id, brands, positions, descriptors)

        # 4. Sanity check: if we have responses but almost nothing parsed, that
        # was a transient API failure, not a real 0%. Fail honestly instead of
        # reporting a misleading "done" with 0% (the colorful-shoes bug).
        with v0.get_conn() as conn:
            total_text = conn.execute(
                "SELECT COUNT(*) FROM responses r JOIN queries q ON q.id=r.query_id "
                "WHERE q.brand_id=? AND length(r.raw_text)>0",
                (brand_id,),
            ).fetchone()[0]
            parsed_ok = conn.execute(
                "SELECT COUNT(*) FROM parsed_responses p JOIN responses r ON r.id=p.response_id "
                "JOIN queries q ON q.id=r.query_id "
                "WHERE q.brand_id=? AND p.brands_mentioned != '[]'",
                (brand_id,),
            ).fetchone()[0]
        if total_text > 0 and parsed_ok < max(1, total_text // 4):
            store.set_status(
                brand_id, "error",
                error=f"Parsing failed for most responses ({parsed_ok}/{total_text}). "
                      f"Likely a transient API error. Re-run the audit.",
            )
            return

        # Aggregation + normalization happen at read time in store.
        store.set_status(brand_id, "done")
    except Exception as exc:
        store.set_status(brand_id, "error", error=str(exc)[:300])
        print(f"[audit] brand {brand_id} failed:\n{traceback.format_exc()}")
