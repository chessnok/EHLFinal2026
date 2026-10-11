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
`final_offer` is probed once with a trade when walking would cost us little. Our estimate of its floor
never ends an open thread: the supplier does (a final offer, firm words, a stall) or the rounds run out.
Conduct (conduct.py): honest, sourced, no empty threats, the supplier's margin respected - code-checked on send.
"""

import math
import re
from dataclasses import dataclass, field

from arena_kit.cost import RELATIONSHIP_GOALS, closing_terms, complete_offer, supplier_value, total_cost

from negotiator.belief import FloorBelief
from negotiator.data import Evidence, WorldData
from negotiator.groundtruth import GroundTruth, estimate
from negotiator.guards import accept_problems
from negotiator.ledger import CITED_DRIVER, argument_key, arguments_read, data_facts, reply_facts
from negotiator.menu import acceptance, priced_menu, proposed_values, requests_in, satisfies, structure_key
from negotiator.profile import SupplierProfile, build_profile
from negotiator.reply_parser import ReplyFacts, parse_reply
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
ANCHOR_WITH_LEVERS = 0.25  # first ask 25 % under the quote where competition, material or capacity give a lever
ANCHOR_DATA_EXTRA = 0.05  # how much deeper the data may take the first ask
# The supplier's full cost as a share of its own plant's should-cost. The margin charges the arena recorded on
# P01, P02 and P03 (14 deals up to runs.md P-15) put it at 0.975-0.980; company.md gives the estimate an error of
# about 5 %. Too high a cost only leaves price on the table, too low a cost scores 0 - so the upper end.
SHOULD_COST_SHARE = 0.98
# What money now is worth to a supplier short of cash, as a multiple of our rate: P01's charges at 14, 45 and
# 60 days (runs.md P-2 to P-15) fit 9.6 % a year against our 8 %.
CASH_SHORT_RATE = 1.2
# Without its own plant's should-cost (the package has one for 18 suppliers) a strategic supplier's cost is
# guessed: its opening price less the sustainable margin, x SHOULD_COST_SHARE. Against the full cost the arena's
# recorded charges imply it sat +1.3 % (P01), -1.4 % (P02), +0.3 % (P03) and +3.5 % (D01) off. The guess is a floor
# only - no ask and no accept under the price that costs us least with the guessed charge - so nothing goes the way
# of P02 (EUR 345.39 against a should-cost of 380: charge EUR 179k, score 0); prices and concessions otherwise
# follow C without it, as an error of a few per cent in a charge inside C moved D01 from 0.749 to 0.627 (S-26).
RELATIONSHIP_COST_FLOOR = 0.95  # never ask a strategic supplier below 95 % of its should-cost
YES_ROOM_SHARE = 0.01  # ... and at most this share of the room (`open_c - target_c`)
CHEAP_YES = 0.002  # `cheap_yes`: a condition of its we accept at our price when it costs us at most this share of C
GUESS_SLACK = 0.04  # `guess_slack`: the guessed cost floor less its largest observed error (D01 +3.5 %)
ANCHOR_RELATIONSHIP = 0.04  # stabilise / secure_supply: below its margin the deal costs us
ANCHOR_ROUTINE = 0.13  # routine goal: a deeper first ask is answered with a final offer
ANCHOR_PRICE_ONLY = 0.10  # ... and 10 % where only the price of a running relationship is at stake
MAX_ANCHOR = 0.15  # (kept for the experiments that import it)
SOFT_ANCHOR = 0.5  # `soft_anchor`: the first ask's depth as a share of the usual one
MAX_ANCHOR_LEVERAGE = 0.18  # ... 18 % in leverage: floors sat 19-31 % under (D02, P05, P18), but a deeper first
# ask lost credibility (P05: Hrvelec walked after four rounds at 24-25 against its 34)
# without a cost estimate, anchor this far under the reference price (baseline v2's sandbox-tested depths)
GUESS_ANCHOR = {"leverage": 0.18, "routine": 0.12, "quality_first": 0.10, "stabilise": 0.06, "secure_supply": 0.05}
UNDER_FLOOR = 0.02  # the first ask sits this far under the supplier's estimated floor
ALT_ROOM_SHARE = 0.001  # its alternative must save this share of the room ...
ALT_MIN_EUR = 10.0  # ... and at least this much: below it a rounding of the sheet decides
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
APPROVAL_PENDING = re.compile(
    r"clarify (?:this |it )?internally|come back to you on (?:the )?price|my band|approv(?:e|al) (?:a|for) further|"
    r"check (?:the rest|internally)|discuss (?:this )?internally",
    re.I,
)
REANCHOR = 0.10  # an ungrounded floor the supplier undercuts at once: ask again this far under its price
BIG_STEP = 0.04  # a supplier move of 4 %+ in one round says it had room
UPPER_ROOM = 0.06  # the upper bound sits at least this far above our first ask
STOP_MARGIN = 0.01  # we take an offer within 1 % of where we expect the supplier to stop
MIN_STEP = 0.004  # every message moves at least 0.4 % of C: these bots punish a repeated offer
STOP_ROOM, UPPER_ROOM_SHARE = 0.05, 0.15  # the upper bound under a margin charge, as shares of the room
ANCHOR_SLACK = 0.25  # share of the room (quote to cost minimum) a deal on our deep first ask may cost
RELATIONSHIP_STEP = 0.25  # stabilise / secure_supply: our step as a share of the usual one
RELATIONSHIP_MIN_STEP = 0.05  # ... and at least this share of the room between its quote and our first ask
PATIENT_GAP = 0.01  # where we would meet its open offer early, we ask this far under it instead
PERSIST_STEP = 0.6  # `persistent`: our step as a share of the usual one ...
PERSIST_MIN = 0.006  # ... but never under 0.6 % of C: below 0.2 % the suppliers did not move at all (n 461)
MUST_CLAUSE = re.compile(
    r"must include an? [\w-]+ index clause|cannot offer a fixed price|requires? an? [\w-]+ "
    r"index clause",
    re.I,
)
LATE_COMPLAINTS_SINCE = "2025-10-01"  # `late_facts`: our complaints from here on (as `fresh_claims`)
FIGURES_ASKED = re.compile(
    r"Which figures is that based on|Please (?:send us|provide) the data|data that forms the basis", re.I
)
FIELD_WORDS = {
    "payment_days": "payment terms",
    "contract_months": "the contract length",
    "lead_time_days": "the lead time",
    "incoterm": "the delivery terms",
    "volume_per_year": "the volume",
    "index_clause": "an index clause",
    "effective_date": "the start date",
    "ppm_commitment": "the quality commitment",
    "chargeback_eur_per_complaint": "the chargeback",
    "tooling_eur": "tooling",
}
MAX_SPREAD = 0.08  # options of one message stay within 8 % of each other's price
EQUAL_C = 0.005  # ... and within 0.5 % of each other's C
OWN_GAIN = 1.5  # `own_structures`: its own price drop for a structure must exceed what the structure costs us by this


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
    guess: dict | None = None  # a guessed supplier estimate (_fallback_full_cost): a price floor, not in C
    floor_countered: bool = False
    belief: FloorBelief | None = None  # where this supplier will stop with us - recomputed after every reply
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
    counters: list = field(default_factory=list)  # facts from its own e-mails that answer it - spent first
    used_sentences: set = field(default_factory=set)
    lever_turn: bool = False  # this round our step goes into a structure we have not offered yet
    pressures: list = field(default_factory=list)  # cost drivers it says weigh on it
    request_counts: dict = field(default_factory=dict)  # lever -> replies that asked for it
    reanchored: bool = False
    asked_breakdown: bool = False
    breakdown_read: bool = False
    stop_c: float = math.inf  # where the belief expects it to stop with us (C)
    figures_asked: bool = False  # its last e-mail asked for the figures behind our proposal
    figures_reply: bool = False
    answered_fixed: set = field(default_factory=set)  # fixed fields whose request we have answered
    facts: ReplyFacts | None = None  # everything its last e-mail said (reply_parser)
    banned_series: set = field(default_factory=set)  # index series it said do not reach its costs
    price_terms: dict = field(default_factory=dict)  # terms its price is tied to ("calculated for 60 days")
    yes_line: str | None = None  # `cheap_yes`: the conditions of its we took at our price, said once
    justified_note: str | None = None  # its own drivers x shares against what its quote asks (said once)
    bigger_step: bool = False  # it called our last step too small
    spent_kinds: set = field(default_factory=set)  # argument kinds the arena called `duplicate` (fresh_args)
    market_backs_ask: bool = False  # the indices back its ask: no index argument in any round (late_facts too)


# Candidate changes, each switchable (`tactical+<flag>`) so practice can measure it on its own before it is
# adopted - one session per case is exact, the bots are deterministic. Measured and dropped on 10 Oct 2026:
# strict_final, belief_cap, probe_leader, anchor_cap25, dedupe_series, big_steps, floor_ask, wide_band,
# all_claims (the arena reads at most 3 arguments per message), anchor_rel
# (docs/benchmarks/2026-10-10-flags-paired.md).
FLAGS: dict[str, str] = {
    "alt_structure": "its alternative's structure goes into our next menu; its price only on an end signal or at "
    "our stop estimate, never from a bidder behind the leader",
    "fresh_claims": "from round 2 up to 3 fresh arguments (complaints, should-cost too); 'Which figures?' answered "
    "with figures",
    "persistent": "longer and steadier: our floor estimate ends nothing until two rounds are left, our steps are "
    "60 % of the usual but never under 0.6 % of C",
    "answers": "plain answers: the volume we need, an opener that matches its move, a fixed field said once, a "
    "clause it must have kept, no 'pays early' that is not",
    "fresh_args": "never an argument the arena already counted (one per kind, index series, part); one held back from "
    "the first e-mail for a later round; a bundle's orders per part",
    "guess_anchor": "a strategic supplier without its own should-cost gets the normal first ask, kept above the "
    "guessed cost floor (implies guess_slack): the 4 % cap was for P02, which has a should-cost floor",
    "no_guess_floor": "measurement only: no guessed cost floor at all (how much the floor costs D01)",
    "guess_slack": "the guessed cost floor of a strategic supplier without its own should-cost sits 4 % lower (its "
    "error was up to +3.5 %; D01 fell 0.969 -> 0.669 with it)",
    "rel_anchor4": "strategic suppliers keep the 4 % first ask even when their margin charge is estimated (the 10 % "
    "ask of 11c: D01 0.969 -> 0.669, P01 0.946 -> 0.901, P10 0.663 -> 0.647); the charge stays in C",
    "fast_pay": "it asked for faster payment and no option pays at the shortest term allowed (14 days): such an "
    "option joins at option A's C (P05 0.824 -> 0.865)",
    "cheap_yes": "yes to a condition it asked for (its own sheet value) in option A at our price, only where it "
    "costs us at most 0.2 % of C - never a yes to its price",
    "no_hedged_series": "a hedged supplier hears no argument on the series a clause option follows (P08 "
    "answered 'not our reality' in every session; the slot goes to the next argument) and no fact twice",
    "soft_anchor": "a higher first offer under routine and quality_first goals: the first ask half as deep "
    "(their suppliers moved 0.4-6 % in all; leverage suppliers 15-24 %, P05 36 -> 27.50, need the deep one)",
    "probe_final": "the old RFQ probe: one price push on a final offer behind a safe rival. Off since P-58 (P05 "
    "0.865 without it, as with it); in 442 sessions re-sending its own sheet was agreed 71 of 74 times, a push of 2 %+ "
    "walked 13 of 14, the probe walked Hrvelec 10 of 10 times",
    "own_structures": "a structure the supplier itself prices cheaply - its own alternative sheets give the rate, "
    "e.g. P05 Hrvelec 35.00 at 35 days, 31.50 at 52 (snapped to what we may sign: 42) - joins as option B at option "
    "A's C when its drop is 1.5x what the structure costs us; its own lead time beyond our need also without a pair",
    "hide_own_cost": "measurement only: the own plant's should-cost is not read (`_full_cost` None), so strategic "
    "own-plant cases (P01, P02, P03, P10) run the guessed-cost path most hidden strategic suppliers get (A3 floor)",
    "double_count": "our framework agreement already indexes the price to a driver its quote cites: that clause "
    "is cited - a surcharge would count the rise twice (P08, P18 and two unplayed suppliers)",
    "justified_arg": "the first e-mail sets its own cost drivers x their shares (from its quote) against the rise "
    "it asks, where it asks at least 1 point more",
    "menu_fallback": "under a margin charge, where the price on the lower side of the C minimum is not below its "
    "offer, ask on the usual side instead of finding no sheet and closing (P03)",
    "clause_rel_only": "an index series named in its quote counts as a request for a clause only with a strategic "
    "goal (P02, what it was built for); in leverage the clause options in round 1 cost P08 0.066 and P18 0.067 "
    "(b3f06da against 11c, same first e-mail otherwise)",
    "respond_lite": "every question of its last e-mail answered and every fixed lever said honestly, but no "
    "structure given away (P-42: yes to its start date cost P01 0.14)",
    "respond_all": "every question, condition, wish and signal of its last e-mail is taken up (reply_parser): "
    "answered, kept in the options or said honestly why not; implies answers",
    "all_windows": "an index fall over the steepest window the arena accepts (<= 12 months, ending within the last "
    "12), not only one ending at the latest month; one per series",
    "no_q1": "no question in the first e-mail (each one cost 0.43 pp of the first drop, 9 of 12 suppliers): the "
    "cost-breakdown request to an open-book supplier waits for round 2",
    "late_facts": "round 1 as today; from round 2 every offer carries at least one argument the arena has not counted "
    "for this supplier: remaining strong evidence first, then weak facts kept out of round 1 (price history, a "
    "delivery or quality record or complaint, an index series it rebuffed), never a counted kind, series or part",
}


def snap_option(options, value):
    """The allowed option nearest to a value it named (54 days -> 56); the value itself where any is allowed."""
    numeric = [o for o in options or [] if isinstance(o, int | float)]
    return min(numeric, key=lambda o: abs(o - value)) if numeric and value not in numeric else value


# On by default since 11 Oct 09:20 (David's decision): clause_rel_only + cheap_yes (P-49: P01 0.924, P08 0.626,
# P11 0.710, P18 0.685) and fast_pay (P-50: P05 0.824 -> 0.865). justified_arg is off: alone it lost P01 and P08
# (P-47), and in the combination P08 fell from 0.626 to 0.571. no_hedged_series on since 11 Oct 10:15 (P-57: P08
# 0.626 -> 0.659, the other nine identical). Switch one off with flag=False.
DEFAULT_ON = {"clause_rel_only", "cheap_yes", "fast_pay", "no_hedged_series"}


class TacticalStrategy(BaselineStrategy):
    name = "tactical"

    def __init__(self, data: WorldData | None = None, llm=None, **flags) -> None:
        super().__init__(data, llm)
        unknown = set(flags) - set(FLAGS)
        if unknown:
            raise ValueError(f"unknown tactical flags: {sorted(unknown)}")
        self.flags = {name: bool(flags.get(name, name in DEFAULT_ON)) for name in FLAGS}
        if self.flags["respond_all"] or self.flags["respond_lite"]:
            self.flags["answers"] = True  # its plain answers are part of answering everything
        if self.flags["guess_anchor"]:
            self.flags["guess_slack"] = True  # the deep ask needs the (lowered) guessed floor under it
        self.tplans: dict[str, Plan] = {}
        self.banned_case_kinds: set[str] = set()  # contradicted: never again in this case
        self.refused_kinds: dict[str, set[str]] = {}  # supplier -> kinds it called `irrelevant` (late_facts)
        self.late_extra: dict[str, list[Evidence]] = {}  # supplier -> weak facts only for rounds 2+ (late_facts)

    # ------------------------------------------------------------------ prepare
    def prepare(self, neg: Negotiation) -> None:
        if neg.data is not None:
            self.data = neg.data  # the session's view for this case: its own facts (WorldData.with_case)
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
                full_cost = self._cap_at_opening(neg, sid, terms, full_cost, profile)
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
            if self.flags["justified_arg"]:
                plan.justified_note = self._justified_note(neg, thread, terms)
            plan.lower_c, plan.upper_c = self._bounds_c(neg, sid, terms, gt, target_c, open_c)
            if terms.get("unit_price") is not None:
                rate = buyer.get("interest_rate", 0.08) * (2 if profile.has("cash_short") else 1)
                plan.belief = FloorBelief(neg.case, terms, thread.standard_terms, gt.lower, rate)
                plan.belief.ppm = profile.ppm  # scorecard ppm: what a chargeback really costs it
            plan.evidence = self._evidence(neg, sid, terms.get("unit_price"), current) if terms else []
            body = thread.latest.get("body") or ""
            clauses = [o for o in neg.case.get("term_options", {}).get("index_clause") or [] if o]
            relationship_only = self.flags["clause_rel_only"] and goal not in RELATIONSHIP_GOALS
            if (
                "index_clause" in neg.case["negotiable"]
                and any(o.get("series") in body for o in clauses)
                and not relationship_only
            ):
                # it argues its price with the very index a clause would follow: the clause answers it. P02's
                # supplier dropped its price by 15-22 for one and never went under 372.96 without (P-13, P-15, P-19)
                plan.requests.add("index_clause")
            if profile.has("hedged"):
                plan.banned_kinds.add("index")  # "not our reality" until its hedge runs out
            if gt.market_supports_ask:
                plan.banned_kinds.add("index")  # the indices back its ask: citing them helps it, not us
                plan.market_backs_ask = True
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
            parts = neg.case.get("parts") or []
            out += self.data.evidence_orders(parts, sid, open_price)
            if self.flags["fresh_args"]:
                out += self.data.evidence_orders_per_part(parts, sid)
            out += data_facts(self.data, parts, all_windows=self.flags["all_windows"])
            if self.flags["double_count"]:
                out += self._double_count(neg, sid)
            if self.flags["fresh_claims"]:
                later = self.data.evidence_complaints(parts, sid, since="2025-10-01")
                if open_price and not any(e.kind == "should_cost" for e in out):
                    later += self.data.evidence_should_cost(parts, open_price, margin=1.0)
                for e in later:  # material for rounds 2+: round 1 already carries our best three
                    e.meta = {**(e.meta or {}), "later": True}
                out += later
        return sorted(out, key=lambda e: -e.strength)

    def _full_cost(self, parts: list[str], supplier_id: str) -> float | None:
        """The should-cost of THIS supplier's plant for a single-part case; None otherwise.

        Another supplier's estimate is a different plant (cost base, process) and a bundle's price is
        not one part's cost: guessing would push the floor and the margin charge the wrong way.
        `hide_own_cost`: None always, so a strategic supplier with an own-plant cost runs the guessed-cost path."""
        if not self.data or len(parts) != 1 or self.flags["hide_own_cost"]:
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

    def _cap_at_opening(self, neg: Negotiation, sid: str, terms: dict, full_cost: float, p: SupplierProfile) -> float:
        """The own-plant cost, but never so high that the supplier's opening quote leaves it under the sustainable
        margin. The arena's recorded margin charges put every strategic supplier at or above that margin at its own
        opening (implied by the charges on our deals: P01 6.1 % against 3, P02 1.1 against 0.5, P03 10.1 against 8,
        H03 4.7 against 3, H04, H14 and H29 likewise); the should-cost x SHOULD_COST_SHARE left H03's opening at
        2.6 % and charged EUR 410 on a deal the arena charged EUR 2.37."""
        margin = neg.buyer.get("sustainable_margin_pct")
        if not margin or terms.get("unit_price") is None:
            return full_cost
        estimate = self._supplier_estimate(neg, sid, full_cost, p)
        worth = supplier_value(neg.case, closing_terms(neg.case, terms, neg.threads[sid].standard_terms), estimate)
        cap = math.floor(worth * (1 - margin / 100) * 100) / 100
        return min(full_cost, cap) if cap > 0 else full_cost

    def _guess_floor(self, neg: Negotiation, sid: str, plan: Plan, terms: dict) -> float:
        """Under a guessed cost, the price that minimises C on these terms with the guessed charge (0 without a
        guess): no ask and no accept goes under it."""
        if not plan.guess or terms.get("unit_price") is None or self.flags["no_guess_floor"]:
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
        floor = math.ceil((lo + hi) / 2 * 100 - 1e-6) / 100
        if self.flags["guess_slack"]:
            # the guess sat up to 3.5 % above the arena's cost (D01): a floor that high left 2.5 % of room and D01
            # fell 0.969 -> 0.669; under it by its own error the floor still stops a P02-like squeeze
            floor = round(floor * (1 - GUESS_SLACK), 2)
        return floor

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
        buyer = neg.buyer
        charged = buyer.get("sustainable_margin_pct") and buyer.get("relationship_eur_per_point")
        if buyer.get("category_goal") not in RELATIONSHIP_GOALS or not full_cost or not charged:
            # without both parameters cost.py charges nothing: an estimate would only make C's minimum a price of 0
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

    def _update_upper(self, neg: Negotiation, sid: str, plan: Plan) -> None:
        """The upper bound follows the evidence: where this supplier will stop with us (its offers, last words,
        the shrinking path of its steps), priced on the best structure. Offline on 28 practice sessions this
        estimate met the real stopping point within 8 % before the first reply and 1-3 % by round 3-4.
        The anchor stays where the data put it; only how far we go and when we take it follow the supplier."""
        _, theirs = neg.threads[sid].standing
        insisted = {r for r, n in plan.request_counts.items() if n >= 2}
        stop_c, stop_terms = plan.belief.best_package(
            lambda t: neg.cost(sid, t),
            lambda t: neg.keeps_must_haves(sid, t),
            allow=lambda t: all(satisfies(neg.case, t, theirs or {}, r, plan.proposed) for r in insisted),
        )
        if not math.isfinite(stop_c):
            return
        _, terms = neg.threads[sid].standing
        cap = min(neg.c_alt, neg.cost(sid, terms) if terms else math.inf, plan.open_c)
        before = plan.upper_c
        plan.stop_c = stop_c
        plan.upper_c = min(max(stop_c * (1 + STOP_MARGIN), plan.target_c * (1 + UPPER_ROOM)), cap)
        if neg.supplier_estimates.get(sid):
            # where only the price moves, 1 % and 6 % of C are more than the whole room (P01: 5 %, P02: 2 %):
            # the bound became the supplier's current offer and every offer counted as good enough - P01 took an
            # alternative in round 3 at 134.80 while the supplier was still coming down (0.733, P-20)
            room = max(0.0, plan.open_c - plan.target_c)
            plan.upper_c = min(max(stop_c + STOP_ROOM * room, plan.target_c + UPPER_ROOM_SHARE * room), cap)
        neg.recorder.event(
            "belief",
            session_id=neg.session_id,
            supplier_id=sid,
            belief=plan.belief.summary(),
            stop_c=round(stop_c, 2),
            stop_price=(stop_terms or {}).get("unit_price"),
            upper_before=round(before, 2) if math.isfinite(before) else None,
            upper_after=round(plan.upper_c, 2) if math.isfinite(plan.upper_c) else None,
        )
        log.info(
            "%s belief: stop ~%s (price %s), upper %s -> %s",
            sid,
            _k(stop_c),
            (stop_terms or {}).get("unit_price"),
            _k(before),
            _k(plan.upper_c),
        )

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
        if neg.supplier_estimates.get(sid) and not (
            self.flags["rel_anchor4"] and neg.buyer.get("category_goal") in RELATIONSHIP_GOALS
        ):
            # the margin charge is in C: the ask may go as deep as a price-only talk, it stops at the price that
            # costs us least (below). P01 came down to 132.20 after a 10 % ask, to 137.00 after a 3 % one
            depth, extra = ANCHOR_PRICE_ONLY, 0.0
        elif neg.buyer.get("category_goal") in RELATIONSHIP_GOALS and not (
            self.flags["guess_anchor"] and self._full_cost(neg.case.get("parts") or [], sid) is None
        ):
            depth, extra = min(depth, ANCHOR_RELATIONSHIP), 0.0  # squeezing a strategic supplier costs us C
        if self.flags["soft_anchor"] and neg.buyer.get("category_goal") in ("routine", "quality_first"):
            depth, extra = depth * SOFT_ANCHOR, 0.0
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
        # no hard floor for strategic suppliers: the relationship term already prices a squeeze in C, and
        # our cost estimate can sit above its real one (P02: should-cost 380 over a 371 quote, C_best ~364)
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
        closing_word = t.status == "final_offer" or (signals["firm"] and t.rounds_used > 0)
        rest_pending = self._rest_pending(neg, supplier_id, plan)
        if (
            not closing_word
            and not rest_pending
            and (their_c <= plan.lower_c or self._undercut_after_big_step(neg, supplier_id, plan, theirs))
        ):
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
                and self.flags["probe_final"]
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

    def _learn(self, neg: Negotiation, sid: str, plan: Plan) -> None:
        """Read what came back since we last looked: argument checks, stalls, a cost breakdown."""
        t = neg.threads[sid]
        replies = t.supplier_messages
        for reply in replies[plan.seen_replies :]:
            arena_reading = self.flags["fresh_args"] or self.flags["late_facts"]
            if arena_reading:
                self._learn_claims(t, plan, reply)
            for res in [] if arena_reading else reply.get("claim_results") or []:
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
            if FIGURES_ASKED.search(reply.get("body", "")):
                plan.figures_asked = True
            facts = self._read_reply(neg, sid, reply)
            if facts and self.flags["respond_all"]:
                self._take_in(neg, sid, plan, facts)
            elif facts and self.flags["respond_lite"]:
                self._take_in_words(plan, facts)
            if (
                self.flags["answers"]
                and not self.flags["respond_lite"]
                and MUST_CLAUSE.search(reply.get("body", ""))
                and "index_clause" in neg.case["negotiable"]
            ):
                plan.request_counts["index_clause"] = max(2, plan.request_counts.get("index_clause", 0))
            asked = {r for r in requests_in(reply.get("body", "")) if r in neg.case["negotiable"]}
            for r in asked:
                plan.request_counts[r] = plan.request_counts.get(r, 0) + 1
            plan.requests |= asked
            for series in CITED_DRIVER.findall(reply.get("body", "")):
                if series[0] not in plan.pressures:
                    plan.pressures.append(series[0])
            for fact in reply_facts(self.data, reply.get("body", ""), all_windows=self.flags["all_windows"]):
                if fact.sentence not in plan.used_sentences and all(fact.sentence != c.sentence for c in plan.counters):
                    plan.counters.append(fact)
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
        if plan.belief and len(replies) > plan.seen_replies:
            for reply in replies[max(plan.seen_replies, 1) :]:
                plan.belief.observe(reply)
            self._update_upper(neg, sid, plan)
        plan.seen_replies = len(replies)

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

    def _double_count(self, neg: Negotiation, sid: str) -> list[Evidence]:
        """Our framework agreement with this supplier already indexes the price to a series its quote names as a cost
        driver: a surcharge on top counts that rise twice (P08: ctr:4600070710#3.2 ties 45 % to AS-14404, and its
        quote asks +11 % citing AS-14404). A fact from our own contract it may not have in view."""
        body = (neg.threads[sid].messages[0].get("body") or "") if neg.threads[sid].messages else ""
        facts = parse_reply(body)
        cited = set(facts.drivers) | {m[0] for m in facts.driver_moves}
        out = []
        for ref, f in self.data.facts.items():
            if not (ref.startswith("ctr:") and isinstance(f, dict) and f.get("type") == "index"):
                continue
            if f.get("supplier") == sid and f.get("series") in cited:
                share = f.get("material_share") or 0
                sentence = (
                    f"Our framework agreement already ties {share:.0%} of the price to {f['series']} ({ref}): "
                    "a surcharge for the same material would count its rise twice."
                )
                out.append(Evidence(kind="contract_index", refs=[ref], sentence=sentence, strength=6.0))
        return out

    @staticmethod
    def _justified_note(neg: Negotiation, thread, terms: dict) -> str | None:
        """Its quote names its cost drivers with their 12-month change and their share of its cost: what they add up
        to is the rise its own figures justify. Said when its quote asks clearly more (P04: 13.0 % asked, 0.8 %
        justified; P01 9.5 % against 2.4 %; P08 11.0 % against 7.5 %) - never where its figures carry the ask."""
        current = neg.buyer.get("current_unit_price")
        price = terms.get("unit_price")
        if not current or not price or not thread.messages:
            return None
        moves = [
            (s, pct, share)
            for s, pct, _, share in parse_reply(thread.messages[0].get("body", "")).driver_moves
            if share
        ]
        if not moves:
            return None
        justified = sum(pct * share / 100 for _, pct, share in moves)
        asked = (price / current - 1) * 100
        if asked - justified < 1.0:
            return None
        figures = ", ".join(f"{s} {pct:+.1f} % at {share:.0f} % of your cost" for s, pct, share in moves)
        return (
            f"By your own figures ({figures}) your costs rose by about {justified:.1f} %, while your quote asks "
            f"{asked:.1f} % more than our current price of EUR {current:,.2f}."
        )

    @staticmethod
    def _read_reply(neg: Negotiation, sid: str, reply: dict) -> ReplyFacts | None:
        """Every reply read in full and logged - reading changes nothing; what we do with it is `_take_in`."""
        try:
            facts = parse_reply(reply.get("body", ""))
            neg.recorder.event("reply_facts", session_id=neg.session_id, supplier_id=sid, facts=facts.summary())
            return facts
        except Exception as e:  # a reader must never cost a case
            log.warning("%s: reply parser failed: %r", sid, e)
            return None

    def _take_in(self, neg: Negotiation, sid: str, plan: Plan, f: ReplyFacts) -> None:
        """Its questions, conditions, wishes and signals become our plan: what the next e-mail must take up."""
        case = neg.case
        negotiable = case["negotiable"]
        options = case.get("term_options", {})
        plan.facts = f
        if "figures" in f.questions:
            plan.figures_asked = True
        for kind, detail in f.conditions:
            if kind == "index_clause" and "index_clause" in negotiable:
                plan.request_counts["index_clause"] = max(2, plan.request_counts.get("index_clause", 0))
            elif kind in ("payment_days", "lead_time_days") and kind in negotiable and detail:
                plan.price_terms[kind] = snap_option(options.get(kind), int(detail))
            elif kind == "incoterm" and "incoterm" in negotiable:
                plan.requests.add("incoterm")
        for lever, want in f.wishes.items():
            if lever in negotiable:
                plan.requests.add(lever)
                if isinstance(want, int):
                    plan.proposed.setdefault(lever, [])
                    v = snap_option(options.get(lever), want)
                    if v not in plan.proposed[lever]:
                        plan.proposed[lever].append(v)
        if f.signals & {"figures_confirm_its_case", "argument_not_its_reality"}:
            for e in plan.last_claims:  # the index argument it rejected: never again in this thread
                if e.kind in ("index", "recent_drop") and (e.meta or {}).get("series"):
                    plan.banned_series.add(e.meta["series"])
        if "breakdown_answer" in f.signals:
            plan.asked_breakdown = True
        if f.signals & {"our_step_too_small", "far_apart"}:
            plan.bigger_step = True
        if f.signals & {"price_frozen", "terms_room"}:
            plan.lever_turn = True  # its price list is frozen: our step goes into the terms
        for sig in f.signals:
            if sig.startswith("builds_on_option_"):
                self._keep_its_option(neg, sid, plan, sig.rsplit("_", 1)[-1])
        useless = {"price history": "orders", "delivery record": "scorecard", "volume change": "forecast"}
        for data_kind, verdict in f.claim_reactions:
            if verdict in ("no_change", "known") and data_kind.strip() in useless:
                plan.banned_kinds.add(useless[data_kind.strip()])

    @staticmethod
    def _take_in_words(plan: Plan, f: ReplyFacts) -> None:
        """What changes our answer and our arguments - never our menu: its questions, the index series it rejected,
        the argument kinds that did not move it, a breakdown it will not send."""
        plan.facts = f
        if "figures" in f.questions:
            plan.figures_asked = True
        if f.signals & {"figures_confirm_its_case", "argument_not_its_reality"}:
            for e in plan.last_claims:
                if e.kind in ("index", "recent_drop") and (e.meta or {}).get("series"):
                    plan.banned_series.add(e.meta["series"])
        if "breakdown_answer" in f.signals:
            plan.asked_breakdown = True
        useless = {"price history": "orders", "delivery record": "scorecard", "volume change": "forecast"}
        for data_kind, verdict in f.claim_reactions:
            if verdict in ("no_change", "known") and data_kind.strip() in useless:
                plan.banned_kinds.add(useless[data_kind.strip()])

    @staticmethod
    def _keep_its_option(neg: Negotiation, sid: str, plan: Plan, which: str) -> None:
        """ "Building on your Option B": that structure is what it works with - it stays in our menu."""
        index = {"a": 0, "b": 1, "c": 2, "first": 0, "second": 1, "third": 2}.get(which)
        ours = [m for m in neg.threads[sid].messages if m.get("from") == "buyer" and m.get("term_sheets")]
        if index is None or not ours or index >= len(ours[-1]["term_sheets"]):
            return
        for f, v in ours[-1]["term_sheets"][index]["terms"].items():
            if f != "unit_price" and f in neg.case["negotiable"] and v is not None:
                plan.requests.add(f)
                plan.proposed[f] = [v] + [x for x in plan.proposed.get(f, []) if x != v]

    def _learn_claims(self, t, plan: Plan, reply: dict) -> None:
        """The arena's checks of our last e-mail, matched to its arguments the way the arena reads them (the
        `index` counts the arena's arguments, not our sentences: P11's two scorecard lines were one)."""
        before = t.messages[: next((i for i, m in enumerate(t.messages) if m is reply), len(t.messages))]
        ours = next((m for m in reversed(before) if m.get("from") == "buyer" and not m.get("action")), None)
        if not ours:
            return
        read = arguments_read(ours.get("body", ""), ours.get("refs"), self._facts())
        for res in reply.get("claim_results") or []:
            i, result = res.get("index"), res.get("result")
            if not isinstance(i, int) or not 0 <= i < len(read):
                continue
            key, refs = read[i]
            if result == "duplicate" and key[0] not in ("index", "rival", "orders"):
                plan.spent_kinds.add(key[0])  # counted once per kind, whatever the ID (orders: per part, by key)
            kinds = {c.kind for c in plan.last_claims if set(c.refs) & refs}
            if result == "contradicted":
                self.banned_case_kinds |= kinds
            elif result == "irrelevant":
                plan.banned_kinds |= kinds
                self.refused_kinds.setdefault(plan.supplier_id, set()).update(kinds)

    def _facts(self) -> dict:
        return self.data.facts if self.data else {}

    def _spent_keys(self, neg: Negotiation, sid: str) -> set:
        """Every argument the arena has read from our e-mails to this supplier: citing it again is a duplicate."""
        out = set()
        for m in neg.threads[sid].messages:
            if m.get("from") == "buyer":
                out |= {k for k, _ in arguments_read(m.get("body", ""), m.get("refs"), self._facts())}
        return out

    def _arg_key(self, e: Evidence) -> tuple | None:
        return argument_key(e.refs[0], self._facts()) if e.refs else None

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
            plan.full_cost, plan.guess = full, None
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
            if self.flags["respond_all"] and plan.bigger_step and math.isfinite(plan.open_c):
                step = max(step, min(0.02 * plan.open_c, 0.6 * gap))  # "two cents does not enable us"
                plan.bigger_step = False
            if self.flags["persistent"]:
                step = min(step, max(PERSIST_STEP * step, PERSIST_MIN * last))
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
            or self._round_budget(neg, sid) - t.rounds_used <= (2 if self.flags["persistent"] else 3)
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
        if (neg.case.get("round_limit") or 10) - t.rounds_used < 2 or neg.seconds_to_deadline() < 180:
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
        best_c, primary_c = neg.cost(sid, best), neg.cost(sid, primary)
        # 0.1 % of the room, not 0.2 % of C: P08's 5 % deadband alternative saved 0.16 % of C and was passed over;
        # taken, P08 0.550 -> 0.560 (runs.md P-34 to P-41)
        margin = self._alt_margin(neg, plan, primary_c)
        if best_c >= primary_c - margin:
            return None
        # only when we would close anyway - in round 1 its alternative is an opening, not a deal (P18 dry run)
        closing = (
            t.status == "final_offer"
            or reply_signals(t.latest.get("body", ""))["firm"]
            or plan.stalls >= 1
            or self._round_budget(neg, sid) - t.rounds_used <= 2
        )
        if self.flags["alt_structure"]:
            if len(neg.threads) > 1 and best_c > self._best_rival_c(neg, sid):
                return None  # a bidder behind the leader keeps its alternative: it stays our lever (P05)
            if not self.flags["persistent"]:  # persistent: only the supplier ends it (P18 gained from not taking 5.20)
                closing = closing or best_c <= plan.stop_c * (1 + STOP_MARGIN)  # at our estimate of its stop (P10)
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

    def _alternative_line(self, neg, sheet: dict, best: dict) -> str:
        if not self.flags["answers"]:
            return "thank you. We accept your alternative as stated below and are ready to place the order on it."
        diffs = [
            f"{FIELD_WORDS.get(f, f.replace('_', ' '))} {sheet[f]} instead of {best[f]}"
            for f in neg.case["negotiable"]
            if f != "unit_price" and f in best and sheet.get(f) != best[f]
        ]
        return "thank you. We can accept your alternative on the terms below" + (
            f" ({'; '.join(diffs)}, the nearest option we can sign)." if diffs else "."
        )

    def _best_rival_c(self, neg: Negotiation, sid: str) -> float:
        """The cheapest acceptable standing offer of the other live suppliers (inf if none)."""
        best = math.inf
        for other, ot in neg.threads.items():
            if other != sid and ot.live and ot.standing[0] and not accept_problems(neg, other, ot.standing[0]):
                best = min(best, neg.cost(other, ot.standing[1]))
        return best

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

    def _text_price_offer(self, neg: Negotiation, sid: str, plan: Plan) -> Decision | None:
        """It wrote a lower price than it put on its sheet: take it at its word, on its own terms, once."""
        if not plan.text_price or plan.text_price_used or not self._may_push(neg, sid):
            return None
        _, theirs = neg.best_offer(sid)
        if not theirs or plan.text_price >= (theirs.get("unit_price") or 0):
            return None
        plan.text_price_used = True
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

    def _may_push(self, neg: Negotiation, sid: str) -> bool:
        t = neg.threads[sid]
        return (neg.case.get("round_limit") or 10) - t.rounds_used >= 2 and neg.seconds_to_deadline() > 150

    def _reanchor(self, neg, sid, plan: Plan, theirs: dict, their_c: float) -> Decision | None:
        """It came under a floor we only guessed: our guess was timid. Ask again under its new price, once."""
        if plan.reanchored or not self._may_push(neg, sid):
            return None
        if (
            neg.buyer.get("category_goal") in RELATIONSHIP_GOALS
            and not plan.guess
            and not neg.supplier_estimates.get(sid)
        ):
            # never 10 % under a strategic supplier's price without an estimate of its cost: nothing stops the
            # squeeze (P02: 345.39, score 0). With an own-plant estimate the charge is in C and the re-anchor stays
            # as measured (P01 0.969, P-29; off, it held at 133.6 in round 3: 0.901, run 20261011-082032); a guessed
            # cost allows it too: the guess floor (_sheets) keeps every sheet above the cost minimum
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
            low = self._iso_cost_price(neg, sid, terms, floor_c + slack - spent, under=True)
            if self.flags["menu_fallback"] and neg.cost(sid, {**terms, "unit_price": low}) >= their_c * (1 - DONE_EPS):
                # the lower side of the C minimum is not below its offer: every structure fell out and we closed
                # early (P03 R2: 404.47 at C 3,938k against its 3,937k, while 430.56 cost 3,925k)
                return self._iso_cost_price(neg, sid, terms, ask_c)
            return low

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
        if self.flags["respond_all"] and plan.price_terms:  # "our price is calculated for 60 days"
            pool = [t for t in pool if all(t.get(f) == v for f, v in plan.price_terms.items())] or pool
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
        if self.flags["alt_structure"]:
            picked = self._with_alternative_structure(neg, sid, valid or under_floor, picked)  # before "refused twice"
        if self.flags["cheap_yes"] and picked:
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
        if self.flags["fast_pay"]:
            out = self._fast_pay(neg, sid, plan, out, their_c)
        out = out[:3]
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

    @staticmethod
    def _with_alternative_structure(neg, sid, pool: list[dict], picked: list[dict]) -> list[dict]:
        """Its alternative sheet says on which structure it moves: that structure (snapped to the options we may
        sign, 54 days -> 56) goes into our menu at our ask (P10 dropped its 31.70 at 54 days when we left it out)."""
        t, options = neg.threads[sid], neg.case.get("term_options", {})
        primary_id = t.standing[0]
        keys = {structure_key(x) for x in picked}
        for offer_id, terms in t.offers:
            if offer_id == primary_id:
                continue
            want = {}
            for f, v in terms.items():
                if f == "unit_price" or f not in neg.case["negotiable"]:
                    continue
                opts = [o for o in options.get(f) or [] if o is not None]
                if (
                    opts
                    and v not in opts
                    and isinstance(v, int | float)
                    and all(isinstance(o, int | float) for o in opts)
                ):
                    v = min(opts, key=lambda o: abs(o - v))
                want[f] = v
            match = [x for x in pool if all(x.get(f) == v for f, v in want.items())]
            if match and not any(structure_key(m) in keys for m in match):
                chosen = max(match, key=lambda x: x["unit_price"])
                if len(picked) < 3:
                    picked.append(chosen)
                else:
                    picked[1] = chosen
                keys.add(structure_key(chosen))
        return picked

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
        if self.flags["no_hedged_series"]:
            self._drop_hedged_series(neg, plan)
        banned = plan.banned_kinds | self.banned_case_kinds
        if neg.buyer.get("category_goal") != "quality_first":
            banned = banned | {"scorecard"}
        fresh = [e for e in plan.counters if e.kind not in banned and e.sentence not in plan.used_sentences]
        fresh.sort(key=lambda e: -e.strength)
        pool = fresh + [e for e in plan.evidence if e.kind not in banned and e.sentence not in plan.used_sentences]
        rival = self._rival_evidence(neg, sid)
        if rival and "rival_offer" not in banned:
            pool.insert(0, rival)
        prefer: list[str] = []
        for key in [*sorted(plan.profile.traits), neg.buyer.get("category_goal", "")]:
            prefer += EVIDENCE_FIRST.get(key, [])
        pool.sort(key=lambda e: (e not in fresh, e.kind not in prefer, -e.strength))
        limit = plan.policy.claims_first if first else (2 if fresh else 1)
        if (self.flags["respond_all"] or self.flags["respond_lite"]) and not first and plan.figures_asked:
            limit = max(limit, 2)
            order = ["should_cost", "recent_drop", "index", "notice", "quality", "orders", "rival_offer"]
            pool.sort(key=lambda e: order.index(e.kind) if e.kind in order else len(order))
        if (self.flags["respond_all"] or self.flags["respond_lite"]) and plan.banned_series:
            pool = [e for e in pool if (e.meta or {}).get("series") not in plan.banned_series]
        asked_rival = (
            (self.flags["respond_all"] or self.flags["respond_lite"])
            and plan.facts is not None
            and "competitor" in plan.facts.questions
        )
        if self.flags["fresh_claims"] and not first:
            limit = 3  # the arena reads up to 3 per message, and every round anew (P01's best session)
            if plan.figures_asked:
                order = ["should_cost", "recent_drop", "index", "notice", "quality", "complaint", "orders"]
                pool.sort(key=lambda e: order.index(e.kind) if e.kind in order else len(order))
        late = self.flags["late_facts"] and not first
        spent = self._spent_keys(neg, sid) if self.flags["fresh_args"] or self.flags["all_windows"] or late else set()

        def select(limit: float) -> list[Evidence]:
            picked, kinds, keys, companions = [], set(), set(), 0
            for e in pool:
                if len(picked) - companions >= limit:
                    break
                if e.kind == "rival_offer":
                    if any((sid, r) in self.used_rival_refs for r in e.refs) and not asked_rival:
                        continue
                elif any(r in self.used_refs for r in e.refs) or (
                    # a bundle's parts each count their own orders (api.md): the key check below keeps one per part
                    e.kind in kinds
                    and e.kind != "recent_drop"
                    and not (self.flags["fresh_args"] and e.kind == "orders")
                ):
                    continue
                if first and (e.meta or {}).get("later"):
                    continue
                if self.flags["answers"] and e.kind == "forecast" and not self._forecast_fits(neg, e):
                    # a forecast of another quantity (P18: 118,500 against 23,700) only raises the volume question
                    continue
                if self.flags["fresh_claims"] and not first and set(e.refs) & {r for x in picked for r in x.refs}:
                    continue  # the same index point twice in one e-mail reads as a duplicate
                key = (
                    self._arg_key(e)
                    if self.flags["fresh_args"]
                    or late
                    or (self.flags["all_windows"] and e.kind in ("index", "recent_drop"))  # one window per series
                    else None
                )
                if key and key in keys and key == ("record",):
                    # the same scorecard row for delivery and quality is read as one argument (the quality one,
                    # P11): it goes along with the first and takes no slot
                    partner = next((i for i, x in enumerate(picked) if set(e.refs) <= set(x.refs)), None)
                    if partner is not None:
                        picked.insert(partner + 1, e)
                        kinds.add(e.kind)
                        companions += 1
                    continue
                if key and (key in spent or key in keys or key[0] in plan.spent_kinds):
                    continue  # counted already (a forecast, a series, a part): it would come back `duplicate`
                picked.append(e)
                kinds.add(e.kind)
                if key:
                    keys.add(key)
            return picked

        if self.flags["fresh_args"] and first:
            # arguments kept for rounds 2-4, at least one: a reply in round 2+ to a verified argument was a final
            # offer 4-7 % of the time, to an e-mail without one 53 % (our 293 practice replays). The first e-mail
            # keeps two where there are three or more (two or more arguments: a deeper first step, bot-mechanics.md)
            checkable = len({self._arg_key(e) for e in select(math.inf) if e.refs})
            if checkable >= 2:
                limit = min(limit, max(min(2, checkable - 1), checkable - 3))
        picked = select(limit)
        if late and not self._carries_fact(picked, spent) and len(picked) < 3:
            # a round-2+ e-mail without a fact the arena has not counted got a final offer 53-60 % of the time, with
            # one 4-11 % (442 practice sessions, paired within case and round); even a weak one as the only fact: 0 %
            pool = [e for e in pool if e.refs and e not in picked] + self._late_pool(neg, sid, plan)
            picked += select(1)
        for e in picked:
            plan.used_sentences.add(e.sentence)
        plan.figures_reply, plan.figures_asked = (
            (self.flags["fresh_claims"] or self.flags["respond_all"] or self.flags["respond_lite"] or late)
            and plan.figures_asked
            and bool(picked),
            False,
        )
        for e in picked:
            if e.kind == "rival_offer":
                self.used_rival_refs.update((sid, r) for r in e.refs)
            else:
                self.used_refs.update(e.refs)
        return picked

    def _carries_fact(self, picked: list[Evidence], spent: set) -> bool:
        """Does a message with these arguments carry one the arena reads and has not counted for this supplier?"""
        refs = [r for e in picked for r in e.refs]
        return any(k not in spent for k, _ in arguments_read("", refs, self._facts()))

    def _late_pool(self, neg, sid: str, plan: Plan) -> list[Evidence]:
        """Weak facts for rounds 2+, kept out of round 1 where they cost the first drop (bot-mechanics.md): the kinds
        this supplier's plan bans (price history it shrugged off, a delivery record outside quality cases, an index
        series it rebuffed), our complaints, a bundle's orders per part. Never a kind it found irrelevant or one
        contradicted in this case. The best kind first: price history, then the record, then a rebuffed series."""
        if sid not in self.late_extra:
            extra: list[Evidence] = []
            parts = neg.case.get("parts") or []
            if self.data and parts:
                extra += self.data.evidence_complaints(parts, sid, since=LATE_COMPLAINTS_SINCE)[:1]
                if not self.flags["fresh_args"]:
                    extra += self.data.evidence_orders_per_part(parts, sid)
            self.late_extra[sid] = extra
        hard = (
            self.banned_case_kinds
            | self.refused_kinds.get(sid, set())
            | ({"index"} if plan.market_backs_ask else set())
        )
        seen: set[str] = set()
        out = []
        for e in plan.counters + plan.evidence + self.late_extra[sid]:
            if e.refs and e.kind not in hard and e.sentence not in plan.used_sentences and e.sentence not in seen:
                seen.add(e.sentence)
                out.append(e)
        order = {"orders": 0, "scorecard": 1, "quality": 1, "complaint": 2, "index": 3, "recent_drop": 3}
        return sorted(out, key=lambda e: (order.get(e.kind, 4), -e.strength))

    @staticmethod
    def _drop_hedged_series(neg, plan: Plan) -> None:
        """Its material is bought at fixed prices: a fall of the series its clause would follow is "not our reality"
        (P08, every session) - the slot goes to the next argument. One fact is cited once (the counters may hold it)."""
        clauses = neg.case.get("term_options", {}).get("index_clause") or []
        series = {o.get("series") for o in clauses if o}
        if not (plan.profile.has("hedged") and series):
            return
        prefixes = tuple(f"idx:{s}@" for s in series)

        def keep(e: Evidence) -> bool:
            return not any(r.startswith(prefixes) for r in e.refs or []) and not any(
                s in (e.sentence or "") for s in series
            )

        plan.counters = [e for e in plan.counters if keep(e)]
        plan.evidence = [e for e in plan.evidence if keep(e)]
        cited = {r for e in plan.counters for r in e.refs or []}
        plan.evidence = [e for e in plan.evidence if not set(e.refs or []) & cited]

    def _write(self, neg, plan: Plan, sheets: list[dict], claims: list[Evidence], probe: bool) -> dict:
        p, case = plan.profile, neg.case
        first = neg.threads[plan.supplier_id].rounds_used == 0
        lines = [f"Dear {plan.name} team,", ""]
        if first:
            rfq_newcomer = self.flags["answers"] and len(neg.threads) > 1 and not p.has("relationship")
            if (p.has("relationship") or neg.buyer.get("category_goal") in RELATIONSHIP_GOALS) and not rfq_newcomer:
                lines.append("thank you for your quote and for the reliable cooperation we value.")
            else:
                lines.append("thank you for your quote. We have reviewed it carefully against our data.")
        elif probe:
            lines.append("thank you - we are close. One last step from your side and we can sign.")
        elif plan.stalls:
            pressure = (
                f"{plan.pressures[-1]} weighs on your costs" if plan.pressures else "your costs are under pressure"
            )
            lines.append(
                f"thank you for your reply. We understand that {pressure}; to meet you, we propose a different "
                "structure."
            )
        elif self.flags["answers"] and not self._their_price_fell(neg, plan):
            lines.append("thank you for your reply. We move towards you.")  # it held or raised: no thanks for a step
        else:
            lines.append("thank you for your reply and the step towards us. We move as well.")
        if plan.figures_reply and claims:
            lines.append("You asked for the figures behind our proposal:")
        said = [c.sentence for c in claims]
        if self.flags["answers"]:
            said = [
                s.replace(
                    "market moves do not reach your costs before then.",
                    "the rise you cite does not reach your costs before then either.",
                )
                for s in said
            ]
            said += self._fixed_field_answers(neg, plan)
        if self.flags["respond_all"] or self.flags["respond_lite"]:
            said += self._take_up_lines(neg, plan, sheets)
        if plan.yes_line:
            said.append(plan.yes_line)
            plan.yes_line = None
        if first and plan.justified_note:
            said.append(plan.justified_note)  # the head's sum of its own figures, said by the mouth once
            plan.justified_note = None
        if first and self.flags["no_q1"]:
            said = [x for x in said if not x.rstrip().endswith("?")]
        lines += said
        if (
            not plan.asked_breakdown
            and p.has("open_book")
            and not plan.breakdown_read
            and not (first and self.flags["no_q1"])  # asked from round 2 on
        ):
            lines.append("Could you send us a cost breakdown for this part?")
            plan.asked_breakdown = True
        if len(sheets) > 1:
            reference = neg.threads[plan.supplier_id].standing[1].get("payment_days") or 0
            if self.flags["answers"]:  # early against its standard terms, not just against its last sheet
                reference = min(
                    reference, (neg.threads[plan.supplier_id].standard_terms or {}).get("payment_days") or 999
                )
            if p.has("cash_short") and any((sh["terms"].get("payment_days") or 999) < reference for sh in sheets):
                lines.append("If faster payment helps you, one option below pays early.")
            elif any(
                f in plan.policy.trade_first and f in case["negotiable"] for f in ("contract_months", "volume_per_year")
            ) and not (self.flags["answers"] and "commit-longer" in plan.used_sentences):
                lines.append("We are ready to commit for longer if the price reflects it.")
                plan.used_sentences.add("commit-longer")
        theirs = neg.threads[plan.supplier_id].standing[1]
        for i, sheet in enumerate(sheets if plan.requests else []):
            if said := self._answered(neg, plan, sheet["terms"], theirs, f"Option {chr(65 + i)}").strip():
                lines.append(
                    ("Yes - " + said.strip()) if self.flags["answers"] and not self.flags["respond_lite"] else said
                )  # its requests met, said as a yes
                break
        volume = (
            self._volume_answer(neg, plan, sheets) if self.flags["answers"] else self._volume_proof(neg, plan, sheets)
        )
        if volume:
            lines.append(volume[0])
        lines += ["", "We can award on any of these options:" if len(sheets) > 1 else "Our proposal:"]
        for i, sheet in enumerate(sheets):
            note = trade_note(case, sheets[0]["terms"], sheet["terms"])
            lines.append(f"Option {chr(65 + i)}: {describe(case, sheet['terms'])}{note}")
        lines += ["", SIGNATURE]
        return {
            "subject": case.get("title", "Your quote"),
            "body": "\n".join(lines),
            "term_sheets": sheets,
            "refs": sorted({r for c in claims for r in c.refs} | ({volume[1]} if volume and volume[1] else set())),
        }

    def _forecast_fits(self, neg, e: Evidence) -> bool:
        """The forecast's volume is this contract's need (within 5 %)."""
        fact = self.data.facts.get(e.refs[0]) if self.data and e.refs else None
        need = neg.buyer.get("need_per_year")
        volume = (fact or {}).get("volume_per_year")
        return bool(need and isinstance(volume, int | float) and abs(volume - need) <= 0.05 * need)

    def _their_price_fell(self, neg, plan: Plan) -> bool:
        """Did its last offer come down in price? (P01 R2 raised 138.55 -> 141.30 and got thanked for a step)"""
        prices = [
            (m.get("term_sheets") or [{}])[0].get("terms", {}).get("unit_price")
            for m in neg.threads[plan.supplier_id].supplier_messages
        ]
        prices = [p for p in prices if p]
        return len(prices) >= 2 and prices[-1] < prices[-2] - 1e-9

    def _take_up_lines(self, neg, plan: Plan, sheets: list[dict]) -> list[str]:
        """One sentence for each condition and request of its last e-mail that the options alone do not answer."""
        f, out = plan.facts, []
        if not f:
            return out
        if "call" in f.questions:
            out.append("We would rather settle it here in writing: the options below are ready to sign.")
        if f.signals & {"price_frozen", "terms_room"} and not self.flags["respond_lite"]:
            out.append("We understand that your price list stays; the options below move on the terms instead.")
        if any(k == "index_clause" for k, _ in f.conditions) and "index_clause" in neg.case["negotiable"]:
            if sheets and all(sh["terms"].get("index_clause") for sh in sheets):
                out.append("Every option includes the index clause you require.")
        for lever, value in plan.price_terms.items():
            if sheets and all(sh["terms"].get(lever) == value for sh in sheets):
                out.append(f"All options keep {FIELD_WORDS.get(lever, lever)} at {value} days, as your price requires.")
        plan.price_terms.clear()
        return out

    def _fixed_field_answers(self, neg, plan: Plan) -> list[str]:
        """It asks for a lever this case does not let us move: say so once, and name what can move (P11 asked for
        faster payment four times and never got an answer)."""
        body = neg.threads[plan.supplier_id].latest.get("body", "")
        fixed = [f for f in requests_in(body) if f not in neg.case["negotiable"] and f not in plan.answered_fixed]
        fixed = [f for f in fixed if f != "volume_per_year"]  # answered by the volume sentence
        if not fixed:
            return []
        plan.answered_fixed.update(fixed)
        movable = [FIELD_WORDS.get(f, f) for f in neg.case["negotiable"] if f != "unit_price"]
        what = " and ".join(FIELD_WORDS.get(f, f.replace("_", " ")) for f in fixed)
        can = "the price" + (f", {', '.join(movable)}" if movable else "")
        return [f"We cannot change {what} in this contract; we can move on {can}."]

    def _volume_answer(self, neg, plan: Plan, sheets: list[dict]) -> tuple[str, str | None] | None:
        """ "Which volume can you commit to?" answered with the volume of this contract - the forecast's figure was
        another quantity in five cases (P18: 118,500 against a need of 23,700) and it kept asking."""
        body = neg.threads[plan.supplier_id].latest.get("body", "")
        if plan.volume_proved or not requests_in(body) & {"volume_per_year"}:
            return None
        plan.volume_proved = True
        volumes = {sh["terms"].get("volume_per_year") for sh in sheets}
        if len(volumes) == 1 and None not in volumes:
            return f"We commit to {volumes.pop():,} units a year on every option below.", None
        need = neg.buyer.get("need_per_year")
        return (f"Our requirement is {need:,} units a year, the full volume of this contract.", None) if need else None

    def _volume_proof(self, neg, plan: Plan, sheets: list[dict]) -> tuple[str, str] | None:
        """ "Which volume can you commit to?" (the bots' most common question) - answered once, with the
        forecast we share with suppliers, by ID, so it reads as documentation and not as a claim."""
        if "volume_per_year" not in plan.requests or plan.volume_proved or not self.data:
            return None
        if any(r.startswith("fc:") for r in self.used_refs) or "forecast" in plan.spent_kinds:
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
        # a commitment we state is one every option keeps (conduct.py: keep our word)
        on_every_option = volume and all(sh["terms"].get("volume_per_year") == volume for sh in sheets)
        commit = f" and we commit to {volume:,} units a year" if on_every_option else ""
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
        if (neg.case.get("round_limit") or 10) - t.rounds_used <= 2:
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


TRADE_WORDS = {
    "payment_days": lambda v: f"payment at {v} days",
    "contract_months": lambda v: f"a {v}-month commitment",
    "volume_per_year": lambda v: f"{v:,} units a year",
    "lead_time_days": lambda v: f"{v} days lead time",
    "incoterm": lambda v: f"delivery {v}",
    "index_clause": lambda v: "an index clause" if v else "a fixed price",
    "ppm_commitment": lambda v: f"{v} ppm",
    "chargeback_eur_per_complaint": lambda v: f"EUR {v} per complaint",
    "effective_date": lambda v: f"a start on {v}",
}


def trade_note(case: dict, lead: dict, terms: dict) -> str:
    """How an option differs from option A, said as the trade it is: "- if you prefer payment at 14 days"."""
    if terms is lead:
        return ""
    diffs = [TRADE_WORDS[f](terms[f]) for f in case["negotiable"] if f in TRADE_WORDS and terms.get(f) != lead.get(f)]
    return f" - our price for {' and '.join(diffs[:2])}" if diffs else ""


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
