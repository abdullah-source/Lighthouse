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


# --- Action workflow: positioning content + JSON-LD schema markup -----------
#
# The real "change the website" output: a publish-ready positioning block PLUS
# the schema.org JSON-LD markup that reinforces the brand's owned attributes for
# AI crawlers. Grounded in the audit (the vibes the brand owns + the sources the
# AI trusts) and honest (no invented facts; [VERIFY] placeholders).

_PLAN_TOOL = {
    "name": "build_action_plan",
    "description": "Produce publish-ready positioning content and matching schema.org JSON-LD markup.",
    "input_schema": {
        "type": "object",
        "properties": {
            "angle": {
                "type": "string",
                "description": "The single positioning angle, one sentence — what to lean into.",
            },
            "positioning_md": {
                "type": "string",
                "description": (
                    "150-300 words of publish-ready Markdown for the brand's site that "
                    "leans into the owned vibes and targets the gap. Mark any specific "
                    "factual claim (price, cert, stat) as [VERIFY: ...]."
                ),
            },
            "schema_jsonld": {
                "type": "string",
                "description": (
                    "A VALID schema.org JSON-LD block as a string (e.g. FAQPage, Product, "
                    "or Service) that reinforces the key attributes for AI crawlers. Use "
                    "placeholder values where specific facts are unknown. Must parse as JSON."
                ),
            },
            "verify_notes": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Specific claims the brand must verify before publishing.",
            },
        },
        "required": ["angle", "positioning_md", "schema_jsonld", "verify_notes"],
    },
}

_PLAN_SYSTEM = (
    "You are a GEO (generative engine optimization) content strategist. Given a brand, "
    "its category, a buyer query it loses on, a winning competitor, the attributes the "
    "AI already associates with the brand (owned vibes), and the source sites the AI "
    "trusts, produce: (1) a publish-ready positioning content block that leans into the "
    "owned vibes and closes the gap, and (2) matching schema.org JSON-LD markup that "
    "reinforces those attributes for AI crawlers. Never invent specific facts — mark them "
    "[VERIFY: ...]. The JSON-LD must be valid JSON."
)


def generate_action_plan(
    brand: str,
    category: str,
    query: str,
    competitor: str | None = None,
    owned_vibes: list[str] | None = None,
    target_sources: list[str] | None = None,
) -> dict:
    """
    Returns {angle, positioning_md, schema_jsonld, verify_notes}, grounded in the
    audit. Uses tool-use so the structure (content + valid JSON-LD) is reliable.
    """
    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    vibes = ", ".join(owned_vibes or []) or "(none captured yet)"
    sources = ", ".join(target_sources or []) or "(none captured yet)"
    comp_line = f"Winning competitor for this query: {competitor}.\n" if competitor else ""
    user = (
        f"Brand: {brand}\n"
        f"Category: {category}\n"
        f"Target buyer query: \"{query}\"\n"
        f"{comp_line}"
        f"Attributes the AI already associates with {brand} (owned vibes): {vibes}\n"
        f"Source sites the AI trusts in this category: {sources}\n\n"
        f"Call build_action_plan with positioning content and schema.org JSON-LD that "
        f"would make AI assistants more likely to recommend {brand} for this query."
    )
    resp = client.messages.create(
        model=MODEL_ACTION,
        max_tokens=1600,
        system=_PLAN_SYSTEM,
        tools=[_PLAN_TOOL],
        tool_choice={"type": "tool", "name": "build_action_plan"},
        messages=[{"role": "user", "content": user}],
    )
    for block in resp.content:
        if block.type == "tool_use" and block.name == "build_action_plan":
            d = block.input
            return {
                "angle": (d.get("angle") or "").strip(),
                "positioning_md": (d.get("positioning_md") or "").strip(),
                "schema_jsonld": (d.get("schema_jsonld") or "").strip(),
                "verify_notes": d.get("verify_notes") or [],
            }
    raise RuntimeError("action plan generation did not return a tool call")
