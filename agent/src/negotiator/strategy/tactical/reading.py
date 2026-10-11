"""Per reply: what came back - argument checks, requests, stalls, a breakdown, the floor belief."""

import math
import re
from dataclasses import dataclass, field

from arena_kit.cost import RELATIONSHIP_GOALS

from negotiator.ledger import CITED_DRIVER, arguments_read, reply_facts
from negotiator.menu import proposed_values, requests_in, satisfies
from negotiator.reply_parser import ReplyFacts, parse_reply
from negotiator.session import Negotiation
from negotiator.strategy.tactical.plan import (
    STALL_EPS,
    STOP_MARGIN,
    STOP_ROOM,
    UPPER_ROOM,
    UPPER_ROOM_SHARE,
    Plan,
    _k,
)
from negotiator.telemetry import log

# what a supplier's e-mail says between the lines
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


def reply_signals(body: str) -> dict:
    """Firmness in the supplier's own words: a last word without the `final_offer` status."""
    return {"firm": bool(FIRM_SIGNALS.search(body or ""))}


@dataclass
class Signals:
    """What one reply says beyond its term sheets - read once, in `_learn`, and kept on the plan (`plan.signals`),
    so every rule asks the same reading instead of matching the e-mail again.

    The regular expressions read first (they know the arena's fixed sentences); a model, where one is configured
    (reader.py), adds what they miss in other words. The model only ever adds: a signal it reports counts when the
    words it quotes stand in the e-mail, and a price only when that figure does."""

    firm: bool = False  # a last word in its own words, without the `final_offer` status
    pending: bool = False  # it checks internally: the rest of its step comes whatever we send
    requests: set = field(default_factory=set)  # negotiable levers it asks us to move
    stated_price: float | None = None  # a price below its sheets that it names in the text
    by_model: list = field(default_factory=list)  # which of these only the model found

    def summary(self) -> dict:
        return {"firm": self.firm, "pending": self.pending, "requests": sorted(self.requests),
                "stated_price": self.stated_price, "by_model": self.by_model}  # fmt: skip


def read_signals(reply: dict, negotiable: list[str]) -> Signals:
    """The regular expressions' reading of one reply."""
    body = reply.get("body") or ""
    prices = [s["terms"].get("unit_price") for s in reply.get("term_sheets") or [] if s.get("terms")]
    prices = [p for p in prices if p]
    said = [p for p in prices_in_text(body) if prices and 0.6 * min(prices) < p < min(prices) - 0.004]
    return Signals(
        firm=bool(FIRM_SIGNALS.search(body)),
        pending=bool(APPROVAL_PENDING.search(body)),
        requests={r for r in requests_in(body) if r in negotiable},
        stated_price=min(said) if said else None,  # "I am dropping the price to EUR 28.00" on a 29.09 sheet (P05)
    )


def merge_hints(signals: Signals, hints: dict, reply: dict, negotiable: list[str]) -> Signals:
    """The model's checked hints (reader.checked_hints) added to the regular expressions' reading."""
    for lever in hints.get("levers") or []:
        if lever in negotiable and lever not in signals.requests:
            signals.requests.add(lever)
            signals.by_model.append(f"request:{lever}")
    if hints.get("last_word") and not signals.firm:
        signals.firm = True
        signals.by_model.append("firm")
    if hints.get("approval_pending") and not signals.pending:
        signals.pending = True
        signals.by_model.append("pending")
    price = hints.get("stated_price")
    prices = [s["terms"].get("unit_price") for s in reply.get("term_sheets") or [] if s.get("terms")]
    prices = [p for p in prices if p]
    if price and signals.stated_price is None and prices and 0.6 * min(prices) < price < min(prices) - 0.004:
        signals.stated_price = price
        signals.by_model.append("stated_price")
    return signals


class ReadingMixin:
    def _learn(self, neg: Negotiation, sid: str, plan: Plan) -> None:
        """Read what came back since we last looked: argument checks, stalls, a cost breakdown."""
        t = neg.threads[sid]
        replies = t.supplier_messages
        for reply in replies[plan.seen_replies :]:
            self._learn_claims(t, plan, reply)
            if not plan.breakdown_read:
                self._read_breakdown(neg, sid, plan, reply)
            self._read_reply(neg, sid, reply)
            signals = read_signals(reply, neg.case["negotiable"])
            if reply is replies[-1]:
                signals = self._model_reading(neg, sid, reply, signals)  # one call per reply, the latest only
                plan.signals = signals
                neg.recorder.event("signals", session_id=neg.session_id, supplier_id=sid, signals=signals.summary())
            asked = signals.requests
            for r in asked:
                plan.request_counts[r] = plan.request_counts.get(r, 0) + 1
            plan.requests |= asked
            for series in CITED_DRIVER.findall(reply.get("body", "")):
                if series[0] not in plan.pressures:
                    plan.pressures.append(series[0])
            for fact in reply_facts(self.data, reply.get("body", "")):
                if fact.sentence not in plan.used_sentences and all(fact.sentence != c.sentence for c in plan.counters):
                    plan.counters.append(fact)
            for f, values in proposed_values(neg.case, reply.get("term_sheets") or []).items():
                plan.proposed.setdefault(f, [])
                plan.proposed[f] += [v for v in values if v not in plan.proposed[f]]
                if len(plan.proposed[f]) > 1:
                    plan.requests.add(f)  # it varies this field across its sheets: a lever it trades on
            if signals.stated_price is not None:
                plan.text_price = signals.stated_price
            sheets = reply.get("term_sheets") or []
            if sheets and sheets[0]["terms"].get("index_clause"):
                plan.requests.add("index_clause")  # it proposed one: it wants one
        if len(replies) > plan.seen_replies and plan.seen_replies > 0:
            path = self._their_c_path(neg, sid)
            if len(path) >= 2:
                moved = path[-2] - path[-1]
                plan.stalls = plan.stalls + 1 if moved <= path[-2] * STALL_EPS else 0
        if plan.belief and len(replies) > plan.seen_replies:
            for reply in replies[max(plan.seen_replies, 1) :]:
                plan.belief.observe(reply)
            self._update_upper(neg, sid, plan)
        plan.seen_replies = len(replies)

    def _model_reading(self, neg: Negotiation, sid: str, reply: dict, signals: Signals) -> Signals:
        """With a model (`self.reader`): its checked hints added to the reading. Without one, or when the call
        fails or is slow, the regular expressions' reading stands."""
        reader = getattr(self, "reader", None)
        if reader is None:
            return signals
        earlier = [m for m in neg.threads[sid].supplier_messages if m is not reply and m.get("term_sheets")]
        previous = earlier[-1]["term_sheets"][0].get("terms") if earlier else None
        deadline = getattr(self, "deadlines", {}).get(sid)
        hints = reader.read(neg, sid, reply, previous, deadline)
        if hasattr(self, "hints"):
            self.hints[sid] = hints  # the writer's prompt takes the reasons and questions from here
        signals = merge_hints(signals, hints, reply, neg.case["negotiable"])
        if signals.by_model:
            neg.recorder.metrics.incr("reader.signals_added", len(signals.by_model))
        neg.recorder.event("reader", session_id=neg.session_id, case_id=neg.case_id, supplier_id=sid, hints=hints,
                           added=signals.by_model)  # fmt: skip
        return signals

    @staticmethod
    def _read_reply(neg: Negotiation, sid: str, reply: dict) -> ReplyFacts | None:
        """Every reply read in full and logged (`reply_facts`): the record the readers are validated against."""
        try:
            facts = parse_reply(reply.get("body", ""))
            neg.recorder.event("reply_facts", session_id=neg.session_id, supplier_id=sid, facts=facts.summary())
            return facts
        except Exception as e:  # a reader must never cost a case
            log.warning("%s: reply parser failed: %r", sid, e)
            return None

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
            _, refs = read[i]
            kinds = {c.kind for c in plan.last_claims if set(c.refs) & refs}
            if result == "contradicted":
                self.banned_case_kinds |= kinds
            elif result == "irrelevant":
                plan.banned_kinds |= kinds

    def _facts(self) -> dict:
        return self.data.facts if self.data else {}

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

    def _their_c_path(self, neg: Negotiation, sid: str) -> list[float]:
        """C of each reply's primary sheet: its step and its stalls are read from the sheet the arena closes on.
        Read from its best sheet for us instead (the one `decide` judges its offer by), an alternative that came
        and went counted as a move of its own, our next step followed it, and practice lost P11 0.710 -> 0.626 and
        P18 0.685 -> 0.618 (runs.md P-60 against P-61, nothing else changed)."""
        out = []
        for m in neg.threads[sid].supplier_messages:
            sheets = m.get("term_sheets") or []
            if sheets:
                c = neg.cost(sid, sheets[0]["terms"])
                if math.isfinite(c):
                    out.append(c)
        return out


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
