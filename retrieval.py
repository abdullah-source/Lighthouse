"""
retrieval.py — the retrieval-simulation product surface (validated cosine core).

Reconstructs the retrieval step behind an answer engine: for a brand's audited
queries, rank the candidate pages by our own embedding retrieval and compare to
the pages the engine ACTUALLY cited. Output per query: the reconstructed ranking,
which pages were really cited, and an aggregate fidelity number (how well our
reconstruction predicts real citations) so the "why" is honestly grounded.

We ship the cosine core (validated: ~7.8x random, distractor-robust). The learned
ranker is a future upgrade gated on citation data scale.

Page text is cached in Postgres (retrieval_cache) when the table exists; if it
doesn't (e.g. before the admin migration, since the app role can't run DDL), we
fall back to live fetch. Embeddings are cheap so we re-embed on use.
"""
from __future__ import annotations

import asyncio
import re
from urllib.parse import urlparse

import httpx
import numpy as np

import rag
import store

UA = "Mozilla/5.0 (compatible; LighthouseBot/0.1)"


def _html_to_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|noscript|svg).*?</\1>", " ", html)
    return re.sub(r"\s+", " ", re.sub(r"(?s)<[^>]+>", " ", html)).strip()


async def _fetch_one(client, url):
    try:
        r = await client.get(url, timeout=10, follow_redirects=True,
                             headers={"User-Agent": UA})
        if r.status_code == 200 and "text/html" in r.headers.get("content-type", ""):
            return url, _html_to_text(r.text)[:16000]
    except Exception:
        pass
    return url, None


async def _fetch_many(urls):
    out = {}
    sem = asyncio.Semaphore(8)
    async with httpx.AsyncClient() as client:
        async def one(u):
            async with sem:
                return await _fetch_one(client, u)
        for coro in asyncio.as_completed([one(u) for u in urls]):
            u, t = await coro
            out[u] = t
    return out


def _get_pages(urls: list[str]) -> dict[str, str]:
    """Return {url: text} using the cache table when present, fetching misses."""
    cached = store.get_cached_pages(urls)          # graceful: {} if table absent
    missing = [u for u in urls if u not in cached or not cached[u]]
    if missing:
        fetched = asyncio.run(_fetch_many(missing))
        got = {u: t for u, t in fetched.items() if t}
        if got:
            store.save_cached_pages(got)           # graceful no-op if table absent
        cached.update(got)
    return {u: t for u, t in cached.items() if t}


def _cos_max(qv: np.ndarray, M: np.ndarray) -> float:
    qn = qv / (np.linalg.norm(qv) + 1e-9)
    Mn = M / (np.linalg.norm(M, axis=1, keepdims=True) + 1e-9)
    return float((Mn @ qn).max())


def reconstruct_for_brand(brand_id: int, max_queries: int = 5) -> dict:
    """For up to max_queries of the brand's queries that carry real citations,
    reconstruct the retrieval ranking and score fidelity against the citations."""
    gt = store.get_query_citations(brand_id)       # {query_text: [urls]}
    gt = {q: us for q, us in gt.items() if us}
    if not gt:
        return {"queries": [], "fidelity": None,
                "note": "No cited queries yet — run an audit with Perplexity enabled."}
    items = list(gt.items())[:max_queries]
    corpus = sorted({u for _, us in items for u in us})
    pages = _get_pages(corpus)
    if not pages:
        return {"queries": [], "fidelity": None, "note": "Could not fetch candidate pages."}

    # embed page chunks
    texts, idx = [], []
    for u, t in pages.items():
        for ch in (rag.chunk_text(t) or [])[:6]:
            texts.append(ch); idx.append(u)
    V = np.array(rag.embed_texts(texts), dtype=np.float32)
    page_vecs: dict[str, np.ndarray] = {}
    for u in pages:
        vs = [V[i] for i in range(len(idx)) if idx[i] == u]
        if vs:
            page_vecs[u] = np.array(vs)
    ranked_pool = [u for u in pages if u in page_vecs]

    qvecs = np.array(rag.embed_texts([q for q, _ in items]), dtype=np.float32)
    p_at_3 = []
    out_queries = []
    for (q, cited), qv in zip(items, qvecs):
        cited_set = {u for u in cited if u in page_vecs}
        scored = sorted(((round(_cos_max(qv, page_vecs[u]), 3), u) for u in ranked_pool),
                        reverse=True)
        ranked = [{"url": u, "domain": urlparse(u).netloc, "score": s,
                   "cited": u in cited_set} for s, u in scored[:8]]
        if cited_set:
            top3 = {r["url"] for r in ranked[:3]}
            p_at_3.append(len(top3 & cited_set) / 3.0)
        out_queries.append({"query": q, "n_cited": len(cited_set), "ranked": ranked})

    fidelity = None
    if p_at_3:
        rand = np.mean([q["n_cited"] for q in out_queries]) / max(1, len(ranked_pool))
        ours = float(np.mean(p_at_3))
        fidelity = {"precision_at_3": round(ours, 3),
                    "random_baseline": round(float(rand), 3),
                    "lift": round(ours / rand, 1) if rand else None,
                    "corpus_pages": len(ranked_pool)}
    return {"queries": out_queries, "fidelity": fidelity,
            "method": "cosine",
            "note": "Reconstructed retrieval (cosine core). Fidelity = how well our "
                    "ranking predicts the pages the engine actually cited."}
