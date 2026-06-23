"""
config.py — loads environment variables and centralizes constants.

Why a separate file:
- Every other module needs the API keys. Loading them once here means
  the rest of the code doesn't need to think about .env loading.
- Model IDs are constants. If Anthropic ships Sonnet 4.7 next month and
  we want to upgrade, we change ONE line here instead of grepping the
  whole codebase.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root into os.environ.
# If .env doesn't exist, this silently does nothing — that's fine for now.
PROJECT_ROOT = Path(__file__).parent
load_dotenv(PROJECT_ROOT / ".env")


# --- API keys ---------------------------------------------------------------

# os.environ.get returns None if the key isn't set. We validate below —
# calling code can assume these are non-None after require_api_keys().
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

# Perplexity (Sonar) — a RETRIEVAL-grounded engine. Unlike plain GPT/Claude,
# it answers from live web search and returns the SOURCES it cited. Optional:
# if the key is absent we simply skip it (no citations captured).
PERPLEXITY_API_KEY = os.environ.get("PERPLEXITY_API_KEY", "")
PERPLEXITY_ENABLED = bool(PERPLEXITY_API_KEY)

# --- Database --------------------------------------------------------------
# When DATABASE_URL (a Postgres connection string, e.g. Supabase) is present,
# the app uses Postgres + pgvector; otherwise it falls back to local SQLite.
# The secret lives ONLY in .env — never hardcode it here.
DATABASE_URL = os.environ.get("DATABASE_URL", "")
USE_POSTGRES = bool(DATABASE_URL)

# --- Clerk auth (optional) --------------------------------------------------
# Logins activate only when a publishable key is present. Without it, the app
# runs in open demo mode. Get keys at https://dashboard.clerk.com (free tier).
CLERK_PUBLISHABLE_KEY = os.environ.get("CLERK_PUBLISHABLE_KEY", "")
CLERK_SECRET_KEY = os.environ.get("CLERK_SECRET_KEY", "")
CLERK_ENABLED = bool(CLERK_PUBLISHABLE_KEY)


def require_api_keys() -> None:
    """
    Fail fast if the required keys are missing.

    Anthropic is REQUIRED — we use it for query generation, parsing, and
    one of the two probed models. OpenAI is OPTIONAL — if absent, probe.py
    skips GPT-5 and only probes Claude Sonnet.

    Called from main.py before any network calls so we don't waste time
    setting up the DB just to crash on the first API request.
    """
    if not ANTHROPIC_API_KEY:
        raise RuntimeError(
            "Missing ANTHROPIC_API_KEY. Copy .env.example to .env and fill it in."
        )
    if not OPENAI_API_KEY:
        print(
            "[config] OPENAI_API_KEY not set — running in Claude-only mode. "
            "GPT-5 probing will be skipped."
        )
    if not PERPLEXITY_API_KEY:
        print(
            "[config] PERPLEXITY_API_KEY not set — skipping the retrieval probe. "
            "No citations / source provenance will be captured."
        )


# --- Model IDs --------------------------------------------------------------
# Centralized so we change them in one place if Anthropic / OpenAI release
# a new version.

MODEL_QUERY_GEN = "claude-sonnet-4-6"           # creative + structured (1 call per brand)
MODEL_PROBE_OPENAI = "gpt-5"                    # one of the models we measure
MODEL_PROBE_ANTHROPIC = "claude-sonnet-4-6"     # the other model we measure
MODEL_PROBE_PERPLEXITY = "sonar"               # retrieval-grounded; returns citations
PERPLEXITY_MODEL_LABEL = "perplexity-sonar"    # how the engine is stored / shown in 'by model'
MODEL_PARSE = "claude-haiku-4-5-20251001"       # cheapest capable for structured extraction
MODEL_ACTION = "claude-sonnet-4-6"              # generates publish-ready action artifacts
MODEL_ASK = "claude-sonnet-4-6"                 # RAG answers over the brand's own corpus

# Embeddings power the RAG layer (chunk → embed → vector store → retrieve).
# Uses the OpenAI key we already have. RAG is enabled only when that key exists;
# without it, panel grounding falls back to stuffing raw context.
EMBED_MODEL = "text-embedding-3-small"          # 1536-d, cheap
RAG_ENABLED = bool(OPENAI_API_KEY)


# --- Storage ----------------------------------------------------------------

# Where the SQLite file lives. Created on first run if it doesn't exist.
# Overridable via env var for testing or alternate locations.
DB_PATH = Path(os.environ.get("BRANDVIZ_DB_PATH", PROJECT_ROOT / "data" / "probe.sqlite"))


# --- Tuning knobs -----------------------------------------------------------

QUERIES_PER_BRAND = 20      # legacy generic fallback (no context provided)
PANEL_SIZE = 40             # v2: queries in a frozen, context-grounded panel.
                            # ~40 gives a stabler mention rate (~±8pt vs ±11 at 20)
                            # and room to split targeted/holdout for causal proof.
PROBE_CONCURRENCY = 5       # max parallel probe API calls (stay under rate limits)
PARSE_CONCURRENCY = 8       # max parallel parse calls (Haiku is fast, can be higher)
