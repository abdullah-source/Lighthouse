# v1 Architecture — GEO measurement app

How the pieces fit, and every variable that matters. Built June 2026.

## Stack (what runs where)

| Layer | Software | Why |
|---|---|---|
| Frontend | Static SPA (HTML + CSS + vanilla JS), served by the backend | Aesthetic, zero build chain, deploys with the API. Next.js deferred. |
| Backend | FastAPI (Python) + Uvicorn | Async-native, reuses `probe.py` / `parse.py` / `queries.py` directly. |
| Pipeline | asyncio + httpx (existing) | Fan-out probing and parsing already work. |
| Database | SQLite (`data/probe.sqlite`) | Right for v1 scale (10 brands). One file, zero ops. |
| LLM APIs | Anthropic (Claude + Haiku), OpenAI (GPT-5) | Probing + parsing. Gemini + Perplexity next. |
| Hosting (later) | Railway (backend + SQLite volume) | Free tier covers the closed beta. |

## The two kinds of variables

### A. GEO domain variables (the problem)
- **Models / surfaces:** which LLMs we probe (GPT-5, Claude now; Gemini, Perplexity next). Each is a separate visibility surface.
- **Query set:** the buyer queries per category. Generated once per brand (Sonnet), editable.
- **Trials per query:** LLMs are non-deterministic, so each query runs N times. Metrics are distributions, not single answers.
- **Brand entity resolution:** the same brand appears as "Brooks", "Brooks Running", "Brooks Adrenaline GTS 23". Must collapse to one canonical brand before counting. This is the silent killer of the numbers. Solved in `brand_identity.py`.
- **Metrics:** mention rate, average position, share of voice, sentiment, by-model breakdown, top competitors.
- **Fast loop vs slow loop:** retrieval models change in days; base models change over months. Both are surfaces we measure.
- **Experiment variables (causal):** target query, candidate content, phase (baseline vs treatment), holdout queries, measured lift.

### B. App infrastructure variables (the system)
- **Frontend:** the dashboard. Renders metrics from the API.
- **Backend API:** FastAPI endpoints (list audits, start audit, fetch dashboard, poll status).
- **Pipeline / jobs:** an audit is generate-queries -> probe -> parse -> normalize -> aggregate. Long (60-90s), so it runs as a background task with status polling.
- **Database:** brands, queries, responses, parsed_responses, brand_aliases, experiments.
- **Config / secrets:** `.env` (Anthropic + OpenAI keys). Never committed.
- **Concurrency:** semaphores cap parallel API calls (rate-limit safety).
- **Status / observability:** each audit has a status (pending, probing, parsing, done, error).

## Data flow

```
  Browser (dashboard)
        |  POST /api/audits {brand, category}
        v
  FastAPI  --background task-->  audit.run_audit(brand_id)
        |                              |
        |                              +-- queries.generate_queries  (Sonnet)
        |                              +-- probe.probe_all           (GPT-5 + Claude)
        |                              +-- parse.parse_all           (Haiku tool-use)
        |                              +-- brand_identity.canonicalize (Brooks fix)
        |                              +-- store: write rows, set status
        v
  Browser polls GET /api/brands/{id}/status -> "done"
        |  GET /api/brands/{id}
        v
  Dashboard renders: mention rate, position, share of voice, by-model, competitors
```

## Schema (v1 additions over v0)

- `brands`: + `status`, + `canonical_name`.
- `brand_aliases`: `canonical`, `alias` (normalized), UNIQUE(alias). The learned mapping that grows over time.
- `experiments`: `brand_id`, `target_query`, `candidate_content`, `baseline_rate`, `treatment_rate`, `created_at`. (Scaffold for the causal layer.)
- `responses`: + `phase` ('baseline' default), + `experiment_id` (nullable). (Scaffold.)
- Existing v0 tables and data are preserved by an idempotent migration.

## The Brooks brand-identity solution

`brand_identity.py` canonicalizes every raw brand string before aggregation:
1. Clean: trim, collapse whitespace, drop punctuation noise.
2. Known-brand match: if the cleaned string starts with a known brand (longest match first, word-boundary aware), map to it. "Brooks Adrenaline GTS 23" -> "Brooks", "Hoka Bondi 8" -> "Hoka".
3. Suffix strip: remove corporate tails (Running, Sports, Footwear, Inc, LLC, Co). "Brooks Running" -> "Brooks".
4. Alias table: learned mappings from the DB take priority and accumulate.
5. Fallback: unknown brands keep a cleaned head form and are recorded as their own canonical.

The dashboard surfaces the effect directly: "N raw variants merged into M brands," so the fix is visible, not hidden.

## Endpoints

- `GET  /api/brands` — list audited brands with headline metrics.
- `POST /api/audits` — start an audit `{brand, category}`; returns brand_id + status.
- `GET  /api/brands/{id}` — full dashboard payload.
- `GET  /api/brands/{id}/status` — for polling while an audit runs.
- `GET  /` — the dashboard SPA.

## Deferred (not in v1)
Postgres, Celery/Redis, Clerk auth, multi-tenant, CMS push, Gemini/Perplexity probing, the live-web causal test.
