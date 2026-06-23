"""
parse.py — extract structured data from raw LLM responses.

We use Claude Haiku because:
- This is high-volume (1 call per response).
- It's an extraction task, not a creative one — cheap+fast is perfect.

We use tool-use to force structured output. The pattern:
1. Define a JSON schema for the data we want.
2. Tell Anthropic to call a tool with that schema.
3. Set tool_choice to force the tool call (the model MUST fill out the
   schema — it can't reply with plain text).
4. Read the tool's input from the response — it's already a parsed dict.

This is more reliable than "prompt the model to return JSON" because the
model is constrained by the schema at decoding time.
"""

import asyncio

from anthropic import AsyncAnthropic

from config import ANTHROPIC_API_KEY, MODEL_PARSE, PARSE_CONCURRENCY


# JSON schema for the parser's output. Anthropic's tool-use machinery
# validates the model's output against this before returning it.
_EXTRACT_TOOL = {
    "name": "extract_brands",
    "description": (
        "Extract every brand or product name mentioned in the assistant's "
        "response, and record the order in which they appeared."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "brands_mentioned": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "All brand or product names mentioned, in the order they "
                    "first appear. De-duplicate so each brand appears at most once."
                ),
            },
            "positions": {
                "type": "object",
                "description": (
                    "Map of brand name → 1-based position in the order of "
                    "appearance. If a brand appears in a numbered list, use "
                    "the list number; otherwise use the order of first mention. "
                    "The first brand mentioned has position 1."
                ),
                "additionalProperties": {"type": "integer"},
            },
            "descriptors": {
                "type": "object",
                "description": (
                    "The 'verbal vibe' for each brand: the descriptive words or "
                    "short phrases the response actually used to characterize it "
                    "(qualities, attributes, use-cases, sentiments). Lowercase, "
                    "1-2 words each, taken only from the text. Shape: map each "
                    "brand name to a list of its descriptors, e.g. "
                    "{\"<brand>\": [\"<descriptor>\", \"<descriptor>\"]}. Only "
                    "include brands actually described; omit ones merely listed. "
                    "Do not invent descriptors that are not in the response."
                ),
                "additionalProperties": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
        },
        "required": ["brands_mentioned", "positions", "descriptors"],
    },
}


_PARSE_SYSTEM_PROMPT = (
    "You are a data extractor. You will receive a shopping recommendation "
    "from an AI assistant. Extract every brand or product name mentioned. "
    "Do not invent brands. Only count names that actually appear in the text."
)


async def _parse_one(
    client: AsyncAnthropic, response_text: str, semaphore: asyncio.Semaphore, attempts: int = 3
) -> dict:
    """
    Run Haiku on one response, return the structured dict.

    Returns: {"brands_mentioned": [...], "positions": {...}, "descriptors": {...}}.
    Retries transient errors (connection drops, rate limits) with backoff;
    returns an empty result only after giving up, never raises.
    """
    empty = {"brands_mentioned": [], "positions": {}, "descriptors": {}}
    if not response_text.strip():
        # If probe.py wrote an empty response (upstream API errored), don't
        # waste an API call trying to parse nothing.
        return empty

    last = None
    for i in range(attempts):
        try:
            async with semaphore:
                response = await client.messages.create(
                    model=MODEL_PARSE,
                    max_tokens=1024,
                    system=_PARSE_SYSTEM_PROMPT,
                    tools=[_EXTRACT_TOOL],
                    # Force the model to call our tool — it cannot reply with text.
                    tool_choice={"type": "tool", "name": "extract_brands"},
                    messages=[{"role": "user", "content": response_text}],
                )
            # Find the tool_use block: one will be type="tool_use" with our
            # extracted data already parsed into a dict.
            for block in response.content:
                if block.type == "tool_use" and block.name == "extract_brands":
                    return block.input
            return empty  # shouldn't happen given tool_choice
        except Exception as exc:
            last = exc
            await asyncio.sleep(1.0 * (i + 1))
    print(f"[parse] gave up after {attempts} tries: {last}")
    return empty


async def parse_all(
    responses: list[tuple[int, str]],
) -> list[tuple[int, list[str], dict[str, int], dict[str, list[str]]]]:
    """
    Parse every (response_id, raw_text) tuple in parallel.

    Returns: list of (response_id, brands_mentioned, positions, descriptors).
    """
    client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    semaphore = asyncio.Semaphore(PARSE_CONCURRENCY)

    async def run_one(response_id: int, text: str):
        result = await _parse_one(client, text, semaphore)
        return (
            response_id,
            result["brands_mentioned"],
            result["positions"],
            result.get("descriptors", {}),
        )

    tasks = [run_one(rid, text) for rid, text in responses]
    return await asyncio.gather(*tasks)
