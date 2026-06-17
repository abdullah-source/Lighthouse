# PRD — Brand Visibility for the LLM Era

**Owner:** Abdullah Ali · **Updated:** June 2026 · **Status:** v1 app built (measurement + normalization + action artifact); causal experiment + MCP next.

This is the live source of truth. It supersedes the positioning in docs 01-04 where they conflict (those predate the June competitive reset).

## 1. Vision

Consumers increasingly ask AI assistants what to buy. The brand the model names gets the sale. We are the layer that measures what AI recommends, proves which change moves it, and ships that change. Measurement is becoming a commodity; proven causal influence over AI recommendations is the durable asset.

## 2. Problem

Brands cannot see whether AI recommends them, who it recommends instead, or what to change. Existing tools (Profound, AirOps, Peec) report a visibility score and, increasingly, generate content. None prove causation: which specific change caused the lift. And naive measurement is wrong because LLMs name one brand many ways ("Brooks", "Brooks Running", "On Cloudmonster").

## 3. Users / ICP

- **Primary (now):** mid-market DTC consumer brands, $10-100M revenue, marketing team but no dedicated SEO hire. They have budget and an existing AI footprint to measure and move.
- **Adjacent (later, honest fit notes):**
  - *PR / comms agencies* — multi-client leverage, but the lane has movers (Bluefish, Meltwater GenAI Lens). Parked.
  - *Early-stage startups wanting AI visibility* — large TAM, but weak fit for the causal wedge: little/no existing AI presence to measure, thin budgets, and moving a brand-new product into AI answers is the slow loop (months). Treat as a v2+ adjacency, not the beachhead.

## 4. Value proposition + differentiator

"We measure how AI recommends or ignores your brand, prove which change moves your mention rate, and ship it." Differentiator = **causal proof + category-dense dataset** (a data network effect), plus **action that is fast, reliable, and seamless** (one click). Stance: neutral, brand-paid only, every recommendation cites the AI responses behind it.

## 5. Product surface

| Capability | State | Notes |
|---|---|---|
| Measurement (probe -> parse -> report) | **Built** | GPT-5 + Claude; mention rate, position, SoV, by-model, competitors. |
| Brand-identity normalization | **Built** | Collapses variants to canonical brands. Fixed the "On" casing + poisoned-alias bug. **Known limitation:** product families that don't contain the brand name (On's "Cloud..." line) are not yet mapped; fix = seed product-family aliases or parser returns brand+product separately. |
| Marketing landing + product app + auth | **Built** | FastAPI-served SPA; Clerk activates with a key. |
| Action artifact generation | **Built** | Sonnet generates publish-ready FAQ targeting a gap. |
| One-click push (live) | **Next** | Needs CMS integration (Shopify/Webflow/WordPress). Today: copy-paste. |
| Causal experiment (baseline/treatment/holdouts) | **Next** | Schema scaffolded; runner + UI to build. The proof slide. |
| Gemini + Perplexity probing | **Next** | Today GPT-5 + Claude only. |
| Agentic query layer + MCP server | **Planned** | See section 9. |

## 6. Out of scope (now)

Multi-tenant org management, billing tiers, CMS push, Postgres, Celery/Redis, mobile, a desktop overlay app.

## 7. Success metrics

- For the user: mention-rate lift per shipped change (target +15pp), time-to-first-insight < 24h.
- For us: free-audit -> pilot conversion; pilot -> paid retention; number of category experiments run (the moat compounds with this).

## 8. Non-functional

- **Cost:** API spend under $500/brand/month at v1. A single audit is ~$0.13.
- **Latency:** audit 60-90s (background + polling); dashboard read instant.
- **Privacy / neutrality:** no consumer data; brand-paid only; no LLM-provider money; public methodology; every recommendation cites its AI-response evidence. Action stays privacy-respecting (no customer/internal data required to generate artifacts).
- **Correctness:** brand-identity resolution is load-bearing; it needs tests (the On bug proved this). Add a normalization test suite before scaling.

## 9. Two product decisions surfaced in this session

### 9a. The "Cluely-like" interface (ask agents about positioning)
The instinct is right; the form factor is not. A desktop overlay that watches your screen is wrong here (privacy, scope, and the value needs no screen access). The correct, on-trend version is two things:
- **A grounded chat panel inside the app:** "How is On positioned vs Hoka on ChatGPT?" answered from the real probe data.
- **An MCP server** (section in the deployment doc) so a marketer's own AI (Claude desktop, Cursor) can query their GEO data directly. Peec and AirOps already ship MCP; this is the standards-based "agent that lives on your computer" without building a desktop app.

Recommendation: build the MCP server + an in-app chat, not a desktop overlay.

### 9b. Early-startup market expansion
Tempting TAM, weak fit for the causal wedge (no baseline, thin budget, slow-loop problem). Recommendation: keep mid-market DTC as the beachhead; revisit early-startup as a v2 adjacency once the causal playbook exists.

## 10. Roadmap

- **Now (this/next week):** ship the causal experiment runner + UI; add normalization tests; one-click "copy artifact" polish.
- **Beta (summer):** deploy (see deployment doc); 2 pilots running; add Perplexity + Gemini; MCP server; in-app chat.
- **v2 (Q4):** CMS push integrations; Postgres; multi-tenant + billing; PR/agency adjacency.

## 11. Risks

Competitors out-execute on breadth (mitigate with causal depth in one category); brand-resolution errors corrupt trust (mitigate with tests); action-layer trust (mitigate: approval-gated, privacy-safe, cited evidence); model non-determinism (mitigate: many trials, holdouts, confidence not certainty).
