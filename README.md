# Lighthouse — the measurement layer for AI search

When people ask AI assistants (ChatGPT/GPT-5, Claude, Perplexity) **what to buy or
who to hire**, Lighthouse measures whether your brand or firm is recommended, **who
wins instead**, **why** (the sources the AI cites), **how** the AI describes you
("verbal vibes"), and turns each gap into a **publish-ready change**. Works for
**any category** — a product, service, software, or firm.

A FastAPI web app backed by Postgres + pgvector (Supabase), with a RAG layer.

> Live demo data spans real audits (footwear, sustainable footwear, and more).
> Deploy-ready (Procfile). See [docs/15](docs/15_v2_architecture_lookahead.md) and
> [docs/16](docs/16_v2_mvp_scope_and_demo.md) for architecture + roadmap.

## What it does

One audit of one brand/firm produces a full AI-visibility report:

- **Mention rate, average position, share of voice** — across GPT-5, Claude, and
  Perplexity, with a per-engine breakdown.
- **Competitors** — who the AI recommends instead, ranked.
- **Off-site provenance** — the actual sources each AI cites (the "why," and the
  list of places to go earn presence).
- **Verbal vibes** — the words AI uses to describe you, and the vibes competitors own.
- **Depth-based search** — paste your own context (reviews, positioning, support
  tickets) and we build a **grounded, frozen, versioned query panel** in your real
  buyers' language instead of generic questions.
- **Ask (RAG)** — ask anything; answers are grounded (pgvector retrieval) in the AI
  responses collected for that brand plus any context you added.
- **Brand entity normalization** — variants like "Brooks" / "Brooks Running" counted as one.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then fill in keys (never commit .env)
```

`.env` keys:
- `ANTHROPIC_API_KEY` — required (query gen, parsing, action, Ask).
- `OPENAI_API_KEY` — GPT-5 probe **and** embeddings for RAG.
- `PERPLEXITY_API_KEY` — the retrieval engine that returns **citations**.
- `DATABASE_URL` — Postgres connection string (e.g. Supabase). With it set, the app
  uses Postgres + pgvector. (Run `create extension if not exists vector;` once.)
- `CLERK_PUBLISHABLE_KEY` / `CLERK_SECRET_KEY` — optional auth; demo mode without them.

## Run

```bash
uvicorn api:app --host 0.0.0.0 --port 8000
```

- `http://localhost:8000`      — marketing landing
- `http://localhost:8000/app`  — the product dashboard (run an audit; tabs: Overview, Vibes, Action, Ask)

### Seed familiar brands for an instant demo

```bash
python seed_demo.py          # runs real audits and caches them
```

### Migrate an old local SQLite db into Postgres (one-off)

```bash
python migrate_sqlite_to_pg.py
```

## How it works

```
form (brand/firm, category, optional context)
  → panel.build_panel    grounded (RAG-retrieved context) or generic → FROZEN, versioned panel
  → probe.probe_all      each query × {GPT-5, Claude, Perplexity}, async, retried; Perplexity returns citations
  → parse.parse_all      Haiku tool-use → {brands, positions, descriptors/vibes}
  → store.aggregate_brand canonicalize names; compute metrics + provenance + lexical
  → dashboard
```

RAG ([rag.py](rag.py)): context + collected AI responses are chunked, embedded
(OpenAI `text-embedding-3-small`), stored in a pgvector `vector(1536)` column, and
retrieved by SQL cosine search — used to ground panel generation and the Ask tab.

## File map

| File | Role |
|---|---|
| `api.py` | FastAPI backend; serves the SPA + JSON API |
| `audit.py` | Orchestrates an audit (panel → probe → parse → done); `resume_audit` recovers orphaned runs |
| `panel.py` | Builds + freezes a versioned query panel (grounded or generic) |
| `queries.py` | Generic + grounded buyer-query generation (Claude Sonnet) |
| `probe.py` | Async fan-out — each query × GPT-5 / Claude / Perplexity (+ citations) |
| `parse.py` | Extracts brands, positions, and vibes per response (Haiku tool-use) |
| `rag.py` | Chunk → embed → pgvector cosine retrieval → grounded Ask answers |
| `brand_identity.py` | Canonicalizes brand/firm name variants |
| `store.py` | DB layer (Postgres): panels, chunks, aggregate (metrics + provenance + lexical) |
| `db.py` | Postgres + pgvector schema, connection pool, helpers |
| `action.py` | Generates a publish-ready action artifact |
| `config.py` | Env vars, model IDs, tuning knobs |
| `seed_demo.py` | Pre-run real audits for familiar brands (instant demo) |
| `migrate_sqlite_to_pg.py` | One-off SQLite → Postgres data migration |
| `web/` | Frontend SPA (light "Signal" theme): landing + dashboard |
| `Procfile` | Deploy start command (`uvicorn ... --port $PORT`) |

## Cost

Per audit, one-time (cached after; same for any vertical):

| Audit | Calls | Est. cost |
|---|---|---|
| Generic (20 queries × 3 engines) | ~121 | ~$0.70–1.00 |
| Grounded (40 queries × 3 engines + embeds) | ~245 | ~$1.50–2.50 |

GPT-5 probing dominates; Haiku parsing and Perplexity are cheap; a frozen panel makes
query generation a one-time cost.

## Deploy

- **Database:** Supabase (Postgres + pgvector). Set `DATABASE_URL` in the host env.
- **App:** any host that runs the Procfile. Railway: deploy from GitHub, set the env
  vars (`DATABASE_URL`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `PERPLEXITY_API_KEY`),
  and it serves both the API and the dashboard.

## Roadmap

Auth/guard on the public app → durable job queue (arq + Redis, so audits survive
restarts) → crawler/agent-readiness diagnostics → collaborative content workflow →
causal proof loop (difference-in-differences) → MCP server. See
[docs/15](docs/15_v2_architecture_lookahead.md) and [docs/16](docs/16_v2_mvp_scope_and_demo.md).
