"""One case being negotiated: the threads, the documents, every move and its telemetry.

`Negotiation` owns the session's state and talks to the arena; strategies only read it and decide.
Every move is recorded (events.jsonl, metrics) and the whole case is written to
`sessions/<session_id>.json` when it ends: case file, e-mails both ways, documents as text, each
decision with its rationale and the costs it saw, the result, the arena's trace and the back office.
"""

import math
import threading
import time
from dataclasses import dataclass, field

from arena_kit.cost import cost_breakdown, must_haves_ok, total_cost
from arena_kit.docs import quote_terms, read_document

from negotiator.client import ArenaClient, ArenaError
from negotiator.data import WorldData
from negotiator.guards import accept_problems, clean_message
from negotiator.telemetry import Recorder, log, safe_name, utc_now

ENDED_STATUSES = {"walked_away", "no_bid"}
MOVE_LIMIT_S = 60.0


class GuardRefused(Exception):
    """A move the hard rules (guards.py) refuse: it would break a must-have or lose to the alternative."""


@dataclass
class ThreadState:
    supplier_id: str
    messages: list[dict] = field(default_factory=list)  # both directions, in order; ours: from=buyer
    last_reply_at: float = field(default_factory=time.monotonic)
    timeouts: int = 0
    closed: str | None = None
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def supplier_messages(self) -> list[dict]:
        return [m for m in self.messages if m.get("from") != "buyer"]

    @property
    def latest(self) -> dict:
        msgs = self.supplier_messages
        return msgs[-1] if msgs else {}

    @property
    def status(self) -> str:
        return "closed" if self.closed else self.latest.get("status", "open")

    @property
    def live(self) -> bool:
        return not self.closed and self.status not in ENDED_STATUSES

    @property
    def standing(self) -> tuple[str | None, dict]:
        sheets = self.latest.get("term_sheets") or []
        return (sheets[0]["term_sheet_id"], sheets[0]["terms"]) if sheets else (None, {})

    @property
    def rounds_used(self) -> int:
        return sum(1 for m in self.messages if m.get("from") == "buyer" and not m.get("action"))

    @property
    def standard_terms(self) -> dict:
        """The supplier's standard terms from its latest quote PDF: what closes for a missing field."""
        for msg in reversed(self.supplier_messages):
            for att in msg.get("attachments") or []:
                if att.get("name", "").startswith("quote") and att.get("text"):
                    return quote_terms(att["text"]).get("standard", {})
        return {}

    def price_path(self) -> list[float]:
        out = []
        for m in self.supplier_messages:
            sheets = m.get("term_sheets") or []
            if sheets and sheets[0]["terms"].get("unit_price") is not None:
                out.append(sheets[0]["terms"]["unit_price"])
        return out

    def our_price_path(self) -> list[float]:
        return [
            m["term_sheets"][0]["terms"]["unit_price"]
            for m in self.messages
            if m.get("from") == "buyer"
            and m.get("term_sheets")
            and m["term_sheets"][0]["terms"].get("unit_price") is not None
        ]

    def seconds_since_reply(self) -> float:
        return time.monotonic() - self.last_reply_at


class Negotiation:
    def __init__(
        self,
        client: ArenaClient,
        recorder: Recorder,
        data: WorldData | None = None,
        *,
        deadline: float | None = None,
        strategy_name: str = "",
    ) -> None:
        self.client, self.recorder, self.data = client, recorder, data
        self.deadline = deadline  # wall clock (time.time()) by which the case must close, e.g. a wave cap
        self.strategy_name = strategy_name
        self.case: dict = {}
        self.case_id = ""
        self.session_id = ""
        self.threads: dict[str, ThreadState] = {}
        self.decisions: list[dict] = []
        self.result: dict | None = None
        self.ended = threading.Event()
        self.started = time.time()
        self.supplier_estimates: dict[str, dict] = {}  # for the relationship term (stabilise, secure_supply)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ open / resume
    def open(self, case_id: str, case: dict | None = None) -> "Negotiation":
        self.case_id = case_id
        try:
            reply = self.client.open_session(case_id)
        except ArenaError as e:
            running = _running_session(e)
            if not running:
                raise
            return self.resume(running, case)
        self.session_id, self.case = reply["session_id"], reply["case"]
        if self.data:
            self.data.with_case(self.case)
        for sid, messages in reply["threads"].items():
            state = ThreadState(sid)
            for message in messages:
                state.messages.append(self._with_documents(message, sid))
            self.threads[sid] = state
        self._log_open(resumed=False)
        return self

    def resume(self, session_id: str, case: dict | None = None) -> "Negotiation":
        """Pick up a session this team already started (after a crash, or a final 409)."""
        self.session_id = session_id
        state = self.client.session(session_id)
        self.case_id = state.get("case_id", self.case_id)
        self.case = case or self.case
        for sid in state.get("threads", {}):
            thread = self.client.thread(session_id, sid)
            ts = ThreadState(sid, closed=thread.get("closed"))
            ts.messages = [
                self._with_documents(m, sid) if m.get("from") != "buyer" else m for m in thread.get("messages", [])
            ]
            self.threads[sid] = ts
        if state.get("status") == "ended":
            self.result = state.get("result") or {"deal": False, "end_reason": state.get("end_reason")}
            self.ended.set()
        self._log_open(resumed=True)
        return self

    def _log_open(self, resumed: bool) -> None:
        opening = {}
        for sid, t in self.threads.items():
            sheet_id, terms = t.standing
            opening[sid] = {
                "offer_id": sheet_id,
                "terms": terms,
                "c": self.cost(sid, terms),
                "standard_terms": t.standard_terms,
            }
        self.recorder.event(
            "session_opened",
            session_id=self.session_id,
            case_id=self.case_id,
            type=self.case.get("type"),
            goal=self.case.get("buyer", {}).get("category_goal"),
            suppliers=list(self.threads),
            resumed=resumed,
            opening=opening,
            c_alt=self.c_alt,
            strategy=self.strategy_name,
        )
        log.info(
            "%s %s: %s, %d supplier(s), C_alt=%s",
            "resumed" if resumed else "opened",
            self.case_id,
            self.case.get("title"),
            len(self.threads),
            _eur(self.c_alt),
        )

    # ------------------------------------------------------------------ documents
    def _with_documents(self, message: dict, supplier_id: str) -> dict:
        """Download every attachment of a supplier message, save the file, add its text."""
        for att in message.get("attachments") or []:
            if not att.get("attachment_id") or "text" in att:
                continue
            try:
                blob = self.client.attachment(self.session_id, att["attachment_id"])
            except ArenaError as e:
                log.warning("attachment %s: %s", att["attachment_id"], e)
                continue
            path = self.recorder.session_dir(self.session_id) / safe_name(f"{supplier_id}-{att['name']}")
            path.write_bytes(blob)
            try:
                att["text"] = read_document(att["name"], blob)
            except Exception as e:  # a document we cannot parse must not stop the case
                att["text"] = ""
                log.warning("cannot read %s: %s", att["name"], e)
            att["file"] = str(path.relative_to(self.recorder.dir))
            self.recorder.metrics.incr(f"documents.{att.get('type', 'unknown')}")
            self.recorder.event(
                "attachment",
                session_id=self.session_id,
                supplier_id=supplier_id,
                name=att["name"],
                type=att.get("type"),
                bytes=len(blob),
                file=att["file"],
            )
        return message

    # ------------------------------------------------------------------ costs
    @property
    def buyer(self) -> dict:
        return self.case.get("buyer", {})

    @property
    def c_alt(self) -> float:
        alt = self.buyer.get("alternative") or {}
        terms = alt.get("terms") or {}
        return total_cost(self.case, terms) if terms.get("unit_price") is not None else math.inf

    @property
    def c_open(self) -> float:
        """Our estimate of C_open: the cheapest opening quote that keeps the must-haves."""
        best = math.inf
        for sid, t in self.threads.items():
            first = next((m for m in t.supplier_messages if m.get("term_sheets")), None)
            if first and self.keeps_must_haves(sid, first["term_sheets"][0]["terms"]):
                best = min(best, self.cost(sid, first["term_sheets"][0]["terms"]))
        return best

    def cost(self, supplier_id: str, terms: dict) -> float:
        if not terms or terms.get("unit_price") is None:
            return math.inf
        t = self.threads.get(supplier_id)
        return total_cost(self.case, terms, t.standard_terms if t else None, self.supplier_estimates.get(supplier_id))

    def breakdown(self, supplier_id: str, terms: dict) -> dict:
        t = self.threads.get(supplier_id)
        return {
            k: round(v, 2)
            for k, v in cost_breakdown(
                self.case, terms, t.standard_terms if t else None, self.supplier_estimates.get(supplier_id)
            ).items()
        }

    def keeps_must_haves(self, supplier_id: str, terms: dict) -> bool:
        t = self.threads.get(supplier_id)
        return must_haves_ok(self.case, terms, t.standard_terms if t else None)

    def seconds_to_deadline(self) -> float:
        return math.inf if self.deadline is None else self.deadline - time.time()

    # ------------------------------------------------------------------ moves
    def send(self, supplier_id: str, message: dict, rationale: dict | None = None) -> dict | None:
        """Send one e-mail; returns the supplier's reply (None if the case ended meanwhile)."""
        t = self.threads[supplier_id]
        message, removed = clean_message(self, supplier_id, message)
        if removed:
            self.recorder.metrics.incr("guards.removed", len(removed))
            self.recorder.event("guard_cleaned", session_id=self.session_id, supplier_id=supplier_id, removed=removed)
            log.warning("%s: guard removed %s", supplier_id, removed)
        waited = t.seconds_since_reply()
        if waited > MOVE_LIMIT_S * 0.8:
            log.warning("%s: answering %.0fs after its reply (limit %.0fs)", supplier_id, waited, MOVE_LIMIT_S)
        self.recorder.metrics.observe("decision.seconds_after_reply", waited)
        sheets = [
            {"terms": s["terms"], "c": self.cost(supplier_id, s["terms"])} for s in message.get("term_sheets", [])
        ]
        round_no = t.rounds_used + 1
        self._decision("message", supplier_id, rationale, round=round_no, sheets=sheets)
        self.recorder.event(
            "message_sent",
            session_id=self.session_id,
            case_id=self.case_id,
            supplier_id=supplier_id,
            round=round_no,
            subject=message.get("subject"),
            body=message.get("body"),
            term_sheets=sheets,
            refs=message.get("refs", []),
            seconds_after_reply=round(waited, 2),
        )
        start = time.perf_counter()
        try:
            reply = self.client.send_message(self.session_id, supplier_id, message)
        except ArenaError as e:
            if e.status == 422:
                self.recorder.metrics.incr("moves.invalid")
                self.recorder.event(
                    "invalid_move", session_id=self.session_id, supplier_id=supplier_id, detail=e.detail
                )
                log.error("%s: invalid message: %s", supplier_id, e.detail)
                raise
            if e.status != 409:
                raise
            self.recorder.metrics.incr("moves.conflict")
            self._refresh_after_conflict(supplier_id, e)
            return None if self.ended.is_set() else t.latest
        took = time.perf_counter() - start
        self.recorder.metrics.observe("supplier.reply_seconds", took)
        with t.lock:
            t.messages.append({**message, "from": "buyer", "sent_at": utc_now()})
            t.messages.append(self._with_documents(reply, supplier_id))
            t.last_reply_at = time.monotonic()
        self._log_reply(supplier_id, reply, took, round_no)
        if reply.get("status") in ENDED_STATUSES:
            t.closed = reply["status"]
        return reply

    def _log_reply(self, supplier_id: str, reply: dict, took: float, round_no: int) -> None:
        m = self.recorder.metrics
        status = reply.get("status")
        m.incr(f"supplier.status.{status}")
        claims = reply.get("claim_results") or []
        for c in claims:
            m.incr(f"claims.{c.get('result')}")
        sheet_id, terms = self.threads[supplier_id].standing
        c = self.cost(supplier_id, terms)
        self.recorder.event(
            "reply",
            session_id=self.session_id,
            case_id=self.case_id,
            supplier_id=supplier_id,
            round=round_no,
            status=status,
            sender=reply.get("from"),
            offer_id=sheet_id,
            terms=terms,
            c=c,
            claim_results=claims,
            missing_fields=reply.get("missing_fields"),
            signals=reply.get("signals"),
            seconds=round(took, 2),
            body=reply.get("body"),
            attachments=[a.get("name") for a in reply.get("attachments") or []],
        )
        log.info(
            "%s r%d: %s %s C=%s claims=%s (%.0fs)",
            supplier_id,
            round_no,
            status,
            terms.get("unit_price"),
            _eur(c),
            [x.get("result") for x in claims] or "-",
            took,
        )

    def _refresh_after_conflict(self, supplier_id: str, error: ArenaError) -> None:
        """After a 409: late (timeout), round limit, or the thread/case ended - read the arena's state."""
        self.recorder.event("conflict", session_id=self.session_id, supplier_id=supplier_id, detail=error.detail)
        log.warning("%s: %s", supplier_id, error.detail)
        state = self.client.session(self.session_id)
        if state.get("status") == "ended":
            self.result = state.get("result") or {"deal": False, "end_reason": state.get("end_reason")}
            self.ended.set()
            return
        thread = self.client.thread(self.session_id, supplier_id)
        t = self.threads[supplier_id]
        known = {m.get("message_id"): m for m in t.messages if m.get("message_id")}
        messages = []
        for m in thread.get("messages", []):
            if m.get("from") == "buyer":
                messages.append(m)
            elif m.get("message_id") in known:  # keep the documents we already downloaded and read
                messages.append(known[m["message_id"]])
            else:
                messages.append(self._with_documents(m, supplier_id))
        timeouts = thread.get("timeouts") or []
        # The supplier's answer to a late move sits in `timeouts`; its offer is the thread's standing offer
        # even when the last message carries no term sheet - without this the best offer would vanish.
        if timeouts and thread.get("offer_id") and messages and not messages[-1].get("term_sheets"):
            last = timeouts[-1]
            messages[-1] = {
                **messages[-1],
                "status": last.get("status", messages[-1].get("status")),
                "term_sheets": [{"term_sheet_id": thread["offer_id"], "terms": last.get("terms", {})}],
                "missing_fields": last.get("missing_fields", []),
            }
        with t.lock:
            t.messages = messages
            t.timeouts = len(timeouts)
            t.closed = thread.get("closed")
            t.last_reply_at = time.monotonic()
        if t.timeouts:
            self.recorder.metrics.incr("moves.timeouts")
        self.recorder.event(
            "thread_refreshed",
            session_id=self.session_id,
            supplier_id=supplier_id,
            offer_id=t.standing[0],
            status=t.status,
            timeouts=t.timeouts,
            closed=t.closed,
        )

    def accept(self, supplier_id: str, term_sheet_id: str, rationale: dict | None = None) -> dict:
        if problems := accept_problems(self, supplier_id, term_sheet_id):
            self.recorder.metrics.incr("guards.accept_refused")
            self.recorder.event("guard_refused", session_id=self.session_id, supplier_id=supplier_id, problems=problems)
            raise GuardRefused(f"{supplier_id} {term_sheet_id}: {'; '.join(problems)}")
        terms = self.threads[supplier_id].standing[1]
        self._decision(
            "accept",
            supplier_id,
            rationale,
            term_sheet_id=term_sheet_id,
            terms=terms,
            c=self.cost(supplier_id, terms),
        )
        return self._close(supplier_id, {"action": {"type": "accept", "term_sheet_id": term_sheet_id}})

    def walk_away(self, supplier_id: str | None = None, rationale: dict | None = None) -> dict:
        supplier_id = supplier_id or next(iter(self.threads))
        self._decision("walk_away", supplier_id, rationale)
        return self._close(supplier_id, {"action": {"type": "walk_away"}})

    def _close(self, supplier_id: str, message: dict) -> dict:
        with self._lock:
            if self.ended.is_set():
                return self.result or {}
            try:
                reply = self.client.send_message(self.session_id, supplier_id, message)
                self.result = reply.get("result", reply)
            except ArenaError as e:
                if e.status != 409:
                    raise
                self.recorder.metrics.incr("moves.close_conflict")
                self.recorder.event(
                    "close_conflict",
                    session_id=self.session_id,
                    supplier_id=supplier_id,
                    action=message.get("action"),
                    detail=e.detail,
                )
                log.error("%s: closing move refused: %s", supplier_id, e.detail)
                state = self.client.session(self.session_id)
                self.result = state.get("result") or {"deal": False, "end_reason": state.get("end_reason")}
            self.ended.set()
            return self.result

    def _decision(self, kind: str, supplier_id: str, rationale: dict | None, **extra) -> None:
        entry = {
            "ts": utc_now(),
            "t": round(time.time() - self.started, 2),
            "action": kind,
            "supplier_id": supplier_id,
            "rationale": rationale or {},
            **extra,
        }
        self.decisions.append(entry)
        self.recorder.event("decision", session_id=self.session_id, case_id=self.case_id, **entry)

    # ------------------------------------------------------------------ the end
    def finalize(self) -> dict:
        """Read the arena's final state (result, trace, replay), the back office, write the transcript."""
        duration = time.time() - self.started
        state, backoffice = {}, None
        try:
            state = self.client.session(self.session_id)
        except ArenaError as e:
            log.warning("final state: %s", e)
        try:
            backoffice = self.client.backoffice(self.session_id)
        except ArenaError as e:
            backoffice = {"unavailable": str(e.detail)}
        result = state.get("result") or self.result or {}
        outcome = self.outcome(result, state, duration)
        m = self.recorder.metrics
        m.observe("case.seconds", duration)
        m.incr("cases.deal" if result.get("deal") else "cases.no_deal")
        self.recorder.event("result", **outcome)
        self.recorder.save_json(
            f"sessions/{safe_name(self.session_id)}.json",
            {
                "outcome": outcome,
                "case": self.case,
                "threads": {
                    sid: {
                        "messages": t.messages,
                        "closed": t.closed,
                        "timeouts": t.timeouts,
                        "standard_terms": t.standard_terms,
                    }
                    for sid, t in self.threads.items()
                },
                "decisions": self.decisions,
                "result": result,
                "trace": state.get("trace") or result.get("trace"),
                "backoffice": backoffice,
                "state": {k: v for k, v in state.items() if k not in ("result", "trace", "threads")},
            },
        )
        log.info(
            "%s ended (%s): deal=%s score=%s C_deal=%s C_open=%s C_best=%s  %s",
            self.case_id,
            outcome["end_reason"],
            outcome["deal"],
            outcome["score"],
            _eur(outcome["c_deal"]),
            _eur(outcome["c_open"]),
            _eur(outcome["c_best"]),
            outcome["replay_url"] or "",
        )
        return outcome

    def _replay_url(self, state: dict) -> str | None:
        url = state.get("replay_url") or (self.client.replay_url(self.session_id) if self.session_id else None)
        return _absolute(self.client.settings.arena_url, url)

    def _model_decisions(self) -> list[dict]:
        """Moves a decision model chose (strategy `decided`): level, probabilities, confidence, extra signals."""
        out = []
        for d in self.decisions:
            meta = (d.get("rationale") or {}).get("decided") if isinstance(d.get("rationale"), dict) else None
            if d.get("action") == "message" and meta:
                out.append({"supplier_id": d["supplier_id"], "round": d.get("round"), **meta})
        return out

    def outcome(self, result: dict, state: dict, duration: float) -> dict:
        threads = {}
        for sid, t in self.threads.items():
            threads[sid] = {
                "rounds": t.rounds_used,
                "status": t.status,
                "timeouts": t.timeouts,
                "their_prices": t.price_path(),
                "our_prices": t.our_price_path(),
            }
        claims: dict[str, int] = {}
        for t in self.threads.values():
            for msg in t.supplier_messages:
                for c in msg.get("claim_results") or []:
                    claims[c.get("result")] = claims.get(c.get("result"), 0) + 1
        return {
            "run_id": self.recorder.run_id,
            "session_id": self.session_id,
            "case_id": self.case_id,
            "set": self.case.get("set"),
            "title": self.case.get("title"),
            "type": self.case.get("type"),
            "goal": self.buyer.get("category_goal"),
            "strategy": self.strategy_name,
            "suppliers": list(self.threads),
            "deal": bool(result.get("deal")),
            "supplier_id": result.get("supplier_id"),
            "terms": result.get("terms"),
            "must_haves_ok": result.get("must_haves_ok"),
            "end_reason": result.get("end_reason") or state.get("end_reason"),
            "score": result.get("score"),
            "c_open": result.get("c_open"),
            "c_deal": result.get("c_deal"),
            "c_alt": result.get("c_alt"),
            "c_best": result.get("c_best"),
            "saved_eur": (result["c_open"] - (result.get("c_deal") or result.get("c_alt") or 0))
            if result.get("c_open") is not None and (result.get("c_deal") or result.get("c_alt"))
            else None,
            "cost_breakdown": result.get("cost_breakdown"),
            "rounds": sum(t.rounds_used for t in self.threads.values()),
            "model_decisions": [
                {"supplier_id": d["supplier_id"], "round": d.get("round"), **d["rationale"]["decided"]}
                for d in self.decisions
                if d.get("action") == "message"
                and isinstance(d.get("rationale"), dict)
                and d["rationale"].get("decided")
            ],
            "threads": threads,
            "claims": claims,
            "seconds": round(duration, 1),
            "replay_url": self._replay_url(state),
        }


def _absolute(base: str, url: str | None) -> str | None:
    if not url:
        return None
    return url if url.startswith("http") else base.rstrip("/") + "/" + url.lstrip("/")


def _running_session(error: ArenaError) -> str | None:
    """A final case played twice answers 409 naming the running session."""
    if error.status != 409:
        return None
    import re

    match = re.search(r"one session per case in the final: (\S+)", str(error.detail))
    return match.group(1).rstrip(".,;") if match else None


def _eur(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, float) and math.isinf(value):
        return "inf"
    return f"{value:,.2f}"
