# 15 — V2 Architecture Lookahead (technical)

Date: June 14, 2026.
Purpose: a precise, technical forward design of the product moving from the
current v1 to v2, written as context for engineers / future sessions. It covers
the problem, the full action/solution workflow, every new component, the data
model and API evolution, orchestration, and deployment.

Read with: [13_strategy_and_pivot_assessment.md](13_strategy_and_pivot_assessment.md)
(strategy of record) and [14_session_log_2026-06-12.md](14_session_log_2026-06-12.md)
(how we got here). This doc is the technical "where it goes."

---

## 0. Baseline: what v1 is today (the thing we evolve)

Monolithic FastAPI + SQLite app, async fan-out to LLM APIs.

```
api.py            FastAPI: pages + JSON API; BackgroundTasks runs audits
audit.py          sync orchestrator: generate → probe → parse → status
queries.py        1 Claude Sonnet call → ~20 generic buyer queries
probe.py          async fan-out → {gpt-5, claude-sonnet, perplexity-sonar}
                  perplexity-sonar returns cited sources (httpx, raw JSON)
parse.py          Claude Haiku tool-use → {brands_mentioned, positions}
brand_identity.py deterministic canonicalization (the Brooks/On fix)
store.py          migrate(), aggregate_brand() (read-time normalization),
                  _build_provenance() (ranked cited domains), aliases, experiments
db.py             SQLite schema + helpers
config.py         keys + model IDs + tuning knobs
web/              static SPA (index.html, app.html, app.js, styles.css, auth.js)
```

Current data model (SQLite, `data/probe.sqlite`):
- `brands(id, name, category, created_at, status, canonical_name, error_message)`
- `queries(id, brand_id, query_text, created_at)`
- `responses(id, query_id, model, raw_text, citations, created_at, phase, experiment_id)`
- `parsed_responses(id, response_id, brands_mentioned, positions, parsed_at)`
- `brand_aliases(id, canonical, alias, created_at)`
- `experiments(id, brand_id, target_query, candidate_content, baseline_rate, treatment_rate, created_at)`

Limitations v2 must fix: queries are generic + non-reproducible; no first-party
grounding; no run/panel concept (can't trend or prove); provenance is
domain-frequency only; action is a one-shot generic FAQ; orchestration is
in-process BackgroundTasks (no scheduling, no durability); single-writer SQLite.

---

## 1. Problem statement (technical framing)

For a given brand B in vertical V, and the set of real buyer intents Q that
consumers express to LLM assistants, we must:

1. **Estimate** P(B is recommended | q) across engines E, with position and
   share-of-voice, reproducibly over time.
2. **Explain** *why*: the retrieved sources S(q) the engine grounded on, and
   B's presence/absence in S(q) (the off-site provenance).
3. **Act**: make B's owned properties machine-readable/preferred by AI crawlers,
   and generate grounded content targeting the gap.
4. **Prove**: show that a specific change Δ caused ΔP(recommended) on a held
   panel, controlling for background engine drift.

v2 is the system that does all four as a continuous, multi-tenant service.

---

## 2. Target architecture (component view)

```
                         ┌──────────────────────────────────────────────┐
   Clerk auth ──────────►│  FastAPI (web)  — REST + SSE + serves SPA      │
                         └───────────────┬──────────────────────────────┘
                                         │ enqueue jobs / read
                         ┌───────────────▼──────────────────────────────┐
                         │  Postgres + pgvector (Supabase / Railway PG)   │
                         │  brands, context_docs, context_chunks(vec),    │
                         │  query_panels, panel_queries, runs, responses, │
                         │  parsed_responses, citation_nodes, provenance, │
                         │  crawl_audits, content_artifacts, experiments  │
                         └───────────────▲──────────────────────────────┘
                                         │ read/write
   ┌─────────────────────────────────────┴───────────────────────────────┐
   │  arq worker(s)  (asyncio task queue + cron scheduler)                  │
   │  jobs: ingest_context, build_panel, run_measurement, parse_batch,      │
   │        build_provenance, crawl_audit, generate_content, run_experiment │
   └───────┬─────────────┬─────────────┬───────────────┬──────────────────┘
           │             │             │               │
     LLM APIs      Perplexity     Embeddings       Headless fetch
   (Claude/GPT)    Sonar (cites)  (text-embed-3)   (httpx + Playwright)
                                         │
                         ┌───────────────▼──────────────┐
                         │  MCP server (stdio/http)       │
                         │  tools over the same data      │
                         └───────────────────────────────┘
```

---

## 3. Layer-by-layer technical design

### A. Ingestion + RAG context layer (NEW)

Job: `ingest_context`. Inputs: pasted text, file upload, or connector (Shopify
reviews, Zendesk tickets, GA/site-search export, sitemap/product feed).

Pipeline:
1. Normalize to documents → `context_documents`.
2. Chunk (≈400–800 tokens, overlap 80) → embed with `text-embedding-3-small`
   (1536-d) → `context_chunks(embedding vector(1536))` with an `ivfflat`/`hnsw`
   index for cosine search.
3. Extract a `seed_summary`: salient buyer intents, personas, objections,
   product attributes, and the brand's own vocabulary (one Sonnet pass over
   retrieved representative chunks).

Why: this is the depth/anti-vibecode layer. The panel and the content are
grounded in B's real customer language, not a generic generator.

### B. Query / panel layer (NEW; replaces ad-hoc `queries.py`)

Concept: a **panel** is a versioned, frozen set of buyer queries for a brand.

Job: `build_panel`.
1. RAG-retrieve representative context chunks + seed_summary.
2. Generate candidate queries (Sonnet), each tagged `intent`
   (discovery/comparison/use-case/budget/persona), `persona`, and
   `grounded_from` (chunk ids).
3. Cluster/dedupe (embedding cosine + intent) to a balanced panel (~30–60).
4. Status `draft`; human can edit; then `freeze` → immutable `version`.

Reproducibility + causal proof both require freezing: all runs and experiments
reference a `panel_id` (a specific frozen version).

### C. Measurement layer (engine fan-out, scheduled)

Job: `run_measurement(brand_id, panel_id, engine_set)` → creates a `run`.
- Reuses the v1 `probe.py` fan-out, generalized: `engine_set` configurable.
- Engines v2: `claude` (weights baseline), `gpt-5` and `chatgpt-search`
  (OpenAI Responses API + `web_search` tool, annotations = citations),
  `perplexity-sonar` (have it), `gemini-grounding` (groundingMetadata).
- Each response row carries `run_id`, `panel_id`, `engine`, `retrieved` (bool),
  `phase` (baseline/treatment), `experiment_id` (nullable), `citations`.
- Scheduling: arq cron triggers recurring runs (e.g., weekly) per active brand
  → trend lines. Cost guarded by `PROBE_CONCURRENCY` and a per-brand budget cap.

### D. Parsing / extraction layer (extended)

Job: `parse_batch`. Keep Haiku tool-use; **extend the schema** the tool returns:
```json
{
  "brands_mentioned": ["..."],
  "positions": {"Brand": 1},
  "attributes": {"Brand": ["wide toe box", "plantar-fasciitis support"]},
  "sentiment": {"Brand": "positive|neutral|negative"}
}
```
`attributes` is the on-page "why" (what the model praised); citations are the
off-page "why". Stored in `parsed_responses(attributes JSONB, sentiment JSONB)`.

### E. Diagnosis / provenance layer (extended)

Beyond v1's ranked domains:
1. **Classify each cited source** (`citation_nodes.source_type`):
   directory / review-aggregator / forum (Reddit/Quora) / editorial / owned /
   social. Heuristic domain map + small LLM fallback.
2. **Absent-source analysis**: for sources cited in answers where the focal
   brand is *absent*, flag them as targets. v2.1 (optional): fetch the source
   and check whether it mentions the brand at all → `mentions_focal` tri-state
   (yes/no/unknown). Materialize into `provenance_gaps`.
3. Output: "these N sources drive the category; you appear in K of them; here
   are the K' you're missing, ranked by citation frequency."

### F. Action layer (re-scoped, two tiers)

**Tier 1 — Crawler / agent-readiness diagnostics.** Job: `crawl_audit`.
For each priority URL (home, category, top product pages from the feed):
- Fetch as AI bot UAs (`GPTBot`, `OAI-SearchBot`, `PerplexityBot`, `ClaudeBot`,
  `Google-Extended`) via httpx.
- Parse `robots.txt` per agent → `robots_allowed`.
- Render diff: raw HTML vs Playwright-rendered → `js_required` (content only
  visible after JS).
- Status/redirect/canonical checks → `status_code`, redirect chain.
- Structured-data extraction (extruct/JSON-LD) → `has_schema`, which types.
- Anti-bot/challenge detection → `blocked_reason`.
- Answer-shape score: LLM scores the page text against the target intent.
- Aggregate to a per-URL and per-brand `readiness_score` + ranked blockers.
Tier 2 (later): server-log / CDN ingestion to observe real bot hits + drop-off.

**Tier 2 — Collaborative content workflow.** Jobs: `generate_content`.
1. Input: a provenance/attribute gap + the target intent + RAG-retrieved brand
   context (voice, true facts).
2. Generate a draft (`content_artifacts.draft_md`) with `[VERIFY: ...]`
   placeholders for any unconfirmed claim; multi-format export
   (product block / FAQ schema / comparison page / blog section / social).
3. Human-in-the-loop: edit → approve → (later) push to CMS via connector.
4. Status machine: suggested → edited → approved → published.

### G. Proof layer (the moat; causal experiment engine)

Job: `run_experiment`.
- An `experiment` references `panel_id`, a `change_ref` (content_artifact or
  crawl fix), a `baseline_run_id`, and (after the change + re-crawl) a
  `treatment_run_id`.
- Lift = treatment_rate − baseline_rate on the **same frozen panel**.
- **Control for engine drift** with difference-in-differences: split the panel
  into *targeted* queries (the change should affect) and a *holdout* control set
  (it shouldn't). Lift = (Δtargeted) − (Δholdout). Removes background drift.
- Significance: two-proportion z-test / bootstrap CI over panel queries; store
  `lift`, `ci_low`, `ci_high`, `p_value`, `status`.
- Honest constraint: only retrieval engines move on the days timescale; proof is
  reported per engine. Snapshots accrue automatically (the "free byproduct").

### H. Ask layer + MCP (NEW)

- **Search bar (fast loop):** RAG over `context_chunks` + `responses` +
  `provenance_gaps`. Hybrid retrieval (pgvector cosine + structured filters by
  intent/engine/run) → grounded answer citing the brand's own data.
- **Simulation:** estimate how an engine would treat a draft (score draft+query
  with a model, or retrieval-emulation). Labeled **estimate**, not proof.
- **MCP server:** expose tools (`search_visibility`, `get_provenance`,
  `get_competitors`, `list_blockers`, `simulate_change`) over stdio/http so a
  marketing team's own agents (Claude Desktop, Cursor) use the data natively.

---

## 4. Data model evolution (Postgres + pgvector)

New / changed tables (DDL sketch; `vector` = pgvector extension):

```sql
-- accounts/multitenancy (Clerk org id)
ALTER TABLE brands ADD COLUMN org_id TEXT, ADD COLUMN domain TEXT;

CREATE TABLE context_documents (
  id BIGSERIAL PRIMARY KEY, brand_id BIGINT REFERENCES brands(id),
  source_type TEXT, title TEXT, uri TEXT, raw_text TEXT, created_at TIMESTAMPTZ);

CREATE TABLE context_chunks (
  id BIGSERIAL PRIMARY KEY, document_id BIGINT REFERENCES context_documents(id),
  brand_id BIGINT, chunk_text TEXT, token_count INT,
  embedding vector(1536), created_at TIMESTAMPTZ);
CREATE INDEX ON context_chunks USING hnsw (embedding vector_cosine_ops);

CREATE TABLE query_panels (
  id BIGSERIAL PRIMARY KEY, brand_id BIGINT, version INT,
  status TEXT, seed_summary TEXT, created_at TIMESTAMPTZ, frozen_at TIMESTAMPTZ);

CREATE TABLE panel_queries (
  id BIGSERIAL PRIMARY KEY, panel_id BIGINT REFERENCES query_panels(id),
  query_text TEXT, intent TEXT, persona TEXT, source TEXT, grounded_from JSONB);

CREATE TABLE runs (
  id BIGSERIAL PRIMARY KEY, brand_id BIGINT, panel_id BIGINT,
  engine_set JSONB, status TEXT, cost_cents INT,
  started_at TIMESTAMPTZ, finished_at TIMESTAMPTZ);

-- responses gains run/panel/engine/retrieved
ALTER TABLE responses
  ADD COLUMN run_id BIGINT, ADD COLUMN panel_query_id BIGINT,
  ADD COLUMN engine TEXT, ADD COLUMN retrieved BOOLEAN;

-- parsed gains attributes + sentiment
ALTER TABLE parsed_responses
  ADD COLUMN attributes JSONB, ADD COLUMN sentiment JSONB;

CREATE TABLE citation_nodes (
  id BIGSERIAL PRIMARY KEY, response_id BIGINT REFERENCES responses(id),
  brand_id BIGINT, url TEXT, domain TEXT, title TEXT, rank INT,
  source_type TEXT, mentions_focal TEXT /* yes|no|unknown */);

CREATE TABLE provenance_gaps (
  id BIGSERIAL PRIMARY KEY, brand_id BIGINT, panel_id BIGINT,
  domain TEXT, source_type TEXT, cited_count INT, focal_present BOOLEAN);

CREATE TABLE crawl_audits (
  id BIGSERIAL PRIMARY KEY, brand_id BIGINT, url TEXT, user_agent TEXT,
  status_code INT, robots_allowed BOOLEAN, js_required BOOLEAN,
  has_schema BOOLEAN, schema_types JSONB, blocked_reason TEXT,
  readiness_score REAL, fetched_at TIMESTAMPTZ);

CREATE TABLE content_artifacts (
  id BIGSERIAL PRIMARY KEY, brand_id BIGINT, panel_id BIGINT,
  target_intent TEXT, competitor TEXT, draft_md TEXT, formats JSONB,
  context_refs JSONB, status TEXT, created_at TIMESTAMPTZ);

-- experiments: rebuilt around runs + DiD
ALTER TABLE experiments
  ADD COLUMN panel_id BIGINT, ADD COLUMN hypothesis TEXT,
  ADD COLUMN change_ref BIGINT, ADD COLUMN baseline_run_id BIGINT,
  ADD COLUMN treatment_run_id BIGINT, ADD COLUMN lift REAL,
  ADD COLUMN ci_low REAL, ADD COLUMN ci_high REAL, ADD COLUMN p_value REAL,
  ADD COLUMN status TEXT;
```

Read-time normalization (`brand_identity.py` + `brand_aliases`) carries over
unchanged; it now runs against `citation_nodes` source classification too.

---

## 5. API surface evolution

```
POST   /api/brands                         create brand/company
POST   /api/brands/{id}/context            ingest docs (paste/upload/connector)
GET    /api/brands/{id}/context            list ingested docs
POST   /api/brands/{id}/panels             build a draft panel from context
POST   /api/panels/{id}/freeze             freeze → immutable version
GET    /api/brands/{id}/panels             list panels/versions
POST   /api/brands/{id}/runs               run measurement vs a frozen panel
GET    /api/runs/{id}                      run status + metrics (SSE for live)
GET    /api/brands/{id}/overview           latest aggregate (+provenance)
GET    /api/brands/{id}/provenance         classified sources + absent analysis
GET    /api/brands/{id}/timeline           trend across runs
POST   /api/brands/{id}/crawl              crawler-readiness audit
GET    /api/brands/{id}/crawl              blockers + readiness score
POST   /api/content/suggest                gaps → suggested artifacts
POST   /api/content/{id}/generate          draft (grounded in context)
PATCH  /api/content/{id}                    edit
POST   /api/content/{id}/approve           approve (→ publish connector later)
POST   /api/experiments                     create from a change_ref
POST   /api/experiments/{id}/measure        run treatment + compute DiD lift
GET    /api/experiments                     list with lift/CI
POST   /api/ask                             RAG Q&A over brand corpus
```
MCP server mirrors the read endpoints as tools.

---

## 6. Orchestration evolution

- Replace FastAPI `BackgroundTasks` with **arq** (asyncio-native Redis queue):
  durable jobs, retries, concurrency control, and **cron** for recurring runs.
- Services: `web` (FastAPI), `worker` (arq), `scheduler` (arq cron), `redis`.
- Long operations return a job/run id; frontend polls `GET /api/runs/{id}` or
  subscribes via SSE. Per-brand monthly budget enforced in the worker.

---

## 7. Deployment (per layer)

| Layer | v1 (now) | v2 |
|---|---|---|
| App (FastAPI) | local uvicorn | Railway web service |
| Worker/scheduler | in-process | Railway arq worker + cron + Redis (Upstash) |
| DB | SQLite file | Postgres + pgvector (Supabase or Railway PG) |
| Vector store | none | pgvector (no separate vector DB) |
| Embeddings | none | OpenAI text-embedding-3-small |
| Headless fetch | none | Playwright in the worker image |
| Auth | Clerk (scaffolded) | Clerk (orgs/multitenant) |
| Object storage | none | Supabase Storage / S3 (uploads) |
| Frontend | SPA via FastAPI | same; optional Next.js on Vercel later |
| MCP | none | stdio (local) + hosted http |

---

## 8. Model + cost map

| Job | Model | Notes |
|---|---|---|
| panel/query gen | Claude Sonnet | grounded by RAG context |
| probe (measure) | gpt-5, chatgpt-search, claude, perplexity-sonar, gemini-grounding | retrieval engines give citations |
| parse/extract | Claude Haiku (tool-use) | brands+positions+attributes+sentiment |
| embeddings | text-embedding-3-small | 1536-d, cheap |
| source classify | Haiku (fallback) | mostly domain heuristics |
| content gen | Claude Sonnet | grounded, `[VERIFY]` gating |
| ask / simulate | Sonnet (+ retrieval) | labeled estimate, not proof |

Cost control: frozen panels (bounded query count) + scheduled (not continuous) +
cheap parse model + per-brand budget cap. Target stays under the $500/brand/mo
ceiling at v1 economics.

---

## 9. End-to-end workflow (technical sequence)

```
1. INGEST   POST /context → ingest_context → chunks+embeddings+seed_summary
2. PANEL    POST /panels  → build_panel (RAG) → edit → POST /freeze (version N)
3. MEASURE  POST /runs    → run_measurement(panel N, engines) → responses(+citations)
4. PARSE    parse_batch   → parsed_responses(brands,positions,attributes,sentiment)
5. DIAGNOSE build_provenance → citation_nodes(classified) + provenance_gaps
            (off-site why) ; attributes (on-page why)
6. ACT(a)   POST /crawl   → crawl_audit → readiness_score + blockers
   ACT(b)   POST /content → generate_content (grounded) → edit → approve
7. PROVE    POST /experiments (change_ref) → publish → re-crawl →
            /measure (treatment run, same panel) → DiD lift + CI
8. ASK      POST /ask (anytime) → RAG over corpus ; MCP tools for agents
   SCHEDULE arq cron re-runs step 3–5 weekly → timeline/trend ; proof accrues
```

---

## 10. New components checklist (v1 → v2)

- [ ] Postgres + pgvector migration (from SQLite); SQLAlchemy/asyncpg + Alembic
- [ ] Context ingestion service + embeddings + chunk store
- [ ] Panel/version model + `build_panel` (RAG-grounded) + freeze
- [ ] `runs` model; generalize probe fan-out; add chatgpt-search + gemini-grounding
- [ ] Parser schema v2 (attributes + sentiment)
- [ ] `citation_nodes` + source classification + absent-source analysis
- [ ] Crawler-readiness service (httpx bot UAs + Playwright + extruct + robots)
- [ ] Collaborative content workflow + status machine + multi-format export
- [ ] Causal experiment engine (DiD + significance) on runs
- [ ] arq worker + cron + Redis; SSE for live runs
- [ ] Ask layer (hybrid RAG) + MCP server
- [ ] Clerk multitenancy (org_id scoping) ; CMS publish connectors (Shopify/Webflow)

---

## 11. Migration path (sequenced, low-risk)

1. (DONE v1) Perplexity provenance.
2. Depth-based search v1: context paste → grounded queries → frozen panel
   (still SQLite; introduces panel/run concepts behind the scenes).
3. Parser v2 (attributes) + provenance classification + absent analysis.
4. Move to Postgres+pgvector; real embeddings/RAG; arq worker + scheduled runs.
5. Crawler-readiness service.
6. Collaborative content workflow + CMS connectors.
7. Causal experiment engine (DiD) + timeline.
8. Ask layer + MCP. Multitenancy + closed beta.

---

## 12. Open technical questions

- chatgpt-search / gemini-grounding citation formats and rate limits at scale.
- `mentions_focal` accuracy without over-fetching sources (cost vs signal).
- JS-render diffing: Playwright cost in the worker vs heuristic detection.
- DiD holdout construction: how to pick control queries that are truly unaffected.
- Engine non-determinism: how many samples per query for stable rates (n≥? per
  engine) without blowing the budget.
- pgvector index choice (hnsw vs ivfflat) at expected corpus sizes.
