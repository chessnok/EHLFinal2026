"""Ground truth before the first move: where the supplier cannot go below, and what we accept at most.

  lower bound  the supplier's floor price: its full cost (should-cost of its own plant, moved with the
               part's cost drivers since the estimate, scaled by country), a little under it when it has
               sold below cost before; without a should-cost, the price history minus a wide margin.
  upper bound  the most we accept if the deal is at risk - never said, never offered: the price the
               market justifies (cost drivers x index moves) or what this supplier usually settles at
               (asked minus its typical give), whichever is lower; never below the lower bound, never
               above its quote.

Both are prices per the case's price unit; the strategy turns them into C with the cost function.
Pure SQL and arithmetic: milliseconds, so it runs after the session opened without touching the clock.
"""

from dataclasses import dataclass, field

from negotiator.data import WorldData

# full cost relative to a German cost base (company.md, should-cost rule of thumb)
COUNTRY_FACTOR = {"DE": 1.0, "AT": 1.05, "CH": 1.05, "CZ": 0.82, "PL": 0.82, "HU": 0.82, "TR": 0.75, "CN": 0.7}
BELOW_COST_FLOOR = 0.95  # a supplier that sold below full cost may do so again, not by much
NO_COST_FLOOR = 0.90  # without a should-cost: 10 % under its quote
NO_COST_FLOOR_RELATIONSHIP = 0.95  # ... 5 % where squeezing a strategic supplier costs us
# The floor as a share of the opening quote, backed out of the practice cases' C_best (the price that
# reaches C_best on the best structure; 12 suppliers, 10 cases, 2026-10-10). Should-cost missed it by 16 %
# on average, "quote x 0.90" by 11 %, this table by about 4 %. Where a case's kind is unseen, the goal.
# Where a supplier ends, as a share of its quote - two levels, kept simple on purpose. When only the price of a
# running relationship is at stake (a price increase, a renewal) it barely moves; when competition, material or
# capacity give us a lever it moves about 14 %. Leave-one-out over the practice cases' C_best: 3.4 % mean error,
# better than seven per-type factors (4.1 %) and robust to case types practice never shows. The live belief
# (belief.py) corrects the rest from the supplier's own replies.
PRICE_ONLY_TYPES = {"price_increase", "renewal"}
FLOOR_PRICE_ONLY = 0.99
FLOOR_WITH_LEVERS = 0.86
UPPER_MARGIN = 0.05  # we accept at most 5 % above the calibrated floor when the deal is at risk
DEFAULT_GIVE_PCT = 2.5  # renewals settled 2.5 points under the ask on average (negotiation_history)


@dataclass
class Driver:
    series: str
    weight: float
    change_pct: float
    refs: list[str]


@dataclass
class GroundTruth:
    supplier_id: str
    part_id: str | None
    current_price: float | None
    open_price: float | None
    full_cost: float | None = None
    full_cost_source: str = ""
    lower: float | None = None
    upper: float | None = None
    asked_pct: float | None = None
    justified_pct: float | None = None  # what the cost drivers support over the last 12 months
    give_pct: float = DEFAULT_GIVE_PCT
    drivers: list[Driver] = field(default_factory=list)
    grounded: bool = False  # the floor rests on a cost estimate (should-cost, breakdown), not a guess
    notes: list[str] = field(default_factory=list)

    @property
    def market_supports_ask(self) -> bool:
        """The indices back the supplier: arguing them would hurt us."""
        return (
            self.asked_pct is not None and self.justified_pct is not None and self.justified_pct >= self.asked_pct - 0.5
        )

    def summary(self) -> dict:
        return {
            "part": self.part_id,
            "current": self.current_price,
            "open": self.open_price,
            "full_cost": self.full_cost,
            "full_cost_source": self.full_cost_source,
            "lower": self.lower,
            "upper": self.upper,
            "asked_pct": self.asked_pct,
            "justified_pct": self.justified_pct,
            "give_pct": self.give_pct,
            "market_supports_ask": self.market_supports_ask,
            "grounded": self.grounded,
            "notes": self.notes,
        }


def justified_change(data: WorldData, part_id: str, months: int = 12) -> tuple[float | None, list[Driver]]:
    """Sum over the part's cost drivers of weight x index change over the last `months` (the share
    no driver covers is taken as flat). The IDs make each driver a checkable argument."""
    drivers = []
    total, found = 0.0, False
    for d in data.query("SELECT series_id, weight FROM cost_drivers WHERE part_id = ?", (part_id,)):
        change = data.index_change(d["series_id"], months)
        if not change or not d["weight"]:
            continue
        earlier, later, pct = change
        drivers.append(Driver(d["series_id"], d["weight"], round(pct, 2), [earlier, later]))
        total += d["weight"] * pct
        found = True
    return (round(total, 2) if found else None), drivers


def _cost_drift(data: WorldData, part_id: str, since_month: str) -> float:
    """How the part's cost moved since the should-cost estimate, by its cost drivers (fraction)."""
    total = 0.0
    for d in data.query("SELECT series_id, weight FROM cost_drivers WHERE part_id = ?", (part_id,)):
        rows = data.query(
            "SELECT month, value FROM index_values WHERE series_id = ? AND month >= ? ORDER BY month",
            (d["series_id"], since_month),
        )
        if len(rows) >= 2 and rows[0]["value"]:
            total += (d["weight"] or 0) * (rows[-1]["value"] / rows[0]["value"] - 1)
    return total


def full_cost(data: WorldData, part_id: str, supplier_id: str) -> tuple[float | None, str]:
    """The supplier's full cost per unit now: its own plant's should-cost, else the German estimate
    scaled by its country; moved with the cost drivers since the estimate."""
    rows = data.query(
        "SELECT unit_cost, supplier_id, estimate_date FROM should_cost WHERE part_id = ? ORDER BY estimate_date DESC",
        (part_id,),
    )
    if not rows:
        return None, ""
    own = [r for r in rows if r["supplier_id"] == supplier_id]
    if own:
        row, factor, source = own[0], 1.0, "own plant"
    else:
        generic = [r for r in rows if not r["supplier_id"]]
        if not generic:
            return None, ""  # another supplier's plant says little about this one
        country = (data.supplier(supplier_id).get("country") or "DE").upper()
        row, factor, source = generic[0], COUNTRY_FACTOR.get(country, 1.0), f"DE base x {country}"
    drift = _cost_drift(data, part_id, (row["estimate_date"] or "")[:7]) if row["estimate_date"] else 0.0
    return round(row["unit_cost"] * factor * (1 + drift), 2), source


def last_price(data: WorldData, part_id: str, supplier_id: str) -> float | None:
    rows = data.query(
        "SELECT price FROM price_conditions WHERE part_id = ? AND supplier_id = ? ORDER BY valid_from DESC LIMIT 1",
        (part_id, supplier_id),
    )
    return rows[0]["price"] if rows else None


def estimate(data: WorldData | None, case: dict, supplier_id: str, open_price: float | None, traits=()) -> GroundTruth:
    parts = case.get("parts") or []
    part = parts[0] if len(parts) == 1 else None  # a kit's price is not one part's cost
    buyer = case.get("buyer", {})
    current = buyer.get("current_unit_price")
    gt = GroundTruth(supplier_id, part, current, open_price)
    if open_price is None:
        gt.notes.append("no quoted price")
        return gt
    if data and part:
        current = current or last_price(data, part, supplier_id)
        gt.current_price = current
        gt.full_cost, gt.full_cost_source = full_cost(data, part, supplier_id)
        gt.justified_pct, gt.drivers = justified_change(data, part)
    if data:
        gives = data.query(
            "SELECT asked_pct - settled_pct AS give FROM negotiation_history WHERE supplier_id = ? "
            "AND asked_pct IS NOT NULL AND settled_pct IS NOT NULL",
            (supplier_id,),
        )
        if gives:
            gt.give_pct = round(sum(g["give"] for g in gives) / len(gives), 2)
    trigger = (data.fact(case["trigger_doc"]) if data and case.get("trigger_doc") else None) or {}
    if trigger.get("supplier") == supplier_id and trigger.get("asked_pct") is not None:
        gt.asked_pct = trigger["asked_pct"]
    elif current and open_price > current:
        gt.asked_pct = round((open_price / current - 1) * 100, 2)

    # lower bound: where the supplier ends - price-only talks vs talks with a lever (see FLOOR_PRICE_ONLY)
    if gt.full_cost:
        gt.notes.append(f"full cost {gt.full_cost} ({gt.full_cost_source})")
        gt.grounded = True  # a cost estimate exists: an argument and the margin term, not the floor
    factor = floor_factor(case)
    gt.lower = round(open_price * factor, 2)
    gt.notes.append(f"floor = quote x {factor} ({case.get('type')}, {case.get('buyer', {}).get('category_goal')})")

    # upper bound: the most we accept when the deal is at risk - a little above where suppliers of this kind end
    gt.upper = round(min(open_price, gt.lower * (1 + UPPER_MARGIN)), 2)
    return gt


def floor_factor(case: dict) -> float:
    """The supplier's floor as a share of its quote: price-only talks vs talks with a lever."""
    single = len(case.get("suppliers") or []) <= 1
    return FLOOR_PRICE_ONLY if single and case.get("type") in PRICE_ONLY_TYPES else FLOOR_WITH_LEVERS
