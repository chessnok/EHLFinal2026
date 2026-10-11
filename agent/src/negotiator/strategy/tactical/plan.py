"""The plan of one supplier thread (`Plan`), the goal policies and the strategy's constants."""

import math
from dataclasses import dataclass, field

from negotiator.belief import FloorBelief
from negotiator.data import Evidence
from negotiator.groundtruth import GroundTruth
from negotiator.profile import SupplierProfile


@dataclass(frozen=True)
class Policy:
    beta: float  # Boulware exponent: > 1 concedes late
    reciprocity: float  # share of the supplier's last concession (in C) we answer at most
    markup: float  # floor vs the supplier's full cost when its margin does not cost us C (suppliers have
    # sold below full cost to keep volume: a leverage floor may sit a little under it)
    claims_first: int = 3  # arguments in the first e-mail
    trade_first: tuple[str, ...] = ()  # levers to offer the supplier, in order


POLICIES = {
    "leverage": Policy(beta=3.0, reciprocity=0.6, markup=-0.03),
    "routine": Policy(beta=2.0, reciprocity=0.8, markup=0.0),
    "quality_first": Policy(beta=2.5, reciprocity=0.8, markup=0.0, trade_first=("contract_months",)),
    "stabilise": Policy(beta=2.0, reciprocity=1.0, markup=0.0, trade_first=("contract_months", "volume_per_year")),
    "secure_supply": Policy(beta=1.8, reciprocity=1.0, markup=0.0, trade_first=("contract_months", "volume_per_year")),
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


SOFT_ANCHOR = 0.5  # `soft_anchor`: the first ask's depth as a share of the usual one
OWN_GAIN = 1.5  # `own_structures`: its own price drop for a structure must exceed what the structure costs us by this
YES_ROOM_SHARE = 0.01  # ... and at most this share of the room (`open_c - target_c`)
CHEAP_YES = 0.002  # a condition of its we accept at our price when it costs us at most this share of C


ANCHOR_RELATIONSHIP = 0.04  # stabilise / secure_supply: below its margin the deal costs us


ANCHOR_ROUTINE = 0.13  # routine goal: a deeper first ask is answered with a final offer


ANCHOR_PRICE_ONLY = 0.10  # ... and 10 % where only the price of a running relationship is at stake


UNDER_FLOOR = 0.02  # the first ask sits this far under the supplier's estimated floor


ALT_ROOM_SHARE = 0.001  # its alternative must save this share of the room ...


ALT_MIN_EUR = 10.0  # ... and at least this much: below it a rounding of the sheet decides


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


MAX_SPREAD = 0.08  # options of one message stay within 8 % of each other's price


EQUAL_C = 0.005  # ... and within 0.5 % of each other's C


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
    signals: object = None  # reading.Signals of its latest reply (set in `_learn`)
    yes_line: str | None = None  # the conditions of its we took at our price, said once


def _k(value: float) -> str:
    return f"{value:,.0f}" if math.isfinite(value) else "inf"


# Candidate changes, each switchable (`tactical+<flag>`) so practice can measure it on its own before it becomes
# part of the strategy; all off. A flag that practice has settled leaves this list: adopted, it is the strategy
# (TRYED.md names the run); rejected, it is deleted with its code.
FLAGS: dict[str, str] = {
    "soft_anchor": "a higher first offer under routine and quality_first goals: the first ask half as deep "
    "(their suppliers moved 0.4-6 % in all; leverage suppliers 15-24 %, P05 36 -> 27.50, need the deep one)",
    "probe_final": "the old RFQ probe: one price push on a final offer behind a safe rival. Off since main's P-58 "
    "(P05 0.865 without it, as with it); in 442 sessions re-sending its own sheet was agreed 71 of 74 times, a push "
    "of 2 %+ walked 13 of 14, the probe walked Hrvelec 10 of 10 times",
    "own_structures": "a structure the supplier itself prices cheaply - its own alternative sheets give the rate, "
    "e.g. P05 Hrvelec 35.00 at 35 days, 31.50 at 52 (snapped to what we may sign: 42) - joins as option B at option "
    "A's C when its drop is 1.5x what the structure costs us; its own lead time beyond our need also without a pair",
    "hide_own_cost": "measurement only: the own plant's should-cost is not read (`_full_cost` None), so strategic "
    "own-plant cases (P01, P02, P03, P10) run the guessed-cost path most hidden strategic suppliers get (A3 floor)",
    "double_count": "our framework agreement already indexes the price to a driver its quote cites: that clause "
    "is cited - a surcharge would count the rise twice (P08, P18 and two unplayed suppliers)",
    "no_q1": "no question in the first e-mail (each one cost 0.43 pp of the first drop, 9 of 12 suppliers): the "
    "cost-breakdown request to an open-book supplier waits for round 2",
}
