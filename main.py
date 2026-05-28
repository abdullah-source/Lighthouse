"""
main.py — CLI entrypoint.

Wires the pipeline together:
  1. Parse CLI args.
  2. Validate API keys.
  3. Initialize the database.
  4. Insert the brand row.
  5. Generate buyer queries (1 sync LLM call).
  6. Probe each query against GPT-5 + Claude (async fan-out).
  7. Parse each response (async fan-out).
  8. Print the report.

Run:
    python main.py --brand "Allbirds" --category "sustainable footwear"
"""

import argparse
import asyncio

from config import require_api_keys
from db import (
    fetch_queries_for_brand,
    fetch_unparsed_responses,
    get_conn,
    init_db,
    insert_brand,
    insert_parsed,
    insert_query,
    insert_response,
)
from parse import parse_all
from probe import probe_all
from queries import generate_queries
from report import print_report


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="LLM brand visibility probe — v0")
    p.add_argument("--brand", required=True, help="Brand name to study (e.g. 'Allbirds').")
    p.add_argument("--category", required=True, help="Product category (e.g. 'sustainable footwear').")
    return p.parse_args()


async def _run_pipeline(brand_id: int) -> None:
    """Async portion of the pipeline: probing + parsing."""
    # Load the queries we just inserted.
    with get_conn() as conn:
        queries = fetch_queries_for_brand(conn, brand_id)
        query_pairs = [(q["id"], q["query_text"]) for q in queries]

    # Probe each query against the available models. probe.py decides
    # whether OpenAI is included based on whether OPENAI_API_KEY is set.
    print(f"  Probing {len(query_pairs)} queries...")
    probe_results = await probe_all(query_pairs)
    with get_conn() as conn:
        for query_id, model, raw_text in probe_results:
            insert_response(conn, query_id, model, raw_text)
    print(f"  Saved {len(probe_results)} responses.")

    # Parse each response.
    with get_conn() as conn:
        unparsed = fetch_unparsed_responses(conn, brand_id)
        response_pairs = [(r["id"], r["raw_text"]) for r in unparsed]

    print(f"  Parsing {len(response_pairs)} responses...")
    parse_results = await parse_all(response_pairs)
    with get_conn() as conn:
        for response_id, brands, positions in parse_results:
            insert_parsed(conn, response_id, brands, positions)
    print(f"  Saved {len(parse_results)} parsed rows.")


def main() -> None:
    args = _parse_args()

    # Fail fast if keys are missing.
    require_api_keys()

    # Set up storage.
    init_db()

    # Generate queries + insert brand row + queries.
    print(f"  Generating queries for '{args.brand}' in '{args.category}'...")
    queries = generate_queries(args.brand, args.category)
    print(f"  Got {len(queries)} queries.")

    with get_conn() as conn:
        brand_id = insert_brand(conn, args.brand, args.category)
        for q in queries:
            insert_query(conn, brand_id, q)

    # Run async portion.
    asyncio.run(_run_pipeline(brand_id))

    # Print the terminal report.
    print_report(brand_id, args.brand, args.category)


if __name__ == "__main__":
    main()
