"""
retrieval_fidelity.py — does our local retrieval predict what the engine cites?

This is the go/no-go experiment behind the retrieval-simulation wedge.

For a brand we've audited, we already hold the exact URLs Perplexity cited for
each query (ground truth). We rebuild the candidate corpus (all cited pages),
embed them with our own retrieval stack, and check: for each query, does OUR
embedding retrieval rank the pages the engine ACTUALLY cited at the top?

If precision@k >> a random baseline, our "little librarian" is faithful — which
means the "why you're not cited" and "simulate the fix" story is grounded, not a
guess. If it's ~random, the wedge is a mirage and we learned it in an afternoon.

Run:  .venv/bin/python retrieval_fidelity.py [brand_id]   (default 24 = GradeWiz)
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
from collections import defaultdict

import httpx
import numpy as np

import db
import rag

UA = "Mozilla/5.0 (compatible; LighthouseBot/0.1)"


def load_ground_truth(brand_id: int) -> dict[str, set[str]]:
    """query_text -> set of URLs the engine actually cited."""
    with db.get_conn() as c:
        rows = c.execute(
            "SELECT q.query_text, r.citations FROM responses r "
            "JOIN queries q ON q.id=r.query_id "
            "WHERE q.brand_id=%s AND r.citations IS NOT NULL ORDER BY q.id",
            (brand_id,),
        ).fetchall()
    gt: dict[str, set[str]] = {}
    for r in rows:
        cites = r["citations"]
        if isinstance(cites, str):
            try:
                cites = json.loads(cites)
            except Exception:
                cites = []
        urls = set()
        for u in (cites or []):
            if isinstance(u, dict):
                u = u.get("url")
            if u:
                urls.add(str(u).strip())
        if urls:
            gt.setdefault(r["query_text"], set()).update(urls)
    return gt


def html_to_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|noscript|svg).*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


async def _fetch(client: httpx.AsyncClient, url: str) -> tuple[str, str | None]:
    try:
        r = await client.get(url, timeout=15, follow_redirects=True,
                             headers={"User-Agent": UA})
        if r.status_code == 200 and "text/html" in r.headers.get("content-type", ""):
            return url, html_to_text(r.text)[:20000]
        return url, None
    except Exception:
        return url, None


async def fetch_all(urls: list[str]) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    sem = asyncio.Semaphore(8)
    async with httpx.AsyncClient() as client:
        async def one(u):
            async with sem:
                return await _fetch(client, u)
        for coro in asyncio.as_completed([one(u) for u in urls]):
            u, t = await coro
            out[u] = t
    return out


def _cos(qv: np.ndarray, M: np.ndarray) -> np.ndarray:
    qn = qv / (np.linalg.norm(qv) + 1e-9)
    Mn = M / (np.linalg.norm(M, axis=1, keepdims=True) + 1e-9)
    return Mn @ qn


def embed_batched(texts: list[str], batch: int = 128) -> list[list[float]]:
    out: list[list[float]] = []
    for i in range(0, len(texts), batch):
        out.extend(rag.embed_texts(texts[i:i + batch]))
    return out


def main(brand_id: int = 24) -> None:
    gt = load_ground_truth(brand_id)
    print(f"queries with real citations: {len(gt)}")
    all_urls = sorted({u for s in gt.values() for u in s})
    print(f"unique cited pages (candidate corpus): {len(all_urls)}")

    pages = asyncio.run(fetch_all(all_urls))
    fetched = [u for u, t in pages.items() if t]
    print(f"fetched OK (visible to a simple crawler): {len(fetched)}/{len(all_urls)}"
          f" ({round(100*len(fetched)/max(1,len(all_urls)))}%)")

    # chunk + embed every fetched page
    texts, index = [], []
    for u in fetched:
        for ch in (rag.chunk_text(pages[u]) or [])[:8]:
            texts.append(ch)
            index.append(u)
    print(f"embedding {len(texts)} page-chunks...")
    V = np.array(embed_batched(texts), dtype=np.float32)
    url_vecs: dict[str, list] = defaultdict(list)
    for u, v in zip(index, V):
        url_vecs[u].append(v)
    corpus = [u for u in fetched if u in url_vecs]

    # embed queries
    q_texts = list(gt.keys())
    qV = np.array(embed_batched(q_texts), dtype=np.float32)

    ks = [3, 5, 10]
    P = {k: [] for k in ks}
    Rc = {k: [] for k in ks}
    MRR = []
    truth_sizes = []
    for qt, qv in zip(q_texts, qV):
        truth = {u for u in gt[qt] if u in url_vecs}   # only fetched truth counts
        if not truth:
            continue
        scores = [(float(_cos(qv, np.array(url_vecs[u])).max()), u) for u in corpus]
        scores.sort(reverse=True)
        ranked = [u for _, u in scores]
        truth_sizes.append(len(truth))
        for k in ks:
            topk = set(ranked[:k])
            P[k].append(len(topk & truth) / k)
            Rc[k].append(len(topk & truth) / len(truth))
        rr = 0.0
        for rank, u in enumerate(ranked, 1):
            if u in truth:
                rr = 1.0 / rank
                break
        MRR.append(rr)

    n = len(MRR)
    C = len(corpus)
    avg_truth = np.mean(truth_sizes) if truth_sizes else 0
    print(f"\n===== FIDELITY  (brand {brand_id}) =====")
    print(f"scored {n} queries against a {C}-page corpus (avg {avg_truth:.1f} true citations/query)")
    print(f"{'metric':<14}{'ours':>8}{'random':>10}{'lift':>8}")
    for k in ks:
        ours = np.mean(P[k])
        rand = min(1.0, avg_truth / C) if C else 0
        lift = (ours / rand) if rand else float('inf')
        print(f"precision@{k:<4}{ours:>8.2f}{rand:>10.3f}{lift:>7.1f}x")
    for k in ks:
        ours = np.mean(Rc[k])
        rand = min(1.0, k / C) if C else 0
        print(f"recall@{k:<7}{ours:>8.2f}{rand:>10.3f}")
    print(f"{'MRR':<14}{np.mean(MRR):>8.2f}")
    print("\nRead: precision@k lift >> 1x means our retrieval tracks what the engine")
    print("actually cites -> the retrieval-simulation 'why' is grounded, not a guess.")
    print("(v1 corpus = cited pages only, a lenient test; v2 adds non-cited distractors.)")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 24)
