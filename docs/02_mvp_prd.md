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

Existing SEO tools (Semrush, Ahrefs, Conductor) were built for Google. They do not measure LLM behavior. A first wave of LLM-visibility tools — led by Profound, with Peec, Otterly, AthenaHQ, and AirOps in adjacent positions — has solved the measurement layer. **None of them ship the change.** Brands are told what their mention rate is and left to figure out what to publish, where, and how. That is the gap.

## 2. Target user

Primary: Head of SEO, Head of Brand Marketing, or CMO at a mid-market consumer brand. We stay horizontal across consumer categories. When we lean by category for marketing, content, and case studies, we lean into **consumer products — clothing, beauty, cosmetics, food** — because that is where consumer LLM-query volume concentrates and the same product works globally.

Secondary: Boutique digital agencies serving the above.

Why this user: they already have a tooling budget for SEO. They are being asked by their CEO what they are doing about ChatGPT. They have authority to buy a 1000-3000 dollar per month tool without a 9-month procurement cycle.

## 3. Core value proposition

> "Profound monitors. We act. We measure how AI models recommend or ignore your brand, generate the publish-ready content and schema changes that move your mention rate, and ship them with your approval."

The wedge is **action**, not measurement. The differentiator that holds up under
competitive pressure is **neutrality**:

- Brand-paid only. No money from OpenAI, Anthropic, Google, or Perplexity.
- No affiliate or referral commissions on tools we recommend.
- Open methodology — the mention-rate score is publicly documented; brands can audit.
- No paid prominence in our index. Ranking position is never for sale.
- Every recommendation cites the actual LLM responses that produced it.

The day any LLM company ships a first-party visibility product, they cannot
credibly be neutral across the other models. We always can.

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

**Action engine (the wedge)**
- For each recommendation, generate **publish-ready output**, not just advice:
  FAQ blocks, comparison-page copy, JSON-LD schema, meta-description rewrites,
  cited-source content fragments.
- Brand previews each artifact and approves before anything is published. No
  autonomous publishing without explicit consent.
- v1 closed beta ships **manual export** (copy-paste / downloadable bundles).
  CMS integrations (Shopify, Webflow, WordPress, Contentful) ship in v2.
- Every shipped change is tracked. Mention-rate lift is measured for 7–30 days
  after publish and reported back to the brand.
- Cross-brand patterns feed a proprietary action playbook — the compounding moat.

**Reporting**
- Weekly email summary including mention-rate trend, top losing queries, and
  ship-and-lift table for action artifacts that landed that week.
- Exportable CSV of all data.

### Out of scope for v1 (deferred)

- **Automated** publishing to the brand's website (v1 = manual export; v2 = CMS push with brand approval)
- API access for the brand
- Multi-brand portfolio view (for agencies)
- Custom LLM coverage (only the big 4 in v1)
- Geographic segmentation (US-only in v1)
- Native integrations with CMS platforms (Shopify, Webflow, WordPress, Contentful — all v2)
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
- **Neutrality (binding principles, not just marketing):**
  - No revenue from any LLM provider.
  - No affiliate / referral / placement commissions.
  - Public methodology document for the mention-rate score.
  - Ranking position in our own index is never sold.
  - Every recommendation surfaces the underlying LLM-response evidence.

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

- **Competitive risk (Profound and adjacent):** Profound is the category leader on measurement; Peec, Otterly, AthenaHQ, AirOps are in adjacent positions. Mitigation: action wedge (we ship the change, they don't) + neutrality stance (we stay credibly cross-model when LLM cos move).
- **Incumbent risk:** Semrush, BrightEdge, Conductor have distribution and are bolting on AI-visibility modules. Mitigation: depth in one problem (LLM visibility + action) and an accumulating cross-brand action playbook they cannot replicate without our trial logs.
- **Market timing:** category is new; some brands may wait 6 months before buying any tool. Mitigation: free audit as the wedge.
- **LLM API cost volatility:** if OpenAI raises prices significantly, unit economics shift. Mitigation: multi-model from day one, route parsing to the cheapest capable model.
- **Model output non-determinism:** results vary run to run. Mitigation: probability-based metrics, multiple trials per query.
- **Neutrality erosion:** taking LLM-provider money (or affiliate commissions) would destroy the positioning. Mitigation: written, public neutrality charter; revenue from brands only; periodic external audit of the methodology.
- **Action-engine trust:** brands will not let an automated system publish to their website without strong guardrails. Mitigation: v1 ships manual export only. v2 CMS push always requires explicit per-artifact approval. No autonomous publishing in any version.

## 12. What "done" looks like for the MVP

A consumer brand can:
1. Sign up in under 5 minutes
2. See their first dashboard within 24 hours
3. Identify at least 3 specific recommendations to improve LLM visibility
4. Track week-over-week changes in their mention rate

If a brand can do all four and is willing to pay 1000 dollars per month for it, the MVP is validated.
