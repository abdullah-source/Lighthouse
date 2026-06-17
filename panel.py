"""
panel.py - build and freeze a query panel for a brand (v2 depth-based search).

A "panel" is a versioned, frozen set of buyer queries. Freezing is what makes
measurement reproducible and the causal proof possible: every run and every
experiment references the same panel.

Two modes:
- GROUNDED: the brand provided first-party context (reviews, tickets,
  positioning). We generate queries that mirror how *this brand's* real buyers
  ask, and store the context + a seed summary. This is the depth differentiator.
- GENERIC: no context. We fall back to the v0 generator. Still frozen as a
  panel so the rest of the system treats both the same.

build_panel returns the plain query strings the existing probe pipeline consumes,
and persists the panel + (if grounded) the context document.
"""

from __future__ import annotations

import rag
import store
from config import PANEL_SIZE
from queries import generate_grounded_queries, generate_queries

# A broad query used to pull the most informative chunks out of the RAG store
# when grounding panel generation (we want coverage of needs/use-cases/objections,
# not one narrow facet).
_GROUNDING_QUERY = (
    "buyer needs, use cases, comparisons, budget concerns, objections, "
    "product attributes, and who the product is for"
)


def build_panel(brand_id: int, brand: str, category: str,
                context_text: str | None = None) -> dict:
    """
    Build + freeze a panel. Returns:
        {"panel_id": int, "grounded": bool, "queries": [str, ...]}
    """
    context_text = (context_text or "").strip()

    if context_text:
        doc_id = store.save_context(brand_id, context_text)
        # Index into the RAG store, then ground generation on the retrieved,
        # most-informative chunks rather than a blind truncation. Falls back to
        # the raw context if RAG is disabled or returns nothing.
        rag.index_context(brand_id, doc_id, context_text)
        retrieved = rag.retrieve(brand_id, _GROUNDING_QUERY, k=10)
        grounding = "\n\n".join(retrieved) if retrieved else context_text
        result = generate_grounded_queries(brand, category, grounding, count=PANEL_SIZE)
        items = result["queries"]                      # [{intent, query}, ...]
        seed_summary = result["seed_summary"]
        grounded = True
    else:
        raw = generate_queries(brand, category)        # [str, ...]
        items = [{"intent": "general", "query": q} for q in raw]
        seed_summary = ""
        grounded = False

    panel_id = store.create_panel(brand_id, items, grounded=grounded, seed_summary=seed_summary)
    return {
        "panel_id": panel_id,
        "grounded": grounded,
        "queries": [it["query"] for it in items],
    }
