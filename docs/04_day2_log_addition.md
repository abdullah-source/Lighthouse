# Day 2 Log Addition — May 20, 2026

## Green bucket idea locked in

**Brand Visibility for the LLM Era.** Google Search Console but for ChatGPT, Claude, Gemini, Perplexity. A SaaS analytics platform that tells consumer brands how AI models are recommending them or ignoring them, what their competitors are doing, and what to change.

Customer: head of SEO or head of marketing at mid-market consumer brands.
Pricing: 1000 to 3000 dollars per month per brand.
Moat: proprietary dataset of LLM responses over time, plus recommendations playbook.
Why not eaten by OpenAI: structural conflict of interest, they will not help brands game their model.
Why not eaten by Semrush: AI-bolted-on vs AI-native, different architecture.

Why this one over the others:
- Trust problem of consumer voice agents disappears, buyer is the brand
- Revenue model is obvious B2B SaaS
- Buyer exists today with budget today
- Working v0 buildable in two weeks
- Category leader does not exist yet

## Stack decision summary

- Frontend: Next.js 15 + Tailwind + shadcn/ui on Vercel
- Backend: FastAPI on Railway
- Database: Postgres on Supabase with pgvector
- Queue: Redis on Upstash
- Workers: Celery for probing and parsing
- LLMs probed: GPT-5, Claude Sonnet, Gemini 2.5 Pro, Perplexity Sonar
- LLMs used internally: Claude Sonnet for query generation and recommendations, Claude Haiku for parsing
- No training, no fine-tuning. Pure orchestration and analytics.

## Cost to launch demo: under 10 dollars
## Cost to run v1 beta with 10 brands: about 1600 to 3100 per month
## Gross margin at v1 beta: about 80 percent

## Three picks now locked for Friday

- Green: Brand Visibility for the LLM Era
- Yellow: Jasper AI (GPT wrapper that lost to ChatGPT in 8 weeks)
- Purple: Still to decide. Edge voice inference for consumer devices is the strongest candidate.

## Files created today

- 01_friday_pitch_green.md — the 2-minute pitch
- 02_mvp_prd.md — full product requirements
- 03_stack_and_architecture.md — technical stack and cost model
- This log addition

## Bucket totals

Green 5, yellow 4, purple 1. Need to fill purple tomorrow.
