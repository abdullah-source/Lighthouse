"""
aivision.py - the "AI Vision for startups" backend.

For an early-stage brand with ~0 AI presence, "where do you rank" is the wrong
question - the honest answer is "nowhere yet." This module reframes the audit
into an offensive playbook: given the category reality (who AI recommends and
the language it rewards), the brand's real positioning, and its actual landing
page, it produces (a) a strategic-coherence read - where the brand's claims,
its live site, and the winning category language agree or diverge - and (b)
concrete, paste-ready landing-page changes + schema that build the brand's image
in the eyes of AI. One Sonnet call, structured via tool-use. Grounded only in
the supplied evidence; the model is told not to invent brand facts.
"""

from __future__ import annotations

import re

import httpx
from anthropic import Anthropic

from config import ANTHROPIC_API_KEY, MODEL_ACTION

UA = "Mozilla/5.0 (compatible; LighthouseBot/0.1)"


def fetch_landing_text(url: str, limit: int = 6000) -> str:
    """Fetch a landing page and return crawlable text (what an AI crawler sees)."""
    if not url:
        return ""
    if not url.startswith("http"):
        url = "https://" + url
    try:
        r = httpx.get(url, timeout=15, follow_redirects=True, headers={"User-Agent": UA})
        html = r.text
    except Exception:
        return ""
    html = re.sub(r"(?is)<(script|style|noscript|svg).*?</\1>", " ", html)
    text = re.sub(r"\s+", " ", re.sub(r"(?s)<[^>]+>", " ", html)).strip()
    return text[:limit]


_TOOL = {
    "name": "ai_vision_plan",
    "description": "A startup-focused AI-visibility playbook grounded in the audit.",
    "input_schema": {
        "type": "object",
        "properties": {
            "positioning_read": {"type": "string", "description": "One-line read of what this brand is really selling."},
            "category_reality": {"type": "string", "description": "2-3 sentences: who AI recommends in this category and the pattern (e.g. legacy brands dominate, the brand's niche is open). Use the real names/percentages."},
            "coherence": {
                "type": "array",
                "description": "Strategic-coherence rows: for each core claim, whether it is aligned/gap/missing across the brand's positioning, its live site, and the language AI rewards.",
                "items": {
                    "type": "object",
                    "properties": {
                        "claim": {"type": "string"},
                        "status": {"type": "string", "enum": ["aligned", "gap", "missing"]},
                        "finding": {"type": "string", "description": "What is true now, referencing site + AI-answer language."},
                        "fix": {"type": "string", "description": "The specific move to close it."},
                    },
                    "required": ["claim", "status", "finding", "fix"],
                },
            },
            "landing_changes": {
                "type": "array",
                "description": "Concrete, paste-ready landing-page edits. Quote the brand's ACTUAL current copy where possible.",
                "items": {
                    "type": "object",
                    "properties": {
                        "section": {"type": "string"},
                        "current": {"type": "string", "description": "The brand's real current copy, or 'absent' if the section does not exist."},
                        "suggested": {"type": "string", "description": "Paste-ready replacement that weaves in winning language the brand can truthfully claim."},
                        "why": {"type": "string"},
                    },
                    "required": ["section", "current", "suggested", "why"],
                },
            },
            "terms_to_own": {"type": "array", "items": {"type": "string"}, "description": "Winning category words the brand can truthfully claim but does not yet own."},
            "schema_jsonld": {"type": "string", "description": "Valid JSON-LD (Organization + Product) the brand can paste into its <head>. Real values where known, [VERIFY] placeholders otherwise."},
            "per_model": {
                "type": "array",
                "description": "One insight per engine on how to earn presence there.",
                "items": {
                    "type": "object",
                    "properties": {"model": {"type": "string"}, "insight": {"type": "string"}},
                    "required": ["model", "insight"],
                },
            },
            "priority_moves": {"type": "array", "items": {"type": "string"}, "description": "The 3-5 highest-leverage moves, ordered."},
        },
        "required": ["positioning_read", "category_reality", "coherence", "landing_changes", "terms_to_own", "schema_jsonld", "per_model", "priority_moves"],
    },
}

_SYSTEM = (
    "You are a GEO (generative engine optimization) strategist for early-stage "
    "brands that currently have near-zero visibility in AI assistant answers. "
    "Reframe the problem from 'where do you rank' to 'how do we build this brand's "
    "image in the eyes of AI so it starts getting recommended.' You are given the "
    "measured category reality (who AI recommends and the language it rewards), the "
    "brand's own positioning, and its ACTUAL live landing-page text. "
    "Rules: ground every statement in the supplied evidence - never invent facts, "
    "prices, or certifications about the brand (use [VERIFY] placeholders). For "
    "landing_changes, quote the brand's real current copy and write suggested copy "
    "that truthfully weaves in the winning category language the brand can legitimately "
    "claim (from its stated positioning). Be concrete and paste-ready, not generic."
)


def generate_ai_vision(
    *,
    brand: str,
    category: str,
    positioning: str,
    landing_text: str,
    competitors: list[dict],
    they_own: list[str],
    sources: list[str],
    by_model: list[dict],
    your_avg_rank: float | None = None,
) -> dict:
    """One Sonnet tool-use call -> structured AI-vision playbook."""
    comp_lines = "\n".join(
        f"  - {c['brand']}: recommended in {round((c.get('rate') or 0)*100)}% of answers"
        for c in (competitors or [])[:8]
    ) or "  (none surfaced)"
    model_lines = "\n".join(
        f"  - {m['model']}: brand appears in {round((m.get('rate') or 0)*100)}% of its answers"
        for m in (by_model or [])
    ) or "  (n/a)"
    rank_line = (
        f"When we reconstruct the retrieval, the brand's own page ranks about #{round(your_avg_rank)} "
        "of the candidate pages for these buyer queries (near the bottom)."
        if your_avg_rank else ""
    )
    user = f"""BRAND: {brand}
CATEGORY: {category}

BRAND POSITIONING (from the founder):
{positioning}

MEASURED CATEGORY REALITY - who AI recommends when buyers ask about this category:
{comp_lines}

Per engine, how often THIS brand appears:
{model_lines}
{rank_line}

Language AI already associates with the winning brands (the category's winning vocabulary):
  {', '.join(they_own[:16]) or '(none captured)'}

Sources AI cites most in this category (where a brand must earn presence):
  {', '.join(sources[:10]) or '(none captured)'}

THE BRAND'S ACTUAL LIVE LANDING-PAGE TEXT (what an AI crawler sees today):
\"\"\"{landing_text[:5000]}\"\"\"

Produce the ai_vision_plan. Focus on strategic coherence (positioning vs live site
vs winning language) and concrete landing-page changes that would build this
brand's image in AI answers. Use the real brand and competitor names.
Keep it tight: at most 6 coherence rows, at most 6 landing_changes, exactly 5
priority_moves, one insight per engine. Always fill priority_moves and
schema_jsonld."""

    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model=MODEL_ACTION,
        max_tokens=8000,
        system=_SYSTEM,
        tools=[_TOOL],
        tool_choice={"type": "tool", "name": "ai_vision_plan"},
        messages=[{"role": "user", "content": user}],
    )
    for block in msg.content:
        if getattr(block, "type", None) == "tool_use":
            return dict(block.input)
    # Fallback: should not happen with forced tool_choice
    return {"error": "no structured output"}
