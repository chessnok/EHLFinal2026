"""The full menu: every combination of the case's term options, priced to cost us the same C.

At equal C the structures differ only in what they give the supplier, so we can pick by acceptance:
  - the supplier's explicit requests, read from its e-mails ("which volume can you commit to?",
    "we cannot accept a fixed price for extended contract durations" -> an index clause);
  - closeness to the structure it proposed itself (it tells us what it likes by what it offers);
  - the price it gets (at equal C, the structure that costs us least leaves it the highest price).
Cases have 20-60 combinations, a few hundred at most: all of them fit easily in the time per move.
"""

import itertools
import re

from arena_kit.cost import complete_offer

MAX_COMBOS = 3000

# what a supplier asks for in its own words -> the lever that answers it
REQUESTS = {
    "index_clause": re.compile(
        r"index clause|price adjustment clause|surcharge clause|cannot accept a fixed price|fixed price for "
        r"(?:extended|longer)|material (?:price )?(?:risk|volatil)|costs? remain volatile|alloy surcharge",
        re.I,
    ),
    "contract_months": re.compile(
        r"longer[- ]term|long-term|multi-year|\b(?:24|36)[- ]month|extended contract|longer contract|contract "
        r"duration|firm, long",
        re.I,
    ),
    "volume_per_year": re.compile(
        r"volume commitment|commit to (?:a )?(?:higher )?volume|which volume|binding (?:higher )?volume|higher volume",
        re.I,
    ),
    "payment_days": re.compile(
        r"faster payment|pay(?:ing)? (?:us )?earlier|earlier payment|payment within|shorter payment|cash ?flow|"
        r"pay our invoices",
        re.I,
    ),
}


def requests_in(text: str) -> set[str]:
    return {lever for lever, pattern in REQUESTS.items() if pattern.search(text or "")}


def combos(case: dict) -> list[dict]:
    """Every combination of the negotiable non-price fields' options (capped)."""
    options = case.get("term_options", {})
    fields = [f for f in case["negotiable"] if f != "unit_price" and options.get(f)]
    values = [options[f] for f in fields]
    out = []
    for combo in itertools.product(*values):
        out.append(dict(zip(fields, combo, strict=True)))
        if len(out) >= MAX_COMBOS:
            break
    return out or [{}]


def satisfies(case: dict, terms: dict, theirs: dict, lever: str) -> bool:
    """Does this structure answer the supplier's request for `lever`?"""
    if lever not in case["negotiable"]:
        return False
    if lever == "index_clause":
        return terms.get("index_clause") is not None
    if lever == "payment_days":
        return terms.get("payment_days", 999) <= theirs.get("payment_days", 999)
    if lever in ("contract_months", "volume_per_year"):
        options = [o for o in case.get("term_options", {}).get(lever, []) if o is not None]
        floor = max(theirs.get(lever) or 0, min(options) if options else 0)
        return (terms.get(lever) or 0) >= floor and (terms.get(lever) or 0) > (min(options) if options else 0)
    return False


def acceptance(case: dict, terms: dict, theirs: dict, requests: set[str]) -> tuple:
    """How readily the supplier takes this structure: requests answered, then likeness to its own."""
    answered = sum(satisfies(case, terms, theirs, r) for r in requests)
    alike = sum(1 for f, v in terms.items() if f != "unit_price" and theirs.get(f) == v)
    return answered, alike


def structure_key(terms: dict) -> str:
    return repr(sorted((k, v) for k, v in terms.items() if k != "unit_price"))


def priced_menu(case: dict, theirs: dict, price_for) -> list[dict]:
    """Every structure, completed and priced by `price_for(terms) -> price` (e.g. iso-C to our ask)."""
    out = []
    for combo in combos(case):
        terms = complete_offer(case, {**theirs, **combo})
        price = price_for(terms)
        if price and price > 0:
            out.append(complete_offer(case, {**terms, "unit_price": round(price, 2)}))
    return out
