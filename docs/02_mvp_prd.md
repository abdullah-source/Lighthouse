# MVP Product Requirements Document
## Brand Visibility for the LLM Era

**Owner:** Abdullah Ali
**Last updated:** May 20, 2026
**Status:** Pre-build, pitching Friday May 22

---

## 1. Problem statement

Consumer buying intent is shifting from Google search to LLM assistants (ChatGPT, Claude, Gemini, Perplexity). When a consumer asks an LLM "what is the best X," the model recommends a small set of brands. Brands not in that set lose the sale.

Today brands have zero visibility into:
- Whether they appear in LLM responses for buying queries in their category
- Which competitors are being recommended instead
- What language, attributes, or content is causing the model to pick competitors
- How their visibility is trending over time

Existing SEO tools (Semrush, Ahrefs, Conductor) were built for Google. They do not measure LLM behavior.

## 2. Target user

Primary: Head of SEO, Head of Brand Marketing, or CMO at a mid-market consumer brand. Examples: a DTC sneaker brand doing 20-200M ARR, a beauty brand, a kitchen-goods brand.

Secondary: Boutique digital agencies serving the above.

Why this user: they already have a tooling budget for SEO. They are being asked by their CEO what they are doing about ChatGPT. They have authority to buy a 1000-3000 dollar per month tool without a 9-month procurement cycle.

## 3. Core value proposition

> "Like Google Search Console, but for the LLM era. See exactly how AI models recommend or ignore your brand, and what to change."

## 4. Success metrics

**For the user (the thing we promise to move):**
- Mention rate: percentage of relevant queries where the brand appears in LLM responses
- Position: when mentioned, is the brand listed first, in a top-3 list, or buried
- Sentiment: positive, neutral, or negative attributes used to describe the brand

**For us (the thing we measure for the business):**
- 30-day mention-rate lift per brand on the platform (target: +15 percentage points)
- Time to first insight (target: under 24 hours from signup)
- Paid pilot to retention conversion (target: 70% retain after 3 months)

## 5. MVP scope (what we ship first)

### In scope for v1

**Onboarding flow**
- Sign up with email
- Enter brand name and category (e.g. "Allbirds, sustainable footwear")
- System auto-generates 200 buyer queries for that category
- User can edit, add, remove queries before the first run

**Probing engine**
- Runs all queries against 4 LLMs: GPT-5 (OpenAI), Claude Sonnet (Anthropic), Gemini Pro (Google), Perplexity Sonar
- Each query runs 3 times per model to get a probability distribution
- Daily refresh for top 50 queries, weekly for the rest

**Parsing engine**
- Extracts from each response: brands mentioned, position in list, attributes used, links provided
- Output is structured rows in Postgres

**Dashboard (the main interface)**
- Top metric: brand mention rate, with trend over time
- Competitor comparison: top 5 competitors and their mention rates side by side
- Query-level drilldown: click any query to see actual LLM responses
- Attribute analysis: what words do models use about your brand vs. competitors

**Recommendations engine**
- For each query the brand loses, generate a recommendation: "Your top competitor is described as X, which appears on their product page but not yours. Adding Y to your site may improve mention rate for this query."

**Reporting**
- Weekly email summary
- Exportable CSV of all data

### Out of scope for v1 (deferred)

- Auto-publishing recommendations to the brand's website
- API access for the brand
- Multi-brand portfolio view (for agencies)
- Custom LLM coverage (only the big 4 in v1)
- Geographic segmentation (US-only in v1)
- Native integrations with CMS platforms (Shopify, etc.)
- A/B testing of content changes

## 6. User stories

### As a brand marketer:
- I want to enter my brand and see, within 24 hours, how often I appear in LLM recommendations
- I want to compare my visibility against my top 5 competitors
- I want to see which specific queries I am losing and why
- I want concrete recommendations for what to change on my website
- I want to track my visibility trend over time as I make changes

### As an agency:
(deferred to v2)

## 7. Non-functional requirements

- **Data freshness:** core metrics no older than 24 hours
- **Latency:** dashboard load under 2 seconds
- **Cost ceiling per brand per month:** under 500 dollars in API spend
- **Reliability:** 99% uptime acceptable for v1 (this is a dashboard, not infrastructure)
- **Privacy:** no consumer data touched. Only brand-provided category info and public LLM responses.

## 8. Technical architecture

See `03_stack_and_architecture.md` for details.

## 9. Phased rollout

**Phase 0 — Friday demo (May 22, 2026)**
- No live product
- One Python script run by hand on 5 brands
- Static report shown in pitch

**Phase 1 — v0 internal demo (June 5, 2026)**
- Single-tenant prototype
- One brand at a time
- Manual onboarding
- Static dashboard generated from a notebook
- Goal: prove the data and the insight are real

**Phase 2 — v1 closed beta (August 2026)**
- Self-serve signup
- 10 paying brands at 1000 dollars per month
- Real dashboard, real probing engine, real recommendations
- Goal: prove retention and willingness to pay

**Phase 3 — v2 public launch (Q4 2026)**
- Open signup
- Goal: 100 paying brands

## 10. Open questions

- Which LLM has the highest commercial signal in buyer intent? (Hypothesis: ChatGPT, then Perplexity, then Claude, then Gemini)
- How does mention-rate stability look across days? Is daily refresh actually necessary or is weekly enough?
- What is the right pricing test? 1000/2000/3000 tiers, or volume-based?
- Do brands want a recommendation engine, or do they just want the data and their agency will figure out what to change?

## 11. Risks

- **Market timing:** category is so new that some brands may wait 6 months before buying any tool. Mitigation: free audit as the wedge.
- **Incumbent risk:** Semrush or Ahrefs could ship a competing module in 6-12 months. Mitigation: move fast, build the dataset moat.
- **LLM API cost volatility:** if OpenAI raises prices significantly, the unit economics shift. Mitigation: multi-model from day one, switch to cheaper models for parsing.
- **Model output non-determinism:** results vary run to run. Mitigation: probability-based metrics, multiple trials per query.

## 12. What "done" looks like for the MVP

A consumer brand can:
1. Sign up in under 5 minutes
2. See their first dashboard within 24 hours
3. Identify at least 3 specific recommendations to improve LLM visibility
4. Track week-over-week changes in their mention rate

If a brand can do all four and is willing to pay 1000 dollars per month for it, the MVP is validated.
