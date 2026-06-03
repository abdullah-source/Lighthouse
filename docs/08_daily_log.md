# Daily Log — Brand Visibility for the LLM Era

Running log, newest entries appended. Continues the tradition of `04_day2_log_addition.md`
and `05_v0_build_log.txt`.

---

## June 1, 2026 — CEO planning / positioning pivot

**Goal today:** pressure-test the product scope before I build the June 8 prototype.
Ran a structured CEO-style plan review with a live competitive scrape.

**The hard finding.** My pivot from two weeks ago — "Profound monitors, we act;
nobody ships the change" — is simply false now. I scraped Profound, Peec, and AirOps
live. Profound is a "full-stack marketing platform" with agents that publish straight
to WordPress / Sanity / Contentful. AirOps' entire product is Insights → Action →
Measure, driven by an agent (Quill) that drafts and executes under approval gates and
loops the team in. The "GitHub for the marketing department, one-click push" idea I
was excited about? That's literally AirOps' Quill + Playbooks, shipping today. So the
action wedge is gone — and neutrality is gone as a marketing line too (nobody even
markets it). Every competitor's case studies are B2B SaaS; consumer/DTC is empty.

**The uncomfortable question I had to sit with:** if action isn't the wedge, am I
just selling a worse AirOps?

**The cleaner framing that came out of it.** Measurement is commoditizing — every
tool shows the same visibility / position / sentiment dashboard. The thing none of
them prove is *causation*: which specific change *caused* the AI to start
recommending you. So the differentiator is **proven causal lift** — controlled
before/after experiments — run **deep in one category** so it compounds into a
dataset competitors can't clone by shipping a feature. And it works on two
timescales: a **fast loop** (retrieval models like Perplexity change what consumers
see in days) and a **slow loop** (base models, retrained, change what the model
*believes* about a category for years). Most tools only touch the fast loop.

**Why this is also the more interesting idea.** When every brand optimizes content
*for the model*, the consumer's choice set stops being "the best brands" and becomes
"the brands that best shaped the model." Over the slow loop you're editing the
default advice a whole generation inherits as neutral fact. That reframes the venture
from "an SEO tool" to "the layer that shapes — and should disclose — what AI
recommends to consumers." Neutrality comes back there, *earned*: it's the only honest
posture for that layer, and structurally impossible for an LLM company to match.

**Decisions:** differentiator = causal proof + the dual-loop framing. Kept the
full-platform vision but demoted action from "the wedge" to table stakes. Segment
still open (consumer/DTC = unclaimed lane vs B2B SaaS = easier sell).

**Shipped:** rewrote the pitch (`01`), wrote a competitor benchmark with the live
data (`06`), wrote a spec for one before/after causal experiment buildable on the v0
(`07`), corrected the stale "we act" claims across `02–04`. Pushed it all.

**Honest state:** the causal moat is a *someday* bet — today it's a thesis and one
experiment, not a moat. I'd rather say that out loud than oversell it.

---

## June 2, 2026 — push, timeline reset, prof feedback

**Did:** pushed yesterday's positioning work to GitHub, so the venture's assessment
now lives in the repo and the progress is tracked in git (turns out ZD likes that the
work lives there — the "github tracking" framing).

**Prof feedback (ZD).** Encouraging note on Friday's pitch — he's sold on GEO as part
of the future, liked the "cleaner framing," and asked me to share it. He flagged the
exact thing I'd been circling: the **assessment layer (the github-style visibility
tracking) is the strong part; the action layer is where even funders are uncertain.**
That matches what the scrape showed — action is crowded and contested. So I'll anchor
the pitch on assessment + causal proof, and be honest that action is approval-gated
and not the wedge.

**Timeline reset against the real deadlines:**
- **Mon June 8 (afternoon):** revised ~5-min single-project pitch — user stories,
  business feasibility, prototype progress. Model: Cheyenne's Tualmi pitch
  (concentrated, funder-facing).
- **Fri June 12 (morning):** meeting with Cameron Hajialiakbar (new-venture lawyer);
  chance for a ~60-second elevator pitch. Also piloting his ownership-law / term-sheet
  course this summer.

**Key call to keep the week unblocked:** I don't need to settle B2B-SaaS-vs-DTC before
building. The causal experiment proves a *mechanism* — I'll prove it on Allbirds
(already wired, ~$5) and let the pitch narrative name the segment. Proof and
go-to-market don't have to be the same brand for a demo.

**Still chewing on:** segment. DTC is the unclaimed lane (better moat) but slower,
less GEO-aware buyers. B2B SaaS is easier to sell and to run experiments with, but
crowded. Leaning B2B-SaaS-niche for the pilot, DTC as the expansion story — not
locked.

**To share with ZD:** the cleaner framing (causal proof + fast/slow dual-loop + the
consumer-choice-set point). He asked for it.
