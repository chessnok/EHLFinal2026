"""How a simulated supplier prices a term structure.

A supplier holds one number per round: V, the price it wants on its own opening structure. Any other
structure costs V times a factor - a rate per term (payment days, lead time, effective date, contract
length, index clause, quality commitment, volume) - plus the freight leg it carries. The rates are fitted
from the alternatives the arena's suppliers quote in one e-mail ("alternatively, with 14 days net: EUR ..."):
two prices at the same V.
"""

import math
from datetime import date

from arena_kit.cost import closing_terms

# one rate per feature; a feature is the distance of a structure from the supplier's opening structure
FEATURES = ("pay", "lead", "eff", "con", "idx", "deadband", "ppm", "chargeback", "vol")


def _months(later: str | None, earlier: str | None) -> float:
    try:
        return (date.fromisoformat(later) - date.fromisoformat(earlier)).days / 30.4
    except (TypeError, ValueError):
        return 0.0


def features(case: dict, terms: dict, ref: dict) -> dict[str, float]:
    """The structure `terms` against the supplier's opening structure `ref` (both closed with its standard terms)."""
    t = closing_terms(case, terms, ref)

    def num(src, field):
        return float(src.get(field) or 0)

    clause, ref_clause = t.get("index_clause") or {}, ref.get("index_clause") or {}
    return {
        "pay": (num(t, "payment_days") - num(ref, "payment_days")) / 360,
        "lead": (num(ref, "lead_time_days") - num(t, "lead_time_days")) / 30,  # faster than its opening
        "eff": _months(t.get("effective_date"), ref.get("effective_date")),
        "con": (num(t, "contract_months") - num(ref, "contract_months")) / 12,
        "idx": float(bool(clause)) - float(bool(ref_clause)),
        "deadband": ((clause.get("deadband_pct") or 0) - (ref_clause.get("deadband_pct") or 0)) / 100,
        "ppm": (num(ref, "ppm_commitment") - num(t, "ppm_commitment")) / 1000,  # tighter than its opening
        "chargeback": (num(t, "chargeback_eur_per_complaint") - num(ref, "chargeback_eur_per_complaint")) / 1000,
        "vol": (num(t, "volume_per_year") / num(ref, "volume_per_year") - 1) if num(ref, "volume_per_year") else 0.0,
    }


def factor(rates: dict[str, float], x: dict[str, float]) -> float:
    return math.exp(sum(rates.get(f, 0.0) * x[f] for f in FEATURES))


def freight_leg(case: dict, terms: dict, ref: dict) -> float:
    """EUR per unit the supplier carries more than on its opening Incoterm."""
    freight = case["buyer"]["freight_eur_per_unit"]
    t = closing_terms(case, terms, ref)
    return freight.get(ref.get("incoterm"), 0.0) - freight.get(t.get("incoterm"), 0.0)


def price_for(case: dict, rates: dict, ref: dict, value: float, terms: dict) -> float:
    """The unit price that is worth `value` (on the opening structure) on the structure `terms`."""
    return value * factor(rates, features(case, terms, ref)) + freight_leg(case, terms, ref)


def value_of(case: dict, rates: dict, ref: dict, terms: dict) -> float:
    """The opening-structure price a term sheet is worth to the supplier."""
    return (terms["unit_price"] - freight_leg(case, terms, ref)) / factor(rates, features(case, terms, ref))


def solve(a: list[list[float]], b: list[float]) -> list[float]:
    """Gaussian elimination with partial pivoting, for the small ridge systems of the fit."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(m[r][col]))
        m[col], m[pivot] = m[pivot], m[col]
        if abs(m[col][col]) < 1e-12:
            continue
        for r in range(n):
            if r != col:
                k = m[r][col] / m[col][col]
                m[r] = [v - k * w for v, w in zip(m[r], m[col], strict=True)]
    return [m[i][n] / m[i][i] if abs(m[i][i]) > 1e-12 else 0.0 for i in range(n)]


def fit_rates(pairs: list[tuple[dict, float, dict, float]], prior: dict[str, float], ridge: float) -> dict[str, float]:
    """Rates from pairs (x1, P1, x2, P2) of two prices at one V, freight removed: ln(P2 / P1) = r.(x2 - x1).
    Ridge towards `prior`, so a supplier with one alternative keeps the pooled rates for the other terms; a
    term no pair varies keeps the prior (0 in the pool: the simulator then does not price it)."""
    n = len(FEATURES)
    a = [[ridge if i == j else 0.0 for j in range(n)] for i in range(n)]
    b = [ridge * prior.get(f, 0.0) for f in FEATURES]
    for x1, p1, x2, p2 in pairs:
        row, target = [x2[f] - x1[f] for f in FEATURES], math.log(p2 / p1)
        for i in range(n):
            b[i] += row[i] * target
            for j in range(n):
                a[i][j] += row[i] * row[j]
    return {f: round(v, 5) for f, v in zip(FEATURES, solve(a, b), strict=True)}
