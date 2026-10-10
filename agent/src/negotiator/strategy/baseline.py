"""Baseline buyer: data-backed anchoring, a concession schedule, multiple term sheets, cost-based closing.

No language model: every number comes from the published cost function C and the data package. It is
a reference to beat and a harness test, not a winner.

Per supplier it prepares:
  - a target price: the lower of the opening and current price, minus an anchor that follows the
    category goal; never below the should-cost (plus the sustainable margin in strategic/bottleneck
    cases, where squeezing the supplier costs C);
  - checkable arguments (data.Evidence): short notice against the contract, index moves below the
    asked increase, a weak scorecard, should-cost, the alternative quote, a cheaper rival in an RFQ.
Each round it offers up to three term sheets:
  A  the target-path price with every other negotiable term set to what minimises C;
  B  the same price on the supplier's own standing terms (a pure price move);
  C  a "cash" variant: shorter payment at the price that costs us the same C as A.
It holds a thread when the supplier agrees, makes a final offer, stops moving, comes close enough
or runs out of rounds; then it accepts the cheapest standing sheet that beats the alternative.
"""

import math
import threading
from dataclasses import dataclass, field

from arena_kit.cost import RELATIONSHIP_GOALS, complete_offer

from negotiator.data import Evidence, WorldData
from negotiator.session import Negotiation
from negotiator.strategy.base import Decision
from negotiator.telemetry import log

# Opening anchor below the lower of opening and current price, by category goal. Practice showed the
# bots' floors sit far below their openings (C_best often 15-25 % under C_open in leverage cases).
GOAL_ANCHOR = {
    "leverage": 0.18,
    "routine": 0.12,
    "stabilise": 0.08,
    "secure_supply": 0.05,
    "quality_first": 0.06,
}
# Share of the gap between our target and the supplier's price we may have given by each round - a
# ceiling; reciprocity (below) usually keeps us under it.
CONCESSION = [0.0, 0.15, 0.28, 0.40, 0.52, 0.63, 0.73, 0.82]
RECIPROCITY = 1.0  # our step, in % of our price, at most this times the supplier's last step in %
MIN_STEP = 0.004  # ... but at least 0.4 %, so a stalled supplier still sees movement
SANE_PRICE = 0.6  # never put a price below 60 % of the supplier's in front of it, even if C would allow
CLOSE_ENOUGH = 0.005  # within 0.5 % of the supplier's price: take it
MAX_CLAIMS = 3  # the arena checks at most 3 arguments per message
SIGNATURE = "Kind regards\nHollerau Pumpenwerke GmbH, Purchasing"


@dataclass
class SupplierPlan:
    supplier_id: str
    name: str
    open_price: float | None
    target_price: float | None
    floor_price: float | None
    evidence: list[Evidence] = field(default_factory=list)
    asked_cost_breakdown: bool = False
    offered: dict[str, float] = field(default_factory=dict)  # non-price terms -> highest price we offered


class BaselineStrategy:
    name = "baseline"

    def __init__(self, data: WorldData | None = None, llm=None) -> None:
        self.data = data
        self.plans: dict[str, SupplierPlan] = {}
        # Each ID counts once per case (a duplicate earns nothing); only a rival's offer may be cited
        # to every other bidder, once per supplier.
        self.used_refs: set[str] = set()
        self.used_rival_refs: set[tuple[str, str]] = set()
        self._claims_lock = threading.Lock()

    # ------------------------------------------------------------------ prepare
    def prepare(self, neg: Negotiation) -> None:
        case, buyer = neg.case, neg.buyer
        goal = buyer.get("category_goal", "leverage")
        parts = case.get("parts", [])
        current = buyer.get("current_unit_price")
        for sid, thread in neg.threads.items():
            _, terms = thread.standing
            open_price = terms.get("unit_price")
            full_cost = self._full_cost(parts, sid)
            std = thread.standard_terms
            if goal in RELATIONSHIP_GOALS and full_cost and {"payment_days", "incoterm"} <= std.keys():
                neg.supplier_estimates[sid] = {
                    "full_cost": full_cost,
                    "interest_rate": buyer.get("interest_rate", 0.08),
                    "standard": std,
                }
            floor = None
            if full_cost:
                margin = (buyer.get("sustainable_margin_pct") or 0) if goal in RELATIONSHIP_GOALS else 1.0
                floor = round(full_cost / (1 - margin / 100), 2)
            target = None
            if open_price is not None:
                base = min(open_price, current) if current else open_price
                target = base * (1 - GOAL_ANCHOR.get(goal, 0.06))
                if floor:
                    target = max(target, floor)
                target = round(min(target, open_price), 2)
            plan = SupplierPlan(sid, self._name(sid), open_price, target, floor)
            plan.evidence = self._evidence(neg, sid, open_price, current)
            self.plans[sid] = plan
            neg.recorder.event(
                "plan",
                session_id=neg.session_id,
                case_id=neg.case_id,
                supplier_id=sid,
                open_price=open_price,
                target_price=target,
                floor_price=floor,
                full_cost=full_cost,
                evidence=[
                    {"kind": e.kind, "refs": e.refs, "strength": round(e.strength, 2), "sentence": e.sentence}
                    for e in plan.evidence
                ],
            )
            log.info(
                "%s plan: open %s target %s floor %s, %d argument(s)",
                sid,
                open_price,
                target,
                floor,
                len(plan.evidence),
            )

    def _full_cost(self, parts: list[str], supplier_id: str) -> float | None:
        if not self.data or not parts:
            return None
        rows = self.data.query(
            f"SELECT supplier_id, unit_cost FROM should_cost WHERE part_id IN ({','.join('?' for _ in parts)})",
            tuple(parts),
        )
        own = [r for r in rows if r["supplier_id"] == supplier_id]
        row = (own or rows or [None])[0]
        return row["unit_cost"] if row else None

    def _name(self, supplier_id: str) -> str:
        if self.data:
            name = self.data.supplier(supplier_id).get("name")
            if name:
                return name
        return supplier_id

    def _evidence(self, neg: Negotiation, sid: str, open_price: float | None, current: float | None) -> list[Evidence]:
        if not self.data:
            return []
        case, d = neg.case, self.data
        parts = case.get("parts", [])
        asked = (open_price / current - 1) * 100 if open_price and current else None
        trigger = case.get("trigger_doc")
        fact = d.fact(trigger) if trigger else None
        if fact and fact.get("asked_pct") is not None:
            asked = fact["asked_pct"]
        out: list[Evidence] = []
        if fact and fact.get("supplier") == sid:
            out += d.evidence_notice(trigger, sid)
        out += d.evidence_indices(parts, asked)
        out += d.evidence_scorecard(sid)
        if open_price:
            out += d.evidence_should_cost(parts, open_price)
        alt = neg.buyer.get("alternative") or {}
        if alt.get("kind") == "quote" and alt.get("ref"):
            alt_price = (alt.get("terms") or {}).get("unit_price")
            if alt_price and open_price and alt_price < open_price:
                out += d.evidence_quote(alt["ref"])
        return sorted(out, key=lambda e: -e.strength)

    # ------------------------------------------------------------------ per thread
    def decide(self, neg: Negotiation, supplier_id: str) -> Decision:
        t, plan = neg.threads[supplier_id], self.plans[supplier_id]
        if not t.live:
            return Decision.drop(supplier_id, f"thread {t.status}")
        sheet_id, theirs = t.standing
        if t.status in ("agreed", "final_offer"):
            return Decision.hold(supplier_id, t.status)
        if theirs.get("unit_price") is None or plan.target_price is None:
            return Decision.hold(supplier_id, "no price to negotiate on")
        rounds_left = neg.case.get("round_limit", 10) - t.rounds_used
        if rounds_left <= 1:
            return Decision.hold(supplier_id, "last round: keep it for the close")
        if neg.seconds_to_deadline() < 120:
            return Decision.hold(supplier_id, "the deadline is near")
        their_path, our_path = t.price_path(), t.our_price_path()
        if len(our_path) >= 2 and len(their_path) >= 3 and len(set(their_path[-3:])) == 1:
            return Decision.hold(supplier_id, "the supplier stopped moving", price=their_path[-1])

        price = self._next_price(plan, theirs["unit_price"], our_path, t.rounds_used, their_path)
        if self._close_enough(neg, supplier_id, theirs, price):
            return Decision.hold(supplier_id, "close enough", ours=price, theirs=theirs["unit_price"])
        sheets = self._term_sheets(neg, supplier_id, theirs, price)
        if not sheets:
            return Decision.hold(supplier_id, "no term sheet beats the standing offer")
        claims = self._pick_claims(neg, supplier_id, plan, first=t.rounds_used == 0)
        message = self._message(neg, plan, sheets, claims, first=t.rounds_used == 0)
        c_theirs = neg.cost(supplier_id, theirs)
        return Decision(
            "message",
            supplier_id,
            message=message,
            rationale={
                "round": t.rounds_used + 1,
                "target": plan.target_price,
                "price": price,
                "their_price": theirs["unit_price"],
                "c_theirs": c_theirs,
                "c_sheets": [neg.cost(supplier_id, s["terms"]) for s in sheets],
                "claims": [c.kind for c in claims],
            },
        )

    def _next_price(
        self,
        plan: SupplierPlan,
        theirs: float,
        ours: list[float],
        round_index: int,
        their_path: list[float] | None = None,
    ) -> float:
        """Price of our C-optimal sheet this round: the concession schedule as a ceiling, and never a bigger
        step (in %) than the supplier's own last step - it moves, we move; it stands, we barely move."""
        share = CONCESSION[min(round_index, len(CONCESSION) - 1)]
        price = plan.target_price + (theirs - plan.target_price) * share
        if ours:
            their_step = 0.0
            if their_path and len(their_path) >= 2 and their_path[-2]:
                their_step = (their_path[-2] - their_path[-1]) / their_path[-2]
            step_cap = ours[-1] * max(their_step * RECIPROCITY, MIN_STEP)
            price = min(price, ours[-1] + step_cap)
            price = max(price, ours[-1])  # never go back on an offer
        return round(min(price, theirs), 2)

    def _term_sheets(self, neg: Negotiation, sid: str, theirs: dict, price: float) -> list[dict]:
        """A menu of equal cost to us (MESO): A is the C-optimal structure at `price`; B is the supplier's own
        structure and C a shorter-payment variant, each priced so that its C equals A's. The supplier picks
        what suits it; whatever it picks costs us the same. Each structure's price only ever rises."""
        case, plan = neg.case, self.plans[sid]
        c_theirs = neg.cost(sid, theirs)
        ideal = complete_offer(case, self._optimise(neg, sid, {**theirs, "unit_price": price}))
        c_target = neg.cost(sid, ideal)
        candidates = [ideal]
        own = complete_offer(case, {**theirs, "unit_price": price})
        own["unit_price"] = self._iso_cost_price(neg, sid, own, c_target)
        candidates.append(own)
        if "payment_days" in case["negotiable"]:
            options = sorted(o for o in case.get("term_options", {}).get("payment_days", []) if o is not None)
            days = self._cash_days(neg, sid, [o for o in options if o < ideal.get("payment_days", 0)])
            if days is not None:
                cash = {**ideal, "payment_days": days}
                cash["unit_price"] = self._iso_cost_price(neg, sid, cash, c_target)
                candidates.append(complete_offer(case, cash))
        out, seen = [], set()
        for terms in candidates:
            key = structure_key(terms)
            terms["unit_price"] = round(max(terms["unit_price"], plan.offered.get(key, 0.0)), 2)
            if key in seen or not neg.keeps_must_haves(sid, terms):
                continue
            if terms["unit_price"] < theirs["unit_price"] * SANE_PRICE:
                continue
            if neg.cost(sid, terms) >= c_theirs:  # never offer something dearer than what is on the table
                continue
            seen.add(key)
            out.append({"terms": terms})
        for sheet in out[:3]:
            key = structure_key(sheet["terms"])
            plan.offered[key] = max(plan.offered.get(key, 0.0), sheet["terms"]["unit_price"])
        return out[:3]

    def _cash_days(self, neg: Negotiation, sid: str, shorter: list[int]) -> int | None:
        """Payment days of the cash variant, from the options shorter than our ideal (a hook for variants)."""
        return shorter[len(shorter) // 2] if shorter else None

    def _close_enough(self, neg: Negotiation, sid: str, theirs: dict, price: float) -> bool:
        """Hold only when the standing offer costs us no more than our best structure at its price would:
        close in price on a worse structure (e.g. a shorter contract) is not close in C."""
        if price < theirs["unit_price"] * (1 - CLOSE_ENOUGH):
            return False
        best_at_theirs = complete_offer(neg.case, self._optimise(neg, sid, dict(theirs)))
        return neg.cost(sid, theirs) <= neg.cost(sid, best_at_theirs) * (1 + CLOSE_ENOUGH)

    def _optimise(self, neg: Negotiation, sid: str, terms: dict) -> dict:
        """Coordinate descent over the non-price options: each field set to what minimises C."""
        options = neg.case.get("term_options", {})
        best = dict(terms)
        for _ in range(2):
            for f in neg.case["negotiable"]:
                if f == "unit_price" or not options.get(f):
                    continue

                def key(value, f=f):
                    trial = {**best, f: value}
                    ok = neg.keeps_must_haves(sid, trial)
                    return (neg.cost(sid, trial) if ok else math.inf, repr(value))

                best[f] = min(options[f], key=key)
        return best

    def _iso_cost_price(self, neg: Negotiation, sid: str, terms: dict, target_c: float) -> float:
        """The price at which these terms cost us `target_c` (C rises with the price)."""
        lo, hi = 0.0, terms["unit_price"] * 1.5
        for _ in range(40):
            mid = (lo + hi) / 2
            if neg.cost(sid, {**terms, "unit_price": mid}) > target_c:
                hi = mid
            else:
                lo = mid
        return round(lo, 2)

    def _pick_claims(self, neg: Negotiation, sid: str, plan: SupplierPlan, first: bool) -> list[Evidence]:
        pool = list(plan.evidence)
        rival = self._rival_evidence(neg, sid)
        if rival:
            pool.insert(0, rival)
        return self._claim(sid, pool, MAX_CLAIMS if first else 1, distinct_kinds=first)

    def _claim(self, sid: str, pool: list[Evidence], limit: int, distinct_kinds: bool = False) -> list[Evidence]:
        """Take up to `limit` arguments from `pool` that have not been used yet (each ID counts once per
        case; a rival's offer once per supplier) and mark them used. Threads of one case call this at once."""
        with self._claims_lock:
            picked: list[Evidence] = []
            kinds = set()
            for e in pool:
                if len(picked) >= limit:
                    break
                if e.kind == "rival_offer":
                    if any((sid, r) in self.used_rival_refs for r in e.refs):
                        continue
                elif any(r in self.used_refs for r in e.refs) or (distinct_kinds and e.kind in kinds):
                    continue
                picked.append(e)
                kinds.add(e.kind)
            for e in picked:
                if e.kind == "rival_offer":
                    self.used_rival_refs.update((sid, r) for r in e.refs)
                else:
                    self.used_refs.update(e.refs)
            return picked

    def _rival_evidence(self, neg: Negotiation, sid: str) -> Evidence | None:
        """In an RFQ: a rival's standing offer that is cheaper than this supplier's."""
        if len(neg.threads) < 2:
            return None
        mine = neg.threads[sid].standing[1].get("unit_price")
        best = None
        for other, t in neg.threads.items():
            offer_id, terms = t.standing
            if other == sid or not offer_id or terms.get("unit_price") is None:
                continue
            if mine and terms["unit_price"] < mine and (best is None or terms["unit_price"] < best[1]):
                best = (offer_id, terms["unit_price"])
        if not best:
            return None
        return Evidence(
            kind="rival_offer",
            refs=[best[0]],
            sentence=f"Another bidder offers EUR {best[1]:.2f} per unit ({best[0]}).",
            strength=3.0,
        )

    def _message(
        self, neg: Negotiation, plan: SupplierPlan, sheets: list[dict], claims: list[Evidence], first: bool
    ) -> dict:
        case = neg.case
        lines = [f"Dear {plan.name} team," if plan.name != plan.supplier_id else "Dear Sir or Madam,", ""]
        lines.append(self._opener(first))
        lines += [c.sentence for c in claims]
        if first and not plan.asked_cost_breakdown:
            lines.append("Could you send us a cost breakdown for this part?")
            plan.asked_cost_breakdown = True
        lines += self._extra_lines(neg, plan, first)
        lines.append("")
        lines.append("We can award on any of these options:" if len(sheets) > 1 else "Our proposal:")
        for i, sheet in enumerate(sheets):
            lines.append(f"Option {chr(65 + i)}: {describe(case, sheet['terms'])}")
        lines += ["", SIGNATURE]
        refs = sorted({r for c in claims for r in c.refs})
        return {
            "subject": f"{case.get('title', 'Your quote')}",
            "body": "\n".join(lines),
            "term_sheets": sheets,
            "refs": refs,
        }

    def _opener(self, first: bool) -> str:
        if first:
            return "thank you for your quote. We have reviewed it against our data and cannot accept it as it stands."
        return "thank you for your reply. We have moved towards you; we need you to move as well."

    def _extra_lines(self, neg: Negotiation, plan: SupplierPlan, first: bool) -> list[str]:
        """Sentences after the arguments, before the options (a hook for variants)."""
        return []

    # ------------------------------------------------------------------ closing
    def conclude(self, neg: Negotiation) -> Decision:
        c_alt = neg.c_alt
        best = None
        for sid, t in neg.threads.items():
            sheet_id, terms = t.standing
            if not sheet_id or t.closed or t.status in ("walked_away", "no_bid"):
                continue
            if not neg.keeps_must_haves(sid, terms):
                continue
            c = neg.cost(sid, terms)
            if best is None or c < best[0]:
                best = (c, sid, sheet_id)
        if best and best[0] < c_alt:
            return Decision(
                "accept",
                best[1],
                term_sheet_id=best[2],
                rationale={
                    "c": best[0],
                    "c_alt": c_alt,
                    "why": "cheapest standing sheet beats the alternative",
                },
            )
        return Decision(
            "walk_away",
            next(iter(neg.threads)),
            rationale={
                "c_best_standing": best[0] if best else None,
                "c_alt": c_alt,
                "why": "nothing beats the alternative",
            },
        )

    def keepalive(self, neg: Negotiation, supplier_id: str) -> dict | None:
        t = neg.threads[supplier_id]
        if neg.case.get("round_limit", 10) - t.rounds_used <= 2:
            return None
        return {
            "subject": f"{neg.case.get('title', 'Your quote')}",
            "body": f"Dear {self.plans[supplier_id].name} team,\n\nthank you. While we complete our evaluation: "
            f"could you confirm your delivery capacity for our annual volume?\n\n{SIGNATURE}",
        }


def structure_key(terms: dict) -> str:
    """The non-price terms of a sheet: offers with the same structure must never get cheaper."""
    return repr(sorted((k, v) for k, v in terms.items() if k != "unit_price"))


def describe(case: dict, terms: dict) -> str:
    """A term sheet in words, for the e-mail body (the term sheet itself is what binds)."""
    unit = (case.get("buyer") or {}).get("price_unit")
    parts = []
    for k, v in terms.items():
        if k == "unit_price":
            parts.append(f"EUR {v:,.2f} per unit" + (f" ({unit})" if unit else ""))
        elif k == "payment_days":
            parts.append(f"payment {v} days net")
        elif k == "lead_time_days":
            parts.append(f"lead time {v} days")
        elif k == "contract_months":
            parts.append(f"{v}-month contract" if v else "single order")
        elif k == "volume_per_year":
            parts.append(f"{v:,} units a year")
        elif k == "effective_date":
            parts.append(f"price valid from {v}")
        elif k == "index_clause":
            parts.append(
                "no index clause"
                if not v
                else f"index clause on {v['series']} ({v['material_share']:.0%} material, deadband "
                f"{v['deadband_pct']}%, base {v['base_month']})"
            )
        elif k == "incoterm":
            parts.append(f"Incoterm {v}")
        elif k == "tooling_eur":
            parts.append(f"tooling EUR {v:,.2f}")
        elif k == "ppm_commitment":
            parts.append(f"quality commitment {v} ppm")
        elif k == "chargeback_eur_per_complaint":
            parts.append(f"chargeback EUR {v} per complaint")
        else:
            parts.append(f"{k} {v}")
    return ", ".join(parts)
