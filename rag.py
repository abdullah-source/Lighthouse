"""
rag.py - the RAG (retrieval-augmented generation) layer.

Real RAG, not prompt-stuffing:
  ingest → chunk → embed → vector store → semantic retrieval → grounded answer.

Storage today is SQLite (embeddings as JSON arrays, cosine computed in Python).
That is genuinely RAG and is fine for MVP corpus sizes (hundreds to a few
thousand chunks). It is deliberately behind a thin interface (store.save_chunks
/ store.fetch_chunks) so the backend swaps to Postgres + pgvector on deploy with
no change to callers.

Two uses:
  1. index_context()  - chunk + embed a brand's first-party context.
  2. retrieve()       - top-k relevant chunks for a query (grounds panel gen).
  3. answer()         - retrieve + let Claude answer over the brand's own data
                        (the "Ask" feature).

Disabled gracefully when OPENAI_API_KEY is absent (no embeddings available).
"""

from __future__ import annotations

import math

from anthropic import Anthropic
from openai import OpenAI

import store
from config import (
    ANTHROPIC_API_KEY,
    EMBED_MODEL,
    MODEL_ASK,
    OPENAI_API_KEY,
    RAG_ENABLED,
)


# --- chunking ---------------------------------------------------------------

def chunk_text(text: str, size: int = 800, overlap: int = 120) -> list[str]:
    """
    Split text into overlapping word-windows. Overlap keeps a sentence that
    straddles a boundary retrievable from either side. Sizes are in words
    (rough proxy for tokens) to stay dependency-free.
    """
    words = text.split()
    if not words:
        return []
    chunks: list[str] = []
    step = max(1, size - overlap)
    for start in range(0, len(words), step):
        window = words[start : start + size]
        if window:
            chunks.append(" ".join(window))
        if start + size >= len(words):
            break
    return chunks


# --- embeddings -------------------------------------------------------------

def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch in one OpenAI call. Returns one vector per input."""
    if not texts:
        return []
    client = OpenAI(api_key=OPENAI_API_KEY)
    resp = client.embeddings.create(model=EMBED_MODEL, input=texts)
    # API preserves input order.
    return [d.embedding for d in resp.data]


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


# --- index + retrieve -------------------------------------------------------

def index_context(brand_id: int, document_id: int, text: str) -> int:
    """Chunk + embed + persist. Returns number of chunks indexed."""
    if not RAG_ENABLED:
        return 0
    chunks = chunk_text(text)
    if not chunks:
        return 0
    embeddings = embed_texts(chunks)
    store.save_chunks(brand_id, document_id, list(zip(chunks, embeddings)))
    return len(chunks)


def retrieve(brand_id: int, query: str, k: int = 6) -> list[str]:
    """Top-k chunk texts most similar to the query (cosine), for this brand."""
    if not RAG_ENABLED:
        return []
    rows = store.fetch_chunks(brand_id)
    if not rows:
        return []
    qvec = embed_texts([query])[0]
    scored = [(_cosine(qvec, emb), text) for text, emb in rows]
    scored.sort(key=lambda s: s[0], reverse=True)
    return [text for _score, text in scored[:k]]


# --- grounded answer (the "Ask" feature) ------------------------------------

_ASK_SYSTEM = (
    "You answer questions for a brand's marketing team using ONLY the provided "
    "context from that brand's own materials and AI-visibility data. If the "
    "context does not contain the answer, say so plainly. Be concise and concrete."
)


def answer(brand_id: int, question: str, k: int = 6) -> dict:
    """
    RAG answer over the brand's indexed context. Returns
    {"answer": str, "sources": [chunk snippets]}.
    """
    chunks = retrieve(brand_id, question, k=k)
    if not chunks:
        return {
            "answer": "No indexed context yet. Run an audit with your own context "
                      "pasted in, then ask again.",
            "sources": [],
        }
    context_block = "\n\n---\n\n".join(chunks)
    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    resp = client.messages.create(
        model=MODEL_ASK,
        max_tokens=600,
        system=_ASK_SYSTEM,
        messages=[{
            "role": "user",
            "content": f"Context:\n{context_block}\n\nQuestion: {question}",
        }],
    )
    body = resp.content[0].text if resp.content else ""
    # short snippets for the UI (first ~160 chars of each retrieved chunk)
    sources = [c[:160] + ("…" if len(c) > 160 else "") for c in chunks]
    return {"answer": body, "sources": sources}
