"""Per round: what to do next in a thread - take, ask (and how much), probe - and the close."""

import math

from arena_kit.cost import RELATIONSHIP_GOALS

from negotiator.guards import accept_problems
from negotiator.session import Negotiation
from negotiator.strategy.base import Decision
from negotiator.strategy.tactical.plan import (
    BIG_STEP,
    DONE_EPS,
    MIN_STEP,
    PATIENT_GAP,
    REANCHOR,
    RELATIONSHIP_MIN_STEP,
    RELATIONSHIP_STEP,
    Plan,
)
from negotiator.strategy.tactical.reading import (
    APPROVAL_PENDING,
    reply_signals,
)
from negotiator.telemetry import log


class ConcessionMixin:
    def decide(self, neg: Negotiation, supplier_id: str) -> Decision:
        t, plan = neg.threads[supplier_id], self.tplans[supplier_id]
        if not t.live:
            return Decision.drop(supplier_id, f"thread {t.status}")
        self._learn(neg, supplier_id, plan)
        sheet_id, theirs = neg.best_offer(supplier_id)  # judge it by its best sheet for us, not its first
        if theirs.get("unit_price") is None or not math.isfinite(plan.target_c):
            return Decision.hold(supplier_id, "no price to negotiate on")
        if text := self._text_price_offer(neg, supplier_id, plan):
            return text  # it wrote a lower price than it sheeted: ask for that first, even next to an agreement
        if t.status == "agreed":
            if take := self._take_agreed(neg, supplier_id):
                return take
            return Decision.hold(supplier_id, "agreed")
        limit = neg.case.get("round_limit") or 10
        if limit - t.arena_rounds <= 0 or (limit - t.rounds_used == 1 and t.our_price_path()):
            # the last round is kept for the close - unless we have not asked anything yet: with round_limit 1
            # holding would never send an offer at all
            return Decision.hold(supplier_id, "last round: keep it for the close")
        if neg.seconds_to_deadline() < 120:
            return Decision.hold(supplier_id, "the deadline is near")
        if counter := self._floor_counter(neg, supplier_id, plan, theirs):
            return counter

        their_c = neg.cost(supplier_id, theirs)
        signals = reply_signals(t.latest.get("body", ""))
        # the lower bound is where we anchor, not where we stop: below it we keep asking - the supplier
        # ends it with a stall or a final offer, and only it knows its real floor
        last_word = t.status == "final_offer" or (signals["firm"] and t.rounds_used > 0)
        rest_pending = self._rest_pending(neg, supplier_id, plan)
        if (
            not last_word
            and not rest_pending
            and (their_c <= plan.lower_c or self._undercut_after_big_step(neg, supplier_id, plan, theirs))
        ):
            if reanchor := self._reanchor(neg, supplier_id, plan, theirs, their_c):
                return reanchor
        if alt := self._take_alternative(neg, supplier_id, plan):
            return alt  # its cheapest sheet is an alternative: the arena closes on the primary one, so ask for it
        return self._choose(neg, supplier_id, plan, theirs, their_c, last_word, rest_pending)

    def _choose(self, neg, supplier_id: str, plan: Plan, theirs: dict, their_c: float, last_word: bool,
                rest_pending: bool) -> Decision:  # fmt: skip
        """Take its offer, ask (and for how much) or probe a last word - here as a chain of rules in order; the
        `tactical-ev` variant (choice.py) makes the same choice by expected cost."""
        if last_word:
            # a last word is taken (the guards still check it): across ~65 pushes on final offers, 17 % ended in a
            # walk-away for ~+0.05 on average - only an RFQ with a safe rival offer may push once, with a real step
            if (
                their_c > plan.upper_c
                and not plan.probed_final
                and self._may_probe(neg, supplier_id, their_c)
                and self._may_push(neg, supplier_id)
            ):
                plan.probed_final = True
                last = plan.our_c[-1] if plan.our_c else plan.target_c
                ask_c = last + 0.5 * max(0.0, their_c - last)  # not capped: a crumb reads as a refusal (P18)
                return self._offer(neg, supplier_id, plan, theirs, ask_c, their_c, probe=True)
            return Decision.hold(supplier_id, "last word: take it", their_c=their_c)
        if not rest_pending and (match := self._price_match(neg, supplier_id, plan, theirs, their_c)):
            return match

        if plan.stalls >= 2 and their_c <= plan.upper_c:
            return Decision.hold(supplier_id, "stalled inside our upper bound: take it", their_c=their_c)
        if plan.stalls >= 3:
            return Decision.hold(supplier_id, "the supplier stopped moving", their_c=their_c)
        ask_c = self._next_c(neg, supplier_id, plan, their_c)
        if ask_c >= their_c * (1 - DONE_EPS) and not self._supplier_done(neg, supplier_id, plan):
            # our estimate of its floor said "this is it" but sat 3-12 % too high (P18: 249k against a C_best of
            # 223k): ask once more just under its offer - it ends the thread itself with a final offer, a stall or an
            # agreement (practice 10 Oct: P01 0.831 -> 0.946, P18 0.618 -> 0.685, P10 0.663 -> 0.601, rest unchanged)
            last = plan.our_c[-1] if plan.our_c else plan.target_c
            ask_c = max(their_c * (1 - PATIENT_GAP), last * (1 + MIN_STEP))
        if ask_c >= their_c * (1 - DONE_EPS):
            return Decision.hold(supplier_id, "their offer meets our ask", ask_c=ask_c, their_c=their_c)
        return self._offer(neg, supplier_id, plan, theirs, ask_c, their_c)

    def _next_c(self, neg: Negotiation, sid: str, plan: Plan, their_c: float) -> float:
        """Boulware over the rounds we can still play, capped by what the supplier gave last."""
        if not plan.our_c:
            return plan.target_c
        t = neg.threads[sid]
        last = plan.our_c[-1]
        budget = self._round_budget(neg, sid)
        progress = min(1.0, t.rounds_used / max(1, budget - 1))
        curve = plan.target_c + (their_c - plan.target_c) * progress**plan.policy.beta
        by_time = max(0.0, curve - last)
        theirs_path = self._their_c_path(neg, sid)
        their_move = theirs_path[-2] - theirs_path[-1] if len(theirs_path) >= 2 else 0.0
        min_step = MIN_STEP * last
        gap = max(0.0, their_c - last)
        if self._rest_pending(neg, sid, plan):
            return min(last + min_step, their_c, plan.upper_c)
        if APPROVAL_PENDING.search(t.latest.get("body", "")):
            # "we need to clarify this internally" / "more than my band allows": its boss approves the next
            # step anyway (8 of 8 in the back office) - hold, with the smallest visible move
            return min(last + min_step, their_c, plan.upper_c)
        if plan.stalls == 1:
            # no move from it: a visible step - a new structure carries it too (holding cost D02 0.608 -> 0.587)
            step = max(min_step, 0.15 * gap)
            plan.lever_turn = True
        elif plan.stalls >= 2:
            step = max(by_time * 0.5, 0.25 * gap)  # break the deadlock
        else:
            # a real counter-step: at least half of its last move (cent steps read as no movement)
            step = min(plan.policy.reciprocity * max(their_move, 0.0), max(by_time, 0.5 * max(their_move, 0.0)))
            step = max(step, min_step)
        if neg.buyer.get("category_goal") in RELATIONSHIP_GOALS:
            # only the price moves here, and the room is narrow: 0.4 % of C is 8 % of what there is to win on
            # P01 and 19 % on P02 - three such steps met the supplier in round 3 of 10 (P01 0.785, P02 0.421,
            # runs.md P-17). A quarter of the step, at least a twentieth of the room; D01 answered a step of 1 %
            # of the room in crumbs (0.809) and one of 5 % in full (0.957-0.969)
            room = max(0.0, plan.open_c - plan.target_c)
            step = max(RELATIONSHIP_STEP * step, min(min_step, RELATIONSHIP_MIN_STEP * room))
        return min(last + step, their_c, plan.upper_c)  # the upper bound is never asked for beyond

    def _rest_pending(self, neg: Negotiation, sid: str, plan: Plan) -> bool:
        """It just answered a rival quote we cited with a big step. "I give half the step now and check
        the rest" - "Checked: give the rest of the step" (P05 back office, 47 of 50): the rest comes in its next
        reply whatever we send, so a step of ours now - or a re-anchor's halfway ask - only pays for it (P05: 28.79
        agreed at once; holding gave 0.742 -> 0.824, runs.md P-31). The same back-office rule ran for four
        suppliers in two cases (P05, D02), so it is the arena's, not one supplier's (docs/bot-mechanics.md)."""
        if not plan.our_c:
            return False
        path = self._their_c_path(neg, sid)
        return (
            any(c.kind == "rival_offer" for c in plan.last_claims)
            and len(path) >= 2
            and path[-2] - path[-1] >= BIG_STEP * path[-2]
        )

    def _supplier_done(self, neg: Negotiation, sid: str, plan: Plan) -> bool:
        """The supplier itself says it is at its end: a final offer, firm words, a stall - or the rounds run out."""
        t = neg.threads[sid]
        return (
            t.status == "final_offer"
            or reply_signals(t.latest.get("body", ""))["firm"]
            or plan.stalls >= 1
            or self._round_budget(neg, sid) - t.rounds_used <= 3
        )

    def _round_budget(self, neg: Negotiation, sid: str) -> int:
        """Messages we can still expect to play in this thread: the round limit, or the clock."""
        t = neg.threads[sid]
        limit = neg.case.get("round_limit") or 10
        left = neg.seconds_to_deadline() - 120  # the runner closes before the cap
        if math.isfinite(left):
            per_round = max(15.0, neg.recorder.metrics.mean("supplier.reply_seconds") or 30.0) + 3.0
            limit = min(limit, t.rounds_used + max(1, int(left / per_round)))
        return limit

    def _may_probe(self, neg: Negotiation, sid: str, their_c: float) -> bool:
        """Push a final offer once - only when its walking away would cost us little."""
        t = neg.threads[sid]
        if (neg.case.get("round_limit") or 10) - t.rounds_used < 2 or neg.seconds_to_deadline() < 180:
            return False
        for other, ot in neg.threads.items():
            if other != sid and self.tplans[other].probed_final and ot.live:
                return False  # one rival is already being pushed: this one stays our safe fallback
        for other, ot in neg.threads.items():
            if other != sid and ot.live and ot.standing[0] and not accept_problems(neg, other, ot.standing[0]):
                return True  # a rival offer we could take instead
        return False  # room words alone are no reason: "bridge the remaining gap" (P18) ended in a walk-away

    def _may_push(self, neg: Negotiation, sid: str) -> bool:
        t = neg.threads[sid]
        return (neg.case.get("round_limit") or 10) - t.rounds_used >= 2 and neg.seconds_to_deadline() > 150

    def _undercut_after_big_step(self, neg: Negotiation, sid: str, plan: Plan, theirs: dict) -> bool:
        """It came down to (or under) our own ask in one big step: the back office of case:D02 read
        "I give half the step now and check the rest" - there is more to get."""
        prices = neg.threads[sid].price_path()
        ours = neg.threads[sid].our_price_path()
        if len(prices) < 2 or not ours or theirs.get("unit_price") is None:
            return False
        step = (prices[-2] - prices[-1]) / prices[-2]
        return theirs["unit_price"] <= ours[-1] * 1.005 and step >= BIG_STEP

    def _reanchor(self, neg, sid, plan: Plan, theirs: dict, their_c: float) -> Decision | None:
        """It came under a floor we only guessed: our guess was timid. Ask again under its new price, once."""
        if plan.reanchored or not self._may_push(neg, sid):
            return None
        if neg.buyer.get("category_goal") in RELATIONSHIP_GOALS and not plan.guess:
            # never 10 % under a strategic supplier's price: without an estimate of its cost nothing stops the
            # squeeze (P02: 345.39, score 0); with one C is not monotone in the price - a price under the floor
            # costs more charge than it saves, and the "re-anchor" asked a C above its offer, so no sheet went out.
            # A guessed cost allows it: the guess floor (_sheets) keeps every sheet above the cost minimum
            return None
        plan.reanchored = True
        price = theirs["unit_price"] * (1 - REANCHOR)
        new_target = neg.cost(sid, self._ideal(neg, sid, theirs, price))
        plan.target_c = min(plan.target_c, new_target)
        plan.lower_c = new_target
        if plan.gt:
            plan.gt.lower = round(price, 2)
        neg.recorder.event("reanchor", session_id=neg.session_id, supplier_id=sid, price=round(price, 2))
        log.info("%s: undercut our guessed floor - re-anchoring at %.2f", sid, price)
        ask_c = new_target + 0.5 * (their_c - new_target)  # meet halfway to the new anchor: credible, not greedy
        if plan.our_c:
            # never below our own last ask: where the first ask was capped (strategic suppliers) the halfway point
            # sat under it, and the step back read as reneging - D01 "we cannot accept a reduction", taken at R2
            ask_c = max(ask_c, plan.our_c[-1] * (1 + MIN_STEP))
        return self._offer(neg, sid, plan, theirs, ask_c, their_c)

    def _take_agreed(self, neg: Negotiation, sid: str) -> Decision | None:
        """It agreed to our terms: if no other live thread offers less, close now - holding it while others
        talk cost P05 two timeouts and nearly the deal."""
        offer_id, terms = neg.threads[sid].standing
        if not offer_id or accept_problems(neg, sid, offer_id):
            return None
        c = neg.cost(sid, terms)
        time_short = neg.seconds_to_deadline() < 180
        for other, ot in neg.threads.items():
            if other == sid or not ot.live:
                continue
            if len(ot.supplier_messages) < 2 and not time_short:
                return None  # a rival has not answered us yet (P05: closed at 33.50 before the 28.00 bidder spoke)
            _, their = neg.best_offer(other)
            if their and neg.cost(other, their) < c * 0.98:
                return None  # a rival is clearly cheaper: keep talking there
        return Decision(
            "accept", sid, term_sheet_id=offer_id, rationale={"c": c, "why": "agreed and the best on the table"}
        )

    def conclude(self, neg: Negotiation) -> Decision:
        best = None
        rejected = {}
        for sid, t in neg.threads.items():
            if t.closed or t.status in ("walked_away", "no_bid"):
                continue
            for sheet_id, terms in [t.standing]:  # the arena closes on the primary sheet whatever id we send
                if problems := accept_problems(neg, sid, sheet_id):
                    rejected[f"{sid} {sheet_id}"] = problems
                    continue
                c = neg.cost(sid, terms)
                if best is None or c < best[0]:
                    best = (c, sid, sheet_id)
        if best:
            return Decision(
                "accept",
                best[1],
                term_sheet_id=best[2],
                rationale={"c": best[0], "c_alt": neg.c_alt, "rejected": rejected, "why": "cheapest safe sheet"},
            )
        return Decision(
            "walk_away",
            next(iter(neg.threads)),
            rationale={"c_alt": neg.c_alt, "rejected": rejected, "why": "no sheet passes the guards"},
        )
