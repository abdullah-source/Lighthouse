"""
queries.py — generate buyer queries for a brand using Claude Sonnet.

Why this is its own file:
- It's the one place we call an LLM creatively (not extractively).
- The prompt design matters: better prompt → better queries → better
  signal in the rest of the pipeline.

Why synchronous (no asyncio here):
- We make exactly ONE API call per brand. async would be overkill and
  would make the code harder to read on a first pass.
"""

from anthropic import Anthropic

from config import ANTHROPIC_API_KEY, MODEL_QUERY_GEN, QUERIES_PER_BRAND


# Prompt design notes:
# - We give the model an explicit role (a consumer research analyst).
# - We constrain the format (numbered list, no commentary) so parsing the
#   response is dead simple.
# - We push for diversity along several axes (price, persona, use case)
#   so the queries actually cover the buying funnel — not 20 variations
#   of the same question.
_SYSTEM_PROMPT = """You are a consumer research analyst. Your job is to
produce realistic, high-intent buyer queries that real consumers ask AI
assistants when shopping in a given category.

Rules:
- Each query is something a real shopper would type or speak.
- Cover a range of buying intent: discovery, comparison, specific use case, budget, persona.
- Mix specific ("running shoes for flat feet under $150") with broad ("best sustainable sneakers").
- Do NOT mention the brand name we're studying — these are open queries
  where the LLM would freely choose what to recommend.
- Output ONLY the numbered list. No preamble, no commentary, no markdown.
"""


def generate_queries(brand_name: str, category: str, count: int = QUERIES_PER_BRAND) -> list[str]:
    """
    Ask Claude to generate `count` realistic buyer queries for a category.

    Returns a list of query strings, in the order Claude produced them.
    Raises if the response can't be parsed.
    """
    # The Anthropic client picks up ANTHROPIC_API_KEY from env automatically,
    # but we pass it explicitly so the dependency is obvious.
    client = Anthropic(api_key=ANTHROPIC_API_KEY)

    user_prompt = (
        f"Brand we're studying (do NOT mention it in the queries): {brand_name}\n"
        f"Category: {category}\n"
        f"Number of queries to produce: {count}\n\n"
        f"Output {count} numbered queries, one per line."
    )

    # messages.create is the Anthropic SDK's main entry point.
    # max_tokens caps the response size — 1024 tokens is plenty for 20 short queries.
    response = client.messages.create(
        model=MODEL_QUERY_GEN,
        max_tokens=1024,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    # response.content is a list of content blocks. For a plain text response
    # there's exactly one block of type "text".
    raw_text = response.content[0].text

    return _parse_numbered_list(raw_text, expected_count=count)


def _parse_numbered_list(text: str, expected_count: int) -> list[str]:
    """
    Pull queries out of a numbered list response like:
        1. best running shoes for flat feet under $150
        2. sustainable sneakers for everyday wear

    Tolerates minor formatting differences (different bullet styles,
    extra whitespace) so we don't crash if the model adds a quirk.
    """
    queries: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or not line[0].isdigit():
            continue
        # Strip leading number + delimiter: "1.", "1)", "1 -", "1:".
        for i, ch in enumerate(line):
            if ch in (".", ")", "-", ":") and i > 0:
                queries.append(line[i + 1 :].strip())
                break

    # Sanity check: if we got way fewer than asked for, surface the raw
    # text so we can debug the prompt.
    if len(queries) < expected_count // 2:
        raise ValueError(
            f"Expected ~{expected_count} queries, parsed {len(queries)}. "
            f"Raw response:\n{text}"
        )

    return queries
