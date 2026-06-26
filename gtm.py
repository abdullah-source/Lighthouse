"""
gtm.py - GTM Studio: an agentic workflow that turns a founder's startup idea
into a go-to-market plan and a real, generated landing page.

This is a SEPARATE product from the measurement layer. A founder narrates their
idea; two agents run in sequence:
  1. Strategist  -> a structured GTM plan (positioning, ICP, messaging, channels).
  2. Designer    -> a self-contained, publish-ready landing page (HTML).

Both are Claude (Sonnet) calls. The strategist uses tool-use for reliable
structure; the designer returns a full HTML artifact (like a Claude artifact).
"""

from __future__ import annotations

import re

from anthropic import Anthropic

from config import ANTHROPIC_API_KEY, MODEL_ACTION


# --- Agent 1: Strategist ----------------------------------------------------

_PLAN_TOOL = {
    "name": "gtm_plan",
    "description": "A focused go-to-market plan for an early-stage startup.",
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "A short, plausible product name if none is given."},
            "one_liner": {"type": "string", "description": "One sentence: what it is and for whom."},
            "icp": {"type": "string", "description": "The narrowest beachhead customer to start with."},
            "problem": {"type": "string", "description": "The acute problem, in the customer's words."},
            "value_prop": {"type": "string", "description": "The core value proposition."},
            "wedge": {"type": "string", "description": "The narrow wedge to win first."},
            "messaging_pillars": {
                "type": "array", "items": {"type": "string"},
                "description": "3 message pillars the brand should own.",
            },
            "channels": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "why": {"type": "string"},
                        "first_move": {"type": "string", "description": "A concrete first action."},
                    },
                    "required": ["name", "why", "first_move"],
                },
                "description": "3 launch channels, ranked, each with a concrete first move.",
            },
            "first_campaign": {"type": "string", "description": "A specific first campaign to run in week one."},
            "north_star": {"type": "string", "description": "The one metric to watch early."},
        },
        "required": ["name", "one_liner", "icp", "problem", "value_prop", "wedge",
                     "messaging_pillars", "channels", "first_campaign", "north_star"],
    },
}

_STRATEGIST_SYSTEM = (
    "You are a sharp go-to-market strategist for early-stage startups (YC-grade thinking). "
    "Given a founder's raw idea, produce a focused, opinionated GTM plan: a narrow beachhead "
    "ICP, the acute problem, a crisp value prop, the wedge to win first, 3 message pillars, "
    "3 ranked launch channels each with a concrete first move, a specific week-one campaign, "
    "and one early metric. Be specific and realistic, not generic. Do not hedge."
)


def generate_gtm_plan(idea: str) -> dict:
    """Strategist agent: idea -> structured GTM plan."""
    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    resp = client.messages.create(
        model=MODEL_ACTION, max_tokens=1600, system=_STRATEGIST_SYSTEM,
        tools=[_PLAN_TOOL], tool_choice={"type": "tool", "name": "gtm_plan"},
        messages=[{"role": "user", "content": f"Founder's idea:\n{idea.strip()[:4000]}"}],
    )
    for block in resp.content:
        if block.type == "tool_use" and block.name == "gtm_plan":
            return block.input
    raise RuntimeError("strategist did not return a plan")


# --- Agent 2: Designer ------------------------------------------------------

_DESIGNER_SYSTEM = (
    "You are a senior product designer + copywriter. Given a startup and its GTM plan, "
    "produce ONE self-contained, modern, aesthetic landing page as a single HTML document "
    "(inline CSS only; you may use one Google Fonts link). Light, clean, premium SaaS look. "
    "Include: a nav with the product name, a hero (headline from the one-liner + subhead + a "
    "primary CTA button), a 3-up value section from the message pillars, a short 'how it works' "
    "or social-proof strip, and a closing CTA + footer. Use real copy from the plan, not lorem "
    "ipsum. "
    "CRITICAL: the document MUST be COMPLETE and valid, ending with </html>. Keep the CSS "
    "concise (a tight <style> block, not exhaustive) so you never run out of room before the "
    "body. Finishing the whole page matters more than elaborate styling. "
    "Return ONLY the HTML document, starting with <!DOCTYPE html>. No commentary, no code fences."
)


def generate_landing_html(idea: str, plan: dict) -> str:
    """Designer agent: idea + plan -> a self-contained landing page (HTML string)."""
    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    plan_brief = (
        f"Product: {plan.get('name')}\nOne-liner: {plan.get('one_liner')}\n"
        f"ICP: {plan.get('icp')}\nValue prop: {plan.get('value_prop')}\n"
        f"Message pillars: {', '.join(plan.get('messaging_pillars', []))}\n"
    )
    resp = client.messages.create(
        model=MODEL_ACTION, max_tokens=8000, system=_DESIGNER_SYSTEM,
        messages=[{"role": "user", "content": f"Startup idea:\n{idea.strip()[:2000]}\n\nGTM plan:\n{plan_brief}\n\nDesign the landing page."}],
    )
    html = resp.content[0].text if resp.content else ""
    # strip any stray code fences just in case
    html = re.sub(r"^```html\s*|\s*```$", "", html.strip())
    if "<!DOCTYPE" in html:
        html = html[html.index("<!DOCTYPE"):]
    # Guard: if the model still got cut off before closing the document, make it
    # valid so the iframe renders what we have rather than a blank page.
    if "</html>" not in html:
        if "</body>" not in html:
            html += "\n</body>"
        html += "\n</html>"
    return html
