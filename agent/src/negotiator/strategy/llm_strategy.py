"""LLM buyer: the model reads the supplier and steers; code keeps every number and every guarantee.

Built on the baseline (target price, checkable arguments, term-sheet construction, cost-based closing).
The model adds what the baseline cannot do:

  before_open  reads the supplier's dossier - letters, call and meeting notes, news, negotiation history,
               credit index, scorecards - and writes a profile: what moves this supplier (cash, volume,
               capacity, relationship, list price, ...), how firm it is, which of the case's levers to use.
               This runs before the session opens, so no supplier clock is ticking yet.
  decide       each round reads the supplier's reply and chooses the stance (push, trade, hold, accept),
               how much of the scheduled concession to give, which lever to trade, which arguments to use
               (by number, from the list code prepared) and writes the e-mail text.

Code then builds the term sheets from the published cost function C, appends the arguments with their
figures and IDs exactly as the data has them, strips any ID the model wrote itself (an unknown ID costs
trust), never offers a sheet dearer than the standing one, and falls back to the baseline move whenever
the model is slow, down or returns something unusable.
"""

import json
import math
import re

from arena_kit.cost import complete_offer

from negotiator.data import Evidence, WorldData
from negotiator.llm import LLM, LLMError
from negotiator.session import Negotiation
from negotiator.strategy.base import Decision
from negotiator.strategy.baseline import CLOSE_ENOUGH, MAX_CLAIMS, SIGNATURE, BaselineStrategy, describe
from negotiator.telemetry import log

ID_RE = re.compile(r"\b(?:idx|quote|offer|sc|qn|po|cost|fc|news|doc|ctr|rfq|sup|part|gr|inv):[\w.:@#/-]*\w")
STANCES = {"push", "trade", "hold", "accept"}
DECIDE_TIMEOUT_S = 30.0  # the e-mail must reach the arena within 60 s of the supplier's reply
LEVER_DISCOUNT_MAX = 0.02  # a traded lever may lower our asked price by at most 2 %
# Sentences with money or percentages: the model must not state figures (term sheets and checked
# arguments carry them); a stray number contradicts the sheets or reads as an unbacked claim.
FIGURE_RE = re.compile(r"(€|\bEUR\b|\beuros?\b|\d[\d.,]*\s?%|\b\d+[.,]\d{2}\b|\bpercent\b)", re.I)

PROFILE_SYSTEM = """You are a senior procurement analyst at Hollerau Pumpenwerke, a German pump maker.
Read everything we know about one supplier and work out what will move it in a negotiation: what it is
dealing with right now, what it values, what it cannot do, and how it reacted in the past.

Return JSON:
{"summary": "<3 sentences: the supplier's situation and what it wants>",
 "drivers": ["<from: cash, volume, capacity, contract_security, list_price, relationship, quality, energy_costs,
              material_costs, wages, lead_time, other>"],
 "cash_pressure": <0..1, how much it needs money soon>,
 "firmness": <0..1, how little it usually concedes>,
 "relationship": "good" | "neutral" | "strained",
 "levers": ["<negotiable fields that should matter to it, from the list given>"],
 "arguments_that_work": "<which kinds of argument it accepts, or 'unknown'>",
 "avoid": "<what would backfire with this supplier>",
 "tone": "<how to write to it>"}"""

DECIDE_SYSTEM = """You are the buyer of Hollerau Pumpenwerke negotiating by e-mail with an industrial supplier.
Goal: the lowest total cost C for our need, without breaking a must-have. Code computes every price and
every term sheet; you choose the strategy for this round and write the e-mail text.

Decide:
- stance: "push" (ask for more with a concession of ours), "trade" (offer something the supplier values -
  a lever - for a better price), "hold" (stop here, keep the standing offer for the close), or "accept"
  (its standing offer is good enough; code still checks it beats our alternative).
- concession: 0..1 - how much of the scheduled price step to give this round (0 = stand firm, 1 = full step).
  Concede little when the supplier moves on its own, more when it is stuck but reasonable.
- lever: one negotiable field to trade, or "none".
- evidence: up to 3 argument numbers from the list (they are inserted verbatim with their figures and IDs);
  pick only those relevant to what the supplier just said; [] if none.
- ask_cost_breakdown: true to ask for its cost breakdown (useful once, early).
- question: one short question to the supplier, or "".
- message: the e-mail body WITHOUT greeting, signature, prices, percentages, data IDs or term sheets (code
  adds all of these). 40-120 words, polite, firm, specific to what the supplier wrote. Never reveal urgency,
  a budget, a missing alternative or our target. Do not claim market benchmarks, competitor prices or any
  fact that is not in the arguments list - the supplier asks for proof and trusts us less. Refer to "the
  options below" instead of naming prices or terms.

Return JSON: {"stance": "...", "concession": 0.0, "lever": "...", "evidence": [], "ask_cost_breakdown": false,
"question": "...", "message": "...", "reason": "<one sentence: why>"}"""


class LLMStrategy(BaselineStrategy):
    name = "llm"

    def __init__(self, data: WorldData | None = None, llm: LLM | None = None) -> None:
        super().__init__(data)
        self.llm = llm or LLM()
        self.profiles: dict[str, dict] = {}

    # ------------------------------------------------------------------ before the clock
    def before_open(self, case: dict) -> None:
        for sid in case.get("suppliers", []):
            self.profiles[sid] = self._profile(case, sid)

    def prepare(self, neg: Negotiation) -> None:
        super().prepare(neg)
        for sid in neg.threads:
            if sid not in self.profiles:  # no case file before opening: profile now, briefly
                self.profiles[sid] = self._profile(neg.case, sid, timeout=20)
            neg.recorder.event(
                "profile", session_id=neg.session_id, case_id=neg.case_id, supplier_id=sid, profile=self.profiles[sid]
            )

    def _profile(self, case: dict, sid: str, timeout: float = 60) -> dict:
        try:
            profile = self.llm.json(
                PROFILE_SYSTEM,
                self._dossier(case, sid),
                purpose="profile",
                max_tokens=600,
                timeout=timeout,
                context={"case_id": case.get("case_id"), "supplier_id": sid},
            )
        except LLMError:
            return {}
        log.info("%s profile: %s", sid, (profile.get("summary") or "")[:200])
        return profile

    def _dossier(self, case: dict, sid: str) -> str:
        d = self.data
        out = [
            f"CASE: {case.get('title')} (type {case.get('type')}, goal {case['buyer'].get('category_goal')})",
            f"Briefing: {case.get('briefing', '')[:800]}",
            f"Negotiable fields: {', '.join(case.get('negotiable', []))}",
        ]
        if not d:
            return "\n".join(out)
        dossier = d.dossier(sid, case.get("parts", []))
        out.append(f"SUPPLIER: {json.dumps(dossier['supplier'], ensure_ascii=False, default=str)}")
        out.append(f"SCORECARDS: {json.dumps(dossier['scorecards'][:3], default=str)}")
        out.append(f"CONTRACTS: {json.dumps(dossier['contracts'], default=str)}")
        out.append(f"PRICE HISTORY: {json.dumps(dossier['price_history'][-6:], default=str)}")
        out.append(f"PAST NEGOTIATIONS: {json.dumps(dossier['negotiations'][:8], default=str)}")
        out.append(f"NEWS: {json.dumps(dossier['news'][-6:], ensure_ascii=False, default=str)}")
        docs = dossier["documents"][-10:]
        if case.get("trigger_doc") and case["trigger_doc"] not in {x["id"] for x in docs}:
            docs.append({"id": case["trigger_doc"]})
        for doc in docs:
            text = d.document_text(doc["id"]) or ""
            out.append(f"--- {doc['id']}\n{text[:900]}")
        for ref, fact in (case.get("facts") or {}).items():  # hidden cases: facts that exist only in the case
            out.append(f"CASE FACT {ref}: {json.dumps(fact, ensure_ascii=False, default=str)[:500]}")
        return "\n".join(out)[:14000]

    # ------------------------------------------------------------------ each round
    def decide(self, neg: Negotiation, supplier_id: str) -> Decision:
        t, plan = neg.threads[supplier_id], self.plans[supplier_id]
        if not t.live:
            return Decision.drop(supplier_id, f"thread {t.status}")
        _, theirs = t.standing
        if t.status in ("agreed", "final_offer"):  # pushing past a final offer risks the supplier walking
            return Decision.hold(supplier_id, t.status)
        if theirs.get("unit_price") is None or plan.target_price is None:
            return Decision.hold(supplier_id, "no price to negotiate on")
        rounds_left = neg.case.get("round_limit", 10) - t.rounds_used
        if rounds_left <= 1 or neg.seconds_to_deadline() < 120:
            return Decision.hold(supplier_id, "out of rounds or time")
        try:
            choice = self._ask(neg, supplier_id, theirs)
        except LLMError:
            neg.recorder.metrics.incr("llm.fallback")
            return super().decide(neg, supplier_id)
        return self._apply_choice(neg, supplier_id, theirs, choice)

    def _ask(self, neg: Negotiation, sid: str, theirs: dict) -> dict:
        t, plan = neg.threads[sid], self.plans[sid]
        scheduled = self._next_price(plan, theirs["unit_price"], t.our_price_path(), t.rounds_used)
        pool = self._pool(neg, sid)
        lines = [
            f"CASE: {neg.case.get('title')} | type {neg.case.get('type')} | goal {neg.buyer.get('category_goal')} | "
            f"round {t.rounds_used + 1} of {neg.case.get('round_limit', 10)}",
            f"SUPPLIER PROFILE: {json.dumps(self.profiles.get(sid) or {}, ensure_ascii=False)}",
            f"STANDING OFFER: {json.dumps(theirs)} -> C = {_eur(neg.cost(sid, theirs))}; status {t.status}",
            f"OUR ALTERNATIVE without a deal: C = {_eur(neg.c_alt)}",
            f"OUR LAST PRICE: {(t.our_price_path() or ['none'])[-1]}; SCHEDULED NEXT PRICE: {scheduled}",
            f"LEVERS (negotiable fields and options): "
            f"{json.dumps({f: neg.case.get('term_options', {}).get(f, 'free') for f in neg.case['negotiable']})}",
            "ARGUMENTS AVAILABLE (by number):",
            *[f"  {i}. [{e.kind}] {e.sentence}" for i, e in enumerate(pool)],
            "THREAD SO FAR (latest last):",
        ]
        for m in t.messages[-6:]:
            who = "US" if m.get("from") == "buyer" else f"SUPPLIER ({m.get('from')}, status {m.get('status')})"
            extra = ""
            if m.get("claim_results"):
                extra += f" claim results {[c.get('result') for c in m['claim_results']]}"
            if m.get("term_sheets"):
                extra += f" terms {json.dumps([s.get('terms') for s in m['term_sheets']])}"
            lines.append(f"--- {who}{extra}\n{(m.get('body') or '')[:900]}")
            for att in m.get("attachments") or []:
                if att.get("text") and "cost" in att.get("name", "").lower():
                    lines.append(f"[attachment {att['name']}]\n{att['text'][:1200]}")
        choice = self.llm.json(
            DECIDE_SYSTEM,
            "\n".join(lines),
            purpose="decide",
            max_tokens=500,
            timeout=DECIDE_TIMEOUT_S,
            context={"case_id": neg.case_id, "supplier_id": sid, "round": t.rounds_used + 1},
        )
        choice["_pool"] = pool
        choice["_scheduled"] = scheduled
        return choice

    def _pool(self, neg: Negotiation, sid: str) -> list[Evidence]:
        pool = [e for e in self.plans[sid].evidence if not any(r in self.used_refs for r in e.refs)]
        rival = self._rival_evidence(neg, sid)
        if rival and not any((sid, r) in self.used_rival_refs for r in rival.refs):
            pool.insert(0, rival)
        return pool[:8]

    def _apply_choice(self, neg: Negotiation, sid: str, theirs: dict, choice: dict) -> Decision:
        t, plan = neg.threads[sid], self.plans[sid]
        stance = str(choice.get("stance", "push")).lower()
        stance = stance if stance in STANCES else "push"
        rationale = {"llm": {k: v for k, v in choice.items() if not k.startswith("_")}}
        if stance in ("hold", "accept"):
            if neg.cost(sid, theirs) < neg.c_alt or stance == "hold":
                return Decision.hold(sid, f"llm: {stance}", **rationale)

        ours = t.our_price_path()
        base = ours[-1] if ours else plan.target_price
        concession = _clamp(choice.get("concession"), 0.0, 1.0, default=1.0)
        price = round(min(base + (choice["_scheduled"] - base) * concession, theirs["unit_price"]), 2)
        if ours:
            price = max(price, ours[-1])
        if price >= theirs["unit_price"] * (1 - CLOSE_ENOUGH):
            return Decision.hold(sid, "close enough", **rationale)

        sheets = self._term_sheets(neg, sid, theirs, price)
        lever = str(choice.get("lever") or "none")
        if stance == "trade" and lever in neg.case["negotiable"] and lever != "unit_price":
            trade = self._lever_sheet(neg, sid, theirs, price, lever)
            if trade:
                sheets = [trade] + [s for s in sheets if s["terms"] != trade["terms"]]
        sheets = sheets[:3]
        if not sheets:
            return Decision.hold(sid, "no term sheet beats the standing offer", **rationale)

        pool = choice["_pool"]
        wanted = [pool[i] for i in choice.get("evidence") or [] if isinstance(i, int) and 0 <= i < len(pool)]
        first = t.rounds_used == 0
        claims = self._claim(sid, wanted, MAX_CLAIMS)
        if first and not claims:
            claims = self._pick_claims(neg, sid, plan, first=True)
        message = self._compose(neg, sid, plan, sheets, claims, choice, first)
        rationale.update(
            round=t.rounds_used + 1,
            stance=stance,
            price=price,
            scheduled=choice["_scheduled"],
            their_price=theirs["unit_price"],
            c_theirs=neg.cost(sid, theirs),
            c_sheets=[neg.cost(sid, s["terms"]) for s in sheets],
            claims=[c.kind for c in claims],
        )
        return Decision("message", sid, message=message, rationale=rationale)

    def _lever_sheet(self, neg: Negotiation, sid: str, theirs: dict, price: float, lever: str) -> dict | None:
        """Give the supplier its own value on `lever` and ask a price that keeps our C where the ideal sheet is."""
        ideal = complete_offer(neg.case, self._optimise(neg, sid, {**theirs, "unit_price": price}))
        if lever not in theirs or theirs[lever] == ideal.get(lever):
            return None
        traded = {**ideal, lever: theirs[lever]}
        # We concede the lever instead of price: same price, or slightly lower where the lever is cheap for
        # us - never the "equal C" price, which can fall far below any sane anchor (e.g. a shorter contract
        # leaves need uncovered at the fallback price).
        iso = self._iso_cost_price(neg, sid, traded, neg.cost(sid, ideal))
        traded["unit_price"] = round(max(iso, price * (1 - LEVER_DISCOUNT_MAX)), 2)
        traded = complete_offer(neg.case, traded)
        if not neg.keeps_must_haves(sid, traded) or neg.cost(sid, traded) >= neg.cost(sid, theirs):
            return None
        return {"terms": traded}

    def _compose(self, neg: Negotiation, sid: str, plan, sheets, claims, choice, first) -> dict:
        text = ID_RE.sub("", str(choice.get("message") or "")).strip()
        text = re.sub(r"\(\s*[,;\s]*\)", "", text)
        text = strip_figures(text)
        lines = [f"Dear {plan.name} team," if plan.name != sid else "Dear Sir or Madam,", ""]
        lines.append(text or ("thank you for your reply." if not first else "thank you for your quote."))
        lines += [c.sentence for c in claims]
        if choice.get("ask_cost_breakdown") and not plan.asked_cost_breakdown:
            lines.append("Could you send us a cost breakdown for this part?")
            plan.asked_cost_breakdown = True
        question = ID_RE.sub("", str(choice.get("question") or "")).strip()
        if question:
            lines.append(question)
        lines += ["", "We can award on any of these options:" if len(sheets) > 1 else "Our proposal:"]
        lines += [f"Option {chr(65 + i)}: {describe(neg.case, s['terms'])}" for i, s in enumerate(sheets)]
        lines += ["", SIGNATURE]
        refs = sorted({r for c in claims for r in c.refs})
        return {
            "subject": neg.case.get("title", "Your quote"),
            "body": "\n".join(lines)[:8000],
            "term_sheets": sheets,
            "refs": refs,
        }


def strip_figures(text: str) -> str:
    """Drop every sentence that states money or a percentage."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    kept = [x for x in sentences if not FIGURE_RE.search(x)]
    return " ".join(kept).strip()


def _clamp(value, lo: float, hi: float, default: float) -> float:
    try:
        return min(hi, max(lo, float(value)))
    except (TypeError, ValueError):
        return default


def _eur(value: float) -> str:
    return "none" if value is None or math.isinf(value) else f"{value:,.0f}"
