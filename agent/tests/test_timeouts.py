"""The 60 s clock with several suppliers: no move on an offer that no longer stands, no timeout we do not count.

The arena is `fake_arena.FakeArena` (its docstring lists what was measured); its clock is 1 s here instead
of 60 s, and so are our constants.
"""

import json
import time
from pathlib import Path

import pytest
from fake_arena import FakeArena

from negotiator import runner, session
from negotiator.client import ArenaError
from negotiator.config import REPO_ROOT
from negotiator.runner import play_case
from negotiator.session import Negotiation, thread_messages, timeouts_by_supplier
from negotiator.strategy.base import Decision
from negotiator.telemetry import Recorder

SIM_CASES = REPO_ROOT / "negotiation-arena-kit" / "starter-kit" / "arena_kit" / "sim_cases"
LIMIT_S = 1.0  # the arena's 60 s, scaled


def rfq(*suppliers: str) -> dict:
    c = json.loads((SIM_CASES / "S01.json").read_text(encoding="utf-8"))
    c.update(type="rfq", suppliers=list(suppliers), round_limit=10)
    return c


@pytest.fixture(autouse=True)
def scaled_clock(monkeypatch, tmp_path):
    monkeypatch.setattr(session, "MOVE_LIMIT_S", LIMIT_S)
    monkeypatch.setattr(session, "SYNC_MARGIN_S", 0.05)
    monkeypatch.setattr(runner, "KEEPALIVE_AFTER_S", 0.33)
    monkeypatch.setattr(runner, "POLL_S", 0.01)
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "")  # no tracing from tests
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "")


class Stepper:
    """Answers the standing offer with 3 % less, `rounds` times per thread; closes on the cheapest standing
    offer. It names the offer it answers, so the fake arena can tell a move on an offer that no longer stands."""

    name = "stepper"

    def __init__(self, rounds: int = 3, think_s: float = 0.0, close_after_s: float = 0.0) -> None:
        self.rounds, self.think_s, self.close_after_s = rounds, think_s, close_after_s

    def prepare(self, neg: Negotiation) -> None:
        pass

    def decide(self, neg: Negotiation, sid: str) -> Decision:
        t = neg.threads[sid]
        if not t.live:
            return Decision.drop(sid, "ended")
        if t.status in ("agreed", "final_offer") or t.rounds_used >= self.rounds:
            return Decision.hold(sid, t.status)
        offer_id, terms = t.standing
        time.sleep(self.think_s)
        sheet = {"terms": {**terms, "unit_price": round(terms["unit_price"] * 0.97, 2)}}
        message = {"subject": "Your quote", "body": "Our offer.", "term_sheets": [sheet], "answers_offer": offer_id}
        return Decision("message", sid, message=message, rationale={"why": "step"})

    def conclude(self, neg: Negotiation) -> Decision:
        time.sleep(self.close_after_s)
        live = [(t.standing[1]["unit_price"], sid) for sid, t in neg.threads.items() if t.live and t.standing[0]]
        if not live:
            return Decision("walk_away", next(iter(neg.threads)), rationale={"why": "nobody left"})
        _, sid = min(live)
        return Decision("accept", sid, term_sheet_id=neg.threads[sid].standing[0], rationale={"why": "cheapest"})

    def keepalive(self, neg: Negotiation, sid: str) -> dict | None:
        return {"subject": "Your quote", "body": "Could you confirm the validity of your offer?"}


def play(tmp_path: Path, arena: FakeArena, strategy: Stepper, deadline=None) -> tuple[dict, Recorder, dict]:
    recorder = Recorder(tmp_path, "timeouts")
    outcome = play_case(arena, recorder, arena.case["case_id"], lambda: strategy, deadline=deadline)  # type: ignore[arg-type]
    recorder.close()
    saved = json.loads((recorder.dir / "sessions" / "fake1.json").read_text(encoding="utf-8"))
    return outcome, recorder, saved


def events(recorder: Recorder, kind: str) -> list[dict]:
    rows = [json.loads(x) for x in (recorder.dir / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    return [r for r in rows if r["kind"] == kind]


# ---------------------------------------------------------------- three suppliers: more work than the clock allows
def test_timeouts_with_three_slow_suppliers_are_seen_counted_and_answered(tmp_path) -> None:
    """case:P05 in small: the three answers of one round take 1.55 clocks, so some thread must run out.
    Before the fix (session 91dbf752ed31c16a) the supplier's answer to the timeout was never read: we offered
    more than its standing price, accepted a dearer supplier, and reported 0 timeouts."""
    arena = FakeArena(rfq("sup:A", "sup:B", "sup:C"), {"sup:A": 0.15, "sup:B": 0.9, "sup:C": 0.5}, limit_s=LIMIT_S)
    outcome, recorder, saved = play(tmp_path, arena, Stepper(rounds=3))

    counted = arena.counted()
    assert sum(counted.values()) > 0  # the scenario does overload the clock
    # our counter is the arena's
    assert {sid: t["timeouts"] for sid, t in outcome["threads"].items()} == counted
    assert outcome["timeouts"] == sum(counted.values())
    assert recorder.metrics.snapshot()["counters"]["moves.timeouts"] == sum(counted.values())
    # no e-mail answered an offer that had been replaced by a timeout answer
    assert arena.stale_moves == []
    # every answer to a timeout is in our thread, in its place: the price path is the arena's
    for sup, th in arena.threads.items():
        ours = saved["threads"][sup]["messages"]
        prices = {a["round"]: a["terms"].get("unit_price") for a in th["timeouts"]}
        mine = {m["round"]: (m["term_sheets"][0]["terms"]["unit_price"] if m["term_sheets"] else None)
                for m in ours if m.get("timeout")}  # fmt: skip
        assert mine == prices
        rounds = [int(m["message_id"].rsplit("-", 2)[1] if not m.get("timeout") else m["round"])
                  for m in ours if m.get("from") != "buyer"]  # fmt: skip
        assert rounds == sorted(rounds)
        assert outcome["threads"][sup]["arena_rounds"] == th["round"]
    # the deal is the cheapest offer standing at the arena, not the cheapest we happened to have seen
    assert outcome["deal"] and outcome["end_reason"] == "accepted"
    standing = {sup: th["price"] for sup, th in arena.threads.items() if not th["closed"]}
    assert outcome["supplier_id"] == min(standing, key=standing.get)
    assert len(events(recorder, "timeout")) == sum(counted.values())


def test_two_suppliers_within_the_clock_have_no_timeout(tmp_path) -> None:
    """Two answers of 0.3 clocks each fit: queued in the order of their clocks, nobody runs out - and the
    supplier that said 'final offer' first is kept alive while the other still negotiates."""
    arena = FakeArena(rfq("sup:A", "sup:B"), {"sup:A": 0.3, "sup:B": 0.3}, limit_s=LIMIT_S, final_after={"sup:A": 1})
    outcome, recorder, _ = play(tmp_path, arena, Stepper(rounds=4))
    assert arena.counted() == {"sup:A": 0, "sup:B": 0}
    assert outcome["timeouts"] == 0 and arena.stale_moves == []
    assert outcome["deal"] and outcome["supplier_id"] == "sup:B"
    assert recorder.metrics.snapshot()["counters"].get("moves.keepalive", 0) >= 1
    assert "moves.timeouts" not in recorder.metrics.snapshot()["counters"]


def test_one_call_of_a_session_at_a_time(tmp_path) -> None:
    """We queue ourselves: no call of ours waits inside the arena behind another one of the same session."""
    arena = FakeArena(rfq("sup:A", "sup:B", "sup:C"), {"sup:A": 0.1, "sup:B": 0.1, "sup:C": 0.1}, limit_s=LIMIT_S)
    waited = []
    inner = arena.send_message

    def send_message(session_id, supplier_id, message):
        free = arena.lock.acquire(blocking=False)
        waited.append(not free)
        if free:
            arena.lock.release()
        return inner(session_id, supplier_id, message)

    arena.send_message = send_message  # type: ignore[method-assign]
    outcome, _, _ = play(tmp_path, arena, Stepper(rounds=3))
    assert outcome["deal"] and waited and not any(waited)


# ---------------------------------------------------------------- one supplier
def test_a_slow_decision_is_decided_again_on_the_timeout_answer(tmp_path) -> None:
    """A decision that takes longer than the clock: the arena has played a timeout and the supplier has
    answered with a new offer. The e-mail written for the old offer is not sent."""
    arena = FakeArena(rfq("sup:A"), {"sup:A": 0.05}, limit_s=LIMIT_S)
    strategy = Stepper(rounds=1, think_s=1.2)
    strategy.think_s = 1.2
    calls = iter([1.2, 0.0, 0.0, 0.0])
    decide = strategy.decide

    def slow_once(neg, sid):
        strategy.think_s = next(calls, 0.0)
        return decide(neg, sid)

    strategy.decide = slow_once  # type: ignore[method-assign]
    outcome, recorder, _ = play(tmp_path, arena, strategy)
    assert arena.counted() == {"sup:A": 1} and outcome["timeouts"] == 1
    assert arena.stale_moves == []
    assert [e["why"] for e in events(recorder, "move_withdrawn")] == ["the supplier answered a timeout meanwhile"]
    assert outcome["threads"]["sup:A"]["rounds"] == 1 and outcome["threads"]["sup:A"]["arena_rounds"] == 2
    assert outcome["deal"]


def test_accept_after_a_timeout_takes_the_offer_that_stands(tmp_path) -> None:
    """The closing move comes after the clock ran out: the id we hold is no longer the standing offer (422).
    The thread is read again - its standing offer is the answer to the timeout - and that one is accepted."""
    arena = FakeArena(rfq("sup:A"), {"sup:A": 0.05}, limit_s=LIMIT_S)
    outcome, recorder, _ = play(tmp_path, arena, Stepper(rounds=1, close_after_s=1.2))
    assert outcome["deal"] and outcome["timeouts"] == 1 == arena.counted()["sup:A"]
    assert outcome["terms"]["unit_price"] == arena.threads["sup:A"]["price"]
    assert len(events(recorder, "accept_retry")) == 1


def test_a_worker_accept_on_an_offer_that_changed_meanwhile_is_decided_again(tmp_path) -> None:
    """A timeout answer read in by another thread's call changes the offer while a worker decides to accept: the
    accept named the old offer, the guard would refuse it and the case would end with a walk-away. It decides
    again on the new offer instead."""

    class AcceptStale(Stepper):
        calls = 0

        def decide(self, neg, sid):
            t = neg.threads[sid]
            self.calls += 1
            if self.calls == 1:
                t.version += 1  # as `_sync_thread` does when it reads a timeout answer
                return Decision("accept", sid, term_sheet_id="offer:stale", rationale={"why": "agreed"})
            return Decision("accept", sid, term_sheet_id=t.standing[0], rationale={"why": "agreed"})

    arena = FakeArena(rfq("sup:A"), {"sup:A": 0.05}, limit_s=LIMIT_S)
    strategy = AcceptStale()
    outcome, recorder, _ = play(tmp_path, arena, strategy)
    assert outcome["deal"] and strategy.calls == 2


def test_a_reply_that_arrives_late_is_followed_by_the_arena_state(tmp_path) -> None:
    """Sandbox, 11 October: a POST hung, its retry returned the reply of round 2 after 181 s - the arena was
    at round 4 by then, two timeouts later. The reply is old news: the thread is read again."""
    arena = FakeArena(rfq("sup:A"), {"sup:A": 0.05}, limit_s=LIMIT_S, delay_reply={("sup:A", 1): 2.3})
    outcome, _, saved = play(tmp_path, arena, Stepper(rounds=1))
    assert arena.counted() == {"sup:A": 2} and outcome["timeouts"] == 2
    their = outcome["threads"]["sup:A"]["their_prices"]
    assert their[-1] == arena.threads["sup:A"]["price"] and len(their) == 4  # opening, reply, two timeout answers
    assert outcome["deal"] and outcome["terms"]["unit_price"] == arena.threads["sup:A"]["price"]


def test_walk_away_goes_through_a_thread_that_is_still_open(tmp_path) -> None:
    """Sandbox, 11 October: 422 'the thread has ended (timeout)' on a walk-away through a thread that three
    timeouts had ended - and the case stayed open."""
    arena = FakeArena(rfq("sup:A", "sup:B"), {"sup:A": 0.05, "sup:B": 0.05}, limit_s=LIMIT_S)
    neg = Negotiation(arena, Recorder(tmp_path, "walk"))  # type: ignore[arg-type]
    neg.open("case:S01")
    arena.threads["sup:A"].update(closed="walked_away", status="walked_away")
    neg.walk_away("sup:A", {"why": "test"})
    assert arena.status == "ended" and arena.end_reason == "walked_away"
    assert arena.calls[-1] == ("walk_away", "sup:B")


# ---------------------------------------------------------------- closing before a deadline
def timed_calls(arena: FakeArena) -> list[tuple[str, float]]:
    """(action or 'message', time.time() when the arena took it) for every e-mail and closing move."""
    calls, inner = [], arena.send_message

    def send_message(session_id, supplier_id, message):
        with arena.lock:  # taken when the arena serves it, not when it was asked
            calls.append(((message.get("action") or {}).get("type") or "message", time.time()))
        return inner(session_id, supplier_id, message)

    arena.send_message = send_message  # type: ignore[method-assign]
    return calls


def test_the_close_does_not_wait_for_a_decision_in_progress(tmp_path, monkeypatch) -> None:
    """A wave's cap: the case closes CLOSE_BEFORE_DEADLINE_S before it. A worker still deciding (an LLM call)
    when the close begins used to be waited for, and its e-mail sent; the accept came after the supplier's
    answer - here after the cap. Now the close goes first and the late e-mail is not sent."""
    monkeypatch.setattr(session, "CLOSE_BEFORE_DEADLINE_S", 1.0)
    monkeypatch.setattr(session, "MOVE_LIMIT_S", 10.0)
    arena = FakeArena(rfq("sup:A"), {"sup:A": 0.8}, limit_s=10.0)
    calls = timed_calls(arena)
    cap = time.time() + 2.5
    outcome, _, _ = play(tmp_path, arena, Stepper(rounds=3, think_s=1.8), deadline=cap)
    assert outcome["deal"] and [c for c, _ in calls] == ["accept"]
    assert calls[0][1] < cap - 0.5
    time.sleep(0.5)  # the worker's decision ends: its e-mail is not sent
    assert [c for c, _ in calls] == ["accept"]


def test_an_email_waiting_for_the_turn_is_not_sent_once_the_close_began(tmp_path) -> None:
    arena = FakeArena(rfq("sup:A"), {"sup:A": 0.05}, limit_s=LIMIT_S)
    neg = Negotiation(arena, Recorder(tmp_path, "closing"))  # type: ignore[arg-type]
    neg.open("case:S01")
    with neg.turn.take(lambda: -1.0):  # another call of the session is at the arena
        neg.closing.set()
    assert neg.send("sup:A", {"subject": "s", "body": "b"}) is None
    assert arena.calls == [] and neg.recorder.metrics.snapshot()["counters"]["moves.not_sent_closing"] == 1
    # by the clock alone: a deadline closer than CLOSE_BEFORE_DEADLINE_S
    neg.closing.clear()
    neg.deadline = time.time() + session.CLOSE_BEFORE_DEADLINE_S - 1
    assert neg.closing_soon() and neg.send("sup:A", {"subject": "s", "body": "b"}) is None
    neg.deadline = None
    assert not neg.closing_soon(10**6)


def test_no_keepalive_whose_answer_would_be_due_after_the_close(tmp_path, monkeypatch) -> None:
    """A held thread gets no keepalive within KEEPALIVE_REPLY_S of the close: it would hold up the closing move."""
    monkeypatch.setattr(session, "CLOSE_BEFORE_DEADLINE_S", 0.5)
    monkeypatch.setattr(runner, "KEEPALIVE_REPLY_S", 100.0)
    arena = FakeArena(rfq("sup:A", "sup:B"), {"sup:A": 0.3, "sup:B": 0.3}, limit_s=LIMIT_S, final_after={"sup:A": 1})
    outcome, recorder, _ = play(tmp_path, arena, Stepper(rounds=4), deadline=time.time() + 30)
    assert outcome["deal"]
    assert "moves.keepalive" not in recorder.metrics.snapshot()["counters"]


def test_a_held_thread_without_keepalive_is_closed_on_before_its_clock_runs_out(tmp_path, monkeypatch) -> None:
    """The strategy sends no keepalive in a thread's last rounds (tactical: two rounds left). The supplier said
    'final offer' and waits while a rival negotiates; at 60 s a timeout would replace or end its offer. The case
    closes once the held thread's answer is CLOSE_UNKEPT_AFTER_S old."""
    monkeypatch.setattr(runner, "CLOSE_UNKEPT_AFTER_S", 0.5)

    class NoKeepalive(Stepper):
        def keepalive(self, neg, sid):
            return None

    arena = FakeArena(rfq("sup:A", "sup:B"), {"sup:A": 0.1, "sup:B": 0.25}, limit_s=LIMIT_S, final_after={"sup:A": 1})
    outcome, recorder, _ = play(tmp_path, arena, NoKeepalive(rounds=8), deadline=time.time() + 1000)
    assert arena.counted()["sup:A"] == 0 and outcome["deal"]
    assert [e["supplier_id"] for e in events(recorder, "close_unkept_thread")] == ["sup:A"]


def test_without_a_wave_cap_a_held_thread_does_not_close_the_case(tmp_path, monkeypatch) -> None:
    """Practice and sandbox keep the behaviour their scores were measured with: no early close."""
    monkeypatch.setattr(runner, "CLOSE_UNKEPT_AFTER_S", 0.5)

    class NoKeepalive(Stepper):
        def keepalive(self, neg, sid):
            return None

    arena = FakeArena(rfq("sup:A", "sup:B"), {"sup:A": 0.1, "sup:B": 0.25}, limit_s=LIMIT_S, final_after={"sup:A": 1})
    _, recorder, _ = play(tmp_path, arena, NoKeepalive(rounds=8))
    assert not events(recorder, "close_unkept_thread")


# ---------------------------------------------------------------- opening in the final
def failing_open(arena: FakeArena, *errors: ArenaError) -> list[str]:
    """The arena refuses the first openings with these errors; returns the list of attempts."""
    attempts, inner, queue = [], arena.open_session, list(errors)

    def open_session(case_id):
        attempts.append(case_id)
        if queue:
            raise queue.pop(0)
        return inner(case_id)

    arena.open_session = open_session  # type: ignore[method-assign]
    return attempts


def test_a_final_case_is_opened_again_after_a_refusal_that_may_pass(tmp_path, monkeypatch) -> None:
    """429 without Retry-After (too many open sessions: the client does not retry it), a 5xx after the client's
    own retries, a transport error: the case is opened again while the wave has time left."""
    monkeypatch.setattr(runner, "OPEN_PAUSE_S", (0.01, 0.02))
    arena = FakeArena(rfq("sup:A"), {"sup:A": 0.05}, limit_s=LIMIT_S)
    attempts = failing_open(
        arena,
        ArenaError(429, "too many open sessions", "POST", "/v1/sessions"),
        ArenaError(503, "unavailable", "POST", "/v1/sessions"),
        ArenaError(0, "ReadTimeout", "POST", "/v1/sessions"),
    )
    outcome, recorder, _ = play(tmp_path, arena, Stepper(rounds=1), deadline=time.time() + 1000)
    assert len(attempts) == 4 and outcome["deal"]
    assert [e["status"] for e in events(recorder, "open_retry")] == [429, 503, 0]


@pytest.mark.parametrize(
    "deadline, error",
    [
        (None, ArenaError(429, "too many open sessions")),  # practice, sandbox: as before
        (1000, ArenaError(429, "practice limit reached")),  # the quota does not come back within a wave
        (1000, ArenaError(422, "unknown case")),
        (30, ArenaError(503, "unavailable")),  # too little of the wave left to negotiate
    ],
)
def test_a_case_is_not_opened_again_when_a_retry_cannot_help(tmp_path, monkeypatch, deadline, error) -> None:
    monkeypatch.setattr(runner, "OPEN_PAUSE_S", (0.01, 0.02))
    arena = FakeArena(rfq("sup:A"), {"sup:A": 0.05}, limit_s=LIMIT_S)
    attempts = failing_open(arena, error)
    with pytest.raises(ArenaError):
        play(tmp_path, arena, Stepper(rounds=1), deadline=deadline and time.time() + deadline)
    assert len(attempts) == 1


# ---------------------------------------------------------------- reading the arena's thread
def test_timeout_answers_are_put_where_they_happened() -> None:
    """The shape of session 91dbf752ed31c16a: round 2 was a timeout, our second e-mail became round 3."""
    sheet = lambda i, p: [{"term_sheet_id": f"offer:x-{i}", "terms": {"unit_price": p}}]  # noqa: E731
    ours = [
        {"from": "sales@x", "message_id": "msg:x-0-0", "term_sheets": sheet(0, 36.0), "attachments": [{"text": "q"}]},
        {"from": "buyer", "body": "first", "sent_at": "t1"},
        {"from": "sales@x", "message_id": "msg:x-1-2", "term_sheets": sheet(1, 30.5)},
        {"from": "buyer", "body": "second", "sent_at": "t2"},
        {"from": "sales@x", "message_id": "msg:x-3-5", "status": "agreed", "term_sheets": sheet(3, 28.79)},
    ]
    thread = {
        "messages": [{k: v for k, v in m.items() if k not in ("sent_at", "attachments")} for m in ours],
        "timeouts": [
            {"offer_id": "offer:x-4", "round": 4, "status": "final_offer", "terms": {"unit_price": 28.79}},
            {"offer_id": "offer:x-2", "round": 2, "status": "open", "terms": {"unit_price": 28.0}, "text": "we move"},
        ],
    }
    out = thread_messages(thread, "sup:x", ours)
    assert [m["term_sheets"][0]["term_sheet_id"] if m.get("from") != "buyer" else m["body"] for m in out] == [
        "offer:x-0", "first", "offer:x-1", "offer:x-2", "second", "offer:x-3", "offer:x-4",
    ]  # fmt: skip
    assert out[3]["timeout"] and out[3]["body"] == "we move" and out[3]["status"] == "open"
    assert out[0]["attachments"] == [{"text": "q"}] and out[4]["sent_at"] == "t2"  # what we held is kept
    assert out[-1]["status"] == "final_offer"
    # a supplier that walked away on the third timeout has no offer left
    gone = thread_messages({"messages": [], "timeouts": [{"offer_id": None, "round": 4, "status": "walked_away"}]}, "s")
    assert gone[0]["term_sheets"] == [] and gone[0]["status"] == "walked_away"


def test_timeouts_are_counted_from_the_sessions_moves_and_from_its_trace() -> None:
    moves = {"moves": [{"supplier_id": "sup:a", "move": {"type": "timeout"}, "reply": {}}] * 2}
    trace = {"trace": [{"actor": "buyer", "move": {"type": "timeout", "supplier_id": "sup:b"}},
                       {"actor": "buyer", "move": {"type": "message", "supplier_id": "sup:b"}},
                       {"actor": "sup:b", "move": {"status": "open"}}]}  # fmt: skip
    assert timeouts_by_supplier(moves) == {"sup:a": 2}
    assert timeouts_by_supplier(trace) == {"sup:b": 1}
    assert timeouts_by_supplier({"result": trace}) == {"sup:b": 1}
    assert timeouts_by_supplier({}) == {}
