"""
probe.py — fan out buyer queries against multiple LLMs in parallel.

This is where you'll learn asyncio. The pattern:

    async def probe_one(...):
        ...one network call, ~2-10 seconds...

    asyncio.gather(probe_one(q1), probe_one(q2), ...)
        ...fires all of them at once, returns when all are done...

Why async instead of threads:
- API calls are I/O bound — most of the time is spent waiting on the
  network. Python's GIL doesn't matter because we're not CPU bound.
- async lets one thread juggle hundreds of in-flight requests cheaply.
- The Anthropic and OpenAI SDKs both ship async clients out of the box.

Concurrency control:
- Firing all 40 calls at once would hit rate limits.
- asyncio.Semaphore caps how many coroutines are "inside" at any moment.
- Inside the semaphore block: only N coroutines run at a time. The rest wait.
"""

import asyncio

import httpx
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from config import (
    ANTHROPIC_API_KEY,
    MODEL_PROBE_ANTHROPIC,
    MODEL_PROBE_OPENAI,
    MODEL_PROBE_PERPLEXITY,
    OPENAI_API_KEY,
    PERPLEXITY_API_KEY,
    PERPLEXITY_MODEL_LABEL,
    PROBE_CONCURRENCY,
)


# A single instruction we give both models. We keep it generic — we're
# simulating a consumer asking an AI assistant, not coaching the model.
_PROBE_SYSTEM_PROMPT = (
    "You are a helpful shopping assistant. The user is researching a "
    "purchase. Recommend specific products or brands by name, and "
    "briefly explain why. Be concrete — vague answers are unhelpful."
)


# Every probe returns a (text, citations) pair so the fan-out can treat all
# engines uniformly. Only the retrieval engine (Perplexity) returns real
# citations; the plain chat models return an empty list.


async def _probe_openai(
    client: AsyncOpenAI, query_text: str, semaphore: asyncio.Semaphore
) -> tuple[str, list]:
    """
    One call to GPT-5. Returns (raw_text, []).

    Two GPT-5-specific quirks:
    1. `max_completion_tokens` replaces the legacy `max_tokens`.
    2. GPT-5 is a "reasoning" model — it burns internal tokens on
       chain-of-thought BEFORE producing visible output. With a small
       budget, the model can use all tokens on reasoning and emit nothing.
       `reasoning_effort='low'` caps internal reasoning so we get an
       actual answer. For shopping recommendations we don't need deep
       reasoning — fast + concrete is what we want.
    """
    async with semaphore:
        response = await client.chat.completions.create(
            model=MODEL_PROBE_OPENAI,
            messages=[
                {"role": "system", "content": _PROBE_SYSTEM_PROMPT},
                {"role": "user", "content": query_text},
            ],
            max_completion_tokens=2000,
            reasoning_effort="low",
        )
        return (response.choices[0].message.content or ""), []


async def _probe_anthropic(
    client: AsyncAnthropic, query_text: str, semaphore: asyncio.Semaphore
) -> tuple[str, list]:
    """One call to Claude Sonnet. Returns (raw_text, [])."""
    async with semaphore:
        response = await client.messages.create(
            model=MODEL_PROBE_ANTHROPIC,
            max_tokens=800,
            system=_PROBE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": query_text}],
        )
        return response.content[0].text, []


def _extract_citations(data: dict) -> list[dict]:
    """
    Pull the cited sources out of a Perplexity response.

    Perplexity has shipped two shapes over time:
      - `search_results`: [{title, url, date}, ...]   (newer)
      - `citations`:      ["https://...", ...]         (older)
    We read both, de-dupe by URL, and normalize to {url, title}.
    """
    out: list[dict] = []
    seen: set[str] = set()

    for item in data.get("search_results") or []:
        url = (item or {}).get("url")
        if url and url not in seen:
            seen.add(url)
            out.append({"url": url, "title": (item.get("title") or "").strip()})

    for c in data.get("citations") or []:
        url = c if isinstance(c, str) else (c.get("url") if isinstance(c, dict) else None)
        if url and url not in seen:
            seen.add(url)
            out.append({"url": url, "title": ""})

    return out


async def _probe_perplexity(
    client: httpx.AsyncClient, query_text: str, semaphore: asyncio.Semaphore
) -> tuple[str, list]:
    """
    One call to Perplexity Sonar (retrieval-grounded). Returns (text, citations).

    The API is OpenAI-compatible, but the cited sources live in extra top-level
    fields the OpenAI SDK would drop, so we call it over raw httpx and read the
    JSON ourselves. Citations are the whole point of this probe.
    """
    async with semaphore:
        resp = await client.post(
            "https://api.perplexity.ai/chat/completions",
            headers={
                "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": MODEL_PROBE_PERPLEXITY,
                "messages": [
                    {"role": "system", "content": _PROBE_SYSTEM_PROMPT},
                    {"role": "user", "content": query_text},
                ],
                "max_tokens": 800,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["choices"][0]["message"]["content"] or ""
        return text, _extract_citations(data)


async def probe_all(queries: list[tuple[int, str]]) -> list[tuple[int, str, str, list]]:
    """
    Probe every (query_id, query_text) against the available models.

    Anthropic always runs (required). OpenAI runs only if OPENAI_API_KEY is set.
    Perplexity (Sonar) runs only if PERPLEXITY_API_KEY is set — it is the
    retrieval-grounded engine, the only one that returns cited sources.

    Returns: list of (query_id, model_id, raw_response_text, citations).
    """
    # Anthropic is required — initialize unconditionally.
    anthropic_client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

    # OpenAI is optional. If the key isn't set, skip it entirely.
    openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

    # Perplexity is optional and called over raw httpx (see _probe_perplexity).
    px_client = httpx.AsyncClient(timeout=60.0) if PERPLEXITY_API_KEY else None

    # Single shared semaphore caps concurrency across all providers.
    semaphore = asyncio.Semaphore(PROBE_CONCURRENCY)

    # Wrap each call so a single failure doesn't kill the whole batch, and
    # retry transient errors (connection drops, rate limits, overloads) with
    # backoff before giving up. `make_coro` is a factory so each retry gets a
    # fresh coroutine. Each coroutine yields (text, citations).
    async def run_one(query_id: int, model: str, make_coro, attempts: int = 3) -> tuple[int, str, str, list]:
        last = None
        for i in range(attempts):
            try:
                text, citations = await make_coro()
                return (query_id, model, text, citations)
            except Exception as exc:
                last = exc
                await asyncio.sleep(1.0 * (i + 1))
        print(f"[probe] gave up on query {query_id} / {model} after {attempts} tries: {last}")
        return (query_id, model, "", [])

    try:
        # Build the list of coroutines: always Claude, optionally GPT-5 + Sonar.
        tasks = []
        for query_id, query_text in queries:
            tasks.append(
                run_one(query_id, MODEL_PROBE_ANTHROPIC,
                        lambda q=query_text: _probe_anthropic(anthropic_client, q, semaphore))
            )
            if openai_client is not None:
                tasks.append(
                    run_one(query_id, MODEL_PROBE_OPENAI,
                            lambda q=query_text: _probe_openai(openai_client, q, semaphore))
                )
            if px_client is not None:
                tasks.append(
                    run_one(query_id, PERPLEXITY_MODEL_LABEL,
                            lambda q=query_text: _probe_perplexity(px_client, q, semaphore))
                )

        # asyncio.gather schedules all tasks. The semaphore ensures only
        # PROBE_CONCURRENCY are in-flight at any moment.
        results = await asyncio.gather(*tasks)
    finally:
        if px_client is not None:
            await px_client.aclose()
    return results
