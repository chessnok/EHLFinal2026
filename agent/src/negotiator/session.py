"""One case being negotiated: the threads, the documents, every move and its telemetry.

`Negotiation` owns the session's state and talks to the arena; strategies only read it and decide.
Every move is recorded (events.jsonl, metrics) and the whole case is written to
`sessions/<session_id>.json` when it ends: case file, e-mails both ways, documents as text, each
decision with its rationale and the costs it saw, the result, the arena's trace and the back office.
"""

import itertools
import math
import threading
import time
from collections import Counter
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field

from arena_kit.cost import cost_breakdown, must_haves_ok, total_cost
from arena_kit.docs import quote_terms, read_document

from negotiator.chats import write_session_chat
from negotiator.client import ArenaClient, ArenaError
from negotiator.data import WorldData
from negotiator.guards import accept_problems, clean_message
from negotiator.telemetry import Recorder, log, safe_name, utc_now

ENDED_STATUSES = {"walked_away", "no_bid"}
MOVE_LIMIT_S = 60.0
# Our copy of a thread's clock starts when the reply reaches us, a moment after the arena's: read the arena's
# state once a clock is this close to its end.
SYNC_MARGIN_S = 3.0


class Turn:
    """One arena call of a session at a time, the most urgent first.

    The arena serves the calls of one session one after another (a document download waited 13 s at the median,
    99 s at most, while an e-mail of the same session was being answered - 0.4 s otherwise). Three e-mails sent
    at once therefore queue there, in an order we do not choose, and the last one is read long after it was
    written: case:P05 offered EUR 28.79 to a supplier that had gone to EUR 28.00 while the e-mail waited. We
    queue here instead: the thread whose clock ends first goes first, and each move is checked against the
    thread's state at the moment it is really sent.
    """

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._busy = False
        self._waiting: dict[int, Callable[[], float]] = {}
        self._ids = itertools.count()

    @contextmanager
    def take(self, urgency: Callable[[], float]):
        """Wait for the turn; among those waiting the lowest `urgency()` goes first (asked again each time)."""
        me = next(self._ids)
        with self._cond:
            self._waiting[me] = urgency
            try:
                while self._busy or min(self._waiting, key=lambda k: (self._waiting[k](), k)) != me:
                    self._cond.wait(0.2)
            finally:
                del self._waiting[me]
            self._busy = True
        try:
            yield
        finally:
            with self._cond:
                self._busy = False
                self._cond.notify_all()


class GuardRefused(Exception):
    """A move the hard rules (guards.py) refuse: it would break a must-have or lose to the alternative."""


@dataclass
class ThreadState:
    supplier_id: str
    messages: list[dict] = field(default_factory=list)  # both directions, in order; ours: from=buyer
    last_reply_at: float = field(default_factory=time.monotonic)  # when the thread's 60 s clock last started
    timeouts: int = 0  # the arena's count: our moves that came too late (each used a round)
    closed: str | None = None
    version: int = 0  # grows whenever the supplier's side changes without a move of ours (a timeout answer)
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
    def offers(self) -> list[tuple[str, dict]]:
        """Every sheet of the supplier's latest message: its primary offer and its alternatives
        (case:P10 offered EUR 31.80 at 54 days next to EUR 33.70 at 42 - the second was ours)."""
        return [
            (s["term_sheet_id"], s["terms"]) for s in self.latest.get("term_sheets") or [] if s.get("term_sheet_id")
        ]

    @property
    def rounds_used(self) -> int:
        """The e-mails we sent. The arena's round limit also counts our timeouts: see `arena_rounds`."""
        return sum(1 for m in self.messages if m.get("from") == "buyer" and not m.get("action"))

    @property
    def arena_rounds(self) -> int:
        """Rounds as the arena counts them against the round limit: our e-mails plus our timeouts."""
        return self.rounds_used + self.timeouts

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

    def seconds_left(self) -> float:
        """What is left of the 60 s for our next move; negative once the arena has counted a timeout."""
        return MOVE_LIMIT_S - self.seconds_since_reply()

    @property
    def timeouts_in_a_row(self) -> int:
        """Timeouts since our last e-mail: the third one ends the thread (the supplier walks away)."""
        n = 0
        for m in reversed(self.messages):
            if m.get("from") == "buyer":
                break
            n += bool(m.get("timeout"))
        return n

    def urgency(self) -> float:
        """Order in the session's queue: the clock that ends first goes first, and a thread that has already
        timed out goes before one that has not - each timeout in a row counts as a whole clock. Without that
        one thread takes every timeout when the suppliers answer slower than the clocks run: its third in a
        row ends it."""
        return max(self.seconds_left(), 0.0) - MOVE_LIMIT_S * self.timeouts_in_a_row


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
        self.turn = Turn()  # one arena call of this session at a time
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
        opened_at = time.monotonic()  # every thread's clock runs from the opening (sandbox: 57.7 s left 2.3 s in)
        for sid, messages in reply["threads"].items():
            state = ThreadState(sid, last_reply_at=opened_at)
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
            self.threads[sid] = ThreadState(sid)
            self._sync_thread(sid)
        self._read_clocks(state)
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
        best = any_opening = math.inf
        for sid, t in self.threads.items():
            first = next((m for m in t.supplier_messages if m.get("term_sheets")), None)
            if not first:
                continue
            c = self.cost(sid, first["term_sheets"][0]["terms"])
            any_opening = min(any_opening, c)
            if self.keeps_must_haves(sid, first["term_sheets"][0]["terms"]):
                best = min(best, c)
        # where no opening keeps the must-haves the arena takes the cheapest of all (P10, P11: its recorded
        # C_open is that of the only opening, which breaks one)
        return best if math.isfinite(best) else any_opening

    def best_offer(self, supplier_id: str) -> tuple[str | None, dict]:
        """The supplier's sheet that costs us least and keeps the must-haves (else its primary one)."""
        t = self.threads[supplier_id]
        valid = [(sid_, terms) for sid_, terms in t.offers if self.keeps_must_haves(supplier_id, terms)]
        if not valid:
            return t.standing
        return min(valid, key=lambda o: self.cost(supplier_id, o[1]))

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
    def send(
        self, supplier_id: str, message: dict, rationale: dict | None = None, *, basis: int | None = None
    ) -> dict | None:
        """Send one e-mail; returns the supplier's reply (None if the case ended meanwhile).

        `basis` is the thread's `version` the message was written for. If the supplier has answered a timeout
        since, the message is not sent - it would answer an offer that no longer stands - and the supplier's
        latest message is returned for a new decision.
        """
        t = self.threads[supplier_id]
        with self.turn.take(t.urgency):
            if self.ended.is_set():
                return None
            self._sync_if_due()
            if self.ended.is_set():
                return None
            if not t.live or (basis is not None and t.version != basis):
                self.recorder.metrics.incr("moves.withdrawn")
                self.recorder.event(
                    "move_withdrawn",
                    session_id=self.session_id,
                    case_id=self.case_id,
                    supplier_id=supplier_id,
                    why="the thread ended" if not t.live else "the supplier answered a timeout meanwhile",
                    standing=t.standing[0],
                    status=t.status,
                )
                log.warning("%s: move withdrawn - the thread changed while it waited (%s)", supplier_id, t.status)
                return t.latest
            return self._send(supplier_id, message, rationale)

    def _send(self, supplier_id: str, message: dict, rationale: dict | None) -> dict | None:
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
        arena_round = t.arena_rounds + 1
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
            t.messages = [*t.messages, {**message, "from": "buyer", "sent_at": utc_now()}, reply]
            t.last_reply_at = time.monotonic()  # the clock runs from the reply, not from when its files are read
        self._with_documents(reply, supplier_id)
        self._log_reply(supplier_id, reply, took, round_no)
        if reply.get("status") in ENDED_STATUSES:
            t.closed = reply["status"]
        answered = _round_of(reply)
        if took > MOVE_LIMIT_S or (answered is not None and answered != arena_round):
            # The arena is further than this reply: it counted timeouts we have not seen (a reply that reached
            # us after a retry was two timeouts old on the sandbox), or the thread ran out while we waited.
            self._sync(force=supplier_id)
        else:
            self._sync_if_due()
        return reply

    # ------------------------------------------------------------------ the arena's own state
    def sync(self) -> set[str]:
        """Read the arena's state of every thread (clocks, standing offers, timeout answers) before a move
        that compares suppliers. Returns the suppliers whose thread had changed."""
        with self.turn.take(lambda: -math.inf):
            return set() if self.ended.is_set() else self._sync()

    def _sync_if_due(self) -> set[str]:
        """Read the arena's state when a clock of ours has (nearly) run out: its timeout answer is waiting."""
        if any(t.live and t.seconds_left() < SYNC_MARGIN_S for t in self.threads.values()):
            return self._sync()
        return set()

    def _sync(self, force: str | None = None) -> set[str]:
        """One GET of the session: each thread's clock, standing offer and timeouts. A thread that differs from
        ours is read in full. The caller holds the turn."""
        try:
            state = self.client.session(self.session_id)
        except ArenaError as e:
            log.warning("sync: %s", e)
            return set()
        if state.get("status") == "ended":
            self.result = state.get("result") or {"deal": False, "end_reason": state.get("end_reason")}
            self.ended.set()
            return set()
        counted = timeouts_by_supplier(state)
        changed = set()
        for sid, info in (state.get("threads") or {}).items():
            t = self.threads.get(sid)
            if t is None:
                continue
            differs = (
                sid == force
                or counted[sid] > t.timeouts
                or bool(info.get("closed")) != bool(t.closed)
                or (not t.closed and info.get("offer_id") != t.standing[0])
            )
            if differs and self._sync_thread(sid):
                changed.add(sid)
        self._read_clocks(state)
        return changed

    def _read_clocks(self, state: dict) -> None:
        now = time.monotonic()
        for sid, info in (state.get("threads") or {}).items():
            left = info.get("seconds_left")
            if sid in self.threads and left is not None:
                self.threads[sid].last_reply_at = now - (MOVE_LIMIT_S - float(left))

    def _sync_thread(self, supplier_id: str) -> bool:
        """Read one thread from the arena and take over what we miss: the supplier's answers to our timeouts
        (they are not in `messages`), its standing offer, whether it ended. True if it had changed."""
        try:
            thread = self.client.thread(self.session_id, supplier_id)
        except ArenaError as e:
            log.warning("%s: cannot read the thread: %s", supplier_id, e)
            return False
        t = self.threads[supplier_id]
        messages = thread_messages(thread, supplier_id, t.messages)
        for m in messages:
            if m.get("from") != "buyer" and not m.get("timeout"):
                self._with_documents(m, supplier_id)
        before = (len(t.messages), t.standing[0], t.status, t.closed, t.timeouts)
        known = {m.get("message_id") for m in t.messages}
        fresh = [m for m in messages if m.get("timeout") and m["message_id"] not in known]
        with t.lock:
            t.messages = messages
            t.timeouts = len(thread.get("timeouts") or [])
            ended = t.latest.get("status") if t.latest.get("status") in ENDED_STATUSES else None
            t.closed = thread.get("closed") or ended
        changed = before != (len(t.messages), t.standing[0], t.status, t.closed, t.timeouts)
        if changed:
            t.version += 1
            t.last_reply_at = time.monotonic()  # until the session's `seconds_left` says it exactly
        for m in fresh:
            self._log_timeout(supplier_id, m)
        self.recorder.event(
            "thread_refreshed",
            session_id=self.session_id,
            supplier_id=supplier_id,
            offer_id=t.standing[0],
            status=t.status,
            timeouts=t.timeouts,
            closed=t.closed,
            changed=changed,
        )
        return changed

    def _log_timeout(self, supplier_id: str, answer: dict) -> None:
        self.recorder.metrics.incr("moves.timeouts")
        self.recorder.metrics.incr(f"supplier.status.{answer.get('status')}")
        sheets = answer.get("term_sheets") or []
        terms = sheets[0]["terms"] if sheets else {}
        self.recorder.event(
            "timeout",
            session_id=self.session_id,
            case_id=self.case_id,
            supplier_id=supplier_id,
            round=answer.get("round"),
            status=answer.get("status"),
            offer_id=sheets[0]["term_sheet_id"] if sheets else None,
            terms=terms,
            c=self.cost(supplier_id, terms),
            body=answer.get("body"),
        )
        log.warning(
            "%s: TIMEOUT counted by the arena in round %s - it answered %s %s",
            supplier_id,
            answer.get("round"),
            answer.get("status"),
            terms.get("unit_price"),
        )

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
        self._sync(force=supplier_id)

    def accept(self, supplier_id: str, term_sheet_id: str, rationale: dict | None = None) -> dict:
        if problems := accept_problems(self, supplier_id, term_sheet_id):
            self.recorder.metrics.incr("guards.accept_refused")
            self.recorder.event("guard_refused", session_id=self.session_id, supplier_id=supplier_id, problems=problems)
            raise GuardRefused(f"{supplier_id} {term_sheet_id}: {'; '.join(problems)}")
        terms = dict(self.threads[supplier_id].offers).get(term_sheet_id) or self.threads[supplier_id].standing[1]
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
        # the arena refuses to walk away through a thread that has ended (422 on the sandbox, after three
        # timeouts): try the live threads first, and never leave the case open
        order = sorted(self.threads, key=lambda sid: (not self.threads[sid].live, sid != supplier_id))
        for i, sid in enumerate(order):
            try:
                return self._close(sid, {"action": {"type": "walk_away"}})
            except ArenaError as e:
                if e.status != 422 or i == len(order) - 1:
                    raise
                log.warning("%s: cannot walk away through this thread (%s) - trying the next", sid, e.detail)
        return self.result or {}

    def _close(self, supplier_id: str, message: dict) -> dict:
        with self._lock, self.turn.take(lambda: -math.inf):  # a closing move goes before every waiting e-mail
            if self.ended.is_set():
                return self.result or {}
            try:
                reply = self.client.send_message(self.session_id, supplier_id, message)
                self.result = reply.get("result", reply)
            except ArenaError as e:
                if e.status == 422 and (message.get("action") or {}).get("type") == "accept":
                    # the standing offer was replaced meanwhile (a keepalive's answer, or the answer to a
                    # timeout - case:D02 lost its deal this way): read the thread again and take the current
                    # sheet if it still passes the guards
                    fresh = self._refreshed_standing(supplier_id)
                    if fresh and not accept_problems(self, supplier_id, fresh):
                        self.recorder.event(
                            "accept_retry", session_id=self.session_id, supplier_id=supplier_id, offer=fresh
                        )
                        log.warning("%s: standing offer changed - accepting %s instead", supplier_id, fresh)
                        reply = self.client.send_message(
                            self.session_id, supplier_id, {"action": {"type": "accept", "term_sheet_id": fresh}}
                        )
                        self.result = reply.get("result", reply)
                        self.ended.set()
                        return self.result
                    raise
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

    def _refreshed_standing(self, supplier_id: str) -> str | None:
        """Reload one thread from the arena; returns its current standing offer id."""
        self._sync_thread(supplier_id)
        return self.threads[supplier_id].standing[0]

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
        self._count_timeouts(state)
        outcome = self.outcome(result, state, duration)
        m = self.recorder.metrics
        m.observe("case.seconds", duration)
        m.incr("cases.deal" if result.get("deal") else "cases.no_deal")
        self.recorder.event("result", **outcome)
        saved = {
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
        }
        self.recorder.save_json(f"sessions/{safe_name(self.session_id)}.json", saved)
        try:  # the chat to read right after the case; never worth failing a case over
            write_session_chat(self.recorder.dir, saved)
        except Exception as e:  # noqa: BLE001
            log.warning("chat transcript: %s", e)
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

    def _count_timeouts(self, state: dict) -> None:
        """Take the arena's count of our timeouts from the final state: a timeout whose answer we never read
        (the case closed first) still happened - six case:P05 sessions had 14 in the trace and 2 in our files."""
        for sid, n in timeouts_by_supplier(state).items():
            t = self.threads.get(sid)
            if t is None or n <= t.timeouts:
                continue
            self.recorder.metrics.incr("moves.timeouts", n - t.timeouts)
            self.recorder.metrics.incr("moves.timeouts_unseen", n - t.timeouts)
            self.recorder.event(
                "timeouts_unseen",
                session_id=self.session_id,
                case_id=self.case_id,
                supplier_id=sid,
                seen=t.timeouts,
                counted=n,
            )
            log.warning("%s: the arena counted %d timeout(s), we had seen %d", sid, n, t.timeouts)
            t.timeouts = n

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
                "arena_rounds": t.arena_rounds,
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
            "timeouts": sum(t.timeouts for t in self.threads.values()),
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


def timeouts_by_supplier(state: dict) -> Counter:
    """How many timeouts the arena counted per supplier: the session's `moves` while it runs, its trace after."""
    moves = Counter(
        m.get("supplier_id") for m in state.get("moves") or [] if (m.get("move") or {}).get("type") == "timeout"
    )
    trace = Counter(
        (r.get("move") or {}).get("supplier_id")
        for r in state.get("trace") or (state.get("result") or {}).get("trace") or []
        if r.get("actor") == "buyer" and (r.get("move") or {}).get("type") == "timeout"
    )
    return Counter({sid: max(moves[sid], trace[sid]) for sid in {*moves, *trace}})


def timeout_message(answer: dict, supplier_id: str, number: int | None = None) -> dict:
    """The supplier's answer to one of our timeouts, in the shape of its e-mails."""
    sheets = []
    if answer.get("offer_id"):
        sheets.append({"term_sheet_id": answer["offer_id"], "terms": answer.get("terms") or {}})
    sheets += [
        {"term_sheet_id": alt["offer_id"], "terms": alt.get("terms") or {}}
        for alt in answer.get("alternatives") or []
        if alt.get("offer_id")
    ]
    return {
        "message_id": f"timeout:{supplier_id.split(':', 1)[-1]}-{answer.get('round', f'n{number}')}",
        "from": f"timeout@{supplier_id}",
        "from_name": f"{supplier_id}, answering our TIMEOUT",
        "timeout": True,
        "round": answer.get("round"),
        "status": answer.get("status"),
        "term_sheets": sheets,
        "missing_fields": answer.get("missing_fields") or [],
        "claim_results": answer.get("claim_results") or [],
        "signals": answer.get("signals"),
        "body": answer.get("text") or "",
    }


def thread_messages(thread: dict, supplier_id: str, ours: list[dict] | None = None) -> list[dict]:
    """A thread as the arena holds it, in the order things happened: its `messages` with the answers to our
    timeouts (a separate list, numbered by round) put where they belong. Messages we already hold are kept,
    with the documents we read and the time we sent ours.

    case:P05, session 91dbf752ed31c16a: round 2 of Dralveck was a timeout answered with EUR 28.00; our next
    e-mail became round 3. The answer was only in `timeouts`, so we kept negotiating from EUR 30.50.
    """
    ours = ours or []
    known = {m["message_id"]: m for m in ours if m.get("message_id")}
    sent = [m for m in ours if m.get("from") == "buyer"]
    every = thread.get("timeouts") or []
    answers = sorted((a for a in every if a.get("round") is not None), key=lambda a: a["round"])
    unnumbered = [timeout_message(a, supplier_id, i) for i, a in enumerate(every) if a.get("round") is None]
    out: list[dict] = []
    n_buyer = 0
    for m in thread.get("messages", []):
        if m.get("from") == "buyer":
            out.append(sent[n_buyer] if n_buyer < len(sent) else m)
            n_buyer += 1
            continue
        round_no = _round_of(m)
        while answers and round_no is not None and answers[0]["round"] < round_no:
            # it came before the e-mail of ours that this message replies to
            at = len(out) - 1 if out and out[-1].get("from") == "buyer" else len(out)
            out.insert(at, timeout_message(answers.pop(0), supplier_id))
        out.append(known.get(m.get("message_id"), m))
    out += [timeout_message(a, supplier_id) for a in answers] + unnumbered
    return [known.get(m.get("message_id"), m) if m.get("timeout") else m for m in out]


def timeout_messages(thread: dict, supplier_id: str) -> list[dict]:
    """The supplier's answers to our late moves, as messages: case:P05 lost track of an agreed offer because
    its standing sheet (offer:70210-5) existed only in the thread's `timeouts` list."""
    rounds = [_round_of(m) for m in thread.get("messages", []) if m.get("from") != "buyer"]
    last = max((r for r in rounds if r is not None), default=-1)
    out = []
    for answer in sorted(thread.get("timeouts") or [], key=lambda a: a.get("round") or 0):
        if (answer.get("round") or 0) <= last:
            continue  # a regular reply came after it: that one stands
        out.append(
            {
                "from": f"timeout@{supplier_id}",
                "status": answer.get("status"),
                "term_sheets": [{"term_sheet_id": answer.get("offer_id"), "terms": answer.get("terms") or {}}],
                "missing_fields": answer.get("missing_fields") or [],
                "claim_results": answer.get("claim_results") or [],
                "signals": answer.get("signals"),
                "body": answer.get("text") or "",
            }
        )
    return out


def _round_of(message: dict) -> int | None:
    """The round of a supplier message from its id (msg:<supplier>-<round>-<n>)."""
    parts = (message.get("message_id") or "").rsplit("-", 2)
    try:
        return int(parts[-2])
    except (IndexError, ValueError):
        return None
