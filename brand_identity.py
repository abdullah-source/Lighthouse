"""
brand_identity.py - the Brooks solution.

The problem: an LLM names the same brand many ways in one breath.
  "Brooks", "Brooks Running", "Brooks Sports", "Brooks Adrenaline GTS 23"
Naive aggregation counts those as four different brands, so a brand that
should sit at 38 percent mention rate reports at 4 percent, and the brand
shows up as its own competitor. Every downstream number becomes noise.

The fix: collapse every raw mention to a single canonical brand BEFORE we
count anything. This module is the only place that decision lives.

Strategy (in priority order):
  1. Learned aliases (from the DB) win. They accumulate over time.
  2. Known-brand prefix match, longest brand first, word-boundary aware.
     "Brooks Adrenaline GTS 23" -> "Brooks", "New Balance 990" -> "New Balance".
  3. Corporate-suffix strip. "Brooks Running" -> "Brooks".
  4. Fallback: a cleaned head form, recorded as its own canonical.

No LLM call here. It is deterministic, testable, and fast.
"""

from __future__ import annotations

import re

# Seed list of canonical brands. Footwear-heavy because that is our first
# category, but extensible: any brand we see becomes part of the working set,
# and the alias table in the DB makes the mapping permanent.
SEED_BRANDS: list[str] = [
    "Allbirds", "Nike", "Adidas", "ASICS", "Brooks", "Hoka", "New Balance",
    "Saucony", "Veja", "Rothy's", "Cariuma", "Vivobarefoot", "On", "Reebok",
    "Puma", "Converse", "Vans", "Salomon", "Merrell", "Skechers", "Birkenstock",
    "Timberland", "Clarks", "Dr. Martens", "Crocs", "Under Armour", "Mizuno",
    "Altra", "Topo Athletic", "Xero Shoes", "Tracksmith", "Atoms", "Thousand Fell",
    # general consumer brands for other categories
    "Glossier", "Olipop", "Necessaire", "Sephora", "Amazon",
]

# Tokens that are company decoration, not part of the brand identity.
CORPORATE_SUFFIXES = {
    "running", "sports", "sport", "footwear", "shoes", "shoe", "inc", "inc.",
    "llc", "co", "co.", "company", "brand", "brands", "group", "the",
    "athletics", "athletic", "apparel", "international", "ltd",
}

_WS = re.compile(r"\s+")
_PUNCT_EDGE = re.compile(r"^[^\w]+|[^\w]+$")


def _clean(raw: str) -> str:
    """Trim, collapse whitespace, drop edge punctuation."""
    s = _WS.sub(" ", raw.strip())
    s = _PUNCT_EDGE.sub("", s)
    return s


def _norm_key(s: str) -> str:
    """Lowercase comparison key with punctuation flattened."""
    return _WS.sub(" ", re.sub(r"[^\w\s]", "", s.lower())).strip()


def _strip_corporate_suffix(s: str) -> str:
    """Drop trailing corporate words: 'Brooks Running' -> 'Brooks'."""
    parts = s.split()
    while len(parts) > 1 and parts[-1].lower().strip(".") in CORPORATE_SUFFIXES:
        parts.pop()
    return " ".join(parts)


class BrandResolver:
    """
    Resolves raw brand strings to canonical brands.

    Build it once per aggregation with the known brands (seed + focal brand +
    anything already learned) and an optional alias map loaded from the DB.
    """

    def __init__(
        self,
        known_brands: list[str] | None = None,
        aliases: dict[str, str] | None = None,
    ) -> None:
        # Canonical display names, keyed by their normalized form.
        # SEED brands register FIRST so their clean display form wins. If the
        # user types "ON" but the seed is "On", we keep "On" as the single
        # canonical, so the focal brand and its mentions resolve identically.
        # (Without this, focal "ON" != mention-resolved "On" and the brand is
        # silently undercounted - the On / Swiss-brands bug.)
        self._canon_by_key: dict[str, str] = {}
        for b in SEED_BRANDS + (known_brands or []):
            self.register(b)
        # Learned aliases: normalized alias -> canonical display name.
        self._aliases: dict[str, str] = {}
        for alias, canon in (aliases or {}).items():
            self._aliases[_norm_key(alias)] = canon
        # Longest brand first so "New Balance" beats "New".
        self._refresh_order()

    def register(self, brand: str) -> None:
        b = _clean(brand)
        if not b:
            return
        key = _norm_key(b)
        if key and key not in self._canon_by_key:
            self._canon_by_key[key] = b

    def _refresh_order(self) -> None:
        self._ordered_keys = sorted(
            self._canon_by_key.keys(), key=lambda k: len(k.split()), reverse=True
        )

    def canonicalize(self, raw: str) -> str:
        """Map one raw brand mention to its canonical brand."""
        cleaned = _clean(raw)
        if not cleaned:
            return ""
        key = _norm_key(cleaned)

        # 1. Learned alias wins.
        if key in self._aliases:
            return self._aliases[key]

        # 2. Exact known brand.
        if key in self._canon_by_key:
            return self._canon_by_key[key]

        # 3. Known-brand prefix match (longest first, word-boundary aware).
        for bk in self._ordered_keys:
            if key == bk or key.startswith(bk + " "):
                return self._canon_by_key[bk]

        # 4. Corporate-suffix strip, then re-check known brands.
        stripped = _strip_corporate_suffix(cleaned)
        skey = _norm_key(stripped)
        if skey and skey != key:
            if skey in self._canon_by_key:
                return self._canon_by_key[skey]
            for bk in self._ordered_keys:
                if skey == bk or skey.startswith(bk + " "):
                    return self._canon_by_key[bk]

        # 5. Fallback: keep the stripped head form, and learn it so future
        #    variants of the same brand collapse to it.
        canon = stripped or cleaned
        self.register(canon)
        self._refresh_order()
        return canon


def canonicalize_list(
    raws: list[str],
    known_brands: list[str] | None = None,
    aliases: dict[str, str] | None = None,
) -> tuple[list[str], dict[str, str]]:
    """
    Convenience: canonicalize a list of raw mentions, de-duplicated in order.

    Returns (canonical_brands_in_order, raw_to_canonical_map).
    """
    resolver = BrandResolver(known_brands=known_brands, aliases=aliases)
    mapping: dict[str, str] = {}
    out: list[str] = []
    seen: set[str] = set()
    for raw in raws:
        canon = resolver.canonicalize(raw)
        mapping[raw] = canon
        if canon and canon not in seen:
            seen.add(canon)
            out.append(canon)
    return out, mapping


# Manual smoke test: python brand_identity.py
if __name__ == "__main__":
    samples = [
        "Brooks", "Brooks Running", "Brooks Sports", "Brooks Adrenaline GTS 23",
        "Hoka Bondi 8", "ASICS Gel-Kayano 30", "New Balance 990v6",
        "Allbirds Wool Runners", "Veja", "some-unknown-brand X1",
    ]
    r = BrandResolver(known_brands=["Allbirds"])
    for s in samples:
        print(f"{s!r:35} -> {r.canonicalize(s)!r}")
