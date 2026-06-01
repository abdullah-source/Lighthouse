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

---

## Day 2 evening — positioning pivot

Reviewed competitive landscape. Profound is the category leader, Peec / AirOps /
Otterly play in adjacent slots, Semrush and BrightEdge are bolting on AI-visibility
modules. The greenfield framing from this morning was wrong. We need a wedge.

**Decisions:**

1. **Stay horizontal, not vertical.** The buyer profile (head of SEO / CMO at a
   mid-market consumer brand) is what we know. We do not need to pick running
   shoes or skincare specifically. If forced to lean by category in marketing or
   pitch, we lean into consumer products — clothing, beauty, cosmetics, food —
   because that is where consumer LLM-query volume concentrates and the same
   product works globally.

2. **The wedge is action, not measurement.** Profound monitors. We act.
   Closest functional analog is AirOps, but AirOps is a generic AI-workflow
   tool. We are LLM-visibility-specialized end to end: probe, parse, recommend,
   and **execute the change**.

3. **Action mechanism (v1):**
   - Generate publish-ready content / schema / page changes optimized for
     LLM mention rate (FAQ blocks, comparison pages, JSON-LD schema, meta
     descriptions, cited-source content).
   - Brand previews and approves — no autonomous publishing without consent.
   - Push via CMS integrations: Shopify, Webflow, WordPress, Contentful
     (deferred to v2 closed beta — v1 ships manual export / copy-paste).
   - Measure mention-rate lift in the 7–30 days after each change.
   - Cross-brand patterns feed a proprietary playbook that compounds.

4. **Neutrality stance (the moat-keeper):**
   - Brand-paid only. No payments from OpenAI, Anthropic, Google, Perplexity.
   - No affiliate / referral commissions.
   - Open methodology — mention-rate score is publicly documented; brands can
     audit.
   - No paid prominence in our index. We never sell ranking position.
   - Every recommendation shows its evidence (the actual LLM responses that
     produced it).
   - Structural advantage the day an LLM company ships their own visibility
     tool: they can never be neutral across the other models. We always can.

**Implication for Friday pitch:** acknowledge Profound by name. Lead with the
action wedge. Mention neutrality explicitly. Drop the "first to fill the vacuum"
language — replace with "Profound monitors; we act."

---

## June 1, 2026 — competitive reality check + differentiator pivot

Ran a live scrape of Profound, Peec, and AirOps (see `06_competitor_benchmark.md`).
The May 20 framing above is wrong now:

- **"Profound monitors; we act" is dead.** Profound ships agents + CMS publish.
  AirOps' whole product is Insights → Action → Measure with an agent (Quill) that
  drafts and executes under approval gates. The "action wedge" — and the later
  "GitHub for marketing / one-click push" idea — is the incumbents' current product.
- **Neutrality** is marketed by nobody; it's not a wedge as copy. Keep it only as an
  earned ethical stance.
- **Measurement is commoditizing.** All three show near-identical visibility
  dashboards.

**New differentiator (decided this session):** proven **causal lift**, deep in one
consumer/DTC category. Measurement is the commodity; proving which specific change
*caused* the AI to recommend you — and compounding that into a category-dense dataset
— is the moat. Spine: the **dual-loop** framing (fast retrieval loop / slow training
loop) and the professor's question about how this reshapes what consumers are
recommended.

**Segment confirmed:** mid-market DTC consumer brands (footwear, beauty, food) —
absent from every competitor's case studies (all B2B SaaS).

**Reality on stakes:** this is the Eship Studio professor pitch, **no funding** — so
the bar is an honest, defensible thesis, not surviving an investor naming AirOps.

**Next:** revised pitch in `01_friday_pitch_green.md`; demo experiment in
`07_demo_experiment_spec.md` (build on the v0 by June 5).
