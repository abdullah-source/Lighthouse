# Friday Pitch — Brand Visibility for the LLM Era

**Abdullah Ali | Summer Startup 2026 | revised June 1, 2026**
**Audience: Eship Studio + Outreach Team (professor pitch, no funding) | ~2 min**

> Revision note: the earlier version of this pitch claimed "Profound monitors, we
> act — none of them ship the change." As of June 2026 that is false: Profound and
> AirOps both generate and publish content changes today. This version drops that
> claim and anchors on the one difference that holds up — proven causal lift, deep
> in one category. See `06_competitor_benchmark.md` for the evidence.

---

## The pitch (read out loud, time it — target 1:55–2:00 at ~140 wpm)

When a consumer asks ChatGPT "what's the best moisturizer for sensitive skin," the
model names a handful of brands. The brand it names makes the sale. The brand it
skips does not exist for that consumer. Buying intent is moving fast from Google to
ChatGPT, Claude, Gemini, and Perplexity.

Let me be honest about the competition up front, because it matters. There is
already a real category here — Profound, AirOps, Peec. They measure how AI sees
your brand, and the leaders now also generate and publish content for you. I am not
going to claim they don't act. They do. So the only question worth asking is: what
is actually different?

Here it is. Everyone hands a brand a visibility score. Nobody proves which specific
change *caused* the AI to start recommending you. Measurement is becoming a
commodity — every tool shows the same visibility, position, and sentiment dashboard.
The durable value is causal proof. We run a controlled before-and-after experiment:
change one thing, re-probe the models, and show the lift with the actual AI
responses as the evidence. Do that deep in one category and you build the one thing
a competitor can't copy overnight — a proprietary dataset of what actually moves AI
recommendations for mid-market consumer brands.

And there's a deeper shift underneath this, which is the part I find most
interesting. When every brand optimizes its content *for the model*, the consumer's
choice set stops being "the best brands" and becomes "the brands that best shaped
the model." It happens on two timescales. A fast loop, where retrieval models like
Perplexity and ChatGPT Search change what consumers are shown this week. And a slow
loop, where the base models, retrained on the web, change what the model *believes*
about a category for years. Most tools only touch the fast loop. The slow loop is
where you edit the default advice a whole generation of consumers inherits as
neutral-sounding fact. That is a real change in who controls consumer discovery, and
it's invisible.

Because we sit at that layer, neutrality is structural, not a slogan. We are
brand-paid only and we cite the exact AI evidence behind every recommendation. The
day an LLM company ships its own visibility tool, it can never be neutral across the
others. We always can.

Where I am: I've built a v0 that probes GPT-5 and Claude across buyer queries for a
brand, parses every response into structured mention data, and reports mention rate,
position, and competitors. The next step is the causal experiment — baseline, one
change, re-probe, measure the lift.

I'll be straight about the moat: today this is a thesis and one experiment, not a
moat yet. The moat compounds as the causal dataset grows inside one category. That's
the bet, and I think it's the right one.

My ask: feedback on the causal-experiment methodology given how non-deterministic
these models are, and intros to anyone running marketing at a mid-market DTC
consumer brand who'd be a willing test case.

---

## The structure (for your reference)

| Beat | Duration | Content |
|---|---|---|
| Hook | 15 sec | Skincare / ChatGPT scenario; picked = sale |
| Market shift | 10 sec | Buying intent moving Google → LLMs |
| Honest competition | 20 sec | Profound / AirOps / Peec exist and DO act |
| The difference | 30 sec | Causal proof, not just a score; category-dense dataset = moat |
| The deeper shift | 25 sec | Fast loop / slow loop; who controls the consumer's choice set |
| Neutrality (earned) | 10 sec | Brand-paid only; structural vs LLM-cos |
| Where I am + honesty | 15 sec | v0 built; moat is a someday bet, said plainly |
| Ask | 10 sec | Methodology feedback + DTC test-case intros |

---

## Anticipated questions and short answers

**Q: How is this not just AirOps or Profound?**
On features, it largely is — they measure, generate, and publish. The difference is
causal proof: I run controlled before/after experiments and show which specific
change moved the mention rate, with the AI responses as evidence. Going deep in one
consumer category turns that into a dataset they don't have and can't clone without
running the same experiments for the same months.

**Q: Isn't "causal" impossible given model non-determinism?**
Not impossible, but noisy, and I won't pretend otherwise. I run many trials per
query, hold out queries I didn't optimize to show the effect is specific not global,
and report mention rate as a distribution with confidence, not a single number. The
noise is itself an interesting measurement problem.

**Q: Why mid-market DTC consumer brands?**
Every competitor's case studies are B2B SaaS — CRMs, Ramp, Carta, Webflow. Consumer
brands (footwear, beauty, food) are absent from their proof, the buyer already has an
SEO budget, and consumer LLM-query volume is highest there.

**Q: What stops Profound from doing this?**
Nothing structural — they could. The defense is category density: a causal dataset
for one consumer category compounds with every experiment and isn't copyable by
shipping a feature. First and deepest in a category wins.

**Q: How does this change marketing itself?**
Content stops being written for humans and starts being written for model ingestion.
Over the slow loop, brands that invest don't just rank — they shape what the model
believes about a category, which consumers then receive as neutral advice. The tool
that proves and discloses that influence is the honest version of this product.

**Q: What's the business model?**
SaaS, brand-paid only, mid-market consumer brands. Pricing to be tested; the near
goal is a willing test case and a proven causal lift, not revenue.

---

## Things to say if you have extra time

- I'm not training a model. I measure what trained models do, change what brands
  publish, and prove the lift across probe cycles.
- The neutrality stance isn't marketing — it's the only credible posture for a layer
  that shapes what consumers get recommended, and it's structurally closed to any
  LLM company.
- The most defensible asset is the causal playbook per category. Measurement is the
  commodity; proof is the moat.
