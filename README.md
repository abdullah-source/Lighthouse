# Brand Visibility Probe — v0

Phase 0 of the [Brand Visibility for the LLM Era](docs/02_mvp_prd.md) project.

A single Python script that takes a brand name + category, generates realistic buyer queries, probes them against GPT-5 and Claude Sonnet, parses what each model recommended, and prints a terminal report showing how often the target brand appeared vs. competitors.

This is the v0 — no web app, no auth, no scheduling. See [docs/03_stack_and_architecture.md](docs/03_stack_and_architecture.md) for the v1 plan.

## How it works

CLI args (`--brand`, `--category`) → SQLite DB → 4 stages glued by IDs:

1. **Query generation** — 1 Claude Sonnet call → 20 buyer queries.
2. **Probing** — each query async fan-out to GPT-5 + Claude Sonnet (40 calls).
3. **Parsing** — each response → Claude Haiku with JSON tool-use → structured brand list.
4. **Report** — terminal output: mention rate, avg position, share of voice, top 5 competitors.

## Setup

### 1. Check Python (need 3.11+)
```bash
python3 --version
```

### 2. Virtual environment + install
```bash
cd "/Users/abdullahali/project - summer"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. API keys
Get keys from [OpenAI](https://platform.openai.com/api-keys) and [Anthropic](https://console.anthropic.com/settings/keys), then:
```bash
cp .env.example .env
# edit .env, paste your keys
```

## Run

```bash
python main.py --brand "Allbirds" --category "sustainable footwear"
```

Takes ~60–90 seconds (most of it waiting on API calls). You'll see something like:

```
======================================================================
  BRAND VISIBILITY REPORT — Allbirds  (sustainable footwear)
======================================================================

  Responses analyzed:   40
  Mention rate:         32.5%  (13 / 40)
  Avg. position:          2.8  (when mentioned, lower is better)
  Share of voice:       11.4%  (13 / 114 brand mentions)

  By model:
    gpt-5                            7/20  (35.0%)
    claude-sonnet-4-6                6/20  (30.0%)

  Top 5 competitors:
    1. Veja                          18 mentions (45.0%)  avg pos 2.1
    2. Adidas                        12 mentions (30.0%)  avg pos 3.4
    ...
```

## File map

| File | Role |
|---|---|
| `main.py` | CLI entrypoint, orchestrates the pipeline |
| `config.py` | Loads env vars + centralizes model IDs and tuning knobs |
| `db.py` | SQLite schema + insert / fetch helpers |
| `queries.py` | Generates 20 buyer queries via Claude Sonnet |
| `probe.py` | Async fan-out — each query against both models |
| `parse.py` | Async fan-out — extracts brands from each response (Haiku + tool-use) |
| `report.py` | Aggregates parsed rows + prints terminal report |
| `requirements.txt` | Pinned Python dependencies |
| `.env.example` | Template for API keys |
| `data/probe.sqlite` | Auto-created on first run (gitignored) |

## Cost expectations

For one brand × 20 queries × 2 models × 1 trial each:

| Stage | Cost |
|---|---|
| Query generation | ~$0.01 |
| Probing (GPT-5, 20 calls) | ~$0.05 |
| Probing (Sonnet, 20 calls) | ~$0.05 |
| Parsing (Haiku, 40 calls) | ~$0.02 |
| **Total per run** | **~$0.13** |

Phase 0 demo (5 brands) ≈ **$0.65** total. Well under the $10 ceiling in [docs/03_stack_and_architecture.md](docs/03_stack_and_architecture.md).

## What's NOT in v0 (deferred)

- Gemini, Perplexity probing — add when API keys are in hand
- 3 trials per query (currently 1) — bump in v1 for probability distributions
- Daily refresh / scheduling
- Action artifact generation (the wedge — see [docs/04_day2_log_addition.md](docs/04_day2_log_addition.md))
- Web dashboard, multi-tenant DB, auth, billing

See [docs/03_stack_and_architecture.md](docs/03_stack_and_architecture.md) section 6 for the v1 build order.
