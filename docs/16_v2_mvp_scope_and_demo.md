# 16 — V2 = the Demoable MVP: Scope, Cloud Checklist, Demo Script

Date: June 16, 2026.
Decision: **V2 is the MVP** — the full loop, multi-tenant, in the cloud, with RAG
and MCP, demoable end to end. This doc is the product/demo framing; the technical
architecture is in [15_v2_architecture_lookahead.md](15_v2_architecture_lookahead.md).

---

## The MVP in one line

A brand logs in, brings in its own context, and walks the whole loop —
ingest → panel → measure → diagnose (why) → act → prove → ask — with an MCP
server exposing the data to their own agents.

## Feature set (everything in scope for the MVP)

1. Auth + multi-tenant (Clerk, org-scoped)
2. RAG context ingestion (paste/upload → embeddings → pgvector)
3. Depth-based search: individualised, frozen, versioned query panels
4. Multi-engine measurement, scheduled. **MVP engines (3 keys we have):** Claude
   (weights baseline), GPT-5 + ChatGPT-with-search (OpenAI key; retrieval +
   citations), Perplexity Sonar (retrieval + citations). **Gemini-grounding added
   later** — pluggable, one probe fn + one key, no redesign. Two
   citation-returning engines (ChatGPT-search + Perplexity) is enough for the
   provenance demo. Embeddings/RAG also run on the OpenAI key.
5. Off-site provenance: classified cited sources + absent-source analysis (the why)
6. Crawler / agent-readiness diagnostics (the blocks stopping AI bots)
7. Collaborative content workflow (suggest → add context → co-generate → approve → multi-format)
8. Causal proof loop (difference-in-differences lift on the frozen panel)
9. Ask / search bar (hybrid RAG over the brand's own corpus)
10. MCP server (hosted http + local stdio) for the team's own agents

## Cloud / infra checklist (all of it)

- [ ] Postgres + pgvector (Supabase or Railway PG) — DB + RAG vector store
- [ ] Redis (Upstash) — arq job queue + cron scheduler
- [ ] Railway services: `web` (FastAPI), `worker` (arq), `scheduler` (cron)
- [ ] Clerk — auth + org multitenancy
- [ ] Object storage (Supabase Storage / S3) — uploaded context files
- [ ] Playwright in worker image — render-diff for crawler readiness
- [x] APIs we HAVE (cover the whole MVP): Anthropic, OpenAI (+ web search + embeddings),
      Perplexity (key set)
- [ ] Gemini — added later for engine breadth (not required for the MVP demo)
- [ ] MCP server — hosted (http) + local (stdio)

## Build phases (each independently demoable)

1. **Cloud foundation** — SQLite → Postgres+pgvector; deploy web + arq worker +
   Redis on Railway; Clerk multitenancy.
2. **RAG + depth panel** — ingestion + embeddings + grounded query gen + frozen panels.
3. **Measurement + provenance v2** — multi-engine runs, parser v2 (attributes +
   sentiment), source classification + absent analysis, trend.
4. **Action** — crawler-readiness diagnostics + collaborative content workflow.
5. **Proof** — causal experiment engine (DiD) + timeline.
6. **Ask + MCP** — RAG search bar + MCP server.
7. **Demo polish** — seed a flagship demo account with real data and a completed
   experiment so the full story plays in ~5 minutes.

## The 5-minute demo script

1. **Log in** (cloud, multi-tenant) → your workspace.
2. **Bring in context** (RAG ingestion) → paste reviews / positioning.
3. **Generate the frozen panel** → "these are YOUR buyers' questions, not generic."
4. **Run measurement** across engines → "you're at 38%; here's who wins."
5. **Show the why** (provenance) → "these cited sources drive it; you're in none."
6. **Show the block** (crawler readiness) → "GPTBot is denied in your robots.txt."
7. **Generate the fix** (content workflow) → grounded in their context, approve.
8. **Show proof** → a completed experiment: "+15 points on the same panel" (DiD).
9. **Ask the bar** → "why is the competitor winning in X?" answered over their data.
10. **Connect via MCP** → their own agent queries the visibility data live.

## Demo discipline (advisor note)

- Build each phase so it demos on its own; never be stuck with a half-thing.
- Seed a flagship demo account and **replay** pre-run measurements/experiments on
  stage. Live multi-engine runs are slow and cost money; the product is real, the
  demo is choreographed.
- Keep cost bounded: frozen panels (bounded query count), scheduled not
  continuous, cheap parse model, per-brand budget cap.

## Sequencing note

This MVP plan supersedes the "fast track, defer infra" Phase-0 framing for the
*demo target*, but the build order still starts from where v1 is: the immediate
next code step (depth-based search v1) can ship on SQLite first, then fold into
the cloud foundation at Phase 1. Nothing is wasted.
