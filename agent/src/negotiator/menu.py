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
    "ppm_commitment": re.compile(r"quality commitment|\bppm\b|defect rate", re.I),
    "chargeback_eur_per_complaint": re.compile(r"chargeback|per complaint", re.I),
    "lead_time_days": re.compile(r"lead ?time|lieferzeit|deliver in", re.I),
    "incoterm": re.compile(r"incoterm|\b(?:EXW|FCA|DAP)\b|freight", re.I),
    "effective_date": re.compile(r"effective (?:date|from)|valid from|starting (?:on|from)|start(?:ing)? date", re.I),
    "tooling_eur": re.compile(r"tooling", re.I),
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


def proposed_values(case: dict, sheets: list[dict]) -> dict[str, list]:
    """The values the supplier itself put on its sheets (its offer and its alternatives), per negotiable field:
    what it names is what it is willing to trade on."""
    out: dict[str, list] = {}
    for sheet in sheets:
        for f, v in (sheet.get("terms") or {}).items():
            if f != "unit_price" and f in case["negotiable"] and v not in out.setdefault(f, []):
                out[f].append(v)
    return out


def satisfies(case: dict, terms: dict, theirs: dict, lever: str, proposed: dict | None = None) -> bool:
    """Does this structure answer the supplier's request for `lever`? Only negotiable fields count; where the
    supplier named values itself, meeting one of them answers it."""
    if lever not in case["negotiable"]:
        return False
    if proposed and proposed.get(lever) and lever not in ("index_clause",):
        return terms.get(lever) in proposed[lever]
    if lever == "index_clause":
        return terms.get("index_clause") is not None
    if lever == "payment_days":
        return terms.get("payment_days", 999) <= theirs.get("payment_days", 999)
    if lever in ("contract_months", "volume_per_year"):
        options = [o for o in case.get("term_options", {}).get(lever, []) if o is not None]
        floor = max(theirs.get(lever) or 0, min(options) if options else 0)
        return (terms.get(lever) or 0) >= floor and (terms.get(lever) or 0) > (min(options) if options else 0)
    return lever in theirs and terms.get(lever) == theirs.get(lever)  # its own value on that lever


def acceptance(case: dict, terms: dict, theirs: dict, requests: set[str], proposed: dict | None = None) -> tuple:
    """How readily the supplier takes this structure: requests answered, then likeness to its own."""
    answered = sum(satisfies(case, terms, theirs, r, proposed) for r in requests)
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
