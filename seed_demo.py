"""
seed_demo.py - pre-run real audits for familiar brands so the demo is instant.

"Short-cut the full process": run this once, the results persist in SQLite, and
the dashboard opens them immediately on stage (no waiting, no live API cost
during the demo). Uses the full real pipeline, so the numbers are authentic.

Usage:
    .venv/bin/python seed_demo.py                 # seed the default familiar brands
    .venv/bin/python seed_demo.py "Hoka:running shoes" "Stanley:insulated water bottles"
"""

from __future__ import annotations

import sys

import store
from audit import run_audit

# Familiar, recognizable brand NAMES that make a room lean in. Note: who we
# demo on and who we sell to are independent - the engine reads public AI
# responses about any brand. We deliberately span verticals to show breadth:
#   - consumer footwear = our deep proof vertical
#   - consulting + legal = the higher-value enterprise ICP we're exploring
# Default seed: footwear only for now (cost-conscious; our deep proof vertical).
# Renowned names make the AI's actual take land harder in a pitch.
DEMO_BRANDS = [
    ("Nike", "running shoes"),
    ("Adidas", "running shoes"),
    ("Puma", "running shoes"),
    ("Reebok", "running shoes"),
    ("Oofos", "recovery footwear"),
]

# Enterprise / professional-services examples for when we want to show the
# product ports beyond shoes (higher-value ICP). Not seeded by default to save
# cost; run explicitly, e.g.:
#   python seed_demo.py "McKinsey:management consulting firms" "Morgan & Morgan:personal injury law firms"
ENTERPRISE_BRANDS = [
    ("McKinsey", "management consulting firms"),
    ("Morgan & Morgan", "personal injury law firms"),
]


def seed(brands: list[tuple[str, str]]) -> None:
    store.migrate()
    for name, category in brands:
        bid = store.create_brand(name, category)
        print(f"[seed] {name} ({category}) -> brand {bid} ...", flush=True)
        run_audit(bid, name, category)            # generic panel (no first-party context)
        row = store.get_brand(bid)
        agg = store.aggregate_brand(bid) if (row["status"] == "done") else {}
        rate = agg.get("mention_rate")
        vibes = len((agg.get("lexical") or {}).get("focal_top", []))
        print(f"[seed]   status={row['status']} rate={rate} vibe_terms={vibes}", flush=True)


def _parse_args(argv: list[str]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for a in argv:
        if ":" in a:
            name, cat = a.split(":", 1)
            out.append((name.strip(), cat.strip()))
    return out or DEMO_BRANDS


if __name__ == "__main__":
    seed(_parse_args(sys.argv[1:]))
