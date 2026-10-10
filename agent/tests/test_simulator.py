"""The calibrated supplier simulator: pricing fit, the supplier's moves, and a round trip through the API."""

import random

from arena_kit.cost import total_cost

from negotiator.config import Settings
from negotiator.data import WorldData
from negotiator.runner import play_many
from negotiator.sim.arena import bench, price_cap
from negotiator.sim.calibrate import as_objects, best_cost, calibrate, load_sessions
from negotiator.sim.pricing import FEATURES, features, fit_rates, price_for, value_of
from negotiator.sim.supplier import Profile, Thread
from negotiator.strategy import BaselineStrategy
from negotiator.telemetry import Recorder

CASE = {
    "case_id": "case:T01",
    "negotiable": ["unit_price", "payment_days"],
    "fixed_terms": {"contract_months": 24, "incoterm": "DAP"},
    "term_options": {"payment_days": [30, 60, 90]},
    "buyer": {
        "need_per_year": 1000,
        "horizon_years": 2,
        "fallback_unit_price": 12.0,
        "interest_rate": 0.08,
        "reference_payment_days": 60,
        "need_lead_time_days": 30,
        "freight_eur_per_unit": {"EXW": 0.5, "FCA": 0.3, "DAP": 0.0},
    },
}
REF = {"unit_price": 10.0, "payment_days": 30, "contract_months": 24, "incoterm": "DAP", "volume_per_year": 1000,
       "lead_time_days": 30}  # fmt: skip


def _profile(**kw) -> Profile:
    base = dict(supplier_id="sup:T", opening={"unit_price": 10.0, "payment_days": 30}, ref=REF, standard={},
                rates={"pay": 0.12}, floor=8.0, quantum=0.01)  # fmt: skip
    return Profile(**{**base, **kw})


def _pool() -> Profile:
    return _profile(supplier_id="pool", steps={}, finals={}, convinced={})


def test_fit_recovers_the_payment_rate() -> None:
    zero = dict.fromkeys(FEATURES, 0.0)
    pairs = []
    for days in (60, 90):
        x = features(CASE, {"unit_price": 1.0, "payment_days": days}, REF)
        pairs.append((zero, 10.0, x, price_for(CASE, {"pay": 0.12}, REF, 10.0, {"payment_days": days})))
    rates = fit_rates(pairs, {}, 1e-6)
    assert abs(rates["pay"] - 0.12) < 0.005
    assert rates["lead"] == 0.0  # a term no pair varies is not priced


def test_value_and_price_are_inverse() -> None:
    sheet = {"unit_price": 9.4, "payment_days": 90}
    value = value_of(CASE, {"pay": 0.12}, REF, sheet)
    assert abs(price_for(CASE, {"pay": 0.12}, REF, value, sheet) - 9.4) < 1e-9
    assert value < 9.4  # late payment is worth less to the supplier


def test_supplier_concedes_towards_its_floor_and_never_below() -> None:
    p = _profile(steps={"moved": [[0.5, False], [0.5, False]]})
    th = Thread(p, _pool(), random.Random(1))
    asks, prices = [7.0, 7.1, 7.2, 7.3, 7.4, 7.5], []
    for ask in asks:
        out = th.reply(CASE, [{"unit_price": ask, "payment_days": 30}], [])
        prices.append(out["terms"]["unit_price"])
    assert prices == sorted(prices, reverse=True) and prices[0] == 9.0
    assert min(prices) >= p.floor


def test_no_movement_no_concession() -> None:
    p = _profile(steps={"moved": [[0.5, False], [0.5, False]], "still": [[0.0, False], [0.0, False]]})
    th = Thread(p, _pool(), random.Random(1))
    sheet = [{"unit_price": 7.0, "payment_days": 30}]
    first = th.reply(CASE, sheet, [])["terms"]["unit_price"]
    assert th.reply(CASE, sheet, [])["terms"]["unit_price"] == first


def test_supplier_agrees_when_a_sheet_meets_its_price() -> None:
    p = _profile(steps={"moved": [[0.5, False], [0.5, False]]})
    th = Thread(p, _pool(), random.Random(1))
    out = th.reply(CASE, [{"unit_price": 9.2, "payment_days": 30}], [])
    assert out["status"] == "agreed" and out["terms"]["unit_price"] == 9.2


def test_no_offer_beats_the_cases_best_cost() -> None:
    c_best = total_cost(CASE, {"unit_price": 9.0, "payment_days": 30}, REF)
    p = _profile(steps={"moved": [[1.0, False], [1.0, False]]})
    th = Thread(p, _pool(), random.Random(1), cap=price_cap(CASE, REF, c_best))
    out = th.reply(CASE, [{"unit_price": 5.0, "payment_days": 30}], [])
    assert total_cost(CASE, out["terms"], REF) >= c_best - 1.0


def test_round_trip_calibrate_and_play(sim: Settings, world: WorldData, tmp_path) -> None:
    """Sessions recorded on the kit's simulator stand in for arena sessions: fit, then play the fitted one."""
    from negotiator.client import ArenaClient

    recorder = Recorder(sim.runs_dir, "pytest-record")
    client = ArenaClient(sim, recorder)
    case_ids = [c["case_id"] for c in client.cases("practice")]
    play_many(client, recorder, case_ids, lambda: BaselineStrategy(world), world, parallel=3)
    recorder.close()

    sessions = [t for t in load_sessions(sim.runs_dir) if t["_id"].startswith(recorder.dir.name)]
    assert len(sessions) == len(case_ids)
    model = as_objects(calibrate(sessions))
    for key, p in model["profiles"].items():
        case = model["cases"][key.split("|")[0]]
        assert p.floor <= p.opening_value
        assert best_cost(case, p, p.opening_value) > 0

    out = bench(model, sim, world, ["baseline"], case_ids, reps=1, runs_dir=tmp_path)
    scores = [s for v in out["scores"].values() for s in v]
    assert len(scores) == len(case_ids) and all(0.0 <= s <= 1.0 for s in scores)
