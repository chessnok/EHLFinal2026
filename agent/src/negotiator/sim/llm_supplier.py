"""The opponent that reads the e-mail: a model plays the supplier, shown how that supplier answered in our replays.

The fitted supplier (`supplier.Thread`) sees term sheets and cited IDs only. This one gets the buyer's text as well
and decides what a person would - hold, move, call its offer final, agree, leave - and writes the reply. The money
stays in code: its floor, its price for a structure, the case's c_best as the limit, and the rule that a sheet worth
its price is a deal. So wording can move this supplier, but never below what the calibration allows.

It is not the arena's supplier: it is a model prompted with recorded exchanges, and it costs tokens and seconds per
reply. `negotiator sim check --opponent llm` measures how close it comes on sessions it was not shown. When the
model does not answer in time, the fitted supplier makes the move (`fallbacks` counts them).
"""

import json
import re
from dataclasses import dataclass, field

from negotiator.llm import LLMError
from negotiator.sim.pricing import price_for, value_of
from negotiator.sim.supplier import EPS, Thread

TIMEOUT_S = 90.0  # under the client's 180 s for one reply
EXAMPLES, RECORD = 6, 10  # recorded exchanges shown in full per reply, and counted in the figures
REPLY_WEIGHT = 0.05  # one reply further away weighs as much as this share of the e-mail's words differing
BUYER_CHARS, REPLY_CHARS, MAIL_CHARS = 700, 900, 4000
DECISIONS = ("counter", "final_offer", "agree", "walk_away")

SYSTEM = """You play the sales contact of one supplier in a simulated purchasing negotiation. A buyer's agent is \
rehearsing against you, so the aim is fidelity: answer as THIS supplier answered in the recorded exchanges you are \
shown - as willing or unwilling to move, as quick to call an offer final, in the same voice and with the same \
habits. Do not be kinder or tougher than the record.

Read the buyer's e-mail as a sales person would. What moves you in the record (a checked fact, a rival quote, a \
real step towards you) moves you here by about as much. Take in what the text gives away or gets wrong: a budget or \
ceiling it names, a deadline, no alternative, a threat, a claim with nothing behind it, the same argument again, an \
option that ignores what you asked for. If the buyer pushes past your final offer, do what the record shows this \
supplier does then.

Your price and your floor are private; never state the floor. Code sets the figures and answers on the buyer's \
option that is worth most to you: you decide how much of your remaining room to give up, and write the e-mail. \
"IN THE RECORD AT THIS POINT" lists what this supplier gave up and how often it called its offer final in the same \
situation. Start from those figures - the typical one, not the most cautious - and leave them only for a reason \
you can name in the buyer's e-mail.

Answer with one JSON object and nothing else:
{"decision": "counter" | "final_offer" | "agree" | "walk_away",
 "concede_share": number from 0 to 1 - the share of the room between your price now and your floor that you give \
up in this reply (0: you hold),
 "why": "one short sentence: what in the record or in the e-mail decided it",
 "body": "the e-mail, as this supplier writes it. Put {offer} where the terms of your offer belong and write no \
price or other figure of your own - code inserts them."}
"agree" takes the buyer's option as it stands; code refuses it when the option is below your floor. "walk_away" \
ends the talks and is only possible after you have called an offer final."""


def _cut(text: str, limit: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[:limit] + " [...]"


def _terms(terms: dict) -> str:
    return json.dumps(terms, ensure_ascii=False, separators=(", ", ": "))


def _room(ask: float | None) -> str:
    if ask is None:
        return ""
    return f"{ask:.0%} of the way from your price to your floor" + (" (below your floor)" if ask > 1 + EPS else "")


def offer_text(terms: dict) -> str:
    rest = [f"{k.replace('_', ' ')} {_terms(v) if isinstance(v, dict) else v}" for k, v in terms.items()
            if k != "unit_price"]  # fmt: skip
    return ", ".join([f"a price of €{terms['unit_price']:.2f} per unit", *rest])


def _words(text: str) -> frozenset:
    return frozenset(w for w in re.findall(r"[a-z]{4,}", (text or "").lower()))


def pick(examples: list[dict], status: str, reply: int, body: str = "", limit: int = EXAMPLES) -> list[dict]:
    """The recorded exchanges closest to this moment: the same status before, then a buyer e-mail in like words
    (so an e-mail that names a ceiling meets the replies to e-mails that named one) and a near reply number;
    one of each (buyer e-mail, outcome), so repeats of one strategy do not fill the prompt."""
    now = _words(body)

    def far(e: dict) -> tuple:
        then = _words(e["buyer"])
        alike = len(now & then) / len(now | then) if now and then else 0.0
        return e["before"] != status, REPLY_WEIGHT * abs(e["reply"] - reply) - alike

    seen, out = set(), []
    for e in sorted(examples, key=far):
        mark = (e["buyer"][:300], e["status"], e["gave"])
        if mark not in seen:
            seen.add(mark)
            out.append(e)
    return out[:limit]


def record(near: list[dict], status: str) -> str:
    """What the supplier did in its recorded replies closest to this moment, in figures: the anchor for the step."""
    near = [e for e in near if e["before"] == status]
    if not near:
        return "  (nothing recorded for this situation)"
    gave = sorted(e["gave"] for e in near if e["gave"] is not None)
    ends = {k: sum(e["status"] == k for e in near) for k in ("open", "final_offer", "agreed", "walked_away")}
    lines = [f"  the {len(near)} closest recorded replies with your status {status}: "
             + ", ".join(f"{n} {k}" for k, n in ends.items() if n)]  # fmt: skip
    if gave:
        lines.append(f"  share of the remaining room given up: {', '.join(f'{g:.0%}' for g in gave)} "
                     f"(median {gave[len(gave) // 2]:.0%})")  # fmt: skip
    return "\n".join(lines)


def show(e: dict) -> str:
    facts = ", ".join(f"{c['type']} {c['result']}" for c in e["claims"]) or "none"
    ask = f"; the buyer's best option: {_room(e['ask'])}" if e["ask"] is not None else ""
    did = e["status"] + ("" if e["gave"] is None else f", gave up {e['gave']:.0%} of the remaining room")
    return (f"- Reply {e['reply']}; your status before: {e['before']}{ask}; cited facts: {facts}\n"
            f"  BUYER: {_cut(e['buyer'], BUYER_CHARS)}\n"
            f"  YOU ({did}): {_cut(e['text'], REPLY_CHARS)}")  # fmt: skip


@dataclass
class LLMThread(Thread):
    """`supplier.Thread` whose decision and e-mail come from a model. `llm`: a `negotiator.llm.LLM`."""

    llm: object = None
    history: list = field(default_factory=list)  # this thread so far: (who, text)
    calls: int = 0
    fallbacks: int = 0

    def prompt(self, case: dict, sheets: list[dict], mail: dict) -> str:
        p = self.profile
        gap = max(self.value - p.floor, 0.0)
        options = []
        for i, s in enumerate(sheets, 1):
            ask = (self.value - value_of(case, p.rates, p.ref, self._feasible(case, s))) / gap if gap > EPS else None
            options.append(f"  {i}. {_terms(s)}" + (f" - {_room(ask)}" if ask is not None else ""))
        facts = ", ".join(f"{c['type']} {c['result']}" for c in mail.get("claims") or []) or "none"
        near = pick(p.examples, self.status, self.replies + 1, mail.get("body", ""), RECORD)
        past = [show(e) for e in near[:EXAMPLES]]
        thread = [f"  {who}: {_cut(text, BUYER_CHARS)}" for who, text in self.history]
        return "\n".join([
            f"CASE: {case.get('title', case['case_id'])} ({case.get('type', '')}). You are {p.supplier_id}.",
            f"YOUR POSITION (private): opening {_terms(p.opening)}; standing offer {_terms(self.terms)}; your price "
            f"now EUR {self.value:.2f} and your floor EUR {p.floor:.2f}, both on your opening structure; status "
            f"{self.status}; replies sent {self.replies} of at most {case.get('round_limit', 10)}.",
            "",
            "RECORDED EXCHANGES of this supplier, from other sessions:",
            *(past or ["  (none recorded)"]),
            "",
            "IN THE RECORD AT THIS POINT:",
            record(near, self.status),
            "",
            "THIS THREAD so far:",
            *(thread or ["  (your quote only)"]),
            "",
            "THE BUYER'S E-MAIL NOW:",
            _cut(mail.get("body", ""), MAIL_CHARS),
            "Its options, as you value them:",
            *(options or ["  (no term sheet)"]),
            f"Cited facts, as checked: {facts}",
        ])  # fmt: skip

    def reply(self, case: dict, sheets: list[dict], claims: list[str], weak: frozenset = frozenset(),
              mail: dict | None = None) -> dict:  # fmt: skip
        if self.llm is None or mail is None:
            return super().reply(case, sheets, claims, weak)
        self.calls += 1
        try:
            choice = self.llm.json(SYSTEM, self.prompt(case, sheets, mail), purpose="sim_supplier", max_tokens=900,
                                   timeout=TIMEOUT_S, context={"case_id": case["case_id"]})  # fmt: skip
            out = self._apply(case, sheets, choice)
        except (LLMError, TypeError, ValueError) as e:
            self.fallbacks += 1
            out = super().reply(case, sheets, claims, weak)
            out["fallback"] = str(e)[:200]
        self.history += [("BUYER", mail.get("body", "")), (f"YOU ({out['status']})", " ".join(out["reasons"]))]
        return out

    def _apply(self, case: dict, sheets: list[dict], choice: dict) -> dict:
        """The model's decision in the fitted supplier's money: the step, the structure, the limits."""
        p = self.profile
        decision = choice.get("decision")
        if decision not in DECISIONS:
            raise ValueError(f"no decision in the model's answer: {decision!r}")
        body = str(choice.get("body") or "").strip()
        values = [(value_of(case, p.rates, p.ref, self._feasible(case, s)), s) for s in sheets]
        top = max(values, key=lambda vs: vs[0]) if values else None
        if top and (self.best_buyer is None or top[0] >= self.best_buyer[0]):
            self.best_buyer = top
        if decision == "walk_away" and self.status == "final_offer":
            self.status = "walked_away"
            return {"status": "walked_away", "terms": dict(self.terms), "reasons": [body or "We end the talks here."]}

        gap = max(0.0, self.value - p.floor)
        share = min(1.0, max(0.0, float(choice.get("concede_share") or 0.0)))
        self.value = max(p.floor, self.value - share * gap)
        if decision == "agree" and top and top[0] >= p.floor - EPS:
            self.value = min(self.value, top[0])
        if self.best_buyer and self.best_buyer[0] >= self.value - EPS and self._allowed(case, self.best_buyer[1]):
            self.status, self.value = "agreed", self.best_buyer[0]
            self.terms = dict(self._feasible(case, self.best_buyer[1]))
            self.replies += 1
            return self._written(body, "We can agree to your terms: {offer}.")

        structure = self._feasible(case, top[1]) if top else self.terms
        final = decision == "final_offer" or self.status == "final_offer" or self.value - p.floor <= p.quantum
        self.status = "final_offer" if final else "open"
        price = price_for(case, p.rates, p.ref, self.value, structure)
        if self.cap:  # no package beats the best one the arena says this case has
            price = max(price, self.cap({k: v for k, v in structure.items() if k != "unit_price"}))
        self.terms = {**structure, "unit_price": max(p.quantum, round(round(price / p.quantum) * p.quantum, 2))}
        self.value = value_of(case, p.rates, p.ref, self.terms)  # what it wrote, after rounding
        self.replies += 1
        return self._written(body, "Our offer: {offer}." + (" This is our final offer." if final else ""))

    def _written(self, body: str, default: str) -> dict:
        offer = offer_text(self.terms)
        text = body.replace("{offer}", offer) if "{offer}" in body else f"{body}\n\n{default.format(offer=offer)}"
        if self.status == "final_offer" and "final" not in text.lower():
            text += " This is our final offer."
        return {"status": self.status, "terms": dict(self.terms), "reasons": [text.strip()]}
