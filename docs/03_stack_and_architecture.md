# Technical Stack and Architecture
## Brand Visibility for the LLM Era

**Owner:** Abdullah Ali
**Last updated:** May 20, 2026

---

## 1. High-level architecture

```
[ Brand User ] → [ Next.js Frontend ] → [ FastAPI Backend ]
                                              ↓
                              [ Postgres (Supabase / Neon) ]
                                              ↑
                         [ Celery Workers ] ← [ Redis Queue ]
                                ↓
                  [ LLM APIs: GPT-5, Claude, Gemini, Perplexity ]
```

The system has three layers:
1. **Probing layer** — workers that query LLMs and store raw responses
2. **Parsing layer** — workers that extract structured data from raw responses
3. **Presentation layer** — backend API and frontend dashboard

## 2. Component breakdown

### 2.1 Query generation
- **Model used:** Claude Sonnet 4.5 (one call per brand at onboarding)
- **Why this model:** best at structured, diverse output for a creative task done once
- **Cost:** about $0.50 per brand at signup, one-time

### 2.2 Probing engine
- **Models probed:** GPT-5 (OpenAI), Claude Sonnet (Anthropic), Gemini 2.5 Pro (Google), Perplexity Sonar
- **Orchestration:** Python with `asyncio` for parallel API calls
- **Workers:** Celery with Redis as the broker
- **Schedule:** Celery Beat for cron-like scheduling
- **Rate limiting:** per-model rate limit handlers to avoid 429s

### 2.3 Parsing engine
- **Model used:** Claude Haiku 4.5 or GPT-5 Mini (cheap, fast, structured)
- **Why:** parsing is a high-volume, low-creativity task. Cheapest capable model wins.
- **Output schema:**
  ```json
  {
    "response_id": "uuid",
    "brands_mentioned": ["Allbirds", "Hoka", "Brooks"],
    "ordered_position": {"Allbirds": 3, "Hoka": 1, "Brooks": 2},
    "attributes_per_brand": {
      "Allbirds": ["sustainable", "comfortable", "minimalist"],
      "Hoka": ["cushioned", "popular for runners"]
    },
    "links_provided": [...],
    "sentiment_per_brand": {"Allbirds": "positive", ...}
  }
  ```

### 2.4 Recommendation engine
- **Model used:** Claude Sonnet 4.5
- **Input:** the user's website content (scraped), top competitor's content (scraped), the LLM responses where the competitor was picked
- **Output:** ranked list of specific content/structure changes to make
- **Frequency:** generated weekly per brand, not per query

### 2.5 Backend API
- **Framework:** FastAPI (Python)
- **Why:** async-native (good for many concurrent API calls), strong typing with Pydantic, fast iteration
- **Auth:** Clerk (handles login, sessions, billing flows)
- **Hosting:** Railway or Fly.io

### 2.6 Frontend
- **Framework:** Next.js 15 with App Router
- **Styling:** Tailwind CSS
- **Components:** shadcn/ui
- **Charts:** Recharts or Tremor
- **Hosting:** Vercel

### 2.7 Database
- **Primary:** Postgres on Supabase (free tier for v0, Pro plan at $25/month for beta)
- **Extensions:** pgvector for semantic search over raw responses
- **Why not a separate vector DB:** Pinecone or Weaviate add cost and complexity. pgvector on Postgres is good enough until 10M+ vectors.

### 2.8 Queue and cache
- **Queue:** Redis (Upstash free tier for v0, or self-hosted on Railway)
- **Cache:** same Redis for caching LLM responses (dedupe identical queries within 24h window)

### 2.9 Observability
- **Errors:** Sentry (free tier)
- **Product analytics:** PostHog (free tier)
- **LLM call logs:** custom Postgres table + Helicone if needed later

## 3. Database schema (simplified)

```sql
-- Brands tracked on the platform
CREATE TABLE brands (
  id UUID PRIMARY KEY,
  user_id UUID REFERENCES users(id),
  name TEXT NOT NULL,
  category TEXT NOT NULL,
  website_url TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Buyer queries per brand
CREATE TABLE queries (
  id UUID PRIMARY KEY,
  brand_id UUID REFERENCES brands(id),
  query_text TEXT NOT NULL,
  is_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Raw LLM responses
CREATE TABLE responses (
  id UUID PRIMARY KEY,
  query_id UUID REFERENCES queries(id),
  model TEXT NOT NULL,        -- 'gpt-5', 'claude-sonnet', 'gemini-pro', 'perplexity'
  trial_number INT NOT NULL,  -- 1, 2, 3 for the 3 runs per query
  raw_text TEXT NOT NULL,
  embedding VECTOR(1536),     -- via pgvector, optional
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Parsed structured data
CREATE TABLE response_parses (
  id UUID PRIMARY KEY,
  response_id UUID REFERENCES responses(id),
  brands_mentioned TEXT[],
  ordered_positions JSONB,    -- {"Allbirds": 3, "Hoka": 1}
  attributes JSONB,           -- {"Allbirds": ["sustainable"]}
  sentiment JSONB,
  links_provided TEXT[],
  parsed_at TIMESTAMPTZ DEFAULT NOW()
);

-- Recommendations
CREATE TABLE recommendations (
  id UUID PRIMARY KEY,
  brand_id UUID REFERENCES brands(id),
  recommendation_text TEXT NOT NULL,
  priority INT,
  related_queries UUID[],
  status TEXT DEFAULT 'open', -- 'open', 'in_progress', 'done', 'dismissed'
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Aggregated daily metrics per brand
CREATE TABLE daily_metrics (
  id UUID PRIMARY KEY,
  brand_id UUID REFERENCES brands(id),
  date DATE NOT NULL,
  mention_rate NUMERIC,       -- 0.0 to 1.0
  avg_position NUMERIC,
  total_queries INT,
  total_mentions INT,
  UNIQUE(brand_id, date)
);
```

## 4. Cost model

### v0 demo (Friday May 22)
| Item | Cost |
|---|---|
| OpenAI API credits | $5 |
| Perplexity API credits | $5 |
| Gemini (free tier) | $0 |
| Anthropic (already on Claude Code) | $0 |
| Hosting | $0 (local laptop) |
| Database | $0 (SQLite or CSV) |
| **Total** | **under $10** |

### v0.5 internal demo (June 5)
| Item | Cost |
|---|---|
| API costs (1 brand, 200 queries, 4 models, daily for 2 weeks) | ~$50 |
| Hosting (Railway hobby) | $5/month |
| Database (Supabase free tier) | $0 |
| Frontend (Vercel free) | $0 |
| **Total** | **~$55** |

### v1 beta (August 2026, 10 paying brands)
| Item | Monthly cost |
|---|---|
| LLM API costs | $1,500-3,000 |
| Hosting (Railway pro) | $20 |
| Database (Supabase Pro) | $25 |
| Redis (Upstash) | $10 |
| Sentry / PostHog | $0 (free tiers) |
| Clerk auth | $25 |
| Domain + email | $20 |
| **Total monthly cost** | **~$1,600-3,100** |
| **Revenue at 10 brands × $1,500** | **$15,000** |
| **Gross margin** | **~80%** |

## 5. Storage requirements

### v0 demo
- 5 brands × 100 queries × 4 models × 3 trials = 6,000 rows
- ~5 KB per row = 30 MB total
- Fits on any laptop.

### v1 beta (10 brands at full operation)
- 10 brands × 500 queries × 4 models × 3 trials × 365 days = ~22M response rows per year
- ~5 KB raw + ~1 KB structured per row = ~130 GB per year, raw text included
- Reducible to ~30 GB if we store raw responses for 30 days only, then drop and keep only parsed data
- Supabase Pro starts at 8 GB included, then $0.125/GB. Manageable.

### Vector embeddings
- Only embed responses if needed for semantic search (a v2 feature)
- For v1, skip embeddings. Saves storage and API cost.

## 6. What I will build first (build order)

1. **Probe script** (day 1-2): a Python script that takes a brand name and category, generates queries, hits 4 LLM APIs, saves raw responses to a local SQLite file. No frontend, no auth.
2. **Parser script** (day 3): reads raw responses from SQLite, calls a parsing model, writes structured rows to the same SQLite.
3. **Static report generator** (day 4-5): reads parsed data, generates a one-page HTML report with charts (using matplotlib or plotly) showing mention rate, competitor comparison, top losing queries.
4. **Show this to brands** (week 2): 5 free audits to mid-market DTC consumer brands. Validate the insight is interesting.
5. **Web app** (week 3-6): if validation works, port the scripts into a FastAPI + Next.js app with self-serve onboarding.
6. **Closed beta launch** (August): 10 paying brands at $1,000-1,500/month.

## 7. What I'm explicitly not doing yet

- Training or fine-tuning any model
- Building a custom LLM
- Real-time streaming (daily refresh is enough)
- Multi-tenant scaling problems
- Enterprise SSO, audit logs, role-based access (defer to enterprise tier)
- Mobile app
- API for customers (defer to v2)

## 8. Dependencies and accounts I need

- [x] Claude Code (have it)
- [ ] OpenAI API account ($5 credit)
- [ ] Perplexity API account ($5 credit)
- [ ] Google Gemini API key (free)
- [ ] Anthropic API key (separate from Claude Code subscription, optional for v0)
- [ ] GitHub repo (private to start)
- [ ] Vercel account (free)
- [ ] Supabase account (free tier)
- [ ] Domain name (defer until v0.5)

## 9. One paragraph technical summary

The system is an LLM orchestration and analytics platform. It queries the four major LLMs at scale on behalf of consumer brands, parses unstructured responses into structured brand-mention data using a smaller cheaper model, and surfaces analytics and recommendations through a Next.js dashboard. No model training. No proprietary AI. The moat is the accumulating proprietary dataset and the recommendation playbooks we develop from observing what actually moves brand mention rates over time.
