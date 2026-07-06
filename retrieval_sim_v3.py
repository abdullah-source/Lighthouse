"""
retrieval_sim_v3.py — learned ranker (learning-to-rank) on real citation labels.

v2 showed naive equal-weight fusion (cosine+BM25+freshness) HURT vs cosine alone.
The honest fix: don't hand-weight signals — LEARN the weights from the citations
we actually observed. This trains a logistic-regression ranker on features
[cosine_max, cosine_mean3, bm25, freshness, log_len] with the label = "did the
engine cite this page for this query," evaluated with GROUP splits by query (a
query is never in both train and test) so there's no leakage.

The point: the moat is a ranker tuned on our proprietary query->citation labels.
No sklearn — plain numpy, so it deploys anywhere.

Run:  .venv/bin/python retrieval_sim_v3.py [brand_id] [distractor_id]
"""
from __future__ import annotations

import sys
from collections import defaultdict
from datetime import datetime

import numpy as np

import rag
from retrieval_fidelity import load_ground_truth, embed_batched, _cos
from retrieval_sim_v2 import fetch_cached, BM25

FEATURES = ["cos_max", "cos_mean3", "bm25", "fresh", "log_len"]


def _recency(date: str | None) -> float:
    if not date:
        return 0.0
    try:
        months = (datetime.now() - datetime.strptime(date, "%Y-%m-%d")).days / 30.0
        return max(0.0, 1.0 - months / 24.0)   # 1=today, 0 at >=2yrs / undated
    except Exception:
        return 0.0


def build_dataset(brand_id: int, distractor_id: int):
    gt = load_ground_truth(brand_id)
    on_urls = sorted({u for s in gt.values() for u in s})
    dgt = load_ground_truth(distractor_id)
    d_urls = [u for u in sorted({u for s in dgt.values() for u in s}) if u not in set(on_urls)][:80]
    pages = fetch_cached(on_urls + d_urls)
    pages = {u: d for u, d in pages.items() if d and d.get("text")}
    corpus = list(pages.keys())

    # embed chunks per page
    texts, index = [], []
    for u in corpus:
        for ch in (rag.chunk_text(pages[u]["text"]) or [])[:8]:
            texts.append(ch); index.append(u)
    V = np.array(embed_batched(texts), dtype=np.float32)
    url_vecs = defaultdict(list)
    for u, v in zip(index, V):
        url_vecs[u].append(v)
    corpus = [u for u in corpus if u in url_vecs]

    bm = BM25([pages[u]["text"] for u in corpus])
    idx = {u: i for i, u in enumerate(corpus)}
    fresh = {u: _recency(pages[u].get("date")) for u in corpus}
    loglen = {u: np.log1p(len(pages[u]["text"])) for u in corpus}

    q_texts = list(gt.keys())
    qV = np.array(embed_batched(q_texts), dtype=np.float32)

    rows = []   # (features, label, query_id, page_url, cos_max)
    for qi, (qt, qv) in enumerate(zip(q_texts, qV)):
        truth = {u for u in gt[qt] if u in url_vecs}
        if not truth:
            continue
        bm_scores = {u: bm.score(qt, idx[u]) for u in corpus}
        bmax = max(bm_scores.values()) or 1.0
        for u in corpus:
            sims = _cos(qv, np.array(url_vecs[u]))
            cmax = float(sims.max())
            cmean3 = float(np.sort(sims)[-3:].mean())
            feats = [cmax, cmean3, bm_scores[u] / bmax, fresh[u], loglen[u]]
            rows.append((feats, 1 if u in truth else 0, qi, u, cmax))
    X = np.array([r[0] for r in rows], dtype=np.float64)
    y = np.array([r[1] for r in rows], dtype=np.float64)
    groups = np.array([r[2] for r in rows])
    cos_only = np.array([r[4] for r in rows])
    return X, y, groups, cos_only, len(corpus)


def train_lr(X, y, epochs=400, lr=0.3, l2=1e-3):
    n, d = X.shape
    w = np.zeros(d); b = 0.0
    pos = y.sum()
    pw = (n - pos) / max(1.0, pos)             # upweight rare positives
    sw = np.where(y == 1, pw, 1.0)
    for _ in range(epochs):
        p = 1.0 / (1.0 + np.exp(-(X @ w + b)))
        g = (p - y) * sw
        w -= lr * (X.T @ g / n + l2 * w)
        b -= lr * g.mean()
    return w, b


def pak(scores, y, groups, ks=(3, 5, 10)):
    out = {k: [] for k in ks}
    for q in np.unique(groups):
        m = groups == q
        order = np.argsort(-scores[m])
        yl = y[m][order]
        if yl.sum() == 0:
            continue
        for k in ks:
            out[k].append(yl[:k].sum() / k)
    return {k: float(np.mean(v)) for k, v in out.items()}


def main(brand_id=24, distractor_id=22):
    X, y, groups, cos_only, C = build_dataset(brand_id, distractor_id)
    qs = np.unique(groups)
    print(f"pairs: {len(y)} · queries: {len(qs)} · corpus: {C} · positives: {int(y.sum())}")

    # 5-fold GROUP CV (split by query) -> no query in both train & test
    rng = np.random.default_rng(0)
    folds = np.array_split(rng.permutation(qs), 5)
    lr_p = {k: [] for k in (3, 5, 10)}
    cos_p = {k: [] for k in (3, 5, 10)}
    for f in folds:
        test_mask = np.isin(groups, f)
        tr, te = ~test_mask, test_mask
        mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-9
        w, b = train_lr((X[tr] - mu) / sd, y[tr])
        s_lr = ((X[te] - mu) / sd) @ w + b
        m_lr = pak(s_lr, y[te], groups[te])
        m_cos = pak(cos_only[te], y[te], groups[te])
        for k in (3, 5, 10):
            lr_p[k].append(m_lr[k]); cos_p[k].append(m_cos[k])

    print("\n===== v3 LEARNED RANKER (held-out, grouped by query) =====")
    print(f"{'method':<16}{'p@3':>7}{'p@5':>7}{'p@10':>7}")
    print(f"{'cosine (v1)':<16}" + "".join(f"{np.mean(cos_p[k]):>7.2f}" for k in (3, 5, 10)))
    print(f"{'learned (v3)':<16}" + "".join(f"{np.mean(lr_p[k]):>7.2f}" for k in (3, 5, 10)))
    lift = np.mean(lr_p[3]) / max(1e-9, np.mean(cos_p[3]))
    print(f"\np@3: learned is {lift:.2f}x the cosine baseline")

    # interpretable weights on full data (standardized)
    mu, sd = X.mean(0), X.std(0) + 1e-9
    w, b = train_lr((X - mu) / sd, y)
    print("\nlearned feature weights (standardized; + = predicts citation):")
    for name, wi in sorted(zip(FEATURES, w), key=lambda t: -abs(t[1])):
        print(f"  {name:<11}{wi:+.3f}")


if __name__ == "__main__":
    a = int(sys.argv[1]) if len(sys.argv) > 1 else 24
    d = int(sys.argv[2]) if len(sys.argv) > 2 else 22
    main(a, d)
