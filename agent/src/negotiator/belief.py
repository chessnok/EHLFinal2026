"""A live estimate of the supplier's floor, recomputed after every reply.

The floor is kept as a *value to the supplier* (the arena's `supplier_value`: the price at its own standard
terms that pays it the same - payment timing, freight leg, tooling and chargebacks included), not as a
price, so one number covers every structure. From a floor value V the best package we can reach is exact:
for each structure of the case the lowest price that still gives the supplier V, priced in our C.

Evidence, in the order it arrives:
  prior           the data's estimate before the first move (ground truth: should-cost, case type)
  every offer     its floor is no higher than the value of any sheet it puts on the table
  alternatives    two sheets that differ in payment days only reveal what money is worth to it
  last words      a final offer or "cannot go below EUR X" pins the floor at that value
  its path        bots concede in shrinking steps (half the step, then less): extrapolating the steps
                  gives where it will stop
Recomputing is cheap (a few hundred cost evaluations), so it runs after every reply, well inside 60 s.
"""

import math
import re

from arena_kit.cost import complete_offer, supplier_value

from negotiator.menu import combos

FLOOR_SAID = re.compile(
    r"(?:cannot|can't|unable to) (?:drop|go|reduce|lower)[^.€]{0,40}?(?:below|under|beneath)"
    r"\s*(?:€|EUR)?\s?(\d[\d,]*\.?\d*)"
    r"|(?:stuck|maxed out|limit) at\s*(?:€|EUR)?\s?(\d[\d,]*\.?\d*)",
    re.I,
)
RATE_MIN, RATE_MAX = 0.02, 0.30  # a plausible yearly cost of money for a supplier


class FloorBelief:
    def __init__(self, case: dict, opening: dict, standard: dict, prior_price: float | None, rate: float) -> None:
        b = case["buyer"]
        freight = b.get("freight_eur_per_unit") or {}
        self.case = case
        self.standard = {
            "payment_days": b.get("reference_payment_days", 60),
            "incoterm": case.get("fixed_terms", {}).get("incoterm")
            or (min(freight, key=freight.get) if freight else "FCA"),
            **{k: v for k, v in opening.items() if k != "unit_price"},
            **(standard or {}),
        }
        self.rate = rate
        self.ppm: float | None = None  # its real defect rate (scorecard), when known
        self.capped = False  # cap the extrapolation (ratio <= 0.6, not under 90 % of its lowest offer value)
        self.structures = [complete_offer(case, {**opening, **c}) for c in combos(case)]
        self.v_open = self.value(opening)
        self.v_hi = self.v_open  # its floor is no higher than any offer it made
        self.v_prior = self.value({**opening, "unit_price": prior_price}) if prior_price else self.v_open * 0.9
        self.v_est = min(self.v_prior, self.v_hi)
        self.path = [self.v_open]
        self.pinned = False
        self.notes: list[str] = []

    # ------------------------------------------------------------------ the supplier's view
    def value(self, terms: dict) -> float:
        if terms.get("unit_price") is None:
            return math.inf
        sup = {"standard": self.standard, "interest_rate": self.rate}
        if self.ppm is not None:
            sup["ppm"] = self.ppm  # the defect rate it really has: a chargeback costs it that much per unit
        return supplier_value(self.case, terms, sup)

    def price_for(self, structure: dict, v: float) -> float:
        """The price at which this structure gives the supplier exactly the value v (value is linear in price)."""
        a = self.value({**structure, "unit_price": 1.0})
        b = self.value({**structure, "unit_price": 2.0})
        slope = b - a
        return (v - (a - slope)) / slope if slope > 0 else math.inf

    # ------------------------------------------------------------------ evidence
    def observe(self, reply: dict) -> None:
        sheets = [s["terms"] for s in reply.get("term_sheets") or [] if s.get("terms", {}).get("unit_price")]
        self._learn_rate(sheets)
        if sheets:
            v = min(self.value(s) for s in sheets)
            self.path.append(v)
            self.v_hi = min(self.v_hi, v)
        said = self._floor_said(reply.get("body") or "", sheets)
        if said is not None:
            self.v_hi = min(self.v_hi, said)
            self.pinned = True
            self.notes.append(f"floor said: {said:.2f}")
        if reply.get("status") == "final_offer":
            self.pinned = True
        self._update_estimate()

    def _learn_rate(self, sheets: list[dict]) -> None:
        """Two sheets that differ in payment days only: the price gap is what that money is worth to it."""
        for i, s1 in enumerate(sheets):
            for s2 in sheets[i + 1 :]:
                diff = {k for k in set(s1) | set(s2) if k != "unit_price" and s1.get(k) != s2.get(k)}
                if diff != {"payment_days"}:
                    continue
                d1, d2 = s1.get("payment_days"), s2.get("payment_days")
                if not d1 or not d2 or d1 == d2:
                    continue
                long_, short = (s1, s2) if d1 > d2 else (s2, s1)
                gap = long_["unit_price"] - short["unit_price"]
                days = abs(d1 - d2)
                if gap > 0:
                    rate = gap / short["unit_price"] * 360 / days
                    self.rate = min(RATE_MAX, max(RATE_MIN, rate))
                    self.notes.append(f"rate from alternatives: {self.rate:.3f}")

    def _floor_said(self, body: str, sheets: list[dict]) -> float | None:
        if not sheets:
            return None
        for m in FLOOR_SAID.finditer(body):
            raw = m.group(1) or m.group(2)
            try:
                price = float(raw.replace(",", ""))
            except ValueError:
                continue
            ref = min(sheets, key=lambda s: abs(s["unit_price"] - price))
            return self.value({**ref, "unit_price": price})
        return None

    def _update_estimate(self) -> None:
        if self.pinned:  # its last word: the floor is where it stands
            self.v_est = self.v_hi
            return
        p = self.path
        extrap = None
        if len(p) >= 2 and p[-2] - p[-1] <= 0.005 * p[-2]:
            # no move in value - a lower price paid for by our concessions (P18: 6.10 -> 5.60 for 90 days, 24
            # months and a clause was the same value to it): it stands at, or near, its floor
            extrap = p[-1]
        elif len(p) >= 3:
            d1, d2 = p[-3] - p[-2], p[-2] - p[-1]
            if d1 > 0 and 0 < d2 < d1:
                r = min(d2 / d1, 0.6) if self.capped else d2 / d1
                extrap = p[-1] - d2 * r / (1 - r)  # the steps shrink geometrically: sum what is left
            elif d1 > 0 and d2 <= 0:
                extrap = p[-1]  # it stopped
        elif len(p) == 2 and p[0] > p[1]:
            # bots move most in round 1 (67 % of all their movement), then about 0.4 of that step more
            extrap = p[1] - 0.4 * (p[0] - p[1])
        if extrap is None:
            self.v_est = min(self.v_est, self.v_hi)
            return
        if self.capped:
            extrap = max(extrap, 0.9 * self.v_hi)  # two equal steps must not blow the estimate up (P01: 131 -> 113)
        weight = 0.6 if len(p) == 2 else 0.85  # its own moves outweigh our prior quickly (prior: data before round 1)
        self.v_est = min(self.v_hi, weight * extrap + (1 - weight) * self.v_prior)

    # ------------------------------------------------------------------ what it means for us
    def best_package(self, cost, keeps, v: float | None = None, allow=None) -> tuple[float, dict | None]:
        """The cheapest package (in our C) that gives the supplier at least v (default: our estimate), among the
        structures it would sign (`allow`: e.g. only with the index clause it insists on - a clause is no cash
        to it, so its value does not see it, but its refusals do)."""
        v = self.v_est if v is None else v
        best, best_terms = math.inf, None
        pool = [st for st in self.structures if allow is None or allow(st)] or self.structures
        for st in pool:
            price = self.price_for(st, v)
            if not math.isfinite(price) or price <= 0:
                continue
            terms = complete_offer(self.case, {**st, "unit_price": round(price + 0.005, 2)})
            if not keeps(terms):
                continue
            c = cost(terms)
            if c < best:
                best, best_terms = c, terms
        return best, best_terms

    def summary(self) -> dict:
        return {
            "v_open": round(self.v_open, 2),
            "v_prior": round(self.v_prior, 2),
            "v_est": round(self.v_est, 2),
            "v_hi": round(self.v_hi, 2),
            "rate": round(self.rate, 3),
            "pinned": self.pinned,
            "notes": self.notes[-3:],
        }
