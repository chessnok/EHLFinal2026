"""Single-tactic experiments on top of the baseline: each variant changes one thing, so a benchmark run
shows what that tactic alone is worth against the supplier bots (results: docs/benchmarks/).

  lowball    a deeper opening anchor: ask for less than we need, so the middle lands in our favour
  questions  three questions in every e-mail: make answering us more work than agreeing
  polite     a warm, appreciative tone
  shelby     a curt, hard tone with a threat to place the order elsewhere
  budget     a ceiling set by a third party ("management released at most EUR X") that we do not cross
  trade      no price move without a move from the supplier, and said so: every option is a trade

Everything else - term sheets from C, arguments, holding and closing - is the baseline's.
"""

from dataclasses import dataclass

from negotiator.session import Negotiation
from negotiator.strategy.baseline import GOAL_ANCHOR, BaselineStrategy, SupplierPlan
from negotiator.telemetry import log

# tone -> (first e-mail, later e-mails, closing line or None)
TONES = {
    "polite": (
        "thank you very much for your quote and for the good cooperation - we appreciate the work your team puts "
        "into it. We would like to find a solution that works for both sides; as it stands the quote is above what "
        "we can accept.",
        "thank you for your reply and for moving towards us - we appreciate it. We have moved as well and hope you "
        "can take a further step.",
        "Thank you for your support - we are confident we will find an agreement.",
    ),
    "shelby": (
        "we have read your quote. It is not a number we will sign.",
        "you have moved a little. It is not enough. We have moved too, and we do not move twice for nothing.",
        "This order will be placed either way - with you or without you. Your move.",
    ),
}
QUESTIONS = [
    "What lead time can you commit to for the first call-off?",
    "Which share of your price is material, and which index does it follow?",
    "How much free capacity do you have for this part in the coming quarter?",
    "Who on your side has to approve a price below your quote?",
    "Would faster payment or a longer commitment help you more?",
    "What defect rate do you achieve on comparable parts?",
    "What would a higher annual volume change in your calculation?",
    "Which Incoterm and packaging are cheapest for you?",
    "Can you hold the price for the whole term without an index clause?",
]


@dataclass(frozen=True)
class Tactic:
    name: str
    anchor_scale: float = 1.0  # multiplies the baseline's anchor per category goal
    tone: str | None = None  # a key of TONES; None: the baseline's wording
    questions_per_round: int = 0
    budget_share: float | None = None  # ceiling = target + share x (opening - target); None: no ceiling
    conditional: bool = False  # the supplier does not move -> we do not move at all


TACTICS = {
    t.name: t
    for t in (
        Tactic("lowball", anchor_scale=1.5),
        Tactic("questions", questions_per_round=3),
        Tactic("polite", tone="polite"),
        Tactic("shelby", tone="shelby"),
        Tactic("budget", budget_share=0.5),
        Tactic("trade", conditional=True),
    )
}


class ExperimentStrategy(BaselineStrategy):
    def __init__(self, tactic: Tactic, data=None, llm=None) -> None:
        super().__init__(data, llm)
        self.tactic = tactic
        self.name = tactic.name
        self.ceilings: dict[str, float] = {}

    def prepare(self, neg: Negotiation) -> None:
        super().prepare(neg)
        tac = self.tactic
        goal = neg.buyer.get("category_goal", "leverage")
        current = neg.buyer.get("current_unit_price")
        for sid, plan in self.plans.items():
            if plan.open_price is None or plan.target_price is None:
                continue
            if tac.anchor_scale != 1.0:
                base = min(plan.open_price, current) if current else plan.open_price
                target = base * (1 - GOAL_ANCHOR.get(goal, 0.06) * tac.anchor_scale)
                plan.target_price = round(min(max(target, plan.floor_price or 0.0), plan.open_price), 2)
            if tac.budget_share is not None:
                gap = plan.open_price - plan.target_price
                self.ceilings[sid] = round(plan.target_price + tac.budget_share * gap, 2)
            neg.recorder.event(
                "experiment",
                session_id=neg.session_id,
                case_id=neg.case_id,
                supplier_id=sid,
                tactic=tac.name,
                target_price=plan.target_price,
                ceiling=self.ceilings.get(sid),
            )
            log.info("%s %s: target %s ceiling %s", sid, tac.name, plan.target_price, self.ceilings.get(sid))

    def _next_price(self, plan: SupplierPlan, theirs, ours, round_index, their_path=None) -> float:
        price = super()._next_price(plan, theirs, ours, round_index, their_path)
        if self.tactic.conditional and ours and their_path and len(their_path) >= 2:
            if their_path[-1] >= their_path[-2]:
                price = ours[-1]
        ceiling = self.ceilings.get(plan.supplier_id)
        if ceiling is not None:
            price = min(price, max(ceiling, ours[-1] if ours else 0.0))
        return price

    def _opener(self, first: bool) -> str:
        if self.tactic.tone is None:
            return super()._opener(first)
        return TONES[self.tactic.tone][0 if first else 1]

    def _extra_lines(self, neg: Negotiation, plan: SupplierPlan, first: bool) -> list[str]:
        tac, lines = self.tactic, []
        ceiling = self.ceilings.get(plan.supplier_id)
        if ceiling is not None:
            lines.append(
                f"Our management has released a fixed budget for this part: EUR {ceiling:,.2f} per unit on the terms "
                "of option A is the most I am allowed to sign."
                if first
                else f"The budget ceiling of EUR {ceiling:,.2f} per unit on the terms of option A stands; I cannot "
                "sign above it."
            )
        if tac.conditional:
            lines.append(
                "We do not pay more without something in return: each option below gives you something you can use "
                "(commitment, payment or delivery terms) at the price it asks. If you need a higher price, tell us "
                "which term you give for it."
            )
        if tac.questions_per_round:
            start = neg.threads[plan.supplier_id].rounds_used * tac.questions_per_round
            lines += [QUESTIONS[(start + i) % len(QUESTIONS)] for i in range(tac.questions_per_round)]
        if tac.tone and TONES[tac.tone][2]:
            lines.append(TONES[tac.tone][2])
        return lines
