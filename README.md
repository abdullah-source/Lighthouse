# Brand Visibility for the LLM Era — v2

Measure whether AI assistants (ChatGPT/GPT-5, Claude, Perplexity) recommend a
brand for real buyer questions, **who** they recommend instead, **why** (the
sources they cite), and **how** they describe each brand ("verbal vibes"). A
local FastAPI web app with a measurement engine, a RAG-grounded depth layer, and
a dashboard. Think "Search Console for the answer engines."

> Status: **v2 MVP, branch `v2-mvp`, runs locally.** Cloud deploy
> (Postgres + pgvector on Supabase/Railway) is the next step — see
> [docs/15_v2_architecture_lookahead.md](docs/15_v2_architecture_lookahead.md)
> and [docs/16_v2_mvp_scope_and_demo.md](docs/16_v2_mvp_scope_and_demo.md).

## What it does

One audit of one brand produces a full AI-visibility report:

- **Mention rate** — % of buyer queries where the brand appears in AI answers.
- **By-engine breakdown** — visibility across GPT-5, Claude, Perplexity.
- **Competitors** — who the AI recommends instead, ranked, with positions.
- **Share of voice + average position.**
- **Verbal vibes (lexical environment)** — the words AI uses to describe the
  brand, plus **vibes you own vs vibes competitors own**.
- **Off-site provenance** — the actual sources the AI cited (the "why," and the
  target list for action).
- **Depth-based search** — paste the brand's own context (reviews, positioning,
  support tickets) and we build a **grounded, frozen, versioned query panel** in
  that brand's real buyer language instead of generic questions.
- **Ask (RAG)** — ask questions answered over the brand's own indexed context.
- **Brand entity normalization** — "Brooks" and "Brooks Running" counted as one.

## Setup

```bash
cd "/Users/abdullahali/project - summer"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then edit .env, paste keys (never commit it)
```

API keys (`.env`):
- `ANTHROPIC_API_KEY` — **required** (query gen, parsing, action, Ask).
- `OPENAI_API_KEY` — GPT-5 probe **and** embeddings for RAG.
- `PERPLEXITY_API_KEY` — retrieval engine that returns **citations** (the "why").
- `CLERK_PUBLISHABLE_KEY` / `CLERK_SECRET_KEY` — optional; logins activate only
  if present, otherwise the app runs in open demo mode.

Each key is optional except Anthropic; missing keys degrade gracefully (the
relevant engine/feature is skipped, the app still runs).

## Run (web app)

```bash
.venv/bin/uvicorn api:app --port 8000
```

- `http://localhost:8000`     — marketing landing
- `http://localhost:8000/app` — the product dashboard (run an audit, view results)

Run an audit from the form (brand + category, plus optional context for a
grounded panel). It runs in the background (~60–120s) and the dashboard polls
until done. Tabs: **Overview**, **Vibes**, **Action**, **Ask**.

### Seed familiar brands for an instant demo

```bash
.venv/bin/python seed_demo.py        # Nike, Adidas, Puma, Reebok, Oofos (cached)
```

Runs real audits once; they persist so the demo opens instantly with authentic
data. Enterprise examples (consulting, legal) are in `seed_demo.py` as
`ENTERPRISE_BRANDS`, run explicitly when you want to show the product ports
beyond footwear.

### v0 CLI (still works)

```bash
python main.py --brand "Allbirds" --category "sustainable footwear"
```

## How it works (pipeline)

```
form (brand, category, optional context)
  → panel.build_panel   grounded (RAG-retrieved context) or generic → FROZEN, versioned panel
  → probe.probe_all     each query × {GPT-5, Claude, Perplexity}, async, retried
                        (Perplexity returns cited sources)
  → parse.parse_all     Haiku tool-use → {brands, positions, descriptors/vibes}
  → store.aggregate_brand   canonicalize names; compute metrics + provenance + lexical
  → dashboard
```

RAG ([rag.py](rag.py)): context is chunked, embedded (OpenAI
`text-embedding-3-small`), stored as vectors, and retrieved by cosine — used to
ground panel generation and to power the **Ask** tab. The vector store sits
behind a thin interface (`store.save_chunks`/`fetch_chunks`) so it swaps to
pgvector on deploy.

## File map

| File | Role |
|---|---|
| `api.py` | FastAPI backend + serves the web app + JSON API |
| `audit.py` | Orchestrates one audit (panel → probe → parse → done), background task |
| `panel.py` | Builds + freezes a versioned query panel (grounded or generic) |
| `queries.py` | Generic + **grounded** buyer-query generation (Claude Sonnet) |
| `probe.py` | Async fan-out — each query × GPT-5 / Claude / Perplexity (+ citations) |
| `parse.py` | Extracts brands, positions, and **vibes** per response (Haiku tool-use) |
| `rag.py` | Chunk → embed → cosine retrieval → grounded **Ask** answers |
| `brand_identity.py` | Canonicalizes brand-name variants (the Brooks/On fix) |
| `store.py` | v1 DB layer: migrations, panels, aggregate (metrics + provenance + lexical) |
| `db.py` | SQLite schema + insert/fetch helpers |
| `action.py` | Generates a publish-ready action artifact (the wedge) |
| `config.py` | Env vars, model IDs, tuning knobs |
| `seed_demo.py` | Pre-run real audits for familiar brands (instant demo) |
| `web/` | Frontend SPA: landing, dashboard (Overview/Vibes/Action/Ask), auth |
| `main.py`, `report.py` | v0 CLI entrypoint + terminal report (still functional) |
| `data/probe.sqlite` | Auto-created, gitignored |

## Cost

Per audit (cached after; re-run only for a fresh trend point):

| Audit | Calls | Est. cost |
|---|---|---|
| Generic (20 queries × 3 engines) | ~121 | **~$0.70–1.00** |
| Grounded (40 queries × 3 engines + embeds) | ~245 | **~$1.50–2.50** |

GPT-5 probing dominates; Haiku parsing and Perplexity Sonar are cheap; a frozen
panel makes query generation a one-time cost. At ~$1–2/audit you can re-measure a
brand daily and stay well under the $500/brand/month ceiling.

## What's next (roadmap)

Cloud foundation (Postgres + pgvector, Railway deploy) → parser v2
(attributes/sentiment) + provenance source-classification + absent-source
analysis → crawler/agent-readiness diagnostics → collaborative content workflow
→ causal proof loop (difference-in-differences) → MCP server + multitenancy.

Full plan and strategy of record:
[docs/13](docs/13_strategy_and_pivot_assessment.md),
[docs/14](docs/14_session_log_2026-06-12.md),
[docs/15](docs/15_v2_architecture_lookahead.md),
[docs/16](docs/16_v2_mvp_scope_and_demo.md).
