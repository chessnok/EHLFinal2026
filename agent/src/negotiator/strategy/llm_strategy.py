"""LLM buyer: the model reads the supplier and steers; code keeps every number and every guarantee.

Built on the tactical strategy, so every number and every safeguard is the tactical one: the calibrated
ground truth (lower and upper bound in C), the full menu of equal-C structures ranked by what the supplier
asked for, counter-steps that answer its last move (at least half of it, at least 0.4 % of C), its cheapest
sheet as the standing offer, a price it writes in its text taken at its word, an agreement accepted at once,
a last word inside the upper bound taken, the guarded close. The model adds what code cannot do:

  before_open  reads the supplier's dossier - letters, call and meeting notes, news, negotiation history,
               credit index, scorecards - and writes a profile: what moves this supplier (cash, volume,
               capacity, relationship, list price, ...), how firm it is, which of the case's levers to use.
               This runs before the session opens, so no supplier clock is ticking yet.
  decide       on an ordinary counter-offer it reads the supplier's reply and chooses the stance (push, trade,
               hold, accept), how big our step is around the one code planned, which lever to give, which
               arguments to use (by number, from the list code prepared) and writes the e-mail text.

Code then builds the term sheets, appends the arguments with their figures and IDs exactly as the data has
them, strips any ID, figure or position leak the model wrote, and falls back to the tactical move whenever
the model is slow, down or returns something unusable.
"""

import json
import math
import re

from negotiator.data import Evidence, WorldData
from negotiator.guards import accept_problems
from negotiator.llm import LLM, LLMError
from negotiator.menu import structure_key
from negotiator.session import Negotiation
from negotiator.strategy.base import Decision
from negotiator.strategy.baseline import MAX_CLAIMS, SIGNATURE, describe
from negotiator.strategy.tactical import DONE_EPS, MIN_STEP, TacticalStrategy, reply_signals
from negotiator.telemetry import log

ID_RE = re.compile(r"\b(?:idx|quote|offer|sc|qn|po|cost|fc|news|doc|ctr|rfq|sup|part|gr|inv):[\w.:@#/-]*\w")
STANCES = {"push", "trade", "hold", "accept"}
DECIDE_TIMEOUT_S = 30.0  # the e-mail must reach the arena within 60 s of the supplier's reply
# Sentences with money or percentages: the model must not state figures (term sheets and checked
# arguments carry them); a stray number contradicts the sheets or reads as an unbacked claim.
FIGURE_RE = re.compile(r"(€|\bEUR\b|\beuros?\b|\d[\d.,]*\s?%|\b\d+[.,]\d{2}\b|\bpercent\b)", re.I)

PROFILE_SYSTEM = """You are a senior procurement analyst at Hollerau Pumpenwerke, a German pump maker.
Read everything we know about one supplier and work out what will move it in a negotiation: what it is
dealing with right now, what it values, what it cannot do, and how it reacted in the past.

Look especially for these signals (they decide which trade works):
- cash: asks to be paid earlier, cash discounts, short-time work, the bank watching, a weak credit index;
- volume and security: wants a binding volume or a longer contract, calls us small or "not strategic";
- index: has bought material forward or insists on a price escalation clause (Preisgleitklausel);
- frozen price: "no room on price", list price for all customers - then trade terms, not price;
- approval ladder: price moves need a committee or head office - expect small steps, keep asking;
- open book: offered to show its calculation - only then is a cost breakdown worth asking for;
- capacity: fully booked (firm) or idle (needs the work).

Return JSON:
{"summary": "<3 sentences: the supplier's situation and what it wants>",
 "drivers": ["<from: cash, volume, capacity, contract_security, list_price, relationship, quality, energy_costs,
              material_costs, wages, lead_time, index_clause, other>"],
 "cash_pressure": <0..1, how much it needs money soon>,
 "firmness": <0..1, how little it usually concedes>,
 "relationship": "good" | "neutral" | "strained",
 "levers": ["<negotiable fields that should matter to it, from the list given>"],
 "open_book": <true if it offered to show its calculation>,
 "arguments_that_work": "<which kinds of argument it accepts, or 'unknown'>",
 "avoid": "<what would backfire with this supplier>",
 "tone": "<how to write to it>"}"""

DECIDE_SYSTEM = """You are the buyer of Hollerau Pumpenwerke negotiating by e-mail with an industrial supplier.
Goal: the lowest total cost C for our need over the whole horizon, without breaking a must-have. C is not the unit
price: a short contract leaves need uncovered at an expensive fallback price, early payment costs interest. Code
computes every price and every term sheet; you choose the strategy for this round and write the e-mail text.

Decide:
- stance: "push" (ask for more with a concession of ours), "trade" (give the supplier a lever it values for a
  better price), "hold" (stop here, keep the standing offer for the close), or "accept" (its standing offer is good
  enough; code still checks it beats our alternative).
- concession: 0..1 - how big our step is this round. Code plans a step that answers the supplier's last move (at
  least half of it, never a crumb); 0 gives three quarters of it, 0.5 a little more than it, 1 one and a half.
  Concede less when it moves a lot on its own, more when it is stuck but reasonable.
- lever: one negotiable field the supplier wants, or "none" - code puts the equal-cost options that give it on top.
- evidence: up to 3 argument numbers from the list (inserted verbatim with their figures and IDs); pick only those
  relevant to what the supplier just said; [] if none.
- ask_cost_breakdown: true only once, and only if the profile says open_book - most suppliers refuse.
- question: one short question to the supplier, or "".
- message: the e-mail body WITHOUT greeting, signature, prices, percentages, data IDs or term sheets (code adds
  all of these). 40-120 words, polite, firm, specific to what the supplier wrote.

What the supplier signals, and how to answer (the SIGNALS line lists what code found in its last e-mail):
- "Which volume can you commit to?" / "a binding higher volume would help": if volume_per_year or contract_months
  is a lever, trade it (lever = that field). Never invent a volume, a growth or a new project.
- "Faster payment is welcome" / cash pressure: trade payment_days if it is a lever. If it is not, do not keep
  squeezing price in tiny steps; give a real step or trade another lever.
- It insists on an index / escalation clause (Preisgleitklausel) for a long contract: trade index_clause - code
  offers it with the widest deadband, which costs us little. Refusing it got us walk-aways.
- "We need to clarify this internally": an approval step - ask again with a small real step; the next concession
  comes on the next message.
- It cites its own cost drivers rising ("your figures confirm our case"): do not use index arguments on those drivers.
- Code handles before you are asked: agreements, final offers and last words, a lower price it wrote in its text,
  and the volume question (answered with our shared forecast by ID). The options already name the request they meet.
- "Price list for all customers", "no room on price": trade terms (payment, contract length, volume), not price.

Never: reveal urgency, a budget, a target, a deadline or a missing alternative; state any fact that is not in the
arguments list (no market benchmarks, competitor prices, other bids, volume growth, forecasts or new projects); name
prices or terms (write "the options below"). The options are equal value to us: invite the supplier to pick.

Return JSON: {"stance": "...", "concession": 0.0, "lever": "...", "evidence": [], "ask_cost_breakdown": false,
"question": "...", "message": "...", "reason": "<one sentence: why>"}"""

# Words that must never reach the supplier: they leak our position or read as claims we cannot back.
FORBIDDEN_RE = re.compile(
    r"\b(budget|benchmark|market price|target price|our target|urgent|urgently|deadline|no alternative|"
    r"other bidders?|competitor)\b",
    re.I,
)
SIGNALS = {
    "asks_volume": re.compile(r"which volume|binding (higher )?volume|volume (can you )?commit|exact volume", re.I),
    "wants_faster_payment": re.compile(r"faster payment|pay(ment)? (earlier|faster|sooner)|cash", re.I),
    "wants_index_clause": re.compile(
        r"index clause|preisgleitklausel|escalation clause|cannot accept a fixed price", re.I
    ),
    "approval_step": re.compile(r"clarify (this )?internally|approval|management|committee", re.I),
    "no_move_no_move": re.compile(r"without (movement|a move)|remain(s)? unchanged|unchanged from your", re.I),
    "drivers_rose": re.compile(r"confirm our case|rose .* of our cost|driver rose", re.I),
    "offers_alternatives": re.compile(r"\balternatively\b|provided (that )?the", re.I),
    "price_frozen": re.compile(r"no room on price|price list applies|frozen", re.I),
}
MIN_CONCESSION_WHEN_MOVED = 0.3  # the supplier moved: no crumbs from us
STEP_SCALE = (0.75, 1.5)  # concession 0..1 scales code's planned step between these factors


class LLMStrategy(TacticalStrategy):
    name = "llm"

    def __init__(self, data: WorldData | None = None, llm: LLM | None = None) -> None:
        super().__init__(data)
        self.llm = llm or LLM()
        self.profiles: dict[str, dict] = {}
        self.longer_offers: dict[str, int] = {}  # times we offered the horizon while its sheet was shorter

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
        """The tactical moves that need no judgement come first (the supplier's best sheet, its written price, an
        agreement, a last word, re-anchoring, stalls); the model steers only an ordinary counter-offer."""
        t, plan = neg.threads[supplier_id], self.tplans[supplier_id]
        if not t.live:
            return Decision.drop(supplier_id, f"thread {t.status}")
        self._learn(neg, supplier_id, plan)
        _, theirs = neg.best_offer(supplier_id)  # its cheapest sheet for us, not its first
        if theirs.get("unit_price") is None or not math.isfinite(plan.target_c):
            return Decision.hold(supplier_id, "no price to negotiate on")
        if text := self._text_price_offer(neg, supplier_id, plan):
            return text
        if t.status == "agreed":
            if take := self._take_agreed(neg, supplier_id):
                return take
            return Decision.hold(supplier_id, "agreed")
        if neg.case.get("round_limit", 10) - t.rounds_used <= 1 or neg.seconds_to_deadline() < 120:
            return Decision.hold(supplier_id, "out of rounds or time")

        their_c = neg.cost(supplier_id, theirs)
        if their_c <= plan.lower_c or self._undercut_after_big_step(neg, supplier_id, plan, theirs):
            if reanchor := self._reanchor(neg, supplier_id, plan, theirs, their_c):
                return reanchor
        last_word = t.status == "final_offer" or (reply_signals(t.latest.get("body", ""))["firm"] and t.rounds_used > 0)
        if last_word and their_c <= plan.upper_c:
            # no probe inside the upper bound, whatever its words ("bridge the remaining gap"): P18 walked after a
            # two-cent push on such a final offer that it would have signed at once
            return Decision.hold(supplier_id, "last word inside our upper bound: take it", their_c=their_c)
        if match := self._price_match(neg, supplier_id, plan, theirs, their_c):
            return match
        if last_word:
            if plan.probed_final or not self._may_probe(neg, supplier_id, their_c):
                return Decision.hold(supplier_id, "final offer: take it at the close", their_c=their_c)
            plan.probed_final = True
            last = plan.our_c[-1] if plan.our_c else plan.target_c
            ask_c = their_c - 0.35 * max(0.0, their_c - last)
            return self._offer(neg, supplier_id, plan, theirs, ask_c, their_c, probe=True)
        if plan.stalls >= 2 and their_c <= plan.upper_c:
            return Decision.hold(supplier_id, "stalled inside our upper bound: take it", their_c=their_c)
        if plan.stalls >= 3:
            return Decision.hold(supplier_id, "the supplier stopped moving", their_c=their_c)

        ask_c = self._next_c(neg, supplier_id, plan, their_c)
        if ask_c >= their_c * (1 - DONE_EPS):
            return Decision.hold(supplier_id, "their offer meets our ask", ask_c=ask_c, their_c=their_c)
        try:
            choice = self._ask(neg, supplier_id, plan, theirs, their_c, ask_c)
        except LLMError:
            neg.recorder.metrics.incr("llm.fallback")
            return self._offer(neg, supplier_id, plan, theirs, ask_c, their_c)
        return self._apply_choice(neg, supplier_id, plan, theirs, their_c, ask_c, choice)

    def _may_probe(self, neg: Negotiation, sid: str, their_c: float) -> bool:
        """Push a final offer once, and only when its walking away costs us little: a rival offer we could take
        or an alternative about as cheap. Its words alone are no reason - every practice walk-away followed a
        push on a final offer."""
        t = neg.threads[sid]
        if neg.case.get("round_limit", 10) - t.rounds_used < 2 or neg.seconds_to_deadline() < 180:
            return False
        for other, ot in neg.threads.items():
            if other != sid and self.tplans[other].probed_final and ot.live:
                return False  # one rival is already being pushed: this one stays our safe fallback
        for other, ot in neg.threads.items():
            if other != sid and ot.live and ot.standing[0] and not accept_problems(neg, other, ot.standing[0]):
                return True
        return math.isfinite(neg.c_alt) and neg.c_alt <= their_c * 1.01

    def _sheets(self, neg, sid, plan, theirs, ask_c, their_c) -> list[dict]:
        """The tactical menu, and every option moves: a structure we offered before comes back at least a minimum
        step dearer, not only option A ("your proposed prices for the indexed options remain unchanged")."""
        before = dict(plan.offered)
        sheets = super()._sheets(neg, sid, plan, theirs, ask_c, their_c)
        for sheet in sheets:
            terms = sheet["terms"]
            key, prev = structure_key(terms), before.get(structure_key(terms))
            if prev is None or terms["unit_price"] > prev:
                continue
            bumped = round(prev * (1 + MIN_STEP), 2)
            if (
                bumped < theirs.get("unit_price", bumped + 1)
                and neg.cost(sid, {**terms, "unit_price": bumped}) < their_c
            ):
                terms["unit_price"] = bumped
                plan.offered[key] = max(plan.offered.get(key, 0.0), bumped)
        return sheets

    def _ask(self, neg: Negotiation, sid: str, plan, theirs: dict, their_c: float, ask_c: float) -> dict:
        t = neg.threads[sid]
        pool = self._pool(neg, sid, plan)
        lines = [
            f"CASE: {neg.case.get('title')} | type {neg.case.get('type')} | goal {neg.buyer.get('category_goal')} | "
            f"round {t.rounds_used + 1} of {neg.case.get('round_limit', 10)}",
            f"SUPPLIER PROFILE: {json.dumps(self.profiles.get(sid) or {}, ensure_ascii=False)}",
            f"TRAITS FROM OUR DATA: {', '.join(sorted(plan.profile.traits)) or 'none'}",
            f"ITS BEST SHEET FOR US: {json.dumps(theirs)} -> C = {_eur(their_c)}; status {t.status}",
            f"OUR ALTERNATIVE without a deal: C = {_eur(neg.c_alt)}",
            f"OUR LAST ASK: C = {_eur(plan.our_c[-1]) if plan.our_c else 'none'}; PLANNED ASK: C = {_eur(ask_c)} "
            f"(answers its last move)",
            f"WHAT IT ASKED FOR SO FAR (levers): {', '.join(sorted(plan.requests)) or 'nothing'}",
            f"SIGNALS in the supplier's last e-mail: {', '.join(signals(t.latest.get('body') or '')) or 'none'}; "
            f"supplier moved last round: {_moved(t)}; contract shorter than our horizon: "
            f"{short_contract(neg, theirs)}",
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
        return choice

    def _pool(self, neg: Negotiation, sid: str, plan) -> list[Evidence]:
        """Unused arguments, minus the kinds the arena found irrelevant or contradicted; the scorecard only in
        quality_first cases (elsewhere the supplier reads it as a complaint, not a reason)."""
        banned = plan.banned_kinds | self.banned_case_kinds
        if neg.buyer.get("category_goal") != "quality_first":
            banned = banned | {"scorecard"}
        pool = [e for e in plan.evidence if e.kind not in banned and not any(r in self.used_refs for r in e.refs)]
        rival = self._rival_evidence(neg, sid)
        if rival and "rival_offer" not in banned and not any((sid, r) in self.used_rival_refs for r in rival.refs):
            pool.insert(0, rival)
        return pool[:8]

    def _apply_choice(self, neg, sid: str, plan, theirs: dict, their_c: float, ask_c: float, choice: dict) -> Decision:
        t = neg.threads[sid]
        stance = str(choice.get("stance", "push")).lower()
        stance = stance if stance in STANCES else "push"
        rationale = {"llm": {k: v for k, v in choice.items() if not k.startswith("_")}}
        if stance in ("hold", "accept") and short_contract(neg, theirs) and self.longer_offers.get(sid, 0) < 1:
            stance = "push"  # never settle on a contract shorter than the horizon before offering the longer one
            rationale["override"] = "short contract: offer the longer structure first"
        if stance == "hold" or (stance == "accept" and their_c < neg.c_alt):
            return Decision.hold(sid, f"llm: {stance}", **rationale)  # the close accepts its best guarded sheet

        if plan.our_c:  # the model sizes the step around the one that answers the supplier's move, never a crumb
            last = plan.our_c[-1]
            concession = _clamp(choice.get("concession"), 0.0, 1.0, default=0.5)
            if _moved(t):
                concession = max(concession, MIN_CONCESSION_WHEN_MOVED)
            step = max((ask_c - last) * (STEP_SCALE[0] + (STEP_SCALE[1] - STEP_SCALE[0]) * concession), MIN_STEP * last)
            ask_c = min(last + step, their_c * (1 - DONE_EPS), plan.upper_c)
        lever = str(choice.get("lever") or "none")
        if stance == "trade" and lever in neg.case["negotiable"] and lever != "unit_price":
            plan.requests.add(lever)  # the menu ranks the structures that give it this lever first

        sheets = self._sheets(neg, sid, plan, theirs, ask_c, their_c)
        for _ in range(4):  # the same offer again reads as a refusal to move
            if not sheets or self._keys(sheets) != plan.last_keys:
                break
            ask_c = min(ask_c + MIN_STEP * ask_c, their_c * (1 - DONE_EPS))
            sheets = self._sheets(neg, sid, plan, theirs, ask_c, their_c)
        if not sheets:
            return Decision.hold(sid, "no valid term sheet below their offer", **rationale)
        if short_contract(neg, theirs) and any(short_contract(neg, s["terms"]) is False for s in sheets):
            self.longer_offers[sid] = self.longer_offers.get(sid, 0) + 1
        plan.last_keys = self._keys(sheets)
        plan.our_c.append(neg.cost(sid, sheets[0]["terms"]))

        pool = choice["_pool"]
        wanted = [pool[i] for i in choice.get("evidence") or [] if isinstance(i, int) and 0 <= i < len(pool)]
        first = t.rounds_used == 0
        claims = self._claim(sid, wanted, MAX_CLAIMS if first else 2)
        if first and not claims:
            claims = self._choose_claims(neg, sid, plan, first=True)
        plan.last_claims = claims
        message = self._compose(neg, sid, plan, sheets, claims, choice, first)
        rationale.update(
            round=t.rounds_used + 1,
            stance=stance,
            ask_c=round(ask_c, 2),
            their_c=round(their_c, 2),
            upper_c=round(plan.upper_c, 2) if math.isfinite(plan.upper_c) else None,
            stalls=plan.stalls,
            c_sheets=[neg.cost(sid, s["terms"]) for s in sheets],
            claims=[c.kind for c in claims],
        )
        return Decision("message", sid, message=message, rationale=rationale)

    def _compose(self, neg: Negotiation, sid: str, plan, sheets, claims, choice, first) -> dict:
        text = ID_RE.sub("", str(choice.get("message") or "")).strip()
        text = re.sub(r"\(\s*[,;\s]*\)", "", text)
        text = strip_figures(text)
        text = strip_forbidden(text)
        lines = [f"Dear {plan.name} team," if plan.name != sid else "Dear Sir or Madam,", ""]
        lines.append(text or ("thank you for your reply." if not first else "thank you for your quote."))
        lines += [c.sentence for c in claims]
        open_book = plan.profile.has("open_book") or bool((self.profiles.get(sid) or {}).get("open_book"))
        if choice.get("ask_cost_breakdown") and open_book and not plan.asked_breakdown and not plan.breakdown_read:
            lines.append("Could you send us a cost breakdown for this part?")
            plan.asked_breakdown = True
        question = strip_forbidden(ID_RE.sub("", str(choice.get("question") or "")).strip())
        if question:
            lines.append(question)
        theirs = neg.threads[sid].standing[1]
        for i, sheet in enumerate(sheets if plan.requests else []):  # say which option answers its requests
            if said := self._answered(neg, plan, sheet["terms"], theirs, f"Option {chr(65 + i)}").strip():
                lines.append(said)
                break
        volume = self._volume_proof(neg, plan, sheets)  # "which volume can you commit to?": the shared forecast
        if volume:
            lines.append(volume[0])
        lines += ["", "We can award on any of these options:" if len(sheets) > 1 else "Our proposal:"]
        lines += [f"Option {chr(65 + i)}: {describe(neg.case, s['terms'])}" for i, s in enumerate(sheets)]
        lines += ["", SIGNATURE]
        refs = sorted({r for c in claims for r in c.refs} | ({volume[1]} if volume else set()))
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


def strip_forbidden(text: str) -> str:
    """Drop every sentence that leaks our position or claims what we cannot back (budget, benchmarks, ...)."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return " ".join(x for x in sentences if not FORBIDDEN_RE.search(x)).strip()


def signals(body: str) -> list[str]:
    """What the supplier's e-mail asks for or warns about, as named signals for the model."""
    return [name for name, pattern in SIGNALS.items() if pattern.search(body or "")]


def short_contract(neg: Negotiation, terms: dict) -> bool | None:
    """True if these terms cover less than the horizon while a longer contract is negotiable; None if n/a."""
    if "contract_months" not in neg.case.get("negotiable", []):
        return None
    months = terms.get("contract_months")
    if months is None:
        return None
    horizon = neg.buyer.get("horizon_years", 1) * 12
    longer = [o for o in neg.case.get("term_options", {}).get("contract_months", []) if o and o > months]
    return bool(months < horizon and longer)


def _moved(t) -> bool:
    """Did the supplier lower its price in its last reply?"""
    path = t.price_path()
    return len(path) >= 2 and path[-1] < path[-2] - 1e-9


def _clamp(value, lo: float, hi: float, default: float) -> float:
    try:
        return min(hi, max(lo, float(value)))
    except (TypeError, ValueError):
        return default


def _eur(value: float) -> str:
    return "none" if value is None or math.isinf(value) else f"{value:,.0f}"
