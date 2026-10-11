"""Per case: the supplier's plan - its policy, cost estimate, floor, first ask and bounds."""

import math

from arena_kit.cost import RELATIONSHIP_GOALS, complete_offer, total_cost

from negotiator.belief import FloorBelief
from negotiator.groundtruth import GroundTruth, estimate
from negotiator.ledger import data_facts
from negotiator.profile import SupplierProfile, build_profile
from negotiator.session import Negotiation
from negotiator.strategy.tactical.plan import (
    ANCHOR_DATA_EXTRA,
    ANCHOR_PRICE_ONLY,
    ANCHOR_RELATIONSHIP,
    ANCHOR_ROUTINE,
    ANCHOR_WITH_LEVERS,
    CASH_SHORT_RATE,
    DEFAULT_POLICY,
    POLICIES,
    SHOULD_COST_SHARE,
    UNDER_FLOOR,
    UPPER_ROOM,
    Plan,
    Policy,
    _k,
)
from negotiator.telemetry import log


class PlanningMixin:
    def prepare(self, neg: Negotiation) -> None:
        if neg.data is not None:
            self.data = neg.data  # the session's view for this case: its own facts (WorldData.with_case)
        # what belongs to one case starts empty, also when the object is reused for the next one
        self.tplans, self.banned_case_kinds = {}, set()
        self.used_refs, self.used_rival_refs = set(), set()
        buyer = neg.buyer
        goal = buyer.get("category_goal", "routine")
        parts = neg.case.get("parts") or []
        current = buyer.get("current_unit_price")
        for sid, thread in neg.threads.items():
            _, terms = thread.standing
            profile = build_profile(self.data, sid, neg.case)
            policy = self._policy(goal, profile)
            full_cost = self._full_cost(parts, sid)
            cost_source = "own plant" if full_cost else ""
            if full_cost and goal in RELATIONSHIP_GOALS:
                full_cost = round(full_cost * SHOULD_COST_SHARE, 2)  # one cost for the charge and the floor
            guess = None
            if not full_cost and goal in RELATIONSHIP_GOALS:
                guessed, cost_source = self._fallback_full_cost(neg, sid)
                guess = self._supplier_estimate(neg, sid, guessed, profile) if guessed else None
            self._estimate_supplier(neg, sid, full_cost, profile)
            floor = self._floor(neg, full_cost, policy)
            open_c = neg.cost(sid, terms)
            gt = estimate(self.data, neg.case, sid, terms.get("unit_price"), tuple(profile.traits))
            if gt.lower and goal not in RELATIONSHIP_GOALS:
                floor = gt.lower  # one floor: the ground truth's (it knows below-cost sellers and countries)
            target_c = self._target_c(neg, sid, terms, policy, profile, floor, current, gt)
            plan = Plan(sid, self._name(sid), policy, profile, open_c, target_c, floor, full_cost, gt)
            plan.guess = guess
            plan.lower_c, plan.upper_c = self._bounds_c(neg, sid, terms, gt, target_c, open_c)
            if terms.get("unit_price") is not None:
                rate = buyer.get("interest_rate", 0.08) * (CASH_SHORT_RATE if profile.has("cash_short") else 1)
                plan.belief = FloorBelief(neg.case, terms, thread.standard_terms, gt.lower, rate)
                plan.belief.ppm = profile.ppm  # scorecard ppm: what a chargeback really costs it
            plan.evidence = self._evidence(neg, sid, terms.get("unit_price"), current) if terms else []
            body = thread.latest.get("body") or ""
            clauses = [o for o in neg.case.get("term_options", {}).get("index_clause") or [] if o]
            if (
                "index_clause" in neg.case["negotiable"]
                and any(o.get("series") in body for o in clauses)
                and goal in RELATIONSHIP_GOALS
            ):
                # it argues its price with the very index a clause would follow: the clause answers it. P02's
                # supplier dropped its price by 15-22 for one and never went under 372.96 without (P-13, P-15, P-19).
                # Only with a strategic goal: in leverage the clause options of round 1 cost P08 0.066 and P18 0.067
                plan.requests.add("index_clause")
            if profile.has("hedged"):
                plan.banned_kinds.add("index")  # "not our reality" until its hedge runs out
            if gt.market_supports_ask:
                plan.banned_kinds.add("index")  # the indices back its ask: citing them helps it, not us
            self.tplans[sid] = plan
            neg.recorder.event(
                "plan",
                session_id=neg.session_id,
                case_id=neg.case_id,
                supplier_id=sid,
                strategy=self.name,
                goal=goal,
                policy=policy.__dict__,
                profile=profile.summary(),
                trait_refs=profile.traits,
                open_price=terms.get("unit_price"),
                open_c=open_c,
                target_c=target_c,
                lower_c=plan.lower_c,
                upper_c=plan.upper_c,
                ground_truth=gt.summary(),
                c_alt=neg.c_alt,
                floor_price=floor,
                full_cost=full_cost,
                full_cost_source=cost_source,
                guessed_full_cost=(guess or {}).get("full_cost"),
                evidence=[{"kind": e.kind, "refs": e.refs, "sentence": e.sentence} for e in plan.evidence],
            )
            log.info(
                "%s plan [%s %s]: price open %s lower %s upper %s (asked %s%%, justified %s%%) | C target %s upper %s",
                sid,
                goal,
                ",".join(sorted(profile.traits)) or "-",
                terms.get("unit_price"),
                gt.lower,
                gt.upper,
                gt.asked_pct,
                gt.justified_pct,
                _k(target_c),
                _k(plan.upper_c),
            )

    def _policy(self, goal: str, p: SupplierProfile) -> Policy:
        base = POLICIES.get(goal, DEFAULT_POLICY)
        beta, recip = base.beta, base.reciprocity
        trade = list(base.trade_first)
        if p.has("underutilised"):
            beta += 0.5  # it needs the volume: no reason for us to move early
        markup = base.markup
        if p.has("full_order_book") or p.has("below_cost"):
            markup = max(markup, 0.0)  # no room under its cost: it is already there or does not need us
        if p.has("approval_ladder"):
            beta += 0.5  # it moves in small approved steps: no reason for us to move fast
        if p.has("cash_short"):
            trade.insert(0, "payment_days")
        if p.has("wants_volume") or p.has("full_order_book") or p.has("price_frozen"):
            trade += ["contract_months", "volume_per_year"]
        if p.has("we_pay_late") or p.has("relationship"):
            recip = min(1.0, recip + 0.1)
        return Policy(beta, recip, markup, base.claims_first, tuple(dict.fromkeys(trade)))

    def _evidence(self, neg, sid, open_price, current):
        out = super()._evidence(neg, sid, open_price, current)
        if self.data:
            parts = neg.case.get("parts") or []
            out += self.data.evidence_orders(parts, sid, open_price)
            out += data_facts(self.data, parts)
        return sorted(out, key=lambda e: -e.strength)

    def _full_cost(self, parts: list[str], supplier_id: str) -> float | None:
        """The should-cost of THIS supplier's plant for a single-part case; None otherwise.

        Another supplier's estimate is a different plant (cost base, process) and a bundle's price is
        not one part's cost: guessing would push the floor and the margin charge the wrong way."""
        if not self.data or len(parts) != 1:
            return None
        rows = self.data.query(
            "SELECT unit_cost FROM should_cost WHERE part_id = ? AND supplier_id = ? ORDER BY estimate_date DESC",
            (parts[0], supplier_id),
        )
        return rows[0]["unit_cost"] if rows and rows[0]["unit_cost"] else None

    def _fallback_full_cost(self, neg: Negotiation, sid: str) -> tuple[float | None, str]:
        """A strategic supplier's full cost where its own plant has no should-cost: the price of the main sheet of
        its first message less the sustainable margin, x SHOULD_COST_SHARE (its alternatives are other structures,
        and a cheaper one would set the guess too low). None where the case puts no price on the supplier's margin
        (no charge to protect) or nothing is quoted."""
        buyer = neg.buyer
        margin = buyer.get("sustainable_margin_pct")
        if not margin or not buyer.get("relationship_eur_per_point"):
            return None, ""
        first = next((m for m in neg.threads[sid].supplier_messages if m.get("term_sheets")), None)
        opening = ((first or {}).get("term_sheets") or [{}])[0].get("terms", {}).get("unit_price")
        if not isinstance(opening, int | float) or opening <= 0:
            return None, ""
        return round(opening * (1 - margin / 100) * SHOULD_COST_SHARE, 2), "opening less the sustainable margin"

    def _guess_floor(self, neg: Negotiation, sid: str, plan: Plan, terms: dict) -> float:
        """Under a guessed cost, the price that minimises C on these terms with the guessed charge (0 without a
        guess): no ask and no accept goes under it."""
        if not plan.guess or terms.get("unit_price") is None:
            return 0.0
        std = neg.threads[sid].standard_terms

        def c(price: float) -> float:
            return total_cost(neg.case, {**terms, "unit_price": price}, std, plan.guess)

        lo, hi = 0.0, terms["unit_price"] * 1.5
        for _ in range(60):
            a, b = lo + (hi - lo) / 3, hi - (hi - lo) / 3
            if c(a) < c(b):
                hi = b
            else:
                lo = a
        return math.ceil((lo + hi) / 2 * 100 - 1e-6) / 100

    def _standard_terms(self, neg: Negotiation, sid: str) -> dict:
        """The supplier's standard terms for the relationship term: its quote PDF, then its master data, then its
        opening sheet. The PDFs of P01, P02, P03 and P10 name neither payment nor Incoterm, which left the charge
        out of C altogether (P02 closed at 345.39 with EUR 179k of it, score 0). What stays unknown is taken as
        the value that charges most - too high a charge costs a little price, too low a charge scores 0."""
        std = dict(neg.threads[sid].standard_terms)
        master = (self.data.supplier(sid) if self.data else None) or {}
        first = next((m for m in neg.threads[sid].supplier_messages if m.get("term_sheets")), None)
        opening = first["term_sheets"][0]["terms"] if first else {}
        fixed = neg.case.get("fixed_terms", {})
        for name in ("payment_days", "incoterm"):
            for source in (master, opening):
                if std.get(name) is None and fixed.get(name) is None and source.get(name) is not None:
                    std[name] = source[name]
        freight = neg.buyer["freight_eur_per_unit"]
        if std.get("incoterm") not in freight and fixed.get("incoterm") is None:
            std["incoterm"] = max(freight, key=freight.get)
        if std.get("payment_days") is None and fixed.get("payment_days") is None:
            options = neg.case.get("term_options", {}).get("payment_days") or []
            std["payment_days"] = min(options, default=neg.buyer["reference_payment_days"])
        return std

    def _estimate_supplier(self, neg: Negotiation, sid: str, full_cost: float | None, p: SupplierProfile) -> None:
        """Our estimate of the supplier for the relationship term in C (stabilise, secure_supply)."""
        if neg.buyer.get("category_goal") not in RELATIONSHIP_GOALS or not full_cost:
            neg.supplier_estimates.pop(sid, None)
            return
        neg.supplier_estimates[sid] = self._supplier_estimate(neg, sid, full_cost, p)

    def _supplier_estimate(self, neg: Negotiation, sid: str, full_cost: float, p: SupplierProfile) -> dict:
        rate = neg.buyer.get("interest_rate", 0.08)
        return {
            "full_cost": full_cost,
            "interest_rate": rate * CASH_SHORT_RATE if p.has("cash_short") else rate,  # money now is dearer to it
            "usual_rate": rate,
            "standard": self._standard_terms(neg, sid),
        }

    def _floor(self, neg: Negotiation, full_cost: float | None, policy: Policy) -> float | None:
        if not full_cost:
            return None
        if neg.buyer.get("category_goal") in RELATIONSHIP_GOALS:
            margin = neg.buyer.get("sustainable_margin_pct") or 0
            return round(full_cost / (1 - margin / 100), 2)
        return round(full_cost * (1 + policy.markup), 2)

    def _target_c(self, neg, sid, terms, policy, profile, floor, current, gt: GroundTruth | None = None) -> float:
        """The C of our first ask: the deepest credible price on our C-optimal terms - just under the
        supplier's estimated floor when we have one, else an anchor below the reference price."""
        open_price = terms.get("unit_price")
        if open_price is None:
            return math.inf
        price_only = bool(gt and gt.lower and gt.lower >= open_price * 0.95)  # the prior says: only the price moves
        depth = ANCHOR_PRICE_ONLY if price_only else ANCHOR_WITH_LEVERS
        extra = ANCHOR_DATA_EXTRA
        if neg.buyer.get("category_goal") == "routine":
            # P07 (bundling, routine): a 13 % ask got 5.59 and four rounds (0.721, P-13); 25-26 % got "your
            # target prices are not feasible", 5.69 and a final offer in round 2 (0.585 P-15, 0.663 P-22)
            depth, extra = min(depth, ANCHOR_ROUTINE), 0.0
        if neg.supplier_estimates.get(sid):
            # the margin charge is in C: the ask may go as deep as a price-only talk, it stops at the price that
            # costs us least (below). P01 came down to 132.20 after a 10 % ask, to 137.00 after a 3 % one
            depth, extra = ANCHOR_PRICE_ONLY, 0.0
        elif neg.buyer.get("category_goal") in RELATIONSHIP_GOALS:
            depth, extra = min(depth, ANCHOR_RELATIONSHIP), 0.0  # squeezing a strategic supplier costs us C
        # round 1 carries 67 % of all supplier movement and no supplier ever walked over a deep first offer
        # (0 of 917 replies); within a case deeper first offers went with better scores - so we open deep
        candidates = [open_price * (1 - depth)]
        if gt and gt.lower and gt.grounded:
            candidates.append(gt.lower * (1 - UNDER_FLOOR))
        alt_price = ((neg.buyer.get("alternative") or {}).get("terms") or {}).get("unit_price")
        if alt_price and alt_price < open_price:
            candidates.append(alt_price * 0.98)
        # the data may take it deeper - a cheaper alternative, a low grounded floor - but not past 5 points more
        price = max(min(candidates), open_price * (1 - depth - extra))
        # no price floor here for strategic suppliers: the relationship term prices a squeeze in C (the first ask
        # stops at the price that costs us least, below), and `_sheets` lifts every sheet to
        # RELATIONSHIP_COST_FLOOR of its should-cost - our estimate can sit above its real cost (P02: 380 over a
        # 371 quote, C_best ~364), so the floor is on the sheets we send, not on the target
        price = min(price, open_price)
        ideal = complete_offer(neg.case, self._optimise(neg, sid, {**terms, "unit_price": round(price, 2)}))
        if neg.supplier_estimates.get(sid):
            # with the margin charge in C, a price under the one that costs us least costs more charge than it
            # saves - and the supplier may agree to it (P02 agreed to 345.39): the first ask stops there
            for _ in range(2):
                ideal["unit_price"] = max(ideal["unit_price"], round(self._cheapest_price(neg, sid, ideal), 2))
                ideal = complete_offer(neg.case, self._optimise(neg, sid, ideal))
        return min(neg.cost(sid, ideal), neg.cost(sid, terms))

    def _bounds_c(self, neg, sid, terms, gt: GroundTruth, target_c: float, open_c: float) -> tuple[float, float]:
        """The bounds in C, on our C-optimal terms: a fair price on poor terms (a short contract that
        leaves need uncovered, early payment, dear freight) must not pass as a good deal."""
        lower_c, upper_c = -math.inf, min(open_c, neg.c_alt)
        if gt.lower:
            low = self._ideal(neg, sid, terms, gt.lower)
            if neg.supplier_estimates.get(sid):
                # under a margin charge a price below the one that costs us least costs more, not less: the bound
                # sits at that price (a floor factor of 0.86 under a strategic supplier's cost put it above its quote)
                low["unit_price"] = max(low["unit_price"], round(self._cheapest_price(neg, sid, low), 2))
            lower_c = neg.cost(sid, low)
        if gt.upper:
            upper_c = min(upper_c, neg.cost(sid, self._ideal(neg, sid, terms, gt.upper)))
        # room to concede above our first ask, whatever the calibration says (P05: an 18 % anchor over a 22 %
        # floor left upper == anchor and only 0.4 % steps) - never above its quote or our alternative
        return lower_c, min(max(upper_c, target_c * (1 + UPPER_ROOM)), open_c, neg.c_alt)

    def _ideal(self, neg, sid, terms: dict, price: float) -> dict:
        return complete_offer(neg.case, self._optimise(neg, sid, {**terms, "unit_price": round(price, 2)}))
