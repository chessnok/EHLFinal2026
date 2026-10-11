"""Tactical buyer: category goal + supplier profile -> tactics; tit-for-tat Boulware concessions in C.

Ideas taken from ASTRA (Kwon et al., github.com/DSincerity/ASTRA-NegoAgent) - the tactics, not the
code: a model of the opponent, an optimiser over the published cost function, several offers of
equal value to us that differ in what they give the supplier, and concessions that answer the
supplier's (no move from it, no move from us).

Per case (prepare):
  - the category goal sets the policy: how slowly we concede (Boulware beta), how much of the
    supplier's move we answer (reciprocity), whether we protect its margin;
  - the supplier's profile (profile.py) adjusts it: idle capacity or an approval ladder -> concede
    later; cash-short -> early payment ranks first; hedged -> skip index arguments ...;
  - target C: the first ask's depth under the quote by case goal (ANCHOR_*), deeper where the data
    allow (a grounded floor, a cheaper alternative); under a margin charge never below the price that
    costs us least, and a strategic supplier never below RELATIONSHIP_COST_FLOOR of its should-cost.

Per round (decide), all in C (our total cost, the score's currency):
  - their concession = drop of C of their standing sheet; ours = drop of the C we ask for;
  - next ask: the Boulware curve over the rounds we can still play (round limit and the clock),
    capped by reciprocity - if they did not move, we hold (then a half step to break a deadlock;
    the third stall settles the thread);
  - up to three term sheets at that same C, from the full menu of structures: the one that costs us
    least, the one the supplier takes most readily (its requests answered, closest to its own), and
    the next most acceptable of another kind. Whatever it agrees to costs us the same.
  - arguments: checkable evidence picked by the profile; what came back irrelevant or contradicted
    is not used again.
Closing: the cheapest standing sheet that passes the guards (guards.py), else walk away; a
`final_offer` is taken, never pushed. Our estimate of its floor
never ends an open thread: the supplier does (a final offer, firm words, a stall) or the rounds run out.
Conduct (conduct.py): honest, sourced, no empty threats, the supplier's margin respected - code-checked on send.

The package: `plan` (the thread's state and the constants), `planning` (prepare), `reading` (what a reply
says), `concession` (decide, conclude), `sheets` (the term sheets of a message), `writing` (arguments, words).
"""

from negotiator.data import WorldData
from negotiator.reader import Reader
from negotiator.strategy.baseline import BaselineStrategy
from negotiator.strategy.tactical.choice import ChoiceMixin
from negotiator.strategy.tactical.concession import ConcessionMixin
from negotiator.strategy.tactical.plan import (
    ALT_MIN_EUR,
    ALT_ROOM_SHARE,
    ANCHOR_DATA_EXTRA,
    ANCHOR_PRICE_ONLY,
    ANCHOR_RELATIONSHIP,
    ANCHOR_ROUTINE,
    ANCHOR_SLACK,
    ANCHOR_WITH_LEVERS,
    BIG_STEP,
    CASH_SHORT_RATE,
    CHEAP_YES,
    DEFAULT_POLICY,
    DONE_EPS,
    EQUAL_C,
    FLAGS,
    MAX_SPREAD,
    MIN_STEP,
    PATIENT_GAP,
    POLICIES,
    REANCHOR,
    RELATIONSHIP_COST_FLOOR,
    RELATIONSHIP_MIN_STEP,
    RELATIONSHIP_STEP,
    SHOULD_COST_SHARE,
    STALL_EPS,
    STOP_MARGIN,
    STOP_ROOM,
    UNDER_FLOOR,
    UPPER_ROOM,
    UPPER_ROOM_SHARE,
    Plan,
    Policy,
)
from negotiator.strategy.tactical.planning import PlanningMixin
from negotiator.strategy.tactical.reading import ReadingMixin, parse_breakdown, prices_in_text, reply_signals
from negotiator.strategy.tactical.sheets import SheetsMixin
from negotiator.strategy.tactical.writing import WritingMixin, trade_note

__all__ = [
    "ALT_MIN_EUR",
    "ALT_ROOM_SHARE",
    "ANCHOR_DATA_EXTRA",
    "ANCHOR_PRICE_ONLY",
    "ANCHOR_RELATIONSHIP",
    "ANCHOR_ROUTINE",
    "ANCHOR_SLACK",
    "ANCHOR_WITH_LEVERS",
    "BIG_STEP",
    "CASH_SHORT_RATE",
    "CHEAP_YES",
    "DEFAULT_POLICY",
    "DONE_EPS",
    "EQUAL_C",
    "FLAGS",
    "MAX_SPREAD",
    "MIN_STEP",
    "PATIENT_GAP",
    "POLICIES",
    "REANCHOR",
    "RELATIONSHIP_COST_FLOOR",
    "RELATIONSHIP_MIN_STEP",
    "RELATIONSHIP_STEP",
    "SHOULD_COST_SHARE",
    "STALL_EPS",
    "STOP_MARGIN",
    "STOP_ROOM",
    "UNDER_FLOOR",
    "UPPER_ROOM",
    "UPPER_ROOM_SHARE",
    "Plan",
    "Policy",
    "ExpectedValueStrategy",
    "TacticalStrategy",
    "parse_breakdown",
    "prices_in_text",
    "reply_signals",
    "trade_note",
]


class TacticalStrategy(PlanningMixin, ReadingMixin, ConcessionMixin, SheetsMixin, WritingMixin, BaselineStrategy):
    name = "tactical"

    def __init__(self, data: WorldData | None = None, llm=None, **flags) -> None:
        super().__init__(data, llm)
        unknown = set(flags) - set(FLAGS)
        if unknown:
            raise TypeError(f"unknown flag(s): {sorted(unknown)}")
        self.flags = {flag: bool(flags.get(flag, False)) for flag in FLAGS}
        self.tplans: dict[str, Plan] = {}
        self.banned_case_kinds: set[str] = set()  # contradicted: never again in this case
        # with a model, its reading of each reply is added to the regular expressions' (reading.Signals)
        self.reader = Reader(llm) if llm is not None else None


class ExpectedValueStrategy(ChoiceMixin, TacticalStrategy):
    """`tactical` with the round's choice (take, ask and how much, probe) made by expected cost: choice.py."""

    name = "tactical-ev"
