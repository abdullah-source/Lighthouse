"""
report.py — aggregate parsed responses and print to terminal.

For v0 we compute the three metrics every Profound / Peec / AirOps
dashboard has converged on:

  - Mention rate: % of responses where the target brand appears.
  - Average position: when mentioned, where in the list does it land?
  - Share of voice: target's mentions / total brand mentions.

We also show the top competitors so the brand sees who they're losing to.

Why no chart library:
- Terminal output is sufficient for v0. Charts come in v1 with the dashboard.
- matplotlib / plotly add install weight and another concept to learn.
"""

import json
from collections import Counter, defaultdict

from db import fetch_parsed_for_brand, get_conn


def _normalize(name: str) -> str:
    """
    Brand name matching is case-insensitive and whitespace-tolerant.
    "Allbirds" and "allbirds" count as the same brand.
    """
    return name.strip().lower()


def print_report(brand_id: int, target_brand: str, category: str) -> None:
    """Read parsed_responses, compute metrics, print them."""
    with get_conn() as conn:
        rows = fetch_parsed_for_brand(conn, brand_id)

    target_norm = _normalize(target_brand)

    total_responses = len(rows)
    if total_responses == 0:
        print("No parsed responses found. Run the pipeline first.")
        return

    # --- aggregate ----------------------------------------------------------
    target_mention_count = 0
    target_positions: list[int] = []
    competitor_counter: Counter[str] = Counter()
    competitor_positions: defaultdict[str, list[int]] = defaultdict(list)
    responses_by_model: Counter[str] = Counter()
    target_mention_by_model: Counter[str] = Counter()

    for row in rows:
        brands = json.loads(row["brands_mentioned"])
        positions = json.loads(row["positions"])
        model = row["model"]
        responses_by_model[model] += 1

        # Did the target brand appear in this response?
        for b in brands:
            if _normalize(b) == target_norm:
                target_mention_count += 1
                target_mention_by_model[model] += 1
                if b in positions:
                    target_positions.append(positions[b])
                break  # count once per response even if mentioned multiple times

        # Count every OTHER brand as a competitor.
        for b in brands:
            if _normalize(b) == target_norm:
                continue
            competitor_counter[b] += 1
            if b in positions:
                competitor_positions[b].append(positions[b])

    # --- compute metrics ----------------------------------------------------
    mention_rate = target_mention_count / total_responses
    avg_position = (
        sum(target_positions) / len(target_positions) if target_positions else None
    )
    total_brand_mentions = target_mention_count + sum(competitor_counter.values())
    share_of_voice = (
        target_mention_count / total_brand_mentions if total_brand_mentions else 0.0
    )

    # --- print --------------------------------------------------------------
    print()
    print("=" * 68)
    print(f"  BRAND VISIBILITY REPORT — {target_brand}  ({category})")
    print("=" * 68)
    print()
    print(f"  Responses analyzed:   {total_responses}")
    print(f"  Mention rate:         {mention_rate:>6.1%}  ({target_mention_count} / {total_responses})")
    if avg_position is not None:
        print(f"  Avg. position:        {avg_position:>6.2f}  (when mentioned, lower is better)")
    else:
        print(f"  Avg. position:        n/a (brand never mentioned)")
    print(f"  Share of voice:       {share_of_voice:>6.1%}  ({target_mention_count} / {total_brand_mentions} brand mentions)")
    print()

    print("  By model:")
    for model, count in responses_by_model.most_common():
        tm = target_mention_by_model.get(model, 0)
        rate = tm / count if count else 0
        print(f"    {model:<32} {tm:>3}/{count:<3}  ({rate:.1%})")
    print()

    print("  Top 5 competitors:")
    if not competitor_counter:
        print("    (no competitors detected)")
    for i, (name, count) in enumerate(competitor_counter.most_common(5), 1):
        positions_list = competitor_positions[name]
        avg_pos = sum(positions_list) / len(positions_list) if positions_list else None
        rate = count / total_responses
        pos_str = f"avg pos {avg_pos:.1f}" if avg_pos is not None else "no positions"
        print(f"    {i}. {name:<30} {count:>3} mentions ({rate:.1%})  {pos_str}")
    print()
    print("=" * 68)
    print()
