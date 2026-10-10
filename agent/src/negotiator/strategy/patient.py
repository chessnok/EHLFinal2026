"""Tactical with slower concessions: the same strategy, our step towards the supplier scaled down.

On practice the supplier agreed as soon as our rising offer reached what it would take (P18: 5.00 -> 5.25 -> 5.50,
agreed; docs/backlog.md 2.1). A smaller step leaves it more replies to come down before that. An experiment to
measure that one change; everything else is tactical's.
"""

from negotiator.session import Negotiation
from negotiator.strategy.tactical import MIN_STEP, Plan, TacticalStrategy

SCALES = {"tactical-slow50": 0.5, "tactical-slow25": 0.25}


class PatientStrategy(TacticalStrategy):
    def __init__(self, scale: float, name: str, data=None, llm=None) -> None:
        super().__init__(data, llm)
        self.scale = scale
        self.name = name

    def _next_c(self, neg: Negotiation, sid: str, plan: Plan, their_c: float) -> float:
        ask = super()._next_c(neg, sid, plan, their_c)
        if not plan.our_c:
            return ask
        last = plan.our_c[-1]
        return min(last + max(self.scale * (ask - last), MIN_STEP * last), their_c)
