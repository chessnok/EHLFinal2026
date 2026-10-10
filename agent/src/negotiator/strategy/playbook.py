"""Playbook: the baseline with the rules of docs/knowledge/get-best-price-guide.md that the replays back.

What the sandbox replays showed the baseline doing wrong, and the rule that fixes it:

  landing    The baseline picks the non-price terms that are cheapest at OUR price. The deal closes on the
             supplier's sheet, at its price, where another structure can be cheaper (a price above today's: the
             later the new price applies, the better). Terms are optimised at the supplier's standing price.
  free asks  Among terms that cost us the same, the baseline took an arbitrary one, e.g. a 21-day lead time when 35
             is needed: a cost for the supplier, worth nothing to us. Ties go to the supplier's own terms.
  big steps  The suppliers answer the size of our step: a "slight adjustment" earns a slight one. The deal closes
             on the supplier's sheet, so a step of ours costs nothing while we stay below its floor. We open below
             the target and walk up to it in halving steps (Ackerman): large moves early, a visible limit late.
  cash       The shorter-payment sheet goes out only to a supplier that said it wants cash, then at the shortest
             payment; otherwise the supplier takes the shorter payment and keeps its price.
  no insult  A sheet priced far below the supplier's offer (the equal-cost price of a structure that is bad for us)
             reads as a lowball: it is dropped.
  anchor     Deeper, as in the `lowball` experiment - neither demo bot punished it.
  wording    Appreciation, and one open question next to every move.
  probe      A final offer is answered once with its own price on our terms - a term trade, not a price push -
             when walking away would cost little (`probe="safe"`) or always (`probe="always"`, to measure it).

Everything else - arguments, concession schedule, reciprocity, holding and closing - is the baseline's.
"""

import math
import re
from dataclasses import dataclass

from arena_kit.cost import complete_offer

from negotiator.data import Evidence
from negotiator.session import Negotiation
from negotiator.strategy.base import Decision
from negotiator.strategy.baseline import GOAL_ANCHOR, MIN_STEP, SIGNATURE, BaselineStrategy, SupplierPlan, describe
from negotiator.telemetry import log

CASH_SIGNAL = re.compile(
    r"need the \d+ days payment|faster payment|earlier payment|payment sooner|liquidity|cash", re.IGNORECASE
)
QUESTIONS = [
    "What would you need from us to come closer on price - a different payment term, delivery term or commitment?",
    "Which of the terms above costs you most, and what would the price be without it?",
    "What would have to change on our side for you to reach option A?",
]
PROBE_FALLBACK = 0.02  # "safe": the next best outcome costs at most 2 % more than the final offer


@dataclass(frozen=True)
class Playbook:
    name: str = "playbook"
    anchor_scale: float = 1.5  # multiplies the baseline's anchor per category goal
    landing: bool = True  # optimise the non-price terms at the supplier's price
    first_claims: int = 2  # arguments in the first e-mail; one a round after that
    depth: float = 0.10  # we open this far below the target and close half of the rest every round
    cash_on_signal: bool = True  # the shorter-payment sheet only for a supplier that asked for cash
    min_sheet_share: float = 0.75  # drop sheets priced below this share of the supplier's price
    wording: bool = True
    probe: str = "safe"  # off | safe | always


VARIANTS = {
    p.name: p
    for p in (
        Playbook(),
        Playbook("playbook-probe", probe="always"),
        Playbook("pb-a", landing=False, cash_on_signal=False, depth=0.0),
        Playbook("pb-b", landing=True, cash_on_signal=False, depth=0.0),
        Playbook("pb-c", landing=False, cash_on_signal=True, depth=0.0),
        Playbook("pb-d", landing=False, cash_on_signal=False, depth=0.0, wording=False),
    )
}


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

    def _next_price(self, plan: SupplierPlan, theirs, ours, round_index, their_path=None) -> float:
        if not self.pb.depth:
            return super()._next_price(plan, theirs, ours, round_index, their_path)
        start = plan.target_price * (1 - self.pb.depth)
        price = start + (plan.target_price - start) * (1 - 0.5**round_index)
        if ours:  # never back, and never the same numbers again: that counts as no move
            price = max(price, ours[-1] * (1 + MIN_STEP))
        return round(min(price, theirs), 2)

    def _optimise(self, neg: Negotiation, sid: str, terms: dict) -> dict:
        """The baseline's coordinate descent, at the landing price, with ties going to the supplier's own terms."""
        t = neg.threads[sid]
        standing = t.standing[1]
        theirs, price = standing.get("unit_price"), terms.get("unit_price")
        at = price
        if self.pb.landing and theirs and price is not None and price < theirs:
            at = theirs
        prefer = {**t.standard_terms, **{k: v for k, v in standing.items() if v is not None}}
        options = neg.case.get("term_options", {})
        best = {**terms, "unit_price": at}
        for _ in range(2):
            for f in neg.case["negotiable"]:
                if f == "unit_price" or not options.get(f):
                    continue

                def key(value, f=f):
                    trial = {**best, f: value}
                    cost = neg.cost(sid, trial) if neg.keeps_must_haves(sid, trial) else math.inf
                    return (round(cost, 2), _distance(value, prefer.get(f)), repr(value))

                best[f] = min(options[f], key=key)
        return {**best, "unit_price": price}

    def _term_sheets(self, neg: Negotiation, sid: str, theirs: dict, price: float) -> list[dict]:
        sheets = super()._term_sheets(neg, sid, theirs, price)
        floor = theirs["unit_price"] * self.pb.min_sheet_share
        return [s for s in sheets if s["terms"]["unit_price"] >= floor] or sheets[:1]

    def _cash_days(self, neg: Negotiation, sid: str, shorter: list[int]) -> int | None:
        if not self.pb.cash_on_signal:
            return super()._cash_days(neg, sid, shorter)
        return shorter[0] if shorter and self._said(neg, sid, CASH_SIGNAL) else None

    def _said(self, neg: Negotiation, sid: str, pattern: re.Pattern) -> bool:
        return any(pattern.search(m.get("body") or m.get("text") or "") for m in neg.threads[sid].supplier_messages)

    # ------------------------------------------------------------------ final offer
    def _may_probe(self, neg: Negotiation, sid: str) -> bool:
        t = neg.threads[sid]
        if self.pb.probe == "off" or sid in self.probed:
            return False
        if neg.case.get("round_limit", 10) - t.rounds_used <= 1 or neg.seconds_to_deadline() < 120:
            return False
        if self.pb.probe == "always":
            return True
        fallback = neg.c_alt if neg.c_alt is not None else math.inf
        for other, o in neg.threads.items():
            offer_id, terms = o.standing
            if other != sid and offer_id and o.live and neg.keeps_must_haves(other, terms):
                fallback = min(fallback, neg.cost(other, terms))
        return fallback <= neg.cost(sid, t.standing[1]) * (1 + PROBE_FALLBACK)

    def _probe(self, neg: Negotiation, sid: str) -> Decision | None:
        """The supplier's final price on our terms: it keeps its number, we ask for the terms around it."""
        case, plan = neg.case, self.plans[sid]
        theirs = neg.threads[sid].standing[1]
        if theirs.get("unit_price") is None:
            return None
        self.probed.add(sid)
        terms = self._optimise(neg, sid, dict(theirs))
        if "payment_days" in theirs and self._said(neg, sid, CASH_SIGNAL):
            terms["payment_days"] = theirs["payment_days"]
        terms = complete_offer(case, terms)
        c_theirs, c_ours = neg.cost(sid, theirs), neg.cost(sid, terms)
        if c_ours >= c_theirs - 1 or not neg.keeps_must_haves(sid, terms):
            return None
        asks = [k for k in case["negotiable"] if k != "unit_price" and theirs.get(k) != terms.get(k)]
        changed = {k: terms[k] for k in asks}
        body = [
            f"Dear {plan.name} team," if plan.name != plan.supplier_id else "Dear Sir or Madam,",
            "",
            "thank you for your final offer - we appreciate the steps you have taken, and we do not ask you to go "
            f"below your price of EUR {theirs['unit_price']:,.2f} per unit.",
            f"To sign at that price we need one thing around it: {describe(case, changed)}.",
            "If you can confirm this, we close today.",
            "",
            f"Our proposal: {describe(case, terms)}",
            "",
            SIGNATURE,
        ]
        return Decision(
            "message",
            sid,
            message={
                "subject": f"{case.get('title', 'Your quote')}",
                "body": "\n".join(body),
                "term_sheets": [{"terms": terms}],
                "refs": [],
            },
            rationale={"probe": True, "c_theirs": c_theirs, "c_sheets": [c_ours], "changed": sorted(changed)},
        )

    # ------------------------------------------------------------------ wording
    def _opener(self, first: bool) -> str:
        if not self.pb.wording:
            return super()._opener(first)
        if first:
            return (
                "thank you for your quote and for the work behind it. We would like to place this with you; on the "
                "quoted terms we cannot yet."
            )
        return "thank you for your reply. We have taken a further step on every option below."

    def _extra_lines(self, neg: Negotiation, plan: SupplierPlan, first: bool) -> list[str]:
        if not self.pb.wording:
            return []
        return [QUESTIONS[neg.threads[plan.supplier_id].rounds_used % len(QUESTIONS)]]


def _distance(value, preferred) -> float:
    """How far an option is from the supplier's own term (0 when it has none)."""
    if preferred is None or value == preferred:
        return 0.0
    if isinstance(value, int | float) and isinstance(preferred, int | float):
        return float(abs(value - preferred))
    return 1.0
