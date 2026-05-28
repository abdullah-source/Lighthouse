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


# --- Model IDs --------------------------------------------------------------
# Centralized so we change them in one place if Anthropic / OpenAI release
# a new version.

MODEL_QUERY_GEN = "claude-sonnet-4-6"           # creative + structured (1 call per brand)
MODEL_PROBE_OPENAI = "gpt-5"                    # one of the models we measure
MODEL_PROBE_ANTHROPIC = "claude-sonnet-4-6"     # the other model we measure
MODEL_PARSE = "claude-haiku-4-5-20251001"       # cheapest capable for structured extraction


# --- Storage ----------------------------------------------------------------

# Where the SQLite file lives. Created on first run if it doesn't exist.
# Overridable via env var for testing or alternate locations.
DB_PATH = Path(os.environ.get("BRANDVIZ_DB_PATH", PROJECT_ROOT / "data" / "probe.sqlite"))


# --- Tuning knobs -----------------------------------------------------------

QUERIES_PER_BRAND = 20      # how many buyer queries we generate per brand
PROBE_CONCURRENCY = 5       # max parallel probe API calls (stay under rate limits)
PARSE_CONCURRENCY = 8       # max parallel parse calls (Haiku is fast, can be higher)
