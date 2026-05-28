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

from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from config import (
    ANTHROPIC_API_KEY,
    MODEL_PROBE_ANTHROPIC,
    MODEL_PROBE_OPENAI,
    OPENAI_API_KEY,
    PROBE_CONCURRENCY,
)


# A single instruction we give both models. We keep it generic — we're
# simulating a consumer asking an AI assistant, not coaching the model.
_PROBE_SYSTEM_PROMPT = (
    "You are a helpful shopping assistant. The user is researching a "
    "purchase. Recommend specific products or brands by name, and "
    "briefly explain why. Be concrete — vague answers are unhelpful."
)


async def _probe_openai(
    client: AsyncOpenAI, query_text: str, semaphore: asyncio.Semaphore
) -> str:
    """
    One call to GPT-5. Returns the raw text response.

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
        return response.choices[0].message.content or ""


async def _probe_anthropic(
    client: AsyncAnthropic, query_text: str, semaphore: asyncio.Semaphore
) -> str:
    """One call to Claude Sonnet. Returns the raw text response."""
    async with semaphore:
        response = await client.messages.create(
            model=MODEL_PROBE_ANTHROPIC,
            max_tokens=800,
            system=_PROBE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": query_text}],
        )
        return response.content[0].text


async def probe_all(queries: list[tuple[int, str]]) -> list[tuple[int, str, str]]:
    """
    Probe every (query_id, query_text) against the available models.

    Anthropic always runs (required). OpenAI runs only if OPENAI_API_KEY is set —
    otherwise we skip GPT-5 and the result list contains only Claude responses.

    Returns: list of (query_id, model_id, raw_response_text).
    """
    # Anthropic is required — initialize unconditionally.
    anthropic_client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

    # OpenAI is optional. If the key isn't set, skip it entirely.
    openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

    # Single shared semaphore caps concurrency across both providers.
    semaphore = asyncio.Semaphore(PROBE_CONCURRENCY)

    # Wrap each call so a single failure doesn't kill the whole batch.
    async def run_one(query_id: int, model: str, coro) -> tuple[int, str, str]:
        try:
            text = await coro
            return (query_id, model, text)
        except Exception as exc:
            print(f"[probe] error for query {query_id} on {model}: {exc}")
            return (query_id, model, "")

    # Build the list of coroutines: always Claude, optionally GPT-5.
    tasks = []
    for query_id, query_text in queries:
        tasks.append(
            run_one(
                query_id,
                MODEL_PROBE_ANTHROPIC,
                _probe_anthropic(anthropic_client, query_text, semaphore),
            )
        )
        if openai_client is not None:
            tasks.append(
                run_one(
                    query_id,
                    MODEL_PROBE_OPENAI,
                    _probe_openai(openai_client, query_text, semaphore),
                )
            )

    # asyncio.gather schedules all tasks. The semaphore ensures only
    # PROBE_CONCURRENCY are in-flight at any moment.
    results = await asyncio.gather(*tasks)
    return results
