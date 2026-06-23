# Tech Stack, Deployment, Cloud & MCP

**Updated:** June 2026. Companion to `10_v1_architecture.md` (how the code fits) and `11_prd.md` (what we build). This doc answers: what software runs where, and what cloud + MCP work is needed.

## 1. Stack

| Concern | Now (v1) | At scale (v2) |
|---|---|---|
| Frontend | Static SPA (HTML/CSS/vanilla JS) served by FastAPI | Next.js 15 + Tailwind + shadcn on its own host |
| Backend | FastAPI + Uvicorn (Python 3.13) | Same, horizontally scaled |
| Pipeline | asyncio + httpx (probe/parse) | + a worker process / queue |
| Database | SQLite (file) | Postgres (managed) + pgvector |
| Auth | Clerk (clerk-js, publishable key) | Clerk + backend session verification |
| LLM APIs | Anthropic (Claude, Haiku), OpenAI (GPT-5) | + Gemini, Perplexity |
| Background jobs | FastAPI BackgroundTasks (in-process) | Redis queue + worker, or platform cron |
| Secrets | `.env` locally; host env vars in prod | Same |
| Observability | console logs | Sentry (errors) + PostHog (product) |

## 2. Where each layer deploys

### Now (v1 beta) — one service, cheapest, recommended
**Everything is one FastAPI service** (it serves the API and the frontend), plus a SQLite file on a persistent disk.

- **Host: Railway** (or Fly.io). One service from this repo.
  - Start command: `uvicorn api:app --host 0.0.0.0 --port $PORT`
  - **Persistent volume** mounted at `/data`; set `BRANDVIZ_DB_PATH=/data/probe.sqlite` so SQLite survives redeploys (config.py already reads this env var).
  - Env vars: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY`.
  - HTTPS + a domain: Railway gives a URL; add a custom domain later.
- **Frontend:** no separate deploy. Served by the same service at `/` and `/app`.
- **Database:** the SQLite file on the Railway volume. No separate DB service.
- **Auth:** Clerk is a managed cloud service; you just add the keys.

Why one service: at 10-brand beta scale SQLite is plenty, and one deploy target is far less ops for a solo founder. This matches the PRD cost ceiling.

### At scale (v2) — split when you need it

- **Frontend → Vercel** (Next.js). Talks to the backend over HTTPS; set `CORS` on FastAPI.
- **Backend → Railway / Fly** (FastAPI), multiple instances.
- **Database → Supabase or Neon** (managed Postgres). Migrate the SQLite schema; the SQL is plain so it ports cleanly.
- **Queue/worker → Upstash Redis** + a worker process for audits (so a 90s probe never ties up a web instance).
- **Object storage (optional) → Cloudflare R2 / S3** only if you store exports or artifact bundles.

```
  NOW:                              SCALE:
  [ Railway service ]              [ Vercel ]  ->  [ Railway: FastAPI x N ]
   FastAPI + static                  Next.js          |        |
   + SQLite (volume)                                  v        v
   + Clerk                                     [ Supabase PG ] [ Upstash Redis + worker ]
```

## 3. Cloud implementation checklist

What you actually have to set up in the cloud:

- [ ] **Railway** project from this repo; add a **persistent volume**; set start command + env vars; set `BRANDVIZ_DB_PATH`.
- [ ] **Clerk** app (dashboard.clerk.com): get publishable + secret keys; add allowed origins (your Railway/Vercel domain).
- [ ] **Domain + HTTPS** (Railway/Vercel provide certs).
- [ ] Later: **Supabase/Neon** (Postgres), **Upstash** (Redis), **Sentry** + **PostHog** (free tiers), optional **R2/S3**.

Everything except the LLM APIs and Clerk is optional until scale. No Kubernetes, no custom infra.

## 4. MCP implementation — yes, build it

**Recommendation: ship an MCP server.** It is the standards-based answer to the "agent that lives on your computer / ask agents about positioning" idea, without building a desktop app. Peec and AirOps already expose MCP; this keeps us current and makes the data usable inside a marketer's own AI (Claude desktop, Cursor, n8n).

### What it exposes (tools)
- `list_brands()` — audited brands + headline metrics.
- `get_brand_visibility(brand, category)` — mention rate, position, share of voice, by-model.
- `top_competitors(brand, category)` — normalized competitor set.
- `compare(brand_a, brand_b, category)` — head-to-head positioning.
- `run_audit(brand, category)` — kick off a new probe (write-scoped; gate behind auth).

### How
- Python **`mcp`** SDK (FastMCP). A thin server that imports `store` and calls the same aggregation the web app uses. One file, e.g. `mcp_server.py`.
- **Transport:** `stdio` for local installs (a user adds it to Claude desktop / Cursor config and points it at the repo) and an optional **streamable-HTTP** transport for a hosted version later.
- **Auth for the hosted version:** scope tools to a brand/account via an API key or Clerk-issued token.
- **Deploy:** local users run it via stdio (no hosting). A hosted MCP endpoint deploys as a second route/service on Railway.

### Effort
Small: it reuses `store.aggregate_brand` and friends. A read-only stdio server is a few hours. Treat it as a beta deliverable alongside the in-app chat.

## 5. Env vars reference

```
ANTHROPIC_API_KEY=...        # required (probe + parse + query-gen + action)
OPENAI_API_KEY=...           # optional (GPT-5 probing; Claude-only without it)
CLERK_PUBLISHABLE_KEY=...    # optional (activates logins)
CLERK_SECRET_KEY=...         # optional (for backend session verification, v2)
BRANDVIZ_DB_PATH=/data/probe.sqlite   # set in prod to a volume path
```

## 6. Run locally (recap)

```bash
cd "/Users/abdullahali/project - summer"
source .venv/bin/activate
uvicorn api:app --reload --port 8000
# landing http://localhost:8000/  · app http://localhost:8000/app
```
Frontend + backend = this one process. Database = `data/probe.sqlite` (a file).
