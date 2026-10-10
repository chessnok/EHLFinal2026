"""Decided buyer: one strategy (tactical) at several levels of aggressiveness; the OpenAI Decisions API picks.

Each round, for one thread, the tactical strategy runs on copies of its state at each level - all harder than plain
tactical, and different in every round where tactical would move at all:

  firm       a first ask 1.3x as deep below the opening C, then 60 % of tactical's step
  hard       1.7x as deep, then 30 % of the step - tests how far the supplier goes
  very_hard  2.2x as deep, then no step at all - holds position and lets the supplier move

Every candidate is a complete, guarded move: term sheets from C, checked arguments, the e-mail. The Decisions API
(`decisions.py`) reads the case, the supplier's profile, the price paths and the latest e-mails, and picks one. The
chosen copy's state for that supplier becomes ours, so candidates that were not sent leave no trace (no arguments
marked used, no asks recorded). If the API fails or is slow, `firm` is sent. Every choice is recorded (`decided`
events with the probabilities and confidence; `decided.choice.<level>` counters).
"""

import copy
import json
import math
import threading

from negotiator.data import WorldData
from negotiator.decisions import DecisionError, DecisionsClient, predicate, score
from negotiator.session import Negotiation
from negotiator.strategy.base import Decision
from negotiator.strategy.tactical import TacticalStrategy
from negotiator.telemetry import log

# level -> (depth of the first ask below the opening C, share of tactical's step we take later, description).
# All levels are harder than plain tactical, and they differ in every round where tactical would move at all:
# the step scales tactical's own next ask, so the stall logic cannot collapse them into one move.
LEVELS = {
    "firm": (1.3, 0.6, "Ask somewhat more than usual and give about half of the normal step."),
    "hard": (1.7, 0.3, "Ask for much more and give only a small step: test how far the supplier will go."),
    "very_hard": (
        2.2,
        0.0,
        "Ask for the most and give nothing this round: hold our position and let the supplier move.",
    ),
}
DEFAULT_LEVEL = "firm"

INSTRUCTIONS = """You are the head of purchasing at Hollerau Pumpenwerke, a German pump maker, reviewing the buyer's
next e-mail to a supplier. The candidates differ only in aggressiveness: how much we ask and how fast we concede. All
are valid and safe. The goal is the lowest total cost C for us at the END of the negotiation, not in this round.
Pick the candidate most likely to get there with this supplier: a supplier that keeps making real steps rewards
patience (harder); one that stalls, hints at its limit, needs approval or is close to walking away needs a softer
step to keep the deal; repeated tiny steps mean we are near its floor.
Money: C is what we pay in EUR over the whole horizon for our whole need (price, uncovered need bought at the
fallback price, payment interest, freight, quality and so on). LOWER C IS BETTER for us. Each candidate states the C
we pay if the supplier accepts it and how much that saves. A greedier ask saves more only if the supplier eventually
agrees; if it stalls the talks or makes the supplier walk, we end up paying more - or the alternative."""


# Asked in the same call as the choice (input tokens only, no output charge): telemetry on how the model reads the
# supplier, to compare later with what actually happened.
EXTRA_QUESTIONS = [
    predicate("near_floor", "Is the supplier at or very close to the lowest price it will accept?"),
    predicate("walk_risk", "Would the supplier walk away or stop negotiating if we pushed harder this round?"),
    score(
        "firmness",
        "How firm is this supplier in this negotiation?",
        [
            ("very_flexible", "Moves a lot every round and invites offers."),
            ("flexible", "Makes real steps when given reasons."),
            ("balanced", "Moves moderately, trades terms for price."),
            ("firm", "Small steps only, insists on its calculation."),
            ("immovable", "Will not move further; final offer territory."),
        ],
    ),
]


class DecidedStrategy:
    name = "decided"

    def __init__(self, data: WorldData | None = None, decider: DecisionsClient | None = None) -> None:
        self.data = data
        self.decider = decider or DecisionsClient()
        self.primary = ScaledTactical(data)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ delegated to tactical
    def prepare(self, neg: Negotiation) -> None:
        self.primary.prepare(neg)

    def conclude(self, neg: Negotiation) -> Decision:
        return self.primary.conclude(neg)

    def keepalive(self, neg: Negotiation, supplier_id: str) -> dict | None:
        return self.primary.keepalive(neg, supplier_id)

    # ------------------------------------------------------------------ one move
    def decide(self, neg: Negotiation, supplier_id: str) -> Decision:
        candidates: dict[str, tuple[Decision, TacticalStrategy]] = {}
        for level in LEVELS:
            clone = self._clone()
            self._apply_level(clone, supplier_id, level)
            candidates[level] = (clone.decide(neg, supplier_id), clone)

        messages = {lv: pair for lv, pair in candidates.items() if pair[0].kind == "message"}
        if len(messages) <= 1 or _same_offers([d for d, _ in messages.values()]):
            # nothing to choose: all hold, or every level would send the same sheets
            level = DEFAULT_LEVEL if DEFAULT_LEVEL in messages or not messages else next(iter(messages))
            decision, clone = candidates[level]
            self._adopt(clone, supplier_id)
            return decision

        level, meta = self._choose(neg, supplier_id, messages)
        decision, clone = messages[level]
        self._adopt(clone, supplier_id)
        neg.recorder.metrics.incr(f"decided.choice.{level}")
        decision.rationale = {**decision.rationale, "decided": {"level": level, **meta}}
        return decision

    def _clone(self) -> TacticalStrategy:
        """A copy of the strategy's state; the data package is shared, locks are fresh."""
        with self._lock:
            p = self.primary
            memo = {id(p.data): p.data, id(p._claims_lock): threading.Lock()}
            return copy.deepcopy(p, memo)

    def _apply_level(self, clone: "ScaledTactical", sid: str, level: str) -> None:
        clone.depth, clone.step_share, _ = LEVELS[level]

    def _adopt(self, clone: TacticalStrategy, sid: str) -> None:
        """Take over the chosen candidate's state for this supplier; merge what the case shares."""
        with self._lock:
            p = self.primary
            if sid in clone.tplans:
                p.tplans[sid] = clone.tplans[sid]
            if sid in clone.plans:
                p.plans[sid] = clone.plans[sid]
            p.used_refs |= clone.used_refs
            p.used_rival_refs |= clone.used_rival_refs
            p.banned_case_kinds |= clone.banned_case_kinds

    def _choose(self, neg: Negotiation, sid: str, messages: dict) -> tuple[str, dict]:
        t = neg.threads[sid]
        plan = self.primary.tplans.get(sid)
        _, theirs = t.standing
        their_c = neg.cost(sid, theirs)
        opens = [p.open_c for p in self.primary.tplans.values() if math.isfinite(p.open_c)]
        c_open = min(opens) if opens else math.inf
        lines = [
            f"Case: {neg.case.get('title')} (type {neg.case.get('type')}, goal {neg.buyer.get('category_goal')}). "
            f"Round {t.rounds_used + 1} of {neg.case.get('round_limit', 10)}. Supplier status: {t.status}.",
            f"Supplier profile: {json.dumps(plan.profile.summary() if plan else {}, default=str)}",
            "All money below is C: our total cost in EUR over the whole horizon by the case's formula - not the unit "
            "price. Its parts: price paid, uncovered need bought at the fallback price plus its risk, interest for "
            "paying earlier than our standard, freight, late delivery, defects, tooling, index clause, supplier "
            "margin charge. LOWER C IS BETTER.",
            f"Supplier's standing offer: terms {json.dumps(theirs)}; C EUR {_k(their_c)} = {_parts(neg, sid, theirs)}.",
            f"Our alternative without a deal: C {_k(neg.c_alt)}.",
            f"Best opening offer in this case: C {_k(c_open)}. Our score grows with the money saved against it: "
            "every euro of C below it counts, lower C is better.",
            f"Supplier prices so far: {t.price_path()}. Our prices so far: {t.our_price_path()}.",
            "Latest e-mails (oldest first):",
        ]
        for m in t.messages[-4:]:
            who = "Buyer" if m.get("from") == "buyer" else f"Supplier ({m.get('status')})"
            lines.append(f"{who}: {(m.get('body') or '')[:700]}")
        choices = []
        for level, (d, _) in messages.items():
            r = d.rationale
            prices = [s["terms"].get("unit_price") for s in d.message.get("term_sheets", [])]
            sheets = d.message.get("term_sheets", [])
            money = _money(r.get("ask_c"), their_c, c_open)
            parts = _parts(neg, sid, sheets[0]["terms"]) if sheets else "-"
            choices.append(
                {
                    "value": level,
                    "description": f"{LEVELS[level][2]} {money} Its first option's C = {parts}. "
                    f"Unit prices of its options (all at equal C): {prices}.",
                }
            )
        try:
            picked = self.decider.choose(
                "\n".join(lines),
                INSTRUCTIONS,
                choices,
                name="aggressiveness",
                extra_questions=EXTRA_QUESTIONS,
                context={"case_id": neg.case_id, "supplier_id": sid, "round": t.rounds_used + 1},
            )
        except DecisionError as e:
            neg.recorder.metrics.incr("decided.fallback")
            return DEFAULT_LEVEL, {"fallback": str(e)[:200]}
        meta = {"probabilities": picked.probabilities, "confidence": picked.confidence, "signals": picked.extras}
        neg.recorder.event(
            "decided",
            session_id=neg.session_id,
            case_id=neg.case_id,
            supplier_id=sid,
            round=t.rounds_used + 1,
            choice=picked.value,
            **meta,
            candidates={
                lv: {
                    "ask_c": d.rationale.get("ask_c"),
                    "saving_vs_their_offer": round(their_c - d.rationale["ask_c"], 2)
                    if d.rationale.get("ask_c") is not None and math.isfinite(their_c)
                    else None,
                    "prices": [s["terms"].get("unit_price") for s in d.message.get("term_sheets", [])],
                }
                for lv, (d, _) in messages.items()
            },
        )
        ex = picked.extras
        log.info(
            "%s decided: %s (confidence %s, %s) near_floor=%s walk_risk=%s firmness=%s",
            sid,
            picked.value,
            picked.confidence,
            picked.probabilities,
            (ex.get("near_floor") or {}).get("probability"),
            (ex.get("walk_risk") or {}).get("probability"),
            (ex.get("firmness") or {}).get("score"),
        )
        return picked.value, meta


class ScaledTactical(TacticalStrategy):
    """Tactical with its ask scaled: a deeper first ask (`depth`) and a share of its usual step later on."""

    depth = 1.0
    step_share = 1.0

    def _next_c(self, neg: Negotiation, sid: str, plan, their_c: float) -> float:
        usual = super()._next_c(neg, sid, plan, their_c)
        if not plan.our_c:  # first ask: further below the opening C
            if math.isfinite(plan.open_c) and math.isfinite(usual):
                return max(0.0, plan.open_c - (plan.open_c - usual) * self.depth)
            return usual
        last = plan.our_c[-1]
        return last + max(0.0, usual - last) * self.step_share


def _money(ask_c: float | None, their_c: float, c_open: float) -> str:
    """What a candidate is worth in money, if the supplier accepts it: lower C is better."""
    if ask_c is None or not math.isfinite(ask_c):
        return "Its total cost is unknown."
    out = f"If the supplier accepts it, our total cost C is EUR {_k(ask_c)} over the horizon (lower is better)"
    if math.isfinite(their_c) and their_c > 0:
        save = their_c - ask_c
        out += f": EUR {_k(save)} ({save / their_c:.1%}) less than the C of the supplier's current offer"
    if math.isfinite(c_open) and c_open > 0:
        out += f", EUR {_k(c_open - ask_c)} ({(c_open - ask_c) / c_open:.1%}) less than the C of the best opening offer"
    return out + "."


PART_NAMES = {
    "price": "price",
    "uncovered_need": "uncovered need",
    "fallback_risk": "fallback risk",
    "payment_terms": "payment interest",
    "freight": "freight",
    "late_delivery": "late delivery",
    "quality": "defects",
    "tooling": "tooling",
    "index_clause": "index clause",
    "index_risk": "index risk",
    "relationship": "supplier margin charge",
}


def _parts(neg: Negotiation, sid: str, terms: dict) -> str:
    """C of a term sheet split into its non-zero parts, e.g. 'price 172,800 + uncovered need 9,100 + freight 0'."""
    try:
        bd = neg.breakdown(sid, terms)
    except (ValueError, KeyError, TypeError):
        return "unknown"
    parts = [f"{PART_NAMES.get(k, k)} {_k(v)}" for k, v in bd.items() if abs(v) >= 0.5]
    return " + ".join(parts) or "0"


def _same_offers(decisions: list[Decision]) -> bool:
    keys = {json.dumps([s["terms"] for s in d.message.get("term_sheets", [])], sort_keys=True) for d in decisions}
    return len(keys) == 1


def _k(value) -> str:
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return "none"
    return f"{value:,.0f}"
