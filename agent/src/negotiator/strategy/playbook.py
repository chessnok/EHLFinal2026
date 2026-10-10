"""Playbook: the baseline plus the rules of docs/knowledge/get-best-price-guide.md that held up on the sandbox.

  closing    A final offer is answered once with a closing offer on exactly the supplier's terms: its last step
             once more, and we sign today. The suppliers read it as a large step from us and give a last one.
  cash       The shorter-payment sheet pays sooner than the supplier's own term where an option allows. Given the
             choice, a supplier takes the payment it wants and prices it.
  anchor     Deeper, as in the `lowball` experiment - neither demo bot punished it.
  free asks  Among terms that cost us the same, ties go to the supplier's own terms: a 21-day lead time when 35 is
             needed costs the supplier and is worth nothing to us.
  question   One open question in the first e-mail, next to our offer: which term would bring the price down.
  no insult  A sheet priced far below the supplier's offer (the equal-cost price of a structure that is bad for us)
             reads as a lowball: it is dropped.

Tried on the sandbox and left out because they lowered the score (docs/benchmarks/2026-10-10-playbook-none.md):
an open question in every later e-mail, a warmer opener, terms optimised at the supplier's price instead of ours, a
single sheet instead of a menu, a deeper opening with halving steps, and citing case IDs without a figure.

Everything else - arguments, concession schedule, reciprocity, holding and closing - is the baseline's.

An experiment, not a strategy for the final: on the 10 practice cases the closing offer made three suppliers walk
away (0.376 against tactical's 0.695, same record).
"""

import math
from dataclasses import dataclass

from arena_kit.cost import complete_offer

from negotiator.data import Evidence
from negotiator.session import Negotiation
from negotiator.strategy.base import Decision
from negotiator.strategy.baseline import (
    GOAL_ANCHOR,
    SIGNATURE,
    BaselineStrategy,
    SupplierPlan,
    describe,
    structure_key,
)
from negotiator.telemetry import log

QUESTION = (
    "What would you need from us to come closer on price - a different payment term, delivery term or commitment?"
)
PROBE_MIN_STEP = 0.005  # the closing offer asks for at least 0.5 % below the final offer
PROBE_FALLBACK = 0.02  # "safe": the next best outcome costs at most 2 % more than the final offer


@dataclass(frozen=True)
class Playbook:
    name: str = "playbook"
    anchor_scale: float = 1.5  # multiplies the baseline's anchor per category goal
    first_claims: int = 2  # arguments in the first e-mail; one a round after that
    cash_below: bool = True  # the cash sheet pays sooner than the supplier's own term, where an option allows
    min_sheet_share: float = 0.75  # drop sheets priced below this share of the supplier's price
    question: bool = True  # one open question in the first e-mail
    probe: str = "always"  # a closing offer after a final offer: off | safe (only with a fallback) | always


VARIANTS = {p.name: p for p in (Playbook(), Playbook("playbook-noprobe", probe="off"))}


class PlaybookStrategy(BaselineStrategy):
    def __init__(self, playbook: Playbook, data=None, llm=None) -> None:
        super().__init__(data, llm)
        self.pb = playbook
        self.name = playbook.name
        self.probed: set[str] = set()

    # ------------------------------------------------------------------ prepare
    def prepare(self, neg: Negotiation) -> None:
        super().prepare(neg)
        goal = neg.buyer.get("category_goal", "leverage")
        current = neg.buyer.get("current_unit_price")
        for sid, plan in self.plans.items():
            if plan.open_price is None or plan.target_price is None or self.pb.anchor_scale == 1.0:
                continue
            base = min(plan.open_price, current) if current else plan.open_price
            target = base * (1 - GOAL_ANCHOR.get(goal, 0.06) * self.pb.anchor_scale)
            plan.target_price = round(min(max(target, plan.floor_price or 0.0), plan.open_price), 2)
            neg.recorder.event(
                "playbook",
                session_id=neg.session_id,
                case_id=neg.case_id,
                supplier_id=sid,
                variant=self.pb.name,
                target_price=plan.target_price,
            )
            log.info("%s %s: target %s", sid, self.pb.name, plan.target_price)

    def _pick_claims(self, neg: Negotiation, sid: str, plan: SupplierPlan, first: bool) -> list[Evidence]:
        pool = list(plan.evidence)
        rival = self._rival_evidence(neg, sid)
        if rival:
            pool.insert(0, rival)
        return self._claim(sid, pool, self.pb.first_claims if first else 1, distinct_kinds=first)

    # ------------------------------------------------------------------ per thread
    def decide(self, neg: Negotiation, supplier_id: str) -> Decision:
        t = neg.threads[supplier_id]
        if t.live and t.status == "final_offer" and self._may_probe(neg, supplier_id):
            probe = self._probe(neg, supplier_id)
            if probe:
                return probe
        return super().decide(neg, supplier_id)

    def _optimise(self, neg: Negotiation, sid: str, terms: dict) -> dict:
        """The baseline's coordinate descent, with ties going to the supplier's own terms."""
        t = neg.threads[sid]
        prefer = {**t.standard_terms, **{k: v for k, v in t.standing[1].items() if v is not None}}
        options = neg.case.get("term_options", {})
        best = dict(terms)
        for _ in range(2):
            for f in neg.case["negotiable"]:
                if f == "unit_price" or not options.get(f):
                    continue

                def key(value, f=f):
                    trial = {**best, f: value}
                    cost = neg.cost(sid, trial) if neg.keeps_must_haves(sid, trial) else math.inf
                    return (round(cost, 2), _distance(value, prefer.get(f)), repr(value))

                best[f] = min(options[f], key=key)
        return best

    def _term_sheets(self, neg: Negotiation, sid: str, theirs: dict, price: float) -> list[dict]:
        sheets = super()._term_sheets(neg, sid, theirs, price)
        floor = theirs["unit_price"] * self.pb.min_sheet_share
        return [s for s in sheets if s["terms"]["unit_price"] >= floor] or sheets[:1]

    def _cash_days(self, neg: Negotiation, sid: str, shorter: list[int]) -> int | None:
        t = neg.threads[sid]
        own = t.standing[1].get("payment_days") or t.standard_terms.get("payment_days")
        below = [o for o in shorter if own and o < own]
        if self.pb.cash_below and below:
            return below[-1]
        return super()._cash_days(neg, sid, shorter)

    def _extra_lines(self, neg: Negotiation, plan: SupplierPlan, first: bool) -> list[str]:
        return [QUESTION] if self.pb.question and first else []

    # ------------------------------------------------------------------ final offer
    def _may_probe(self, neg: Negotiation, sid: str) -> bool:
        t = neg.threads[sid]
        if self.pb.probe == "off" or sid in self.probed:
            return False
        if (neg.case.get("round_limit") or 10) - t.rounds_used <= 1 or neg.seconds_to_deadline() < 120:
            return False
        if self.pb.probe == "always":
            return True
        fallback = neg.c_alt
        for other, o in neg.threads.items():
            offer_id, terms = o.standing
            if other != sid and offer_id and o.live and neg.keeps_must_haves(other, terms):
                fallback = min(fallback, neg.cost(other, terms))
        return fallback <= neg.cost(sid, t.standing[1]) * (1 + PROBE_FALLBACK)

    def _probe(self, neg: Negotiation, sid: str) -> Decision | None:
        """One closing offer on exactly the supplier's terms: its last step once more, and we sign today."""
        case, plan, t = neg.case, self.plans[sid], neg.threads[sid]
        theirs = t.standing[1]
        path = t.price_path()
        if theirs.get("unit_price") is None or len(path) < 2:
            return None
        self.probed.add(sid)
        step = max(path[-2] - path[-1], path[-1] * PROBE_MIN_STEP)
        terms = complete_offer(case, {**theirs, "unit_price": round(path[-1] - step, 2)})
        key = structure_key(terms)
        if terms["unit_price"] <= plan.offered.get(key, 0.0) or not neg.keeps_must_haves(sid, terms):
            return None
        plan.offered[key] = terms["unit_price"]
        body = [
            f"Dear {plan.name} team," if plan.name != plan.supplier_id else "Dear Sir or Madam,",
            "",
            "thank you for your final offer - we appreciate the steps you have taken, and we accept your terms as "
            "they stand.",
            f"We are ready to sign today at EUR {terms['unit_price']:,.2f} per unit: one more step of the size of "
            "your last one, and a large one from our side.",
            "",
            f"Our proposal: {describe(case, terms)}",
            "",
            SIGNATURE,
        ]
        message = {
            "subject": f"{case.get('title', 'Your quote')}",
            "body": "\n".join(body),
            "term_sheets": [{"terms": terms}],
            "refs": [],
        }
        rationale = {"probe": True, "c_theirs": neg.cost(sid, theirs), "c_sheets": [neg.cost(sid, terms)]}
        return Decision("message", sid, message=message, rationale=rationale)


def _distance(value, preferred) -> float:
    """How far an option is from the supplier's own term (0 when it has none)."""
    if preferred is None or value == preferred:
        return 0.0
    if isinstance(value, int | float) and isinstance(preferred, int | float):
        return float(abs(value - preferred))
    return 1.0
