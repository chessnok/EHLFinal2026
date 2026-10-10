"""Play cases: one case (threads in parallel), many cases in parallel, or the Live Final in waves.

Every supplier thread has its own 60 s clock from its last reply, so each live thread gets its own
worker. A thread the strategy holds (agreed, final offer, ...) keeps ticking while the others still
negotiate: the coordinator sends the strategy's keepalive before the clock runs out, and closes the
case with `strategy.conclude` once every thread is held or dropped - or when the deadline is near.
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
CLOSE_BEFORE_DEADLINE_S = 90.0
POLL_S = 0.5

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
    neg.open(case_id, case)
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


def _negotiate(neg: Negotiation, strategy: Strategy, deadline) -> None:
    held: dict[str, Decision] = {}
    stop = threading.Event()

    def worker(sid: str) -> None:
        while not neg.ended.is_set() and not stop.is_set():
            # No lock: an LLM call for one thread must not hold up the others (each has its own clock).
            with neg.recorder.metrics.timer("strategy.decide"):
                decision = strategy.decide(neg, sid)
            if decision.kind == "message":
                try:
                    neg.send(sid, decision.message, decision.rationale)
                except ArenaError as e:
                    if e.status == 422:  # invalid message: costs nothing, but do not loop on it
                        held[sid] = Decision.hold(sid, f"invalid message: {e.detail}")
                        return
                    raise
                continue
            if decision.kind in ("accept", "walk_away"):
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
    with ThreadPoolExecutor(max_workers=max(1, len(live)), thread_name_prefix=f"{neg.case_id}") as pool:
        futures = {sid: pool.submit(worker, sid) for sid in live}
        while not neg.ended.is_set():
            cap = deadline() if callable(deadline) else deadline
            if cap is not None:
                neg.deadline = cap
            if neg.seconds_to_deadline() < CLOSE_BEFORE_DEADLINE_S:
                log.warning("%s: deadline near - closing", neg.case_id)
                stop.set()
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
                message = strategy.keepalive(neg, sid)
                if message is None:
                    continue
                neg.recorder.metrics.incr("moves.keepalive")
                neg.send(sid, message, {"why": "keepalive while other threads negotiate"})
            time.sleep(POLL_S)
        stop.set()
    if not neg.ended.is_set():
        with neg.recorder.metrics.timer("strategy.conclude"):
            decision = strategy.conclude(neg)
        _apply(neg, decision)


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
            except ArenaError as e:
                if e.status != 403:  # 403: no wave yet
                    raise
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
