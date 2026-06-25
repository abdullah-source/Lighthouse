"""
queries.py — generate buyer queries for a brand using Claude Sonnet.

Why synchronous (no asyncio here):
- We make exactly ONE API call per brand. async would be overkill and
  would make the code harder to read on a first pass.
"""

from anthropic import Anthropic

from config import ANTHROPIC_API_KEY, MODEL_QUERY_GEN, PANEL_SIZE, QUERIES_PER_BRAND


# Prompt design notes:
# - We give the model an explicit role (a consumer research analyst).
# - We constrain the format (numbered list, no commentary) so parsing the
#   response is dead simple.
# - We push for diversity along several axes (price, persona, use case)
#   so the queries actually cover the buying funnel — not 20 variations
#   of the same question.
_SYSTEM_PROMPT = """You are a research analyst. Your job is to produce
realistic, high-intent queries that real people ask AI assistants when deciding
what to choose in a given category. The category can be anything: a consumer
product, a service, software, or a provider/firm.

Rules:
- Each query is something a real decision-maker would type or speak.
- Cover a range of intent: discovery, comparison, specific use case, budget, persona.
- Mix specific ("running shoes for flat feet under $150", "CRM for a 10-person
  sales team", "employment lawyer for a wrongful termination case") with broad
  ("best sustainable sneakers", "top project management tools").
- Do NOT mention the brand/firm name we're studying — these are open queries
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


# --- Grounded panel generation (v2: depth-based search) ---------------------
#
# The generic generator above invents plausible queries from just brand +
# category. The grounded generator below is the depth differentiator: it reads
# the brand's OWN context (reviews, support tickets, positioning, customer
# language) and produces queries that mirror how *this brand's* real buyers ask.
# It also returns a short seed_summary of the themes it found, so the product
# can show the team "here is what we read in your context."
#
# We use tool-use to force a structured result (seed_summary + intent-tagged
# queries), the same reliability trick parse.py uses.

_PANEL_TOOL = {
    "name": "build_panel",
    "description": (
        "Produce a short summary of the buyer themes found in the brand's "
        "context, plus a set of realistic, high-intent buyer queries grounded "
        "in that context."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "seed_summary": {
                "type": "string",
                "description": (
                    "2-3 sentences naming the buyer intents, personas, "
                    "objections, and vocabulary you found in the context."
                ),
            },
            "queries": {
                "type": "array",
                "description": "The grounded buyer queries.",
                "items": {
                    "type": "object",
                    "properties": {
                        "intent": {
                            "type": "string",
                            "description": (
                                "One of: discovery, comparison, use_case, "
                                "budget, persona."
                            ),
                        },
                        "query": {
                            "type": "string",
                            "description": "What a real decision-maker would ask the AI.",
                        },
                    },
                    "required": ["intent", "query"],
                },
            },
        },
        "required": ["seed_summary", "queries"],
    },
}


_GROUNDED_SYSTEM_PROMPT = """You are a research analyst. You are given a
brand/firm, its category, and raw first-party context from it (reviews, support
tickets, positioning, customer language). The category can be anything: a
product, service, software, or provider/firm. Produce realistic, high-intent
queries that real decision-makers in THIS audience ask AI assistants when
choosing in the category.

Rules:
- Ground the queries in the language, use cases, personas, and objections that
  actually appear in the provided context. Mirror how these specific people talk.
- Do NOT mention the brand/firm name in the queries. These are open queries where
  the LLM would freely choose what to recommend.
- Cover a range of intent: discovery, comparison, specific use case, budget,
  persona. Mix specific with broad.
- De-duplicate. Each query should be distinct.
"""


def generate_grounded_queries(
    brand_name: str, category: str, context_text: str, count: int = PANEL_SIZE
) -> dict:
    """
    Generate a context-grounded query panel.

    Returns {"seed_summary": str, "queries": [{"intent": str, "query": str}, ...]}.
    Raises if the model returns far fewer queries than asked for.
    """
    client = Anthropic(api_key=ANTHROPIC_API_KEY)

    # Cap the context we send so a huge paste does not blow the token budget.
    context_excerpt = context_text.strip()[:12000]
    user_prompt = (
        f"Brand we're studying (do NOT mention it in the queries): {brand_name}\n"
        f"Category: {category}\n"
        f"Number of queries to produce: {count}\n\n"
        f"--- BRAND CONTEXT (first-party) ---\n{context_excerpt}\n--- END CONTEXT ---\n\n"
        f"Call build_panel with a seed_summary and {count} grounded queries."
    )

    response = client.messages.create(
        model=MODEL_QUERY_GEN,
        max_tokens=4096,
        system=_GROUNDED_SYSTEM_PROMPT,
        tools=[_PANEL_TOOL],
        tool_choice={"type": "tool", "name": "build_panel"},
        messages=[{"role": "user", "content": user_prompt}],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "build_panel":
            data = block.input
            queries = [
                {"intent": (q.get("intent") or "general").strip(), "query": q["query"].strip()}
                for q in data.get("queries", [])
                if q.get("query", "").strip()
            ]
            if len(queries) < count // 2:
                raise ValueError(
                    f"Grounded gen returned only {len(queries)} queries (wanted {count})."
                )
            return {"seed_summary": (data.get("seed_summary") or "").strip(), "queries": queries}

    raise ValueError("Grounded query generation did not return a build_panel tool call.")
