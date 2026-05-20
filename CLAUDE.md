# Project: Brand Visibility for the LLM Era

**Owner:** Abdullah Ali
**Status:** Pre-build. Phase 0 pitch on Friday May 22, 2026.

## What this is

A SaaS tool that measures whether mid-market consumer brands appear in LLM
recommendations (ChatGPT / Claude / Gemini / Perplexity) for buyer-intent
queries, who's being recommended instead, and what to change. Positioning:
"Google Search Console for the LLM era." Pricing target: $1k-3k / brand / month.

## Where to look first

- [docs/01_friday_pitch_green.md](docs/01_friday_pitch_green.md) — pitch narrative for Friday May 22 demo
- [docs/02_mvp_prd.md](docs/02_mvp_prd.md) — full PRD: scope, user stories, success metrics, phased rollout
- [docs/03_stack_and_architecture.md](docs/03_stack_and_architecture.md) — technical architecture, schema, cost model, build order
- [docs/04_day2_log_addition.md](docs/04_day2_log_addition.md) — running build log

Treat these as the source of truth. Don't propose scope or stack changes
without checking them first.

## Current phase and build order

We are on **Phase 0** — a single Python script that probes 4 LLMs for 5 brands
and produces a static report for the Friday pitch. Not a web app yet. See
[docs/03_stack_and_architecture.md](docs/03_stack_and_architecture.md) section 6 for the strict build order:

1. Probe script (Python + SQLite, days 1-2)
2. Parser script (day 3)
3. Static HTML report generator (days 4-5)
4. Free audits to 5 DTC brands (week 2)
5. Web app port (FastAPI + Next.js, week 3-6) — **only after validation**
6. Closed beta — August 2026

Do not pull in Phase 1+ infrastructure (Celery, Supabase, Clerk, Vercel deploys)
while we are still on Phase 0.

## Cost discipline

API-spend ceiling is **$500 / brand / month** at v1. Phase 0 demo should stay
**under $10 total**. When suggesting model choices, default to the cheapest
capable model (e.g. Claude Haiku 4.5 or GPT-5 Mini for parsing).

## gstack

This project uses [Garry Tan's gstack](https://github.com/garrytan/gstack) skill
pack for solo-founder workflow discipline. Use `/browse` from gstack for all
web browsing. Never use `mcp__claude-in-chrome__*` tools.

Available skills: `/office-hours`, `/plan-ceo-review`, `/plan-eng-review`,
`/plan-design-review`, `/design-consultation`, `/design-shotgun`, `/design-html`,
`/review`, `/ship`, `/land-and-deploy`, `/canary`, `/benchmark`, `/browse`,
`/open-gstack-browser`, `/qa`, `/qa-only`, `/design-review`,
`/setup-browser-cookies`, `/setup-deploy`, `/setup-gbrain`, `/sync-gbrain`,
`/retro`, `/investigate`, `/document-release`, `/document-generate`, `/codex`,
`/cso`, `/autoplan`, `/pair-agent`, `/careful`, `/freeze`, `/guard`,
`/unfreeze`, `/gstack-upgrade`, `/learn`.

**Phase-mapped usage:**
- Phase 0 pitch prep — `/plan-ceo-review`, `/investigate`, `/document-release`, `/design-html`
- Phase 1 probe script — `/ship`, `/review`, `/qa`, `/benchmark`, `/cso`
- Phase 2 beta — `/plan-eng-review`, `/design-consultation`, `/design-shotgun`, `/design-review`, `/land-and-deploy`, `/canary`, `/freeze`, `/guard`
- Always-on — `/codex` (second opinion), `/pair-agent` (parallel work), `/retro`, `/learn`

When approaching a gated moment (pitch review, pre-launch QA, design polish,
deploy), prefer the matching gstack command over ad-hoc requests.