"""
mcp_server.py - a Model Context Protocol server that exposes Lighthouse's
AI-visibility data as tools.

This lets a marketing team's OWN agent (Claude Desktop, Cursor, etc.) query
Lighthouse directly: "how is my brand doing in AI search?", "who wins?",
"what does AI say about us?" — the agent calls these tools, which read the
same Postgres + pgvector data the web app uses.

Run (stdio):
    .venv/bin/python mcp_server.py

Connect from Claude Desktop (claude_desktop_config.json):
    {
      "mcpServers": {
        "lighthouse": {
          "command": "/abs/path/.venv/bin/python",
          "args": ["/abs/path/mcp_server.py"]
        }
      }
    }
The process loads DATABASE_URL + API keys from .env, same as the web app.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

import rag
import store

mcp = FastMCP("Lighthouse")


@mcp.tool()
def list_brands() -> list[dict]:
    """List the brands/firms that have been audited, with their headline mention rate."""
    return [
        {"name": b["name"], "category": b["category"], "status": b["status"],
         "mention_rate": b["mention_rate"]}
        for b in store.list_brands()
    ]


@mcp.tool()
def get_report(brand: str) -> dict:
    """
    Full AI-visibility report for a brand by name: mention rate, by-engine
    breakdown, ranked competitors, the verbal vibes (how AI describes it), and
    the off-site sources the AI cites.
    """
    bid = store.find_brand_by_name(brand)
    if bid is None:
        return {"error": f"No audited brand named '{brand}'. Use list_brands to see options."}
    agg = store.aggregate_brand(bid)
    lex = agg.get("lexical", {})
    return {
        "brand": agg["name"],
        "category": agg["category"],
        "mention_rate": agg["mention_rate"],
        "avg_position": agg["avg_position"],
        "share_of_voice": agg["share_of_voice"],
        "by_model": agg["by_model"],
        "competitors": [{"brand": c["brand"], "rate": c["rate"]} for c in agg["competitors"][:8]],
        "vibes_you_own": [x["term"] for x in lex.get("you_own", [])[:10]],
        "vibes_competitors_own": [x["term"] for x in lex.get("they_own", [])[:10]],
        "top_cited_sources": [s["domain"] for s in agg.get("provenance", {}).get("top_sources", [])[:8]],
        "responses_analyzed": agg["total_responses"],
    }


@mcp.tool()
def ask(brand: str, question: str) -> dict:
    """
    Ask a question about a brand. Grounded (RAG) in that brand's collected AI
    responses and context when available; otherwise a general answer.
    """
    bid = store.find_brand_by_name(brand)
    if bid is None:
        return {"error": f"No audited brand named '{brand}'. Use list_brands to see options."}
    out = rag.answer(bid, question)
    return {"answer": out["answer"], "grounded": out.get("grounded", False),
            "sources": out.get("sources", [])}


if __name__ == "__main__":
    store.migrate()
    mcp.run()
