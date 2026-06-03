# Week Plan → June 8 Pitch

**Window:** June 2 → June 8 (prototype + business-research week; ZD away).
**Primary deliverable:** Mon **June 8 afternoon** — revised **~5-min single-project**
pitch with **user stories + business feasibility + prototype progress**. Model on
Cheyenne's **Tualmi** pitch (concentrated, funder-facing).
**Secondary:** Fri **June 12 morning** — **~60-sec elevator** pitch for Cameron
(new-venture lawyer).

> Standing strategy (locked this week): anchor on the **assessment layer + causal
> proof**. Action is table stakes / approval-gated — ZD confirmed funders are
> uncertain on it, so don't lead with it. Prove the mechanism on **Allbirds**; name
> the segment separately in the narrative.

---

## The three pitch pieces ZD asked for

1. **User stories** — 2–3 crisp "As a [marketer], I want [X] so that [Y]." Pull/sharpen
   from `02_mvp_prd.md §6`. Make at least one about *causal proof* ("I want to know
   the change I shipped actually moved my mentions").
2. **Business feasibility** — market (mid-market consumer or a B2B SaaS niche),
   pricing ($1–3k/mo), unit economics + margin (from `03 §4`), and the moat (causal
   dataset per category). One honest slide on competition (Profound/AirOps) and why
   causal proof is the difference.
3. **Prototype progress** — the live proof: v0 probe + one before/after causal
   experiment + a static results page. This is the "site + service."

---

## To-do, by priority

### P1 — must have for June 8
- [ ] **Watch the Tualmi pitch** (≈1:03:45, passcode `s8i6@f##`); note its structure
      and steal the shape. (~30 min)
- [ ] **Confirm the v0 runs clean end-to-end** — `python main.py --brand "Allbirds"
      --category "sustainable footwear"`. The build log never confirmed the full
      40-call run. Fix anything broken first. (human ~1–2h / CC ~30m)
- [ ] **Build the experiment delta** (per `07_demo_experiment_spec.md`): `--phase`
      flag + `experiment_id` column (`db.py`), context-injection mode (`probe.py`),
      experiment report (`report.py`). (human ~1 day / CC ~1–2h)
- [ ] **Run the experiment:** baseline → make one content change → treatment +
      holdouts → get the lift number; sanity-check (target moves, holdouts flat).
- [ ] **Static results page** ("the site"): baseline vs treatment, the lift, AI
      responses side by side. (`/design-html` from the report data.) (CC ~1–2h)
- [ ] **Write the 5-min pitch** — extend `01_friday_pitch_green.md` from 2→5 min with
      the three pieces above; single-project focus (drop the 3-bucket framing).
- [ ] **Rehearse + time** to ~5:00; nail the "how is this not AirOps?" answer.

### P2 — strongly wanted
- [ ] **Decide the segment** (B2B SaaS niche vs one DTC category). One slide; affects
      user stories + feasibility. Lean B2B-SaaS-niche for the pilot.
- [ ] **Write up the "cleaner framing"** for ZD (he asked): causal proof + fast/slow
      dual-loop + the consumer-choice-set point. A short note/section.
- [ ] **Honest competition slide:** name Profound/AirOps, show the causal-proof gap.

### P3 — after June 8 / lower urgency this week
- [ ] **Draft the ~60-sec elevator** for June 12 (Cameron). Compress the 5-min to one
      breath: problem → causal-proof difference → traction → ask.
- [ ] Skim Cameron's term-sheet / ownership-law topics before the 12th.
- [ ] Join Summer-of-CS events through the week.

---

## Critical path (what actually gates the pitch)

```
confirm v0 runs ─▶ build experiment delta ─▶ run + get lift number ─▶ results page
                                                      │
                                                      └─▶ this number IS the prototype-progress slide
write 5-min pitch (uses the number) ─▶ rehearse ─▶ June 8
```

If the experiment lift number isn't believable or the v0 won't run, that's the only
real risk to the pitch — front-load it (do it first, not Friday).

## Suggested day shape (compressed, solo)
- **Tue–Wed:** Tualmi watch, confirm v0, build experiment delta.
- **Thu:** run experiment, lock the lift number, start results page.
- **Fri:** results page done; draft the 5-min pitch.
- **Sat–Sun:** finish pitch, rehearse, the "cleaner framing" writeup.
- **Mon June 8:** final rehearse → present (afternoon).

## Open decisions
- **Segment** (B2B SaaS niche vs DTC) — pick by Thu so the feasibility + user-story
  slides are coherent.
- **The one content change to test** in the experiment — pick the losing query first.

## Hard line
Do **not** build the FastAPI/Next.js platform in `03_stack_and_architecture.md`. The
static results page is the site; the probe is the service. Anything more burns the
week.
