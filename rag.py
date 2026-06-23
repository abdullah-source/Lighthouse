"""
rag.py - the RAG (retrieval-augmented generation) layer.

Real RAG, not prompt-stuffing:
  ingest → chunk → embed → vector store → semantic retrieval → grounded answer.

Storage is Postgres + pgvector (Supabase): embeddings live in a vector(1536)
column and retrieval is a SQL cosine search (`embedding <=> query`). It sits
behind a thin interface (store.save_chunks / store.search_chunks) so callers
don't touch SQL.

Two uses:
  1. index_context()  - chunk + embed a brand's first-party context.
  2. retrieve()       - top-k relevant chunks for a query (grounds panel gen).
  3. answer()         - retrieve + let Claude answer over the brand's own data
                        (the "Ask" feature).

Disabled gracefully when OPENAI_API_KEY is absent (no embeddings available).
"""

from __future__ import annotations

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


# --- index + retrieve -------------------------------------------------------

def index_context(brand_id: int, document_id: int, text: str) -> int:
    """Chunk + embed + persist first-party context. Returns chunks indexed."""
    if not RAG_ENABLED:
        return 0
    chunks = chunk_text(text)
    if not chunks:
        return 0
    embeddings = embed_texts(chunks)
    store.save_chunks(brand_id, document_id, list(zip(chunks, embeddings)), kind="context")
    return len(chunks)


def index_responses(brand_id: int) -> int:
    """
    Index the AI answers collected for a brand so Ask can search what the
    engines actually said (works even with no first-party context). Idempotent:
    clears prior 'response' chunks first. Best-effort; returns chunks indexed.
    """
    if not RAG_ENABLED:
        return 0
    texts = store.fetch_response_texts(brand_id)
    if not texts:
        return 0
    chunks: list[str] = []
    for t in texts:
        chunks.extend(chunk_text(t))
    if not chunks:
        return 0
    embeddings = embed_texts(chunks)
    store.delete_chunks(brand_id, kind="response")
    store.save_chunks(brand_id, None, list(zip(chunks, embeddings)), kind="response")
    return len(chunks)


def retrieve(brand_id: int, query: str, k: int = 6, kinds: list[str] | None = None) -> list[str]:
    """
    Top-k chunk texts most similar to the query, via pgvector cosine search.
    `kinds` filters the store: None = everything (Ask), ['context'] = first-party
    only (panel grounding).
    """
    if not RAG_ENABLED:
        return []
    qvec = embed_texts([query])[0]
    return store.search_chunks(brand_id, qvec, k=k, kinds=kinds)


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
    chunks = retrieve(brand_id, question, k=k)   # all kinds: context + AI responses
    if not chunks:
        return {
            "answer": "Nothing to search yet. Run an audit for this brand first "
                      "(and optionally paste your own context), then ask again.",
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
