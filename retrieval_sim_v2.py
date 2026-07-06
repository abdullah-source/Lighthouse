"""
retrieval_sim_v2.py — v2 of the retrieval-simulation fidelity test.

v1 (retrieval_fidelity.py) used embedding cosine only and scored 5.6x random.
v2 adds the signals real answer engines use, and makes the test HARDER:

  1. BM25 lexical retrieval (free, local)
  2. Hybrid ranking via Reciprocal Rank Fusion of cosine + BM25
  3. Freshness (page publish/modified date) as a third RRF signal
  4. A HARDER corpus: inject off-topic distractor pages from another category,
     so we are not grading on a curve.

Honesty guardrails: no feature is derived from the citation labels we predict
(no target leakage). Freshness = page metadata; BM25 = page text; cosine =
embeddings. Reports precision@k for cosine-only vs hybrid vs hybrid+fresh.

Run:  .venv/bin/python retrieval_sim_v2.py [brand_id] [distractor_brand_id]
      default 24 (GradeWiz) with distractors from 22 (Cooley, legal).
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import re
import sys
from collections import defaultdict
from datetime import datetime

import httpx
import numpy as np

import rag
from retrieval_fidelity import load_ground_truth, html_to_text, embed_batched, _cos

UA = "Mozilla/5.0 (compatible; LighthouseBot/0.1)"
CACHE = "/tmp/lh_page_cache.json"


# ---------- fetching (with disk cache + date extraction) --------------------

def _extract_date(html: str) -> str | None:
    for pat in (
        r'"datePublished"\s*:\s*"([0-9]{4}-[0-9]{2}-[0-9]{2})',
        r'"dateModified"\s*:\s*"([0-9]{4}-[0-9]{2}-[0-9]{2})',
        r'article:published_time"[^>]*content="([0-9]{4}-[0-9]{2}-[0-9]{2})',
        r'datetime="([0-9]{4}-[0-9]{2}-[0-9]{2})',
    ):
        m = re.search(pat, html)
        if m:
            return m.group(1)
    return None


async def _fetch(client, url):
    try:
        r = await client.get(url, timeout=15, follow_redirects=True,
                             headers={"User-Agent": UA})
        if r.status_code == 200 and "text/html" in r.headers.get("content-type", ""):
            return url, {"text": html_to_text(r.text)[:20000], "date": _extract_date(r.text)}
        return url, None
    except Exception:
        return url, None


async def _fetch_all(urls):
    out = {}
    sem = asyncio.Semaphore(8)
    async with httpx.AsyncClient() as client:
        async def one(u):
            async with sem:
                return await _fetch(client, u)
        for coro in asyncio.as_completed([one(u) for u in urls]):
            u, d = await coro
            out[u] = d
    return out


def fetch_cached(urls):
    cache = {}
    if os.path.exists(CACHE):
        try:
            cache = json.load(open(CACHE))
        except Exception:
            cache = {}
    missing = [u for u in urls if u not in cache]
    if missing:
        fresh = asyncio.run(_fetch_all(missing))
        cache.update({u: v for u, v in fresh.items()})
        json.dump(cache, open(CACHE, "w"))
    return {u: cache.get(u) for u in urls}


# ---------- BM25 -------------------------------------------------------------

def _tok(s):
    return re.findall(r"[a-z0-9]+", s.lower())


class BM25:
    def __init__(self, docs, k1=1.5, b=0.75):
        self.docs = [_tok(d) for d in docs]
        self.N = len(self.docs)
        self.avgdl = sum(len(d) for d in self.docs) / max(1, self.N)
        self.tf = []
        df = defaultdict(int)
        for d in self.docs:
            counts = defaultdict(int)
            for t in d:
                counts[t] += 1
            self.tf.append(counts)
            for t in set(d):
                df[t] += 1
        self.idf = {t: math.log(1 + (self.N - n + 0.5) / (n + 0.5)) for t, n in df.items()}
        self.k1, self.b = k1, b

    def score(self, query, i):
        s, dl = 0.0, len(self.docs[i])
        for t in _tok(query):
            f = self.tf[i].get(t, 0)
            if not f:
                continue
            s += self.idf.get(t, 0.0) * (f * (self.k1 + 1)) / (
                f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
        return s

    def rank(self, query):
        return sorted(range(self.N), key=lambda i: self.score(query, i), reverse=True)


def rrf(rankings, k=60):
    score = defaultdict(float)
    for r in rankings:
        for rank, pid in enumerate(r):
            score[pid] += 1.0 / (k + rank)
    return sorted(score, key=lambda p: score[p], reverse=True)


# ---------- experiment -------------------------------------------------------

def build_corpus(urls, label):
    pages = fetch_cached(urls)
    ok = {u: d for u, d in pages.items() if d and d.get("text")}
    print(f"  [{label}] fetched {len(ok)}/{len(urls)}")
    return ok


def main(brand_id=24, distractor_id=22):
    gt = load_ground_truth(brand_id)
    print(f"queries: {len(gt)}")
    on_urls = sorted({u for s in gt.values() for u in s})
    on = build_corpus(on_urls, "on-topic")

    # HARDER corpus: distractor pages from another category
    dgt = load_ground_truth(distractor_id)
    d_urls = sorted({u for s in dgt.values() for u in s})[:80]
    distract = build_corpus(d_urls, "distractors")
    for u in on:            # ensure no overlap
        distract.pop(u, None)

    all_pages = {**on, **distract}
    corpus = list(all_pages.keys())
    print(f"corpus: {len(on)} on-topic + {len(distract)} distractors = {len(corpus)} pages")

    # embed page chunks
    texts, index = [], []
    for u in corpus:
        for ch in (rag.chunk_text(all_pages[u]["text"]) or [])[:8]:
            texts.append(ch)
            index.append(u)
    print(f"embedding {len(texts)} chunks...")
    V = np.array(embed_batched(texts), dtype=np.float32)
    url_vecs = defaultdict(list)
    for u, v in zip(index, V):
        url_vecs[u].append(v)
    corpus = [u for u in corpus if u in url_vecs]

    # BM25 over page text
    bm = BM25([all_pages[u]["text"] for u in corpus])

    # freshness order (most recent first; undated -> bottom)
    def recency(u):
        d = all_pages[u].get("date")
        if not d:
            return -1e9
        try:
            return datetime.strptime(d, "%Y-%m-%d").timestamp()
        except Exception:
            return -1e9
    fresh_rank = sorted(range(len(corpus)), key=lambda i: recency(corpus[i]), reverse=True)

    # queries
    q_texts = list(gt.keys())
    qV = np.array(embed_batched(q_texts), dtype=np.float32)

    ks = [3, 5, 10]
    methods = ["cosine", "hybrid", "hybrid+fresh"]
    P = {m: {k: [] for k in ks} for m in methods}
    truth_sizes = []

    for qt, qv in zip(q_texts, qV):
        truth = {u for u in gt[qt] if u in url_vecs}
        if not truth:
            continue
        truth_sizes.append(len(truth))
        cos_scores = [float(_cos(qv, np.array(url_vecs[u])).max()) for u in corpus]
        cos_rank = sorted(range(len(corpus)), key=lambda i: cos_scores[i], reverse=True)
        bm_rank = bm.rank(qt)
        ranks = {
            "cosine": cos_rank,
            "hybrid": rrf([cos_rank, bm_rank]),
            "hybrid+fresh": rrf([cos_rank, bm_rank, fresh_rank]),
        }
        for m in methods:
            ranked = [corpus[i] for i in ranks[m]]
            for k in ks:
                topk = set(ranked[:k])
                P[m][k].append(len(topk & truth) / k)

    n = len(truth_sizes)
    C = len(corpus)
    avg_truth = np.mean(truth_sizes) if truth_sizes else 0
    rand = min(1.0, avg_truth / C) if C else 0
    print(f"\n===== v2 FIDELITY (harder corpus) =====")
    print(f"{n} queries · {C} pages ({len(distract)} off-topic distractors) · random p@k ~ {rand:.3f}")
    print(f"{'method':<14}" + "".join(f"p@{k:<5}" for k in ks))
    for m in methods:
        row = "".join(f"{np.mean(P[m][k]):<7.2f}" for k in ks)
        print(f"{m:<14}{row}")
    print(f"\nbaseline random p@k ~ {rand:.3f}. Higher = our reconstruction tracks the engine.")


if __name__ == "__main__":
    a = int(sys.argv[1]) if len(sys.argv) > 1 else 24
    b = int(sys.argv[2]) if len(sys.argv) > 2 else 22
    main(a, b)
