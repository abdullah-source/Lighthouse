# 17 — Action layer strategy: merge GTM into Action (no fake projection)

**Date:** 2026-06-29
**Decision owner:** Abdullah Ali
**Status:** Decided + building.

## The decision

Do **not** ship "GTM Studio" as a separate product. **Merge it into the Action
layer** of the measurement product. Keep the agents, kill the separate-product framing.

- **Keep separate** → no. Standalone GTM is a red ocean (Clay, Apollo, 11x, the
  all-in-ones) and points at the wrong buyer (pre-launch founders who won't pay
  $1–3k/mo).
- **Kill it** → no. The strategist + designer agents are the strongest "wow" in
  the demo. Reuse them.
- **Merge into Action** → yes. One product, one buyer (mid-market brand) at three
  moments.

## The honest frame: measure → build-from-evidence → re-measure

The only defensible asset is the **real measurement**: actual probes of
GPT-5 / Claude / Perplexity → real mention rate, position, share of voice, the
**sources each engine cites**, and the **language** competitors own that you don't.

So the Action layer is **not** "generate + predict." It is:

1. **Measure** — where you stand in AI search (core, real).
2. **Build the fix** — the GTM strategist + landing designer, **fed the brand's
   real audit** (cited sources, missing language, winning competitors). The output
   targets what AI demonstrably rewards in *this* category, not generic copy. This
   grounding is the edge no vibecoded GTM tool has.
3. **Re-measure** — ship it, re-run the audit in 2–3 weeks, show the **real**
   before/after movement. That is the proof.

## Killed: the simulation as a selling point

`simulate_impact` injects the proposed content as "trusted facts" and re-asks a
sample — the answer is baked in. It is **not** a projection of how the real
engines behave after a website change. **Removed from the pitch and from the
Action UI.** Replaced by:

- **Gap diagnosis** (real, from the audit): the sources AI cites here, the
  language rivals own that you don't, who wins instead.
- **Re-measure CTA** (real): the honest before/after over time.

No fabricated "31% → 46%." Per the no-fabrication rule.

## Cold-start (solves "new brands have no AI presence")

A brand-new startup has nothing to measure about *itself* — so we measure the
**category**: who AI recommends, the sources it cites, the language it rewards.
That is real value on day one and the honest baseline they re-measure as they publish.

Flow: GTM Studio (`/gtm`) "describe your idea" → strategist + designer →
**"Measure in AI search"** → baseline audit → lands in the measured dashboard
(`/app?brand=ID`). GTM Studio stays as a marketing/demo entry that funnels into
the loop, not a dead end.

## Positioning vs Profound

Profound = enterprise measurement dashboard for the Fortune 500 ($96M Series C,
$1B, Feb 2026). Lighthouse = **measure + build-from-evidence + re-measure** for
mid-market and emerging brands. The wedge is the grounded build layer + the
honest re-measurement loop, not a projection model.

## Build status

- `gtm.py` — strategist/designer now accept `evidence` (the real audit) and a
  `category` field for the cold-start baseline.
- `api.py` — `POST /api/brands/{id}/build {mode: landing|gtm}` grounds the agents
  in `_audit_evidence(...)`.
- `web/app.js` — Action tab rebuilt: gap diagnosis + build buttons
  (landing / GTM strategy) + re-measure CTA; simulation removed.
- `web/gtm.html` — "Measure in AI search" cold-start CTA → `/app?brand=ID`.
