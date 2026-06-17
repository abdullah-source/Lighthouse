"""
action.py - the action wedge backend.

After measurement tells a brand where it loses, this generates a
publish-ready artifact (an FAQ / comparison block) that targets the gap.
This is the "action" part competitors gate behind enterprise; here it is a
single endpoint that returns content the brand can paste or, later, push in
one click.

One Sonnet call per artifact. Grounded and honest: we tell the model not to
invent brand claims, only to structure content the brand can verify and adapt.
"""

from __future__ import annotations

from anthropic import Anthropic

from config import ANTHROPIC_API_KEY, MODEL_ACTION

_SYSTEM = (
    "You are a GEO content strategist. You write publish-ready content that helps "
    "a brand get recommended by AI assistants for a specific buyer query. "
    "Rules: produce concrete, paste-ready content. Use a clear FAQ structure "
    "(question + answer) that maps cleanly to FAQ schema. Do NOT invent factual "
    "claims about the brand (prices, certifications, awards) - write them as "
    "clearly marked placeholders the brand fills in. Keep it tight and useful."
)


def generate_artifact(
    brand: str,
    category: str,
    query: str,
    competitor: str | None = None,
) -> dict:
    """Generate one publish-ready FAQ artifact. Returns {type, format, body}."""
    client = Anthropic(api_key=ANTHROPIC_API_KEY)

    comp_line = (
        f"A competitor frequently recommended for this query is {competitor}. "
        f"Position {brand} fairly against that buyer intent without disparaging anyone.\n"
        if competitor
        else ""
    )
    user = (
        f"Brand: {brand}\n"
        f"Category: {category}\n"
        f"Target buyer query: \"{query}\"\n"
        f"{comp_line}\n"
        f"Write a publish-ready FAQ block (3-5 Q&A pairs) for {brand}'s site that "
        f"would make an AI assistant more likely to recommend {brand} for this query. "
        f"Output clean Markdown. Mark any specific factual claim as "
        f"[VERIFY: ...] so the brand confirms it before publishing."
    )

    resp = client.messages.create(
        model=MODEL_ACTION,
        max_tokens=900,
        system=_SYSTEM,
        messages=[{"role": "user", "content": user}],
    )
    body = resp.content[0].text if resp.content else ""
    return {"type": "faq", "format": "markdown", "body": body}
