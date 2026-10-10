"""Tactical buyer: category goal + supplier profile -> tactics; tit-for-tat Boulware concessions in C.

Ideas taken from ASTRA (Kwon et al., github.com/DSincerity/ASTRA-NegoAgent) - the tactics, not the
code: a model of the opponent, an optimiser over the published cost function, several offers of
equal value to us that differ in what they give the supplier, and concessions that answer the
supplier's (no move from it, no move from us).

Per case (prepare):
  - the category goal sets the policy: how deep we anchor, how slowly we concede (Boulware beta),
    how much of the supplier's move we answer (reciprocity), whether we protect its margin;
  - the supplier's profile (profile.py) adjusts it: idle capacity -> anchor deeper; fully booked or
    below cost -> shallower; cash-short -> offer early payment; hedged -> skip index arguments ...;
  - target C: the deepest credible price (anchor, should-cost, history, alternative), never below
    what the supplier can sell at (its full cost, plus the sustainable margin where squeezing costs C).

Per round (decide), all in C (our total cost, the score's currency):
  - their concession = drop of C of their standing sheet; ours = drop of the C we ask for;
  - next ask: the Boulware curve over the rounds we can still play (round limit and the clock),
    capped by reciprocity - if they did not move, we hold (then a half step to break a deadlock;
    the third stall settles the thread);
  - up to three term sheets at that same C: our C-optimal terms; a trade the supplier values
    (early payment for the cash-short, a long commitment for those who want volume or security);
    a pure price move on its own terms. Whatever it agrees to costs us the same.
  - arguments: checkable evidence picked by the profile; what came back irrelevant or contradicted
    is not used again.
Closing: the cheapest standing sheet that passes the guards (guards.py), else walk away; a
`final_offer` is probed once with a trade when walking would cost us little.
"""

import math
import re
from dataclasses import dataclass, field

from arena_kit.cost import RELATIONSHIP_GOALS, complete_offer

from negotiator.data import Evidence, WorldData
from negotiator.groundtruth import GroundTruth, estimate
from negotiator.guards import accept_problems
from negotiator.menu import acceptance, priced_menu, proposed_values, requests_in, satisfies, structure_key
from negotiator.profile import SupplierProfile, build_profile
from negotiator.session import Negotiation
from negotiator.strategy.base import Decision
from negotiator.strategy.baseline import SIGNATURE, BaselineStrategy, describe
from negotiator.telemetry import log


@dataclass(frozen=True)
class Policy:
    anchor: float  # first ask: this share below the reference price
    beta: float  # Boulware exponent: > 1 concedes late
    reciprocity: float  # share of the supplier's last concession (in C) we answer at most
    markup: float  # floor vs the supplier's full cost when its margin does not cost us C (suppliers have
    # sold below full cost to keep volume: a leverage floor may sit a little under it)
    claims_first: int = 3  # arguments in the first e-mail
    trade_first: tuple[str, ...] = ()  # levers to offer the supplier, in order


POLICIES = {
    "leverage": Policy(anchor=0.10, beta=3.0, reciprocity=0.6, markup=-0.03),
    "routine": Policy(anchor=0.07, beta=2.0, reciprocity=0.8, markup=0.0),
    "quality_first": Policy(anchor=0.05, beta=2.5, reciprocity=0.8, markup=0.0, trade_first=("contract_months",)),
    "stabilise": Policy(
        anchor=0.04, beta=2.0, reciprocity=1.0, markup=0.0, trade_first=("contract_months", "volume_per_year")
    ),
    "secure_supply": Policy(
        anchor=0.03, beta=1.8, reciprocity=1.0, markup=0.0, trade_first=("contract_months", "volume_per_year")
    ),
}
DEFAULT_POLICY = POLICIES["routine"]
STALL_EPS = 0.0005  # a C move below 0.05 % is no move
DONE_EPS = 0.001  # our ask within 0.1 % of their C: nothing left worth a round
MAX_ANCHOR = 0.15  # the first ask never lies more than 15 % below the supplier's quote ...
MAX_ANCHOR_LEVERAGE = 0.18  # ... 18 % in leverage: floors sat 19-31 % under (D02, P05, P18), but a deeper first
# ask lost credibility (P05: Hrvelec walked after four rounds at 24-25 against its 34)
# without a cost estimate, anchor this far under the reference price (baseline v2's sandbox-tested depths)
GUESS_ANCHOR = {"leverage": 0.18, "routine": 0.12, "quality_first": 0.10, "stabilise": 0.06, "secure_supply": 0.05}
UNDER_FLOOR = 0.02  # the first ask sits this far under the supplier's estimated floor
# what a supplier's e-mail says between the lines (the replay of case:D01/D02 showed both kinds)
ROOM_SIGNALS = re.compile(
    r"can move further|come back to you on price|free capacity|step from your side|bridge the (?:remaining )?gap"
    r"|clarify this internally|happy to discuss|open to|we could consider|room to",
    re.I,
)
FIRM_SIGNALS = re.compile(
    r"cannot (?:reduce|lower|go) (?:the price )?(?:any )?further|all possible concessions"
    r"|no further (?:room|concession)|our (?:absolute )?limit|not able to move|this is our last"
    r"|must (?:\w+ )?(?:hold|maintain) our (?:current )?offer|does not allow us to reduce|unable to (?:reduce|improve)"
    r"|we maintain our (?:current )?offer",
    re.I,
)
REANCHOR = 0.10  # an ungrounded floor the supplier undercuts at once: ask again this far under its price
BIG_STEP = 0.04  # a supplier move of 4 %+ in one round says it had room
UPPER_ROOM = 0.06  # the upper bound sits at least this far above our first ask
MIN_STEP = 0.004  # every message moves at least 0.4 % of C: these bots punish a repeated offer
MAX_SPREAD = 0.08  # options of one message stay within 8 % of each other's price


def reply_signals(body: str) -> dict:
    """Room or firmness in the supplier's own words - a `final_offer` that asks for our step is no last word."""
    return {"room": bool(ROOM_SIGNALS.search(body or "")), "firm": bool(FIRM_SIGNALS.search(body or ""))}


EVIDENCE_FIRST = {  # profile trait / goal -> evidence kinds to put first
    "not_tracking_costs": ["index"],
    "open_book": ["should_cost"],
    "quality_first": ["quality", "scorecard"],
}


@dataclass
class Plan:
    supplier_id: str
    name: str
    policy: Policy
    profile: SupplierProfile
    open_c: float
    target_c: float
    floor_price: float | None
    full_cost: float | None
    gt: GroundTruth | None = None
    lower_c: float = -math.inf  # C at the supplier's estimated floor: take it at once
    upper_c: float = math.inf  # the most we accept when the deal is at risk - never said, never asked for
    evidence: list[Evidence] = field(default_factory=list)
    banned_kinds: set[str] = field(default_factory=set)
    our_c: list[float] = field(default_factory=list)  # the C we asked for, per round
    last_claims: list[Evidence] = field(default_factory=list)
    seen_replies: int = 0
    stalls: int = 0
    probed_final: bool = False
    price_matched: bool = False
    requests: set[str] = field(default_factory=set)  # levers the supplier asked for in its e-mails
    last_keys: frozenset = frozenset()  # the structures and prices we sent last
    offered: dict = field(default_factory=dict)  # structure -> the highest price we offered for it
    volume_proved: bool = False
    proposed: dict = field(default_factory=dict)  # field -> values the supplier put on its own sheets
    text_price: float | None = None  # a lower price it wrote in the text but not on a sheet
    text_price_used: bool = False
    alternatives_taken: set = field(default_factory=set)
    request_counts: dict = field(default_factory=dict)  # lever -> replies that asked for it
    reanchored: bool = False
    asked_breakdown: bool = False
    breakdown_read: bool = False


class TacticalStrategy(BaselineStrategy):
    name = "tactical"

    def __init__(self, data: WorldData | None = None, llm=None) -> None:
        super().__init__(data, llm)
        self.tplans: dict[str, Plan] = {}
        self.banned_case_kinds: set[str] = set()  # contradicted: never again in this case

    # ------------------------------------------------------------------ prepare
    def prepare(self, neg: Negotiation) -> None:
        buyer = neg.buyer
        goal = buyer.get("category_goal", "routine")
        parts = neg.case.get("parts", [])
        current = buyer.get("current_unit_price")
        for sid, thread in neg.threads.items():
            _, terms = thread.standing
            profile = build_profile(self.data, sid, neg.case)
            policy = self._policy(goal, profile)
            full_cost = self._full_cost(parts, sid)
            self._estimate_supplier(neg, sid, full_cost, profile)
            floor = self._floor(neg, full_cost, policy)
            open_c = neg.cost(sid, terms)
            gt = estimate(self.data, neg.case, sid, terms.get("unit_price"), tuple(profile.traits))
            if gt.lower and goal not in RELATIONSHIP_GOALS:
                floor = gt.lower  # one floor: the ground truth's (it knows below-cost sellers and countries)
            target_c = self._target_c(neg, sid, terms, policy, profile, floor, current, gt)
            plan = Plan(sid, self._name(sid), policy, profile, open_c, target_c, floor, full_cost, gt)
            plan.lower_c, plan.upper_c = self._bounds_c(neg, sid, terms, gt, target_c, open_c)
            plan.evidence = self._evidence(neg, sid, terms.get("unit_price"), current) if terms else []
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
        anchor, beta, recip = base.anchor, base.beta, base.reciprocity
        trade = list(base.trade_first)
        if p.has("underutilised"):
            anchor, beta = anchor + 0.03, beta + 0.5
        markup = base.markup
        if p.has("full_order_book") or p.has("below_cost"):
            anchor = max(0.02, anchor - 0.03)
            markup = max(markup, 0.0)  # no room under its cost: it is already there or does not need us
        if p.has("price_frozen"):
            anchor = max(0.02, anchor - 0.02)
        if p.has("approval_ladder"):
            beta += 0.5  # it moves in small approved steps: no reason for us to move fast
        if p.has("cash_short"):
            trade.insert(0, "payment_days")
        if p.has("wants_volume") or p.has("full_order_book") or p.has("price_frozen"):
            trade += ["contract_months", "volume_per_year"]
        if p.has("we_pay_late") or p.has("relationship"):
            recip = min(1.0, recip + 0.1)
        return Policy(anchor, beta, recip, markup, base.claims_first, tuple(dict.fromkeys(trade)))

    def _evidence(self, neg, sid, open_price, current):
        out = super()._evidence(neg, sid, open_price, current)
        if self.data:
            out += self.data.evidence_orders(neg.case.get("parts", []), sid, open_price)
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

    def _estimate_supplier(self, neg: Negotiation, sid: str, full_cost: float | None, p: SupplierProfile) -> None:
        """Our estimate of the supplier for the relationship term in C (stabilise, secure_supply)."""
        if neg.buyer.get("category_goal") not in RELATIONSHIP_GOALS or not full_cost:
            neg.supplier_estimates.pop(sid, None)
            return
        std = neg.threads[sid].standard_terms
        if not {"payment_days", "incoterm"} <= std.keys():
            return
        rate = neg.buyer.get("interest_rate", 0.08)
        neg.supplier_estimates[sid] = {
            "full_cost": full_cost,
            "interest_rate": rate * 2 if p.has("cash_short") else rate,  # money now is dearer to it
            "usual_rate": rate,
            "standard": std,
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
        ref = min(open_price, current) if current else open_price
        goal = neg.buyer.get("category_goal", "routine")
        if gt and gt.lower and gt.grounded:
            candidates = [gt.lower * (1 - UNDER_FLOOR)]
        else:  # a guessed floor is no anchor: go as deep as these bots tolerate
            candidates = [ref * (1 - max(policy.anchor, GUESS_ANCHOR.get(goal, 0.1)))]
        alt_price = ((neg.buyer.get("alternative") or {}).get("terms") or {}).get("unit_price")
        if alt_price and alt_price < open_price:
            candidates.append(alt_price * 0.98)
        cap = MAX_ANCHOR_LEVERAGE if goal == "leverage" else MAX_ANCHOR
        price = max(min(candidates), open_price * (1 - cap))  # deeper reads as an insult, not an ask
        # no hard floor for strategic suppliers: the relationship term already prices a squeeze in C, and
        # our cost estimate can sit above its real one (P02: should-cost 380 over a 371 quote, C_best ~364)
        price = min(price, open_price)
        ideal = complete_offer(neg.case, self._optimise(neg, sid, {**terms, "unit_price": round(price, 2)}))
        return min(neg.cost(sid, ideal), neg.cost(sid, terms))

    def _bounds_c(self, neg, sid, terms, gt: GroundTruth, target_c: float, open_c: float) -> tuple[float, float]:
        """The bounds in C, on our C-optimal terms: a fair price on poor terms (a short contract that
        leaves need uncovered, early payment, dear freight) must not pass as a good deal."""
        lower_c, upper_c = -math.inf, min(open_c, neg.c_alt)
        if gt.lower:
            lower_c = neg.cost(sid, self._ideal(neg, sid, terms, gt.lower))
        if gt.upper:
            upper_c = min(upper_c, neg.cost(sid, self._ideal(neg, sid, terms, gt.upper)))
        # room to concede above our first ask, whatever the calibration says (P05: an 18 % anchor over a 22 %
        # floor left upper == anchor and only 0.4 % steps) - never above its quote or our alternative
        return lower_c, min(max(upper_c, target_c * (1 + UPPER_ROOM)), open_c, neg.c_alt)

    def _ideal(self, neg, sid, terms: dict, price: float) -> dict:
        return complete_offer(neg.case, self._optimise(neg, sid, {**terms, "unit_price": round(price, 2)}))

    # ------------------------------------------------------------------ per thread
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
        rounds_left = neg.case.get("round_limit", 10) - t.rounds_used
        if rounds_left <= 1:
            return Decision.hold(supplier_id, "last round: keep it for the close")
        if neg.seconds_to_deadline() < 120:
            return Decision.hold(supplier_id, "the deadline is near")

        their_c = neg.cost(supplier_id, theirs)
        signals = reply_signals(t.latest.get("body", ""))
        # the lower bound is where we anchor, not where we stop: below it we keep asking - the supplier
        # ends it with a stall or a final offer, and only it knows its real floor
        if their_c <= plan.lower_c or self._undercut_after_big_step(neg, supplier_id, plan, theirs):
            if reanchor := self._reanchor(neg, supplier_id, plan, theirs, their_c):
                return reanchor
        if alt := self._take_alternative(neg, supplier_id, plan):
            return alt  # its cheapest sheet is an alternative: the arena closes on the primary one, so ask for it
        last_word = t.status == "final_offer" or (signals["firm"] and t.rounds_used > 0)
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
        if match := self._price_match(neg, supplier_id, plan, theirs, their_c):
            return match

        if plan.stalls >= 2 and their_c <= plan.upper_c:
            return Decision.hold(supplier_id, "stalled inside our upper bound: take it", their_c=their_c)
        if plan.stalls >= 3:
            return Decision.hold(supplier_id, "the supplier stopped moving", their_c=their_c)
        ask_c = self._next_c(neg, supplier_id, plan, their_c)
        if ask_c >= their_c * (1 - DONE_EPS):
            return Decision.hold(supplier_id, "their offer meets our ask", ask_c=ask_c, their_c=their_c)
        return self._offer(neg, supplier_id, plan, theirs, ask_c, their_c)

    def _learn(self, neg: Negotiation, sid: str, plan: Plan) -> None:
        """Read what came back since we last looked: argument checks, stalls, a cost breakdown."""
        t = neg.threads[sid]
        replies = t.supplier_messages
        for reply in replies[plan.seen_replies :]:
            for res in reply.get("claim_results") or []:
                i, result = res.get("index"), res.get("result")
                if not isinstance(i, int) or not 0 <= i < len(plan.last_claims):
                    continue
                kind = plan.last_claims[i].kind
                if result == "contradicted":
                    self.banned_case_kinds.add(kind)
                elif result == "irrelevant":
                    plan.banned_kinds.add(kind)
            if not plan.breakdown_read:
                self._read_breakdown(neg, sid, plan, reply)
            asked = {r for r in requests_in(reply.get("body", "")) if r in neg.case["negotiable"]}
            for r in asked:
                plan.request_counts[r] = plan.request_counts.get(r, 0) + 1
            plan.requests |= asked
            for f, values in proposed_values(neg.case, reply.get("term_sheets") or []).items():
                plan.proposed.setdefault(f, [])
                plan.proposed[f] += [v for v in values if v not in plan.proposed[f]]
                if len(plan.proposed[f]) > 1:
                    plan.requests.add(f)  # it varies this field across its sheets: a lever it trades on
            sheet_prices = [s["terms"].get("unit_price") for s in reply.get("term_sheets") or []]
            sheet_prices = [p for p in sheet_prices if p]
            said = [
                p
                for p in prices_in_text(reply.get("body", ""))
                if sheet_prices and 0.6 * min(sheet_prices) < p < min(sheet_prices) - 0.004
            ]
            if said:
                plan.text_price = min(said)  # "I am dropping the price to EUR 28.00" on a 29.09 sheet (P05)
            sheets = reply.get("term_sheets") or []
            if sheets and sheets[0]["terms"].get("index_clause"):
                plan.requests.add("index_clause")  # it proposed one: it wants one
        if len(replies) > plan.seen_replies and plan.seen_replies > 0:
            path = [neg.cost(sid, (m.get("term_sheets") or [{}])[0].get("terms") or {}) for m in replies]
            path = [c for c in path if math.isfinite(c)]
            if len(path) >= 2:
                moved = path[-2] - path[-1]
                plan.stalls = plan.stalls + 1 if moved <= path[-2] * STALL_EPS else 0
        plan.seen_replies = len(replies)

    def _read_breakdown(self, neg: Negotiation, sid: str, plan: Plan, reply: dict) -> None:
        """A cost breakdown XLSX: the supplier's own cost per unit is the floor it will not go below."""
        for att in reply.get("attachments") or []:
            name = (att.get("name") or "").lower()
            if not name.endswith(".xlsx") or "breakdown" not in name or not att.get("text"):
                continue
            full = parse_breakdown(att["text"])
            price = neg.threads[sid].standing[1].get("unit_price")
            if not full or not price or not 0.3 * price < full < price * 1.05:
                continue
            plan.breakdown_read = True
            plan.full_cost = full
            if plan.gt and neg.buyer.get("category_goal") not in RELATIONSHIP_GOALS:
                floor = round(full * (1 + plan.policy.markup), 2)
                if plan.gt.lower is None or floor < plan.gt.lower:  # it told us it has more room: use it
                    plan.gt.lower, plan.gt.grounded = floor, True
                    _, theirs = neg.threads[sid].standing
                    plan.lower_c = neg.cost(sid, self._ideal(neg, sid, theirs, floor))
                    plan.target_c = min(plan.target_c, plan.lower_c)
            # where its margin costs us C, the relationship term now prices it exactly; elsewhere the
            # breakdown is its own account of cost - information, not a floor that forces our hand
            self._estimate_supplier(neg, sid, full, plan.profile)
            neg.recorder.event(
                "breakdown_read", session_id=neg.session_id, supplier_id=sid, full_cost=full, floor=plan.floor_price
            )
            log.info("%s: cost breakdown says full cost %.2f, floor %s", sid, full, plan.floor_price)

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
        if plan.stalls == 1:
            step = max(min_step, 0.15 * gap)  # no move from it: a visible step, not a "small bump"
        elif plan.stalls >= 2:
            step = max(by_time * 0.5, 0.25 * gap)  # break the deadlock
        else:
            # a real counter-step: at least half of its last move (cent steps read as no movement)
            step = min(plan.policy.reciprocity * max(their_move, 0.0), max(by_time, 0.5 * max(their_move, 0.0)))
            step = max(step, min_step)
        return min(last + step, their_c, plan.upper_c)  # the upper bound is never asked for beyond

    def _round_budget(self, neg: Negotiation, sid: str) -> int:
        """Messages we can still expect to play in this thread: the round limit, or the clock."""
        t = neg.threads[sid]
        limit = neg.case.get("round_limit", 10)
        left = neg.seconds_to_deadline() - 120  # the runner closes before the cap
        if math.isfinite(left):
            per_round = max(15.0, neg.recorder.metrics.mean("supplier.reply_seconds") or 30.0) + 3.0
            limit = min(limit, t.rounds_used + max(1, int(left / per_round)))
        return limit

    def _their_c_path(self, neg: Negotiation, sid: str) -> list[float]:
        out = []
        for m in neg.threads[sid].supplier_messages:
            sheets = m.get("term_sheets") or []
            if sheets:
                c = neg.cost(sid, sheets[0]["terms"])
                if math.isfinite(c):
                    out.append(c)
        return out

    def _may_probe(self, neg: Negotiation, sid: str, their_c: float) -> bool:
        """Push a final offer once - only when its walking away would cost us little."""
        t = neg.threads[sid]
        if neg.case.get("round_limit", 10) - t.rounds_used < 2 or neg.seconds_to_deadline() < 180:
            return False
        for other, ot in neg.threads.items():
            if other != sid and self.tplans[other].probed_final and ot.live:
                return False  # one rival is already being pushed: this one stays our safe fallback
        for other, ot in neg.threads.items():
            if other != sid and ot.live and ot.standing[0] and not accept_problems(neg, other, ot.standing[0]):
                return True  # a rival offer we could take instead
        return False  # room words alone are no reason: "bridge the remaining gap" (P18) ended in a walk-away

    # ------------------------------------------------------------------ the offer
    def _undercut_after_big_step(self, neg: Negotiation, sid: str, plan: Plan, theirs: dict) -> bool:
        """It came down to (or under) our own ask in one big step: the back office of case:D02 read
        "I give half the step now and check the rest" - there is more to get."""
        prices = neg.threads[sid].price_path()
        ours = neg.threads[sid].our_price_path()
        if len(prices) < 2 or not ours or theirs.get("unit_price") is None:
            return False
        step = (prices[-2] - prices[-1]) / prices[-2]
        return theirs["unit_price"] <= ours[-1] * 1.005 and step >= BIG_STEP

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
        best_c = neg.cost(sid, best)
        if best_c >= neg.cost(sid, primary) * (1 - 0.002):
            return None
        # only when we would close anyway - in round 1 its alternative is an opening, not a deal (P18 dry run)
        closing = (
            t.status == "final_offer"
            or reply_signals(t.latest.get("body", ""))["firm"]
            or plan.stalls >= 1
            or best_c <= plan.upper_c
            or self._round_budget(neg, sid) - t.rounds_used <= 2
        )
        if not closing:
            return None
        std = t.standard_terms
        sheet = complete_offer(
            neg.case, {**{k: v for k, v in std.items() if k in neg.case["negotiable"]}, **primary, **best}
        )
        if not neg.keeps_must_haves(sid, sheet) or neg.cost(sid, sheet) >= neg.c_alt:
            return None
        plan.alternatives_taken.add(best_id)
        plan.our_c.append(neg.cost(sid, sheet))
        plan.last_keys = self._keys([{"terms": sheet}])
        body = "\n".join(
            [
                f"Dear {plan.name} team,",
                "",
                "thank you. We accept your alternative as stated below and are ready to place the order on it.",
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

    def _take_agreed(self, neg: Negotiation, sid: str) -> Decision | None:
        """It agreed to our terms: if no other live thread offers less, close now - holding it while others
        talk cost P05 two timeouts and nearly the deal."""
        offer_id, terms = neg.threads[sid].standing
        if not offer_id or accept_problems(neg, sid, offer_id):
            return None
        c = neg.cost(sid, terms)
        for other, ot in neg.threads.items():
            if other == sid or not ot.live:
                continue
            _, their = neg.best_offer(other)
            if their and neg.cost(other, their) < c * 0.98:
                return None  # a rival is clearly cheaper: keep talking there
        return Decision(
            "accept", sid, term_sheet_id=offer_id, rationale={"c": c, "why": "agreed and the best on the table"}
        )

    def _text_price_offer(self, neg: Negotiation, sid: str, plan: Plan) -> Decision | None:
        """It wrote a lower price than it put on its sheet: take it at its word, on its own terms, once."""
        if not plan.text_price or plan.text_price_used or not self._may_push(neg, sid):
            return None
        _, theirs = neg.best_offer(sid)
        if not theirs or plan.text_price >= (theirs.get("unit_price") or 0):
            return None
        plan.text_price_used = True
        sheet = complete_offer(neg.case, {**theirs, "unit_price": round(plan.text_price, 2)})
        if not neg.keeps_must_haves(sid, sheet):
            return None
        plan.our_c.append(neg.cost(sid, sheet))
        plan.last_keys = self._keys([{"terms": sheet}])
        body = "\n".join(
            [
                f"Dear {plan.name} team,",
                "",
                f"thank you - you wrote that you can go to EUR {plan.text_price:,.2f}. We accept that price on your "
                "terms below and are ready to place the order.",
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

    def _may_push(self, neg: Negotiation, sid: str) -> bool:
        t = neg.threads[sid]
        return neg.case.get("round_limit", 10) - t.rounds_used >= 2 and neg.seconds_to_deadline() > 150

    def _reanchor(self, neg, sid, plan: Plan, theirs: dict, their_c: float) -> Decision | None:
        """It came under a floor we only guessed: our guess was timid. Ask again under its new price, once."""
        if plan.reanchored or not self._may_push(neg, sid):
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
        return self._offer(neg, sid, plan, theirs, ask_c, their_c)

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
            or (gt.grounded and gt.lower is not None and price <= gt.lower * (1 + UNDER_FLOOR))  # at its floor
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
        sheets = [{"terms": matched}]
        plan.our_c.append(neg.cost(sid, matched))
        plan.last_keys = self._keys(sheets)
        lines = [
            f"Dear {plan.name} team,",
            "",
            f"thank you. We can accept your price of EUR {price:,.2f} - on the terms below, which complete the "
            "agreement for our full requirement."
            + self._answered(neg, plan, matched, theirs)
            + (" " + proof[0] if (proof := self._volume_proof(neg, plan)) else ""),
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
        plan.our_c.append(neg.cost(sid, sheets[0]["terms"]))
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
        menu = priced_menu(case, theirs, lambda terms: self._iso_cost_price(neg, sid, terms, ask_c))
        valid, under_floor = [], []
        for terms in menu:
            if not neg.keeps_must_haves(sid, terms) or neg.cost(sid, terms) >= their_c:
                continue
            if plan.floor_price and terms["unit_price"] < plan.floor_price * (1 - UNDER_FLOOR - 0.01):
                under_floor.append(terms)  # far below what it can sell at: an insult
                continue
            valid.append(terms)
        pool = valid or under_floor  # never go silent: an offer under its floor beats none
        if not pool:
            return []
        repeated = {r for r, n in plan.request_counts.items() if n >= 2}
        meets = [t for t in pool if all(satisfies(case, t, theirs, r, plan.proposed) for r in repeated)]
        if repeated and meets:
            pool = meets  # an option it has refused twice is no option

        def rank(t):
            return (*acceptance(case, t, theirs, plan.requests, plan.proposed), t["unit_price"])

        for t in pool:  # a structure offered before never comes back at a lower price
            before = plan.offered.get(structure_key(t))
            if before is not None and t["unit_price"] < before:
                t["unit_price"] = before
        pool = [t for t in pool if neg.cost(sid, t) < their_c] or pool
        top = max(t["unit_price"] for t in pool)
        pool = [t for t in pool if t["unit_price"] >= top * (1 - MAX_SPREAD)]
        picked = [max(pool, key=lambda t: t["unit_price"]), max(pool, key=rank)]
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
        out, keys = [], set()
        for t in picked:
            if structure_key(t) not in keys:
                keys.add(structure_key(t))
                out.append({"terms": t})
                plan.offered[structure_key(t)] = max(plan.offered.get(structure_key(t), 0.0), t["unit_price"])
        return out[:3]

    def _trade_terms(self, neg, sid, plan, ideal: dict) -> dict | None:
        """Our terms with the levers the supplier values given to it (the price pays for them)."""
        options = neg.case.get("term_options", {})
        negotiable = neg.case["negotiable"]
        trade = dict(ideal)
        changed = False
        for f in plan.policy.trade_first or ("payment_days",):
            if f not in negotiable or not options.get(f):
                continue
            values = [v for v in options[f] if v is not None]
            if not values:
                continue
            if f == "payment_days":
                pick = min(values)  # early payment: cash for the supplier
            elif f == "contract_months":
                pick = max(values)  # security; beyond our horizon it costs us nothing
            elif f == "volume_per_year":
                need = neg.buyer.get("need_per_year", 0)
                fitting = [v for v in values if v <= need] or values
                pick = max(fitting)
            else:
                continue
            if trade.get(f) != pick and neg.keeps_must_haves(sid, {**trade, f: pick}):
                trade[f] = pick
                changed = True
        return trade if changed else None

    # ------------------------------------------------------------------ arguments and words
    def _choose_claims(self, neg, sid, plan, first: bool) -> list[Evidence]:
        banned = plan.banned_kinds | self.banned_case_kinds
        if neg.buyer.get("category_goal") != "quality_first":
            banned = banned | {"scorecard"}
        pool = [e for e in plan.evidence if e.kind not in banned]
        rival = self._rival_evidence(neg, sid)
        if rival and "rival_offer" not in banned:
            pool.insert(0, rival)
        prefer: list[str] = []
        for key in [*sorted(plan.profile.traits), neg.buyer.get("category_goal", "")]:
            prefer += EVIDENCE_FIRST.get(key, [])
        pool.sort(key=lambda e: (e.kind not in prefer, -e.strength))
        picked, kinds = [], set()
        limit = plan.policy.claims_first if first else 1
        for e in pool:
            if len(picked) >= limit:
                break
            if e.kind == "rival_offer":
                if any((sid, r) in self.used_rival_refs for r in e.refs):
                    continue
            elif any(r in self.used_refs for r in e.refs) or e.kind in kinds:
                continue
            picked.append(e)
            kinds.add(e.kind)
        for e in picked:
            if e.kind == "rival_offer":
                self.used_rival_refs.update((sid, r) for r in e.refs)
            else:
                self.used_refs.update(e.refs)
        return picked

    def _write(self, neg, plan: Plan, sheets: list[dict], claims: list[Evidence], probe: bool) -> dict:
        p, case = plan.profile, neg.case
        first = neg.threads[plan.supplier_id].rounds_used == 0
        lines = [f"Dear {plan.name} team,", ""]
        if first:
            if p.has("relationship") or neg.buyer.get("category_goal") in RELATIONSHIP_GOALS:
                lines.append("thank you for your quote and for the reliable cooperation we value.")
            else:
                lines.append("thank you for your quote. We have reviewed it carefully against our data.")
        elif probe:
            lines.append("thank you - we are close. One last step from your side and we can sign.")
        elif plan.stalls:
            lines.append("thank you for your reply. We see no movement yet, so we propose a different structure.")
        else:
            lines.append("thank you for your reply and the step towards us. We move as well.")
        lines += [c.sentence for c in claims]
        if not plan.asked_breakdown and p.has("open_book") and not plan.breakdown_read:
            lines.append("Could you send us a cost breakdown for this part?")
            plan.asked_breakdown = True
        if len(sheets) > 1:
            if p.has("cash_short") and any(
                (sh["terms"].get("payment_days") or 999)
                < (neg.threads[plan.supplier_id].standing[1].get("payment_days") or 0)
                for sh in sheets
            ):
                lines.append("If faster payment helps you, one option below pays early.")
            elif any(
                f in plan.policy.trade_first and f in case["negotiable"] for f in ("contract_months", "volume_per_year")
            ):
                lines.append("We are ready to commit for longer if the price reflects it.")
        theirs = neg.threads[plan.supplier_id].standing[1]
        for i, sheet in enumerate(sheets if plan.requests else []):
            if said := self._answered(neg, plan, sheet["terms"], theirs, f"Option {chr(65 + i)}").strip():
                lines.append(said)
                break
        volume = self._volume_proof(neg, plan)
        if volume:
            lines.append(volume[0])
        lines += ["", "We can award on any of these options:" if len(sheets) > 1 else "Our proposal:"]
        for i, sheet in enumerate(sheets):
            lines.append(f"Option {chr(65 + i)}: {describe(case, sheet['terms'])}")
        lines += ["", SIGNATURE]
        return {
            "subject": case.get("title", "Your quote"),
            "body": "\n".join(lines),
            "term_sheets": sheets,
            "refs": sorted({r for c in claims for r in c.refs} | ({volume[1]} if volume else set())),
        }

    def _volume_proof(self, neg, plan: Plan) -> tuple[str, str] | None:
        """ "Which volume can you commit to?" (the bots' most common question) - answered once, with the
        forecast we share with suppliers, by ID, so it reads as documentation and not as a claim."""
        if "volume_per_year" not in plan.requests or plan.volume_proved or not self.data:
            return None
        if any(r.startswith("fc:") for r in self.used_refs):
            plan.volume_proved = True  # a duplicate earns nothing ("we have already taken that data into account")
            return None
        parts = neg.case.get("parts") or []
        if len(parts) != 1:
            return None
        num = parts[0].split(":", 1)[-1]
        ids = sorted(k for k in self.data.facts if k.startswith(f"fc:{num}@"))
        if not ids:
            return None
        fc = self.data.facts[ids[-1]]
        change, volume = fc.get("change_pct"), fc.get("volume_per_year")
        if change is None or change < 0:
            return None  # a falling forecast is no argument for a better price
        plan.volume_proved = True
        self.used_refs.add(ids[-1])
        commit = f" and we commit to {volume:,} units a year" if volume else ""
        return (
            f"Our demand forecast for this part, shared with you, rose {change:+.1f}% ({ids[-1]}){commit}.",
            ids[-1],
        )

    @staticmethod
    def _answered(neg, plan: Plan, terms: dict, theirs: dict, label: str = "Option A") -> str:
        """One sentence on the requests this offer answers - and on a request the case does not let us meet."""
        words = {
            "index_clause": "the index clause you asked for",
            "contract_months": "the longer commitment you asked for",
            "volume_per_year": "a binding volume",
            "payment_days": "the payment term you proposed",
            "ppm_commitment": "the quality commitment you proposed",
            "chargeback_eur_per_complaint": "the chargeback you proposed",
            "lead_time_days": "your lead time",
            "incoterm": "your delivery terms",
            "effective_date": "your start date",
            "tooling_eur": "your tooling terms",
        }
        met = [
            words[r]
            for r in sorted(plan.requests)
            if r in words and satisfies(neg.case, terms, theirs, r, plan.proposed)
        ]
        return f" {label} includes {' and '.join(met)}." if met else ""

    def keepalive(self, neg: Negotiation, supplier_id: str) -> dict | None:
        """A held thread's clock runs while others negotiate: a harmless question keeps it alive."""
        t = neg.threads[supplier_id]
        if neg.case.get("round_limit", 10) - t.rounds_used <= 2:
            return None
        plan = self.tplans[supplier_id]
        asks = [
            "could you confirm your delivery capacity for our annual volume?",
            "could you confirm the lead time you can commit to for the first call-off?",
            "could you confirm the validity of your offer?",
        ]
        question = asks[t.rounds_used % len(asks)]
        return {
            "subject": neg.case.get("title", "Your quote"),
            "body": f"Dear {plan.name} team,\n\nthank you. While we complete our evaluation: {question}\n\n{SIGNATURE}",
        }

    # ------------------------------------------------------------------ closing
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


PRICE_IN_TEXT = re.compile(
    r"(?:drop|lower|reduce|go(?: down)? to|come down to|can do|offer you)[^.€]{0,50}(?:€|EUR)\s?(\d[\d,]*\.?\d*)", re.I
)


def prices_in_text(body: str) -> list[float]:
    out = []
    for raw in PRICE_IN_TEXT.findall(body or ""):
        try:
            out.append(float(raw.replace(",", "")))
        except ValueError:
            pass
    return out


def parse_breakdown(text: str) -> float | None:
    """Full cost per unit from a cost-breakdown sheet: the EUR elements except margin and totals."""
    skip = ("margin", "profit", "gewinn", "unit price", "price", "total", "sum", "element")
    total, found = 0.0, False
    for line in text.splitlines():
        cells = [c.strip() for c in line.split("|")]
        if len(cells) < 2 or not cells[0] or cells[0].startswith("["):
            continue
        if any(s in cells[0].lower() for s in skip):
            continue
        try:
            value = float(cells[1])
        except ValueError:
            continue
        total += value
        found = True
    return round(total, 2) if found and total > 0 else None


def _k(value: float) -> str:
    return f"{value:,.0f}" if math.isfinite(value) else "inf"
