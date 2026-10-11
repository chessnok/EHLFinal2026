"""The round's choice by expected cost (tactical/choice.py): the response model, the belief, and end to end."""

import json

from test_tactical import _reply, case, negotiation

from negotiator.client import ArenaClient
from negotiator.config import Settings
from negotiator.data import WorldData
from negotiator.report import write_report
from negotiator.runner import play_many
from negotiator.strategy import STRATEGIES
from negotiator.strategy.tactical import ExpectedValueStrategy
from negotiator.strategy.tactical.choice import (
    AFTER_FINAL_WALKS,
    RESPONSE,
    STEPS,
    best_step,
    gives,
    played,
    probe_pays,
    stops,
)
from negotiator.telemetry import Recorder


def test_a_crumb_buys_less_than_a_real_step() -> None:
    assert gives(0.01) < gives(0.05) < gives(0.15) < gives(0.25) == gives(0.60)
    assert [g for _, g in RESPONSE] == sorted(g for _, g in RESPONSE)


def test_the_belief_stays_between_our_first_ask_and_its_offer() -> None:
    belief = stops(stop_c=95.0, their_c=100.0, target_c=80.0, replies=1)
    assert all(80.0 <= stop <= 100.0 for stop, _ in belief) and abs(sum(w for _, w in belief) - 1) < 1e-9
    early, late = stops(95.0, 100.0, 80.0, 0), stops(95.0, 100.0, 80.0, 3)
    assert max(s for s, _ in late) - min(s for s, _ in late) < max(s for s, _ in early) - min(s for s, _ in early)
    assert all(80.0 <= stop <= 100.0 for stop, _ in stops(float("inf"), 100.0, 80.0, 0))  # no estimate yet


def test_with_room_the_smallest_step_that_moves_it_wins() -> None:
    belief = stops(90.0, 100.0, 80.0, 1)
    step, expected = best_step(100.0, 80.0, belief, reply=1, rounds=6)
    assert 0.10 <= step <= 0.40  # enough of its room to get its full step; more only gives our ask away
    assert expected[step] < expected[0.02] and expected[step] < expected[0.60] and set(expected) == set(STEPS)


def test_no_room_or_no_round_left_takes_its_offer() -> None:
    assert best_step(100.0, 80.0, [(100.0, 1.0)], reply=2, rounds=5)[0] is None  # it stands at its stop
    assert best_step(100.0, 80.0, stops(90.0, 100.0, 80.0, 1), reply=2, rounds=0)[0] is None


def test_a_pending_step_is_not_paid_for() -> None:
    step, _ = best_step(100.0, 80.0, stops(90.0, 100.0, 80.0, 1), reply=1, rounds=6, pending=True)
    assert step == min(STEPS)  # the rest of its step comes whatever we send


def test_an_ask_that_reaches_its_next_offer_is_taken_at_our_ask() -> None:
    # our ask of 92 stays under its next offer of 96.9, which it calls final; from 97 our 98.8 is above its 96.9
    assert played(100.0, 80.0, 90.0, 0.60, reply=5, rounds=1, pending=False) == 96.5  # final at its own offer
    assert played(100.0, 97.0, 90.0, 0.60, reply=0, rounds=3, pending=False) == 98.8  # it agrees to our 98.8


def test_a_last_word_is_pushed_only_next_to_a_safe_rival() -> None:
    their_c, stop = 100.0, 97.0
    assert not probe_pays(their_c, stop, walk_c=120.0)  # no rival: a walk-away loses the deal
    assert probe_pays(their_c, stop, walk_c=100.5)  # a rival half a per cent behind: little to lose
    assert AFTER_FINAL_WALKS > 0.1


def test_the_variant_takes_a_final_offer_and_asks_while_it_is_open(tmp_path, world) -> None:
    neg, sid = negotiation(tmp_path, world, case(), {"unit_price": 17.47, "payment_days": 30})
    strategy = ExpectedValueStrategy(world)
    strategy.prepare(neg)
    first = strategy.decide(neg, sid)
    assert first.kind == "message"
    neg.threads[sid].messages.append({"from": "buyer", **first.message})
    neg.threads[sid].messages.append(
        {
            "from": f"sales@{sid}",
            "status": "open",
            "body": "",
            "term_sheets": [{"term_sheet_id": "offer:x-1", "terms": {"unit_price": 17.0, "payment_days": 30}}],
            "attachments": neg.threads[sid].messages[0]["attachments"],
        }
    )
    second = strategy.decide(neg, sid)
    plan = strategy.tplans[sid]
    assert second.kind == "message" and plan.our_c[-1] > plan.our_c[-2]  # a step, never back
    assert plan.our_c[-1] < neg.cost(sid, {"unit_price": 17.0, "payment_days": 30})
    _reply(neg, sid, [{"unit_price": 16.9, "payment_days": 30}], status="final_offer")
    held = strategy.decide(neg, sid)
    assert held.kind == "hold" and "last word" in held.rationale["why"]


def test_the_variant_closes_every_sim_case(sim: Settings, world: WorldData) -> None:
    recorder = Recorder(sim.runs_dir, "pytest-tactical-ev")
    client = ArenaClient(sim, recorder)
    case_ids = [c["case_id"] for c in client.cases("practice")]
    outcomes = play_many(client, recorder, case_ids, lambda: STRATEGIES["tactical-ev"](world, None), world, parallel=3)
    recorder.close()
    summary = write_report(recorder.dir, outcomes)
    assert summary["cases"] == len(case_ids) and not summary["failed"], summary["failed"]
    assert all(o["deal"] and o["score"] and o["score"] > 0 for o in summary["outcomes"]), [
        (o["case_id"], o["deal"], o["end_reason"], o["score"]) for o in summary["outcomes"]
    ]
    kinds = [json.loads(line).get("kind") for line in (recorder.dir / "events.jsonl").read_text().splitlines()]
    assert "choice" in kinds
    assert recorder.metrics.snapshot()["timings"]["strategy.decide"]["max"] < 2.0
