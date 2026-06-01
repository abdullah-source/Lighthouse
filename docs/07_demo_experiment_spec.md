# Demo Experiment Spec — Causal Lift, v0

**Goal:** prove the differentiator with one clean before/after experiment, buildable
on the existing v0 (`probe.py`, `parse.py`, `report.py`, `db.py`) by June 5.
**Thesis being demonstrated:** measurement is the commodity; *causal proof of lift* is
the moat. We don't just show a score — we show a specific change moving the mention
rate, with the AI responses as evidence.

---

## The honesty problem (read first)

A true causal test means changing a brand's live content and watching the models'
recommendations change. Two timescales:

- **Fast loop (days):** retrieval-grounded models (Perplexity, ChatGPT Search,
  Gemini grounding) re-crawl and reflect the change.
- **Slow loop (months):** base models change only after retraining.

We do **not** control a real brand's website, and we can't wait for the slow loop. So
the demo uses a **retrieval-efficacy test** as an honest proxy for the fast loop:
probe each model with and without the candidate content supplied as a retrieved
source, and measure whether the recommendation changes. Label it exactly that in the
demo — "this measures whether the content *would* move a retrieval-grounded answer,"
not "this proves a live-web causal effect." The live-page test (below) is the pilot
validation, not the demo.

```
  BASELINE                          TREATMENT
  query x N trials x models   -->   same query x N trials x models
  (no extra context)                (+ candidate content as a provided source)
        │                                   │
        ▼                                   ▼
  mention rate / position           mention rate / position
        └──────────────  Δ lift + side-by-side responses  ──────────────┘
```

## Setup

- **Brand / category:** Allbirds / sustainable footwear (already wired in
  `queries.py`). One brand is enough.
- **Target query:** pick ONE query from the baseline where Allbirds is absent or
  buried (low position). This is the query we "fix."
- **Holdout queries:** keep 3–5 queries we do NOT touch. They prove the effect is
  specific to the change, not a global shift in the model's mood.
- **Trials:** N = 15–20 per query per model (enough for a believable proportion).
- **Models:** GPT-5 + Claude (both already in `probe.py`). Add Perplexity if the key
  is live — it's the most retrieval-grounded and makes the fast-loop point cleanest.

## Procedure

1. **Baseline run.** Run the target query + holdouts, N trials, all models. Parse to
   mention rate + position for Allbirds. Store with a `phase = "baseline"` tag.
2. **Generate the change.** Produce one candidate content artifact aimed at the
   target query (an FAQ block or comparison snippet that states the attributes the
   winning competitors have and Allbirds lacks in the responses). This is the
   "action" step — reuse the Sonnet path.
3. **Treatment run.** Re-run the *same* target query + holdouts, N trials, all
   models, but inject the candidate content into the prompt as a labeled retrieved
   source (e.g. "Here is a source from the brand's site: …"). Tag `phase =
   "treatment"`.
4. **Measure.** For the target query: Δ mention rate, Δ average position, attribute
   changes. For holdouts: confirm ~no change. Report proportions with a simple
   confidence interval; do not report a single number.
5. **Show the evidence.** Print 2–3 actual baseline responses (Allbirds absent) next
   to 2–3 treatment responses (Allbirds present), so the lift is visible, not
   asserted.

## What to build (delta on v0)

- A `--phase {baseline,treatment}` flag and a `phase`/`experiment_id` column on the
  responses table (`db.py`).
- A context-injection mode in `probe.py` that prepends a provided source block to the
  query prompt (treatment only).
- An experiment report in `report.py`: baseline vs treatment table (target +
  holdouts), Δ mention rate / position, and the side-by-side response excerpts.
- Keep it a CLI. No web app.

## Success criteria for the demo

- Target query shows a visible, defensible mention-rate lift in treatment.
- Holdouts stay flat (proves specificity).
- The side-by-side responses make the lift legible to a non-technical room.
- You can state the caveat in one sentence: "This is a fast-loop retrieval-efficacy
  test; the live-web and slow-loop versions are the pilot."

## Cost / time

- N=20 × ~6 queries × 2 phases × 2–3 models ≈ 480–720 calls. Well under $5.
- Build: ~1 day with the v0 already in place.

## Pilot validation (after the demo, not for June 5)

For a real brand willing to partner: make the change live on a page they control,
confirm indexing, then re-probe retrieval models over 1–2 weeks to measure the actual
fast-loop lift. That's the first real data point for the causal playbook.

## Risks / honest caveats

- **Non-determinism:** N trials + holdouts + confidence intervals, not a point claim.
- **Proxy ≠ live:** context injection overstates what live content achieves (the
  model is handed the source instead of having to retrieve it). Disclose it.
- **Single brand/category:** one experiment is a thesis, not a moat. Say so.
