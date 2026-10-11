"""Play cases: one case (threads in parallel), many cases in parallel, or the Live Final in waves.

Every supplier thread has its own 60 s clock, from the opening and then from each of its replies, so each
live thread gets its own worker. A thread the strategy holds (agreed, final offer, ...) keeps ticking while
the others still negotiate: the coordinator sends the strategy's keepalive before the clock runs out, and
closes the case with `strategy.conclude` once every thread is held or dropped - or when the deadline is near.

The arena answers one call of a session at a time, so with several suppliers a thread waits while the
others are answered, and its 60 s can run out (case:P05, three suppliers: 14 timeouts in six sessions; no
single-supplier session had one). At the end of the 60 s the arena itself plays the timeout: it repeats our
last offer, uses a round, and the supplier answers - a new price, a final offer, or it walks away (the third
in a row). That answer is in no reply of ours: only in the thread's `timeouts` and the session's `moves`.
So the workers queue for the session's turn (`Negotiation.turn`, the clock that ends first goes first), the
arena's state is read whenever a clock has run out, and a move written before a timeout answer arrived is
not sent: the strategy decides again on the offer that stands.
"""

import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from negotiator.client import ArenaClient, ArenaError
from negotiator.data import WorldData
from negotiator.session import GuardRefused, Negotiation
from negotiator.strategy.base import Decision, Strategy
from negotiator.telemetry import Recorder, log

# A held thread's clock: answer well before 60 s. We see a reply only when our HTTP call returns, and the arena
# serves one session's calls one after another - a reply can reach us long after the supplier's clock started.
KEEPALIVE_AFTER_S = 20.0
# No keepalive this close to the case's own close (session.CLOSE_BEFORE_DEADLINE_S): its answer would be due then.
KEEPALIVE_REPLY_S = 60.0
# A held thread nothing keeps alive (no keepalive in its last rounds, or too near the close) loses its offer to a
# timeout at 60 s while the others negotiate: the case closes once its supplier's answer is this old.
CLOSE_UNKEPT_AFTER_S = 40.0
POLL_S = 0.5
# Opening a case with a deadline (the final) is tried again after a 429 (too many open sessions), a 5xx or a
# transport error, with a growing pause, while this much of the cap is left: a case never opened has no deal.
OPEN_RETRY_STATUS = {0, 429, 500, 502, 503, 504}
OPEN_MIN_LEFT_S = 60.0
OPEN_PAUSE_S = (2.0, 15.0)  # first pause, longest pause

StrategyFactory = Callable[[], Strategy]


def play_case(
    client: ArenaClient,
    recorder: Recorder,
    case_id: str,
    new_strategy: StrategyFactory,
    data: WorldData | None = None,
    *,
    case: dict | None = None,
    deadline: Callable[[], float | None] | float | None = None,
) -> dict:
    """Play one case to its end and return its outcome (score, costs, rounds, replay link, ...)."""
    strategy = new_strategy()
    if case is not None and hasattr(strategy, "before_open"):
        # Reading and thinking before the session opens: no supplier clock runs yet.
        with recorder.metrics.timer("strategy.before_open"):
            strategy.before_open(case)
    neg = Negotiation(client, recorder, data, strategy_name=strategy.name)
    neg.deadline = deadline() if callable(deadline) else deadline
    _open(neg, case_id, case, deadline)
    if neg.ended.is_set():  # resumed a case that had already ended
        return neg.finalize()
    try:
        with recorder.metrics.timer("strategy.prepare"):
            strategy.prepare(neg)
        _negotiate(neg, strategy, deadline)
    except Exception as e:
        recorder.event("case_error", session_id=neg.session_id, case_id=case_id, error=repr(e))
        log.exception("%s: %s", case_id, e)
        if not neg.ended.is_set():  # never leave a case open: close on the best we have
            try:
                _apply(neg, strategy.conclude(neg))
            except Exception:
                log.exception("%s: could not close", case_id)
    return neg.finalize()


def _open(neg: Negotiation, case_id: str, case: dict | None, deadline) -> None:
    """Open the case; with a deadline, try again on an error that may pass. A session that did open answers
    the next try with 409 and is resumed (`Negotiation.open`), so a retry never opens a case twice."""
    pause, longest = OPEN_PAUSE_S
    while True:
        try:
            neg.open(case_id, case)
            return
        except ArenaError as e:
            cap = deadline() if callable(deadline) else deadline
            if cap is None or e.status not in OPEN_RETRY_STATUS or e.quota_used_up:
                raise
            if cap - time.time() - pause < OPEN_MIN_LEFT_S:  # too late for a negotiation: the wave is lost
                raise
            neg.recorder.event("open_retry", case_id=case_id, status=e.status, detail=str(e.detail), pause=pause)
            log.warning("%s: opening failed (%s) - trying again in %.0f s", case_id, e, pause)
            time.sleep(pause)
            pause = min(pause * 2, longest)


def _negotiate(neg: Negotiation, strategy: Strategy, deadline) -> None:
    held: dict[str, Decision] = {}

    def worker(sid: str) -> None:
        t = neg.threads[sid]
        while not neg.ended.is_set() and not neg.closing.is_set():
            # No lock: an LLM call for one thread must not hold up the others (each has its own clock).
            basis = t.version
            with neg.recorder.metrics.timer("strategy.decide"):
                decision = strategy.decide(neg, sid)
            if decision.kind == "message" and not t.live:
                decision = Decision.drop(sid, f"the thread has ended: {t.closed or t.status}")
            if decision.kind == "message" and t.arena_rounds >= _round_limit(neg):
                # our timeouts used rounds too: the arena takes no further e-mail, only an accept
                decision = Decision.hold(sid, f"round limit reached with {t.timeouts} timeout(s)")
            if decision.kind == "message":
                try:
                    # not sent if the supplier answered a timeout meanwhile: the next turn decides again
                    neg.send(sid, decision.message, decision.rationale, basis=basis)
                except ArenaError as e:
                    if e.status == 422:  # invalid message: costs nothing, but do not loop on it
                        held[sid] = Decision.hold(sid, f"invalid message: {e.detail}")
                        return
                    raise
                continue
            if decision.kind in ("accept", "walk_away"):
                if neg.closing.is_set():
                    return  # the close compares what stands at the arena now (`conclude`)
                if t.version != basis:
                    continue  # its offer changed while we decided (a timeout answer): decide on the new one
                _apply(neg, decision)
                return
            held[sid] = decision
            neg.recorder.event(
                f"thread_{decision.kind}",
                session_id=neg.session_id,
                case_id=neg.case_id,
                supplier_id=sid,
                **decision.rationale,
            )
            log.info("%s: %s (%s)", sid, decision.kind, decision.rationale.get("why"))
            return

    live = [sid for sid, t in neg.threads.items() if t.live]
    pool = ThreadPoolExecutor(max_workers=max(1, len(live)), thread_name_prefix=f"{neg.case_id}")
    try:
        futures = {sid: pool.submit(worker, sid) for sid in live}
        while not neg.ended.is_set():
            cap = deadline() if callable(deadline) else deadline
            if cap is not None:
                neg.deadline = cap
            if neg.closing_soon():
                log.warning("%s: deadline near - closing", neg.case_id)
                neg.closing.set()
                break
            running = [sid for sid, f in futures.items() if not f.done()]
            for f in futures.values():
                if f.done() and f.exception():
                    raise f.exception()
            if not running:
                break
            # keep held threads alive while others still negotiate
            for sid in list(held):
                t = neg.threads[sid]
                if held[sid].kind != "hold" or not t.live or t.seconds_since_reply() < KEEPALIVE_AFTER_S:
                    continue
                basis, message = t.version, None
                # the last round is not worth a question; nor is one answered after the close
                if t.arena_rounds < _round_limit(neg) - 1 and not neg.closing_soon(KEEPALIVE_REPLY_S):
                    message = strategy.keepalive(neg, sid)
                if message is None:
                    # only under a wave cap: practice and sandbox keep the behaviour their scores were measured with
                    if neg.deadline is not None and t.seconds_since_reply() >= CLOSE_UNKEPT_AFTER_S:
                        neg.recorder.event(
                            "close_unkept_thread",
                            session_id=neg.session_id,
                            case_id=neg.case_id,
                            supplier_id=sid,
                            seconds_since_reply=round(t.seconds_since_reply(), 1),
                        )
                        log.warning("%s: held without a keepalive - closing before its clock runs out", sid)
                        neg.closing.set()
                        break
                    continue
                neg.recorder.metrics.incr("moves.keepalive")
                neg.send(sid, message, {"why": "keepalive while other threads negotiate"}, basis=basis)
            if neg.closing.is_set():
                break
            time.sleep(POLL_S)
    finally:
        # Closing by the clock does not wait for the workers: a decision still being made (an LLM call) is
        # dropped, and an e-mail waiting for the turn is not sent (`Negotiation.send`) - the closing move goes
        # first. Only an e-mail already at the arena is waited for, by the turn.
        closing_early = neg.closing.is_set()
        neg.closing.set()
        pool.shutdown(wait=not closing_early, cancel_futures=True)
    if not neg.ended.is_set() and len(neg.threads) > 1:
        neg.sync()  # the closing move compares the suppliers: on what stands at the arena now
    if not neg.ended.is_set():
        with neg.recorder.metrics.timer("strategy.conclude"):
            decision = strategy.conclude(neg)
        _apply(neg, decision)


def _round_limit(neg: Negotiation) -> int:
    return neg.case.get("round_limit") or 10


def _apply(neg: Negotiation, decision: Decision) -> None:
    if decision.kind == "accept":
        log.info("%s: accept %s %s", neg.case_id, decision.supplier_id, decision.term_sheet_id)
        try:
            neg.accept(decision.supplier_id, decision.term_sheet_id, decision.rationale)
        except GuardRefused as e:  # never close on a sheet that scores 0: the alternative is safer
            log.error("%s: accept refused (%s) - walking away", neg.case_id, e)
            neg.walk_away(decision.supplier_id, {**decision.rationale, "why": f"accept refused: {e}"})
    else:
        log.info("%s: walk away (%s)", neg.case_id, decision.rationale.get("why"))
        neg.walk_away(decision.supplier_id, decision.rationale)


def play_many(
    client: ArenaClient,
    recorder: Recorder,
    case_ids: list[str],
    new_strategy: StrategyFactory,
    data: WorldData | None = None,
    *,
    parallel: int = 4,
    cases: dict[str, dict] | None = None,
) -> list[dict]:
    """Many cases at once (at most 10 open sessions per key). Stops starting cases once the practice
    quota is used up. Returns one outcome per case (or an error entry)."""
    used_up = threading.Event()

    def one(case_id: str) -> dict:
        if used_up.is_set():
            return {"case_id": case_id, "error": "not started: practice quota used up"}
        try:
            return play_case(client, recorder, case_id, new_strategy, data, case=(cases or {}).get(case_id))
        except ArenaError as e:
            if e.quota_used_up:
                used_up.set()
            log.error("%s: %s", case_id, e)
            recorder.event("case_failed", case_id=case_id, status=e.status, detail=e.detail)
            return {"case_id": case_id, "error": str(e)}
        except Exception as e:
            log.exception("%s failed", case_id)
            recorder.event("case_failed", case_id=case_id, error=repr(e))
            return {"case_id": case_id, "error": repr(e)}

    with ThreadPoolExecutor(max_workers=max(1, min(parallel, 10)), thread_name_prefix="case") as pool:
        return list(pool.map(one, case_ids))


def play_final(
    client: ArenaClient,
    recorder: Recorder,
    new_strategy: StrategyFactory,
    data: WorldData | None = None,
    *,
    waves: int = 5,
    parallel: int = 10,
    poll: float = 3.0,
) -> list[dict]:
    """The Live Final: poll the case list, play every case of each started wave in parallel within its
    cap, until `waves` waves have closed. Reads only our own cases and sessions."""
    if not client.settings.final_mode:
        raise RuntimeError("set NEGOTIATOR_FINAL=1: final mode blocks the live feed for the agent")
    started: dict[str, object] = {}
    closed: set[int] = set()
    caps: dict[int, float] = {}
    with ThreadPoolExecutor(max_workers=parallel, thread_name_prefix="final") as pool:
        while len(closed) < waves or not all(f.done() for f in started.values()):
            try:
                cases = client.cases("final")
            except Exception as e:
                if not (isinstance(e, ArenaError) and e.status == 403):  # 403: no wave yet
                    # 5xx, transport error, ...: the poll loop must never die - a case it misses has no deal
                    _poll_failed(recorder, e)
                    time.sleep(poll)
                    continue
                cases = []
            for case in cases:
                wave = case.get("wave")
                if not case.get("open"):
                    closed.add(wave)
                    continue
                if case.get("seconds_left") is not None:
                    caps[wave] = time.time() + case["seconds_left"]
                if case["case_id"] not in started and case.get("seconds_left"):
                    if wave not in {c.get("wave") for c in cases if c["case_id"] in started}:
                        recorder.event(
                            "wave_started",
                            wave=wave,
                            theme=case.get("theme"),
                            seconds_left=case.get("seconds_left"),
                        )
                        log.warning("wave %s started: %s", wave, case.get("theme"))
                    started[case["case_id"]] = pool.submit(
                        play_case,
                        client,
                        recorder,
                        case["case_id"],
                        new_strategy,
                        data,
                        case=case,
                        deadline=lambda w=wave: caps.get(w),
                    )
            time.sleep(poll)
    out = []
    for case_id, future in started.items():
        try:
            out.append(future.result())
        except Exception as e:
            out.append({"case_id": case_id, "error": repr(e)})
    return out


def _poll_failed(recorder: Recorder, error: Exception) -> None:
    """A failed read of the final's case list (5xx, transport error): logged, and polled again."""
    status = error.status if isinstance(error, ArenaError) else None
    recorder.event("final_poll_failed", status=status, error=repr(error))
    log.warning("final: reading the case list failed (%s) - polling again", error)
