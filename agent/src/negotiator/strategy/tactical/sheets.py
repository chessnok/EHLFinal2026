"""The term sheets of one message: the menu at our ask, and the single-sheet moves on its own offer."""

import math

from arena_kit.cost import RELATIONSHIP_GOALS, complete_offer

from negotiator.menu import acceptance, priced_menu, satisfies, structure_key
from negotiator.session import Negotiation
from negotiator.strategy.base import Decision
from negotiator.strategy.baseline import SIGNATURE, describe
from negotiator.strategy.tactical.plan import (
    ALT_MIN_EUR,
    ALT_ROOM_SHARE,
    ANCHOR_SLACK,
    CHEAP_YES,
    DONE_EPS,
    EQUAL_C,
    MAX_SPREAD,
    MIN_STEP,
    OWN_GAIN,
    RELATIONSHIP_COST_FLOOR,
    STALL_EPS,
    UNDER_FLOOR,
    YES_ROOM_SHARE,
    Plan,
)
from negotiator.strategy.tactical.writing import FIELD_WORDS
from negotiator.telemetry import log


class SheetsMixin:
    def _offer(self, neg, sid, plan, theirs, ask_c, their_c, probe: bool = False) -> Decision:
        sheets = self._sheets(neg, sid, plan, theirs, ask_c, their_c)
        for _ in range(4):  # the same offer again reads as a refusal to move ("proposal unchanged")
            if not sheets or self._keys(sheets) != plan.last_keys:
                break
            ask_c = min(ask_c + MIN_STEP * ask_c, their_c * (1 - DONE_EPS))
            sheets = self._sheets(neg, sid, plan, theirs, ask_c, their_c)
        if not sheets:
            return Decision.hold(sid, "no valid term sheet below their offer")
        plan.last_keys = self._keys(sheets)
        # with a margin charge the sheets of a deep ask cost more than the ask they stand for (`_sheets`); under a
        # guessed cost the floor lifts them - the concession curve goes on from the ask, as without the guess
        lifted = neg.supplier_estimates.get(sid) or plan.guess
        plan.our_c.append(ask_c if lifted else neg.cost(sid, sheets[0]["terms"]))
        claims = self._choose_claims(neg, sid, plan, first=not plan.last_claims and neg.threads[sid].rounds_used == 0)
        plan.last_claims = claims
        message = self._write(neg, plan, sheets, claims, probe)
        return Decision(
            "message",
            sid,
            message=message,
            rationale={
                "round": neg.threads[sid].rounds_used + 1,
                "goal": neg.buyer.get("category_goal"),
                "traits": sorted(plan.profile.traits),
                "ask_c": round(ask_c, 2),
                "their_c": round(their_c, 2),
                "target_c": round(plan.target_c, 2),
                "stalls": plan.stalls,
                "probe": probe,
                "c_sheets": [neg.cost(sid, s["terms"]) for s in sheets],
                "claims": [c.kind for c in claims],
            },
        )

    @staticmethod
    def _keys(sheets: list[dict]) -> frozenset:
        return frozenset(repr(sorted(sh["terms"].items(), key=lambda kv: kv[0])) for sh in sheets)

    def _sheets(self, neg, sid, plan, theirs, ask_c, their_c) -> list[dict]:
        """Up to three packages from the full menu, all costing us `ask_c`:
        A  the structure that costs us least - at equal C it leaves the supplier the highest price;
        B  the structure the supplier takes most readily (its requests answered, closest to its own);
        C  the next most acceptable structure of a different kind (another clause, term or payment)."""
        case = neg.case
        # never above what it asks: under a guessed cost its offer at hand; with its own plant's cost its standing
        # price - not a cheaper alternative it named (P01: 132.55 at 90 days against its 132.40 at 30, as measured)
        _, standing = neg.threads[sid].standing
        ceiling = theirs["unit_price"]
        if not plan.guess and (standing or {}).get("unit_price"):
            ceiling = max(ceiling, standing["unit_price"])
        capping = bool(plan.guess or neg.supplier_estimates.get(sid))
        # Under a margin charge every C above the minimum has two prices. While our ask is within ANCHOR_SLACK
        # of the minimum we send the lower one: a deep first ask whose every step up is a move the supplier sees
        # and a gain for us, and if it agrees we pay at most the slack. After that, the usual side.
        slack = ANCHOR_SLACK * max(0.0, plan.open_c - plan.target_c) if neg.supplier_estimates.get(sid) else 0.0
        spent = max(0.0, ask_c - plan.target_c)
        under = spent < slack

        def least(terms: dict) -> float:
            return neg.cost(sid, {**terms, "unit_price": self._cheapest_price(neg, sid, terms)})

        def asked(terms: dict) -> bool:
            return any(satisfies(case, terms, theirs, r, plan.proposed) for r in plan.requests)

        # a dearer structure the supplier asked for (an index clause) is offered at the price that costs us
        # least - the cheapest such structure only (P02: deadband 5, not 3 or 0)
        asked_least = min(
            (least(t) for t in priced_menu(case, theirs, lambda _t: theirs["unit_price"]) if asked(t)), default=math.inf
        )

        def price_for(terms: dict) -> float:
            if not under:
                return self._iso_cost_price(neg, sid, terms, ask_c - slack)
            floor_c = least(terms)
            if floor_c > plan.target_c + 0.25 * slack:
                # only the structures about as cheap for us as the best one go deep: P03's deep ask went out on
                # a volume below our need, P02's on an index clause, and the supplier agreed to both (P-18)
                if asked(terms) and floor_c <= asked_least * (1 + STALL_EPS):
                    return self._cheapest_price(neg, sid, terms)
                return 0.0
            return self._iso_cost_price(neg, sid, terms, floor_c + slack - spent, under=True)

        def capped(terms: dict) -> float:
            # never above its own price: where the margin charge falls faster than the price rises (a sustainable
            # margin above what its quote leaves it) the cost-optimal price sat over its quote (brief variants)
            price = price_for(terms)
            return min(price, ceiling) if capping else price

        menu = priced_menu(case, theirs, capped)
        valid, under_floor = [], []
        for terms in menu:
            if not neg.keeps_must_haves(sid, terms) or neg.cost(sid, terms) >= their_c:
                continue
            if under:
                valid.append(terms)
                continue
            if plan.floor_price and terms["unit_price"] < plan.floor_price * (1 - UNDER_FLOOR - 0.01):
                under_floor.append(terms)  # far below what it can sell at: an insult
                continue
            valid.append(terms)
        if neg.supplier_estimates.get(sid) and valid and not under:
            # under a margin charge a structure cannot cost less than at its cheapest price. One that misses
            # `ask_c` there stays only while it is nearer to our ask than to the supplier's offer (P02: the index
            # clause costs us 0.8 % and is the one structure it lowers its price for)
            limit = max(ask_c, min(neg.cost(sid, t) for t in valid), (ask_c + their_c) / 2)
            valid = [t for t in valid if neg.cost(sid, t) <= limit * (1 + STALL_EPS)]
        pool = valid or under_floor  # never go silent: an offer under its floor beats none
        if not pool:
            return []
        if neg.buyer.get("category_goal") in RELATIONSHIP_GOALS and plan.full_cost:
            # a strategic supplier is never asked below 95 % of its own plant's should-cost: P02 closed at 345
            # against a should-cost of 380 and paid EUR 179k of margin charge (score 0); its C_best sat near 362
            floor = round(plan.full_cost * RELATIONSHIP_COST_FLOOR, 2)
            for t in pool:
                t["unit_price"] = max(t["unit_price"], floor)
                if capping:
                    t["unit_price"] = min(t["unit_price"], ceiling)
            pool = [t for t in pool if neg.cost(sid, t) < their_c] or pool
        if plan.guess:
            # a guessed cost is a floor: no sheet under the price that costs us least with the guessed charge
            for t in pool:
                t["unit_price"] = min(max(t["unit_price"], self._guess_floor(neg, sid, plan, t)), theirs["unit_price"])
            pool = [t for t in pool if neg.cost(sid, t) < their_c] or pool
            # the floor lifts the structures by different amounts in C (D01: 12 months at 50.75 cost EUR 22k more
            # than 24 months): only those about as cheap for us as the cheapest lifted one stay
            least_c = min(neg.cost(sid, t) for t in pool)
            pool = [t for t in pool if neg.cost(sid, t) <= least_c * (1 + EQUAL_C)]
        repeated = {r for r, n in plan.request_counts.items() if n >= 2}
        meets = [t for t in pool if all(satisfies(case, t, theirs, r, plan.proposed) for r in repeated)]
        if repeated and meets:
            pool = meets  # an option it has refused twice is no option

        def rank(t):
            # at equal C for us: what it asked for first, then what the package is worth to it in cash (its cost of
            # money, the chargebacks at its real defect rate) - P11's best package dropped a chargeback that cost us
            # little and it a lot; P02's paid early instead of a price its margin could not carry
            answered, alike = acceptance(case, t, theirs, plan.requests, plan.proposed)
            worth = plan.belief.value(t) if asymmetric else 0.0
            return (answered, round(worth, 4), alike, t["unit_price"])

        # what a package is worth to it ranks the options only where the data shows a lever is worth much more to
        # it than it costs us: chargebacks at its real defect rate (scorecard). On payment days and freight both
        # sides value money alike - offering it the cash-richest package (D02: 14 days, EXW) only bought it a
        # structure that is dear for us, not a lower price (sandbox 0.608 -> 0.535)
        asymmetric = bool(plan.belief and plan.belief.ppm and "chargeback_eur_per_complaint" in case["negotiable"])

        for t in pool:  # a structure offered before never comes back at a lower price
            before = plan.offered.get(structure_key(t))
            if before is not None and t["unit_price"] < before:
                t["unit_price"] = before
        pool = [t for t in pool if neg.cost(sid, t) < their_c] or pool
        top = max(t["unit_price"] for t in pool)
        pool = [t for t in pool if t["unit_price"] >= top * (1 - MAX_SPREAD)]
        picked = [max(pool, key=lambda t: t["unit_price"]), max(pool, key=rank)]
        if plan.lever_turn:  # a structure it has not seen yet carries our step
            new = [t for t in pool if structure_key(t) not in plan.offered]
            if new:
                picked[1] = max(new, key=rank)
            plan.lever_turn = False
        lead, before = picked[0], plan.offered.get(structure_key(picked[0]))
        if before is not None and lead["unit_price"] <= before:  # "your proposal remains unchanged"
            bumped = round(before * (1 + MIN_STEP), 2)
            if bumped < theirs.get("unit_price", bumped + 1):
                lead["unit_price"] = bumped
        seen = {structure_key(t) for t in picked}
        for t in sorted(pool, key=rank, reverse=True):
            if structure_key(t) not in seen:
                picked.append(t)
                break
        for t in picked:
            before = plan.offered.get(structure_key(t))
            if before is not None and t["unit_price"] <= before:
                bumped = round(before * (1 + MIN_STEP), 2)
                if bumped < theirs.get("unit_price", bumped + 1):
                    t["unit_price"] = bumped
        if picked:
            picked[0] = self._cheap_yes(neg, sid, plan, theirs, picked[0])
        # every option of a message costs us the same: floors and bumps can lift one above our ask, and the supplier
        # then picks the one dearest to us (P02 agreed at once to an index clause at the same price, EUR 39k more C;
        # without it practice P02 0.167 -> 0.731)
        cheapest = min(neg.cost(sid, t) for t in picked)
        picked = [t for t in picked if neg.cost(sid, t) <= cheapest * (1 + EQUAL_C)]
        # never an option dearer for us than its own standing offer: it would simply take that one
        picked = [t for t in picked if neg.cost(sid, t) < their_c] or picked
        out, keys = [], set()
        for t in picked:
            if structure_key(t) not in keys:
                keys.add(structure_key(t))
                out.append({"terms": t})
        if self.flags["own_structures"]:
            out = self._own_structures(neg, sid, plan, out, their_c)
        out = self._fast_pay(neg, sid, plan, out, their_c)[:3]
        for o in out:  # only what is sent counts as offered: a dropped option must not floor the next round
            t = o["terms"]
            if structure_key(t) in keys:  # the menu's own options, as before (fast_pay's never counted)
                plan.offered[structure_key(t)] = max(plan.offered.get(structure_key(t), 0.0), t["unit_price"])
        return out

    @staticmethod
    def _own_rates(neg: Negotiation, sid: str) -> dict[str, tuple]:
        """What the supplier's own sheets say a structure is worth to it: per field, (its value on the dearer sheet,
        its value on the cheaper one, the price drop) from two sheets of one message that differ in that field only
        (P05 Hrvelec: 35.00 at 35 days next to 31.50 at 52). The latest message wins."""
        negotiable = [f for f in neg.case["negotiable"] if f != "unit_price"]
        rates: dict[str, tuple] = {}
        for m in neg.threads[sid].supplier_messages:
            sheets = [s.get("terms") or {} for s in m.get("term_sheets") or []]
            sheets = [{**sheets[0], **s} for s in sheets if isinstance(s.get("unit_price"), int | float)]
            for i, x in enumerate(sheets):
                for y in sheets[i + 1 :]:
                    diff = [f for f in negotiable if x.get(f) != y.get(f)]
                    if len(diff) != 1 or x["unit_price"] == y["unit_price"]:
                        continue
                    dear, cheap = (x, y) if x["unit_price"] > y["unit_price"] else (y, x)
                    f = diff[0]
                    rates[f] = (dear.get(f), cheap.get(f), dear["unit_price"] - cheap["unit_price"])
        return rates

    def _own_structures(self, neg: Negotiation, sid: str, plan: Plan, out: list[dict], their_c: float) -> list[dict]:
        """A structure the supplier prices far more cheaply than it costs us joins as option B, at option A's C.

        Lead time is the big asymmetry: our late cost is one sum per day for the whole contract, its overtime is
        priced per unit - P05 Hrvelec asked 9.9 % less at 52 days than at 35 (n 29; 7 days over our need cost us
        EUR 1,400 in all), P10's supplier 5.6 % less at 54 days than at 42. Our menu never sent them: at equal C the
        longer lead time has a slightly lower price, and option A takes the highest price."""
        if not out:
            return out
        case, options = neg.case, neg.case.get("term_options", {})
        a = out[0]["terms"]
        a_c = neg.cost(sid, a)
        keys = {structure_key(sh["terms"]) for sh in out}
        candidates = []  # (its gain - our cost, terms)
        rated = False  # a sheet pair already gave its rate for the lead time

        def priced(f, value):
            terms = complete_offer(case, {**a, f: value})
            if structure_key(terms) in keys or not neg.keeps_must_haves(sid, terms):
                return None
            terms["unit_price"] = max(
                self._iso_cost_price(neg, sid, terms, a_c), plan.offered.get(structure_key(terms), 0)
            )
            return terms

        def allowed(f, near):
            """The option we may sign nearest to its value (52 days -> 42 under a 42-day must-have)."""
            opts = [o for o in options.get(f) or [] if o is not None and neg.keeps_must_haves(sid, {**a, f: o})]
            if not opts:
                return None
            if isinstance(near, int | float) and all(isinstance(o, int | float) for o in opts):
                return min(opts, key=lambda o: (abs(o - near), o))
            return near if near in opts else None

        for f, (dear, cheap, drop) in self._own_rates(neg, sid).items():
            value = allowed(f, cheap)
            if value is None or value == a.get(f):
                continue
            if all(isinstance(v, int | float) for v in (dear, cheap, value, a.get(f))):
                gain = drop * (value - dear) / (cheap - dear)  # its price per unit of the field, within its own pair
            elif a.get(f) == dear and value == cheap:
                gain = drop
            else:
                continue
            terms = priced(f, value)
            if terms and gain > max(0.0, OWN_GAIN * (a["unit_price"] - terms["unit_price"])):
                candidates.append((gain - (a["unit_price"] - terms["unit_price"]), terms))
                rated = rated or f == "lead_time_days"
        if "lead_time_days" in case["negotiable"] and not rated:
            # its own lead time beyond our need, where no sheet pair gives its rate yet (P05 Hrvelec opened at 52
            # days, P10's supplier at 54): at equal C it costs us nothing, and a shorter one means overtime for it
            own = [
                v
                for m in neg.threads[sid].supplier_messages
                for s in m.get("term_sheets") or []
                if isinstance(v := (s.get("terms") or {}).get("lead_time_days"), int | float)
            ]
            need = neg.buyer.get("need_lead_time_days") or 0
            if own and max(own) > max(need, a.get("lead_time_days") or 0):
                value = allowed("lead_time_days", max(own))
                if value is not None and value > (a.get("lead_time_days") or 0):
                    terms = priced("lead_time_days", value)
                    if terms:
                        candidates.append((0.0, terms))
        for _, terms in sorted(candidates, key=lambda x: -x[0]):
            if terms["unit_price"] > a["unit_price"] or terms["unit_price"] <= 0:
                continue  # never an option dearer than A: it anchors its price up
            if neg.cost(sid, terms) > a_c * (1 + EQUAL_C) or neg.cost(sid, terms) >= their_c:
                continue  # every option of a message costs us the same
            plan.offered[structure_key(terms)] = max(plan.offered.get(structure_key(terms), 0.0), terms["unit_price"])
            log.info("%s: its own structure %s joins at %.2f", sid, structure_key(terms), terms["unit_price"])
            return out[:1] + [{"terms": terms}] + out[1:2]  # option B: fast_pay may still take option C
        return out

    def _cheap_yes(self, neg: Negotiation, sid: str, plan: Plan, theirs: dict, terms: dict) -> dict:
        """Yes to its conditions that cost us little - never to its price: each value of its own sheet on a lever it
        asked for goes into our option A at OUR price when it costs us at most CHEAP_YES of C (P-42: a yes to its
        start date at a lower price cost P01 0.14)."""
        base = neg.cost(sid, terms)
        out, granted = dict(terms), []
        for f in sorted(plan.requests):
            want = theirs.get(f)
            if f == "unit_price" or f not in neg.case["negotiable"] or want is None or want == out.get(f):
                continue
            options = neg.case.get("term_options", {}).get(f)
            if options and want not in options:
                continue  # a value we may not sign (P10's 54 days) would void the whole option
            trial = {**out, f: want}
            # a share of C, and never more than 1 % of the room: P02's room is 2.3 % of C, so 0.2 % of C there
            # would be up to 0.087 of the score for one yes (stress test of 11 Oct)
            room = plan.open_c - plan.target_c
            # no room, no free yes; an unknown room (no estimate) keeps the share of C
            limit = min(CHEAP_YES * base, YES_ROOM_SHARE * max(0.0, room)) if math.isfinite(room) else CHEAP_YES * base
            if neg.keeps_must_haves(sid, trial) and neg.cost(sid, trial) - neg.cost(sid, out) <= limit:
                out, granted = trial, granted + [(f, want)]
        if granted:
            words = " and ".join(f"{FIELD_WORDS.get(f, f.replace('_', ' '))} {v}" for f, v in granted)
            plan.yes_line = f"Yes to {words}, as you asked - at the same price."
        return out

    def _fast_pay(self, neg: Negotiation, sid: str, plan: Plan, out: list[dict], their_c: float) -> list[dict]:
        """It asked for faster payment and no option pays at the shortest term the case allows (14 days in every
        practice case): one that does joins, at the same C as option A.
        It costs us ~0.10 EUR a unit for 16 days; P05's 70210 gave 0.50 for it ("I can drop the price to 27.50 for
        14 days payment": 0.824 -> 0.865)."""
        options = [o for o in neg.case.get("term_options", {}).get("payment_days") or [] if isinstance(o, int | float)]
        if (
            not out
            or not options
            or "payment_days" not in neg.case["negotiable"]
            or "payment_days" not in plan.requests
        ):
            return out
        fastest = min(options)  # the shortest term the case allows (14 days in every practice case)
        if any((sh["terms"].get("payment_days") or 999) <= fastest for sh in out):
            return out
        if len(neg.threads) < 2:
            return out  # measured to win only in an RFQ (P05 +0.041); alone it lost P08 0.055 and P07 0.012 (P-51)
        if neg.supplier_estimates.get(sid) or neg.buyer.get("category_goal") in RELATIONSHIP_GOALS:
            return (
                out  # under a margin charge the 14-day option prices high and pulls its price up (P01 0.943 -> 0.818)
            )
        a = out[0]["terms"]
        base = complete_offer(neg.case, {**a, "payment_days": fastest})
        base["unit_price"] = self._iso_cost_price(neg, sid, base, neg.cost(sid, a))
        if base["unit_price"] > a["unit_price"]:
            return out  # never an option dearer than A: it anchors its price up
        if not neg.keeps_must_haves(sid, base) or neg.cost(sid, base) >= their_c:
            return out
        plan.offered[structure_key(base)] = max(plan.offered.get(structure_key(base), 0.0), base["unit_price"])
        return out[:2] + [{"terms": base}]

    def _take_alternative(self, neg: Negotiation, sid: str, plan: Plan) -> Decision | None:
        """Its alternative sheet costs us less than its primary one: say yes to the alternative as our offer.

        The arena closes an accept on the supplier's primary sheet whatever id we send (P10: we accepted the
        EUR 31.90 alternative and were booked at 33.80) - so the alternative has to come back as our term
        sheet; the supplier then agrees and we close on it. 54 % of all alternatives were cheaper for us."""
        t = neg.threads[sid]
        primary_id, primary = t.standing
        best_id, best = neg.best_offer(sid)
        if not best_id or best_id == primary_id or best_id in plan.alternatives_taken or not self._may_push(neg, sid):
            return None
        best_c, primary_c = neg.cost(sid, best), neg.cost(sid, primary)
        # 0.1 % of the room, not 0.2 % of C: P08's 5 % deadband alternative saved 0.16 % of C and was passed over;
        # taken, P08 0.550 -> 0.560 (runs.md P-34 to P-41)
        margin = self._alt_margin(neg, plan, primary_c)
        if best_c >= primary_c - margin:
            return None
        # only when we would close anyway - in round 1 its alternative is an opening, not a deal (P18 dry run)
        closing = (
            t.status == "final_offer"
            or self._says(plan, "firm")
            or plan.stalls >= 1
            or self._round_budget(neg, sid) - t.rounds_used <= 2
        )
        if not closing:
            return None
        std = t.standard_terms
        sheet = complete_offer(
            neg.case, {**{k: v for k, v in std.items() if k in neg.case["negotiable"]}, **primary, **best}
        )
        if plan.guess:  # never under the guess floor; then only while it still beats its primary sheet
            sheet["unit_price"] = max(sheet["unit_price"], self._guess_floor(neg, sid, plan, sheet))
            if neg.cost(sid, sheet) >= neg.cost(sid, primary) * (1 - 0.002):
                return None
        if not neg.keeps_must_haves(sid, sheet) or neg.cost(sid, sheet) >= neg.c_alt:
            return None
        if neg.cost(sid, sheet) >= primary_c - margin:
            return None  # completed with its standard terms, the sheet no longer beats its primary offer
        plan.alternatives_taken.add(best_id)
        plan.our_c.append(neg.cost(sid, sheet))
        plan.last_claims = []
        plan.last_keys = self._keys([{"terms": sheet}])
        body = "\n".join(
            [
                f"Dear {plan.name} team,",
                "",
                self._alternative_line(neg, sheet, best),
                "",
                f"Our proposal: {describe(neg.case, sheet)}",
                "",
                SIGNATURE,
            ]
        )
        return Decision(
            "message",
            sid,
            message={"subject": neg.case.get("title", "Your quote"), "body": body, "term_sheets": [{"terms": sheet}]},
            rationale={"move": "take its alternative", "alternative": best_id, "c": neg.cost(sid, sheet)},
        )

    @staticmethod
    def _alt_margin(neg: Negotiation, plan: Plan, primary_c: float) -> float:
        """How much cheaper its alternative must be to be worth a round: 0.1 % of the room between the opening and
        the supplier's estimated floor, i.e. about 0.001 of the score (the score is the saving as a share of a room
        of the same order). P08's 5 % deadband alternative saved 0.16 % of C, 0.0094 of the score, and fell under
        the old bar of 0.2 % of C in 4 of 4 sessions. Without a floor estimate: 0.05 % of C."""
        room = neg.c_open - plan.lower_c
        if math.isfinite(room) and room > 0:
            return max(ALT_MIN_EUR, ALT_ROOM_SHARE * room)
        return max(ALT_MIN_EUR, 0.0005 * primary_c)

    def _price_match(self, neg, sid, plan: Plan, theirs: dict, their_c: float) -> Decision | None:
        """Its price is within our upper bound but its other terms cost us: take the price, fix the terms.

        Easy for the supplier to say yes to (it keeps its price) and it recovers what the terms cost -
        e.g. a 12-month sheet in a 24-month need, or early payment. Once per thread."""
        gt = plan.gt
        price = theirs.get("unit_price")
        if plan.price_matched or not gt or not gt.upper or price is None:
            return None
        uncovered = neg.breakdown(sid, theirs).get("uncovered_need", 0) > 0
        if price > gt.upper and not uncovered:
            return None  # its price is too high to take; only a sheet that leaves need uncovered is worth fixing
        t = neg.threads[sid]
        if t.rounds_used < 2 and t.status != "final_offer":
            return None  # never give its price away before we have negotiated (P02 round 1)
        at_risk = (
            t.status == "final_offer"
            or plan.stalls >= 2
            or self._round_budget(neg, sid) - t.rounds_used <= 2
            # at its floor - where we have one: with a margin charge the floor is only the prior of 1 % under
            # its quote, and P01 came down 4.4 % (132.50); matching 133.50 in round 3 ended that run at 0.728
            or (
                not neg.supplier_estimates.get(sid)
                and gt.grounded
                and gt.lower is not None
                and price <= gt.lower * (1 + UNDER_FLOOR)
            )
        )
        if not at_risk:
            return None  # the upper bound is our emergency line, not an early yes
        menu = [m for m in priced_menu(neg.case, theirs, lambda _t: price) if neg.keeps_must_haves(sid, m)]
        if not menu:
            return None
        # the structures that answer most of its requests; among them the one that costs us least
        best_answer = max(acceptance(neg.case, m, theirs, plan.requests, plan.proposed)[0] for m in menu)
        matched = min(
            (m for m in menu if acceptance(neg.case, m, theirs, plan.requests, plan.proposed)[0] == best_answer),
            key=lambda m: neg.cost(sid, m),
        )
        if neg.cost(sid, matched) >= their_c * (1 - 0.005):
            return None  # its terms are already as good as ours
        plan.price_matched = True
        plan.last_claims = []
        sheets = [{"terms": matched}]
        plan.our_c.append(neg.cost(sid, matched))
        plan.last_keys = self._keys(sheets)
        lines = [
            f"Dear {plan.name} team,",
            "",
            f"thank you. We can accept your price of EUR {price:,.2f} - on the terms below, which complete the "
            "agreement for our full requirement."
            + self._answered(neg, plan, matched, theirs)
            + (" " + proof[0] if (proof := self._volume_proof(neg, plan, sheets)) else ""),
            "",
            "We can award on any of these options:" if len(sheets) > 1 else "Our proposal:",
        ]
        lines += [f"Option {chr(65 + i)}: {describe(neg.case, sh['terms'])}" for i, sh in enumerate(sheets)]
        lines += ["", SIGNATURE]
        return Decision(
            "message",
            sid,
            message={
                "subject": neg.case.get("title", "Your quote"),
                "body": "\n".join(lines),
                "term_sheets": sheets,
                "refs": [proof[1]] if proof else [],
            },
            rationale={
                "round": neg.threads[sid].rounds_used + 1,
                "move": "price match: its price, our terms",
                "their_price": price,
                "upper_price": gt.upper,
                "their_c": round(their_c, 2),
                "c_sheets": [neg.cost(sid, sh["terms"]) for sh in sheets],
            },
        )

    def _text_price_offer(self, neg: Negotiation, sid: str, plan: Plan) -> Decision | None:
        """It wrote a lower price than it put on its sheet: take it at its word, on its own terms, once."""
        if not plan.text_price or plan.text_price_used or not self._may_push(neg, sid):
            return None
        _, theirs = neg.best_offer(sid)
        if not theirs or plan.text_price >= (theirs.get("unit_price") or 0):
            return None
        plan.text_price_used = True
        plan.last_claims = []
        price = max(round(plan.text_price, 2), self._guess_floor(neg, sid, plan, theirs))
        if price >= theirs["unit_price"]:
            return None  # under our guess floor: its sheet stands
        sheet = complete_offer(neg.case, {**theirs, "unit_price": price})
        if not neg.keeps_must_haves(sid, sheet):
            return None
        plan.our_c.append(neg.cost(sid, sheet))
        plan.last_keys = self._keys([{"terms": sheet}])
        body = "\n".join(
            [
                f"Dear {plan.name} team,",
                "",
                f"thank you - you wrote that you can go to EUR {plan.text_price:,.2f}. We accept that price on your "
                "terms below and are ready to place the order."
                if price == round(plan.text_price, 2)
                else f"thank you - you wrote that you can go to EUR {plan.text_price:,.2f}. We propose EUR "
                f"{price:,.2f} on your terms below, a price that keeps the supply sustainable for you as well.",
                "",
                f"Our proposal: {describe(neg.case, sheet)}",
                "",
                SIGNATURE,
            ]
        )
        return Decision(
            "message",
            sid,
            message={"subject": neg.case.get("title", "Your quote"), "body": body, "term_sheets": [{"terms": sheet}]},
            rationale={"move": "take its written price", "text_price": plan.text_price},
        )

    def _floor_counter(self, neg: Negotiation, sid: str, plan: Plan, theirs: dict) -> Decision | None:
        """Its offer sits under our guess floor: taking it could leave it below its sustainable margin and cost us
        more charge than the price saves (P02). Offer the floor on its own terms instead - once, while we can."""
        if not plan.guess or plan.floor_countered or not self._may_push(neg, sid):
            return None
        floor = self._guess_floor(neg, sid, plan, theirs)
        if theirs["unit_price"] >= floor - 0.005:
            return None
        sheet = complete_offer(neg.case, {**theirs, "unit_price": floor})
        if not neg.keeps_must_haves(sid, sheet):
            return None
        plan.floor_countered = True
        plan.last_claims = []
        plan.our_c.append(neg.cost(sid, sheet))
        plan.last_keys = self._keys([{"terms": sheet}])
        plan.offered[structure_key(sheet)] = max(plan.offered.get(structure_key(sheet), 0.0), floor)
        body = "\n".join(
            [
                f"Dear {plan.name} team,",
                "",
                "thank you for your offer. We want this supply to stay sustainable for you as well, so we propose "
                f"EUR {floor:,.2f} on your terms below and are ready to place the order.",
                "",
                f"Our proposal: {describe(neg.case, sheet)}",
                "",
                SIGNATURE,
            ]
        )
        log.info("%s: offer %.2f under the guess floor - proposing %.2f", sid, theirs["unit_price"], floor)
        return Decision(
            "message",
            sid,
            message={"subject": neg.case.get("title", "Your quote"), "body": body, "term_sheets": [{"terms": sheet}]},
            rationale={"move": "guess floor", "their_price": theirs["unit_price"], "floor": floor},
        )
