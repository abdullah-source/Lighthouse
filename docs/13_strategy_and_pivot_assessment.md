# 13 — Strategy: Measurement Depth, Off-Site "Why," and the Entity-Graph Pivot Assessment

Status: working strategy notes from the June 11, 2026 CEO-planning session.
This consolidates the measurement/proof plan the founder asked to save, plus an
honest assessment of the Gemini-proposed "Lighthouse / entity-graph / llms.txt"
pivot so the reasoning is on record for the decision.

Treat the **foundation** sections as decided direction and the **contested**
section as an open call, clearly labelled.

---

## 1. The decided foundation: a deep measurement layer

"One vertical" must mean *deep*, not *small*. Our current input is surface-level:
one Sonnet call invents 20 generic queries, probed against two **no-retrieval**
chat models, one shot. That is a vibe check, not a benchmark.

What deep looks like (the Profound-grade input, scoped to one vertical):

- **Individualised, not a canned word-set.** Generate realistic conversational
  prompt strings varied by persona / intent / phrasing.
- **Grounded in first-party voice-of-customer.** Seed prompts from the brand's
  own reviews, support tickets, on-site search logs, sales-call transcripts,
  plus demand signals (autocomplete, People-Also-Ask, Reddit). Profound estimates
  *generic* conversation volume; we individualise to *this brand's real demand*.
  No horizontal competitor can easily individualise this way — it is the wedge.
- **Frozen, versioned panels.** A living exploration layer keeps discovering new
  prompts; periodically promote a snapshot to a frozen version. Track trend and
  prove lift against frozen versions (reproducibility); explore with the living
  layer. This resolves the tension between "individualised" and "reproducible."
- **Real engines, retrieval ON, citations captured.** Probe surfaces the way real
  users hit them (Perplexity first — cleanest citations; ChatGPT-with-search via
  existing OpenAI key; Gemini grounding later). Capture mention, position,
  sentiment, AND the cited source URLs.
- **Scheduled / continuous**, so we get trend lines, not snapshots.

This single pipeline is both the measurement layer AND the "why" (citations).

## 2. The workflow map (what the marketing team does in-product)

A loop they live in, not a monthly CMO report:

```
 INGEST            MEASURE             DIAGNOSE             ACT               PROVE
 brand + VoC   →  scheduled runs   →  the "why" per     →  targeted change →  hold panel
 + competitors    across real          query (cited        + off-site source   version,
 → individualised  engines →           sources, attrs;     target list)        re-measure,
 query panel       SoV, position,      "you lose because                       show lift
 (frozen versions) sentiment,          these N sources                         (attributed)
                   citations, trend    don't mention you")
                          │                                                         │
                          └──────────────────  ASK  ◄───────────────────────────────┘
        (agent / search bar grounded in the brand's own measurement corpus)
```

## 3. The service surface (which one leads matters)

- **Measure** (Profound's lane) — the foundation; everything sits on it.
- **Why** (citations + attributes + **off-site provenance**) — comes with
  measurement done right; this is the differentiated insight. See §4.
- **Ask** (agent/search bar) — the daily-use surface, grounded in the brand's data.
- **Act** (AirOps' lane) — content + push; gated on the customer shipping fast.
- **Prove** (causal lift) — the open space neither competitor truly owns.

## 4. The "why," sharpened: off-site citation provenance

Both this project's prior analysis and the external Gemini analysis converge on
the same point: **LLM recommendations are driven heavily by third-party / off-site
sources**, not just the brand's own site. So the differentiated "why" is the
*provenance* view:

> "Perplexity recommends Brooks for this query; it cited RunRepeat, Reddit, and
> Wirecutter; you appear in none of them. Here is the list of sources to go earn."

This is valuable on day one and does **not** depend on the customer shipping a
change fast — which sidesteps the slow-market problem.

## 5. Causal proof vs. action (do not conflate)

- **Action** = the change you make in the world (publish content, earn a mention).
  The lever. AirOps industrialises this; it is commoditizing.
- **Causal proof** = the instrument proving the lever moved the number: baseline on
  a frozen panel → change → re-measure same panel → attribute the delta. NOT an
  action. Almost nobody can do it; it is the moat candidate.

## 6. Honest status of the v1 action layer

The current action (`action.py` + `/api/recommendations/generate`) is demo-ware:
the frontend sends only `{brand_id, competitor}`; the backend grabs **one arbitrary
sample query** (`get_sample_query`, fallback literally `"best {category}"`), pairs
it with a competitor name, and makes one Sonnet call returning a generic FAQ. It is
**not** tied to the queries where the brand actually loses and has **no** idea why
the competitor wins. It is "just words." It gains depth only by becoming a
*consequence* of measurement + off-site why + proof — not by swapping the FAQ
generator for a trendier generator.

## 7. The third-product options (same market, same customer, different job)

- **Reputation / hallucination monitor** — track what AI *says* about the brand
  (false claims, stale facts, sentiment) with alerts. Acute pain, *different buyer*
  (brand/comms), same pipeline. Strong clean wedge.
- **Pre-publish recommendability simulator** — simulate how engines would treat a
  draft before publishing; the causal engine as a testing product; natural home for
  the Ask search bar. Most novel/defensible, hardest to make rigorous.

## 8. CONTESTED: the Gemini "Lighthouse / entity-graph / llms.txt" pivot

An external (Gemini) thread proposed renaming to "Lighthouse" and repositioning the
product around an **off-site entity-graph + `llms.txt`** thesis. Assessment:

**Valid kernel (adopt):** off-site sources drive recommendations; a "provenance /
where did it learn that" view is strong. The crawl-timing critique of website-based
causal experiments is a real caution (mitigated, not removed, by retrieval engines).
The Brooks/On normalization is a great *entity-resolution story* for the pitch.

**Risks (do NOT bet the product on):**
- **`llms.txt` is unproven.** It is a *proposed* standard with limited adoption; no
  solid evidence the major answer engines rank/recommend by it, and Google has
  publicly said it does not use it. Building the core *action* as an llms.txt
  compiler bets the company on a standard nobody confirmed the engines read. At
  most: generate it as one cheap optional output and *test* whether it moves
  anything. Do not headline it.
- **"One-click Wikidata/Wikipedia sync" is not a clean SaaS action.** Notability
  gatekeeping, reverts, contested edits — it is digital PR/editorial, not an API
  button. Entity consistency matters as a *diagnostic*, not as a one-click product.
- **Whipsaw risk.** Renaming + regenerating a deck + repositioning around an
  unvalidated thesis hours before a pitch trades a defensible story for a glossy
  one you cannot demo or defend under questioning.

**Recommendation:** Do not pivot wholesale. Absorb the off-site/provenance insight
into the "why" layer (§4). Keep measurement-deep as the foundation. Stay skeptical
of llms.txt-as-product. If a pitch is imminent, lead with what is true and
demoable (the real engine + the Brooks/On entity finding + the off-site provenance
direction as the forward edge), not the Lighthouse rebrand.

## 9. Open decisions (founder's call)

1. Which differentiated layer leads v1: causal-proof + Ask, reputation monitor, or
   action engine. (Leaning: measurement-deep foundation now; causal/proof as the
   differentiator; action as expansion.)
2. Whether to keep the consumer/DTC framing narrowed to *fast-shipping* brands, or
   move the buyer (agency / B2B SaaS) where acting fast is the customer's job.
3. How far to chase off-site (provenance reporting only, vs. assisted off-site
   action). Provenance reporting first; assisted action later.
