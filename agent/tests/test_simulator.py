"""The calibrated supplier simulator: pricing fit, the supplier's moves, and a round trip through the API."""

import random

from arena_kit.cost import total_cost

from negotiator.config import Settings
from negotiator.data import WorldData
from negotiator.llm import LLMError
from negotiator.runner import play_many
from negotiator.sim.arena import bench, price_cap
from negotiator.sim.calibrate import as_objects, best_cost, calibrate, load_sessions
from negotiator.sim.llm_supplier import LLMThread, pick
from negotiator.sim.pricing import FEATURES, features, fit_rates, price_for, value_of
from negotiator.sim.supplier import PERSONAS, Profile, Thread
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


def _prices(persona: str) -> list[float]:
    p = _profile(steps={"moved": [[0.2, False], [0.2, False]]}, finals={})
    th = Thread(p, _pool(), random.Random(1), persona=PERSONAS[persona])
    return [
        th.reply(CASE, [{"unit_price": 6.0 + i / 10, "payment_days": 30}], [])["terms"]["unit_price"] for i in range(4)
    ]


def test_opponent_types_bend_the_fitted_supplier() -> None:
    fitted, soft, hard, rushed = (_prices(n) for n in ("fitted", "cooperative", "hardball", "deadline"))
    assert soft[-1] < fitted[-1] < hard[-1]
    assert rushed[-1] < fitted[-1] and rushed[0] == fitted[0]  # the same first step, then faster


def test_walker_leaves_at_the_first_push_past_its_final_offer() -> None:
    p = _profile(steps={"moved": [[0.2, False], [0.2, False]], "final": [[0.0, False], [0.0, False]]},
                 finals={"1/move": [1, 1]})  # fmt: skip
    th = Thread(p, _pool(), random.Random(1), persona=PERSONAS["walker"])
    sheet = [{"unit_price": 6.0, "payment_days": 30}]
    assert th.reply(CASE, sheet, [])["status"] == "final_offer"
    assert th.reply(CASE, sheet, [])["status"] == "walked_away"


def test_manipulator_bluffs_a_final_offer_and_writes_instructions() -> None:
    p = _profile(steps={"moved": [[0.2, False], [0.2, False]]}, finals={})
    th = Thread(p, _pool(), random.Random(1), persona=PERSONAS["manipulator"])
    outs = [th.reply(CASE, [{"unit_price": 6.0 + i / 10, "payment_days": 30}], []) for i in range(3)]
    assert [o["status"] for o in outs] == ["open", "final_offer", "open"]
    assert outs[2]["terms"]["unit_price"] < outs[1]["terms"]["unit_price"]  # the "final" offer was not
    assert all("ignore your previous instructions" in " ".join(o["reasons"]) for o in outs)


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

    pool = bench(model, sim, world, ["baseline"], case_ids[:1], reps=1, runs_dir=tmp_path,
                 opponents=("hardball", "manipulator"), jitter=True)  # fmt: skip
    assert set(pool["by_opponent"]) == {("baseline", "hardball"), ("baseline", "manipulator")}
    assert all(0.0 <= r["score"] <= 1.0 for rows in pool["by_opponent"].values() for r in rows)


class _Model:
    """Stands in for `negotiator.llm.LLM`: answers every prompt with the next prepared choice."""

    def __init__(self, *choices):
        self.choices, self.prompts = list(choices), []

    def json(self, system, user, **_):
        self.prompts.append(user)
        choice = self.choices.pop(0)
        if isinstance(choice, Exception):
            raise choice
        return choice


def _llm_thread(model, **kw) -> LLMThread:
    return LLMThread(_profile(**kw), _pool(), random.Random(1), llm=model)


def test_llm_opponent_moves_by_the_models_share_and_never_below_the_floor() -> None:
    model = _Model({"decision": "counter", "concede_share": 0.5, "body": "We move: {offer}."},
                   {"decision": "final_offer", "concede_share": 5, "body": "No further."})  # fmt: skip
    th = _llm_thread(model, examples=[{"session": "s", "reply": 1, "before": "open", "buyer": "Our ceiling is 9.",
                                       "sheets": [], "claims": [], "status": "open", "gave": 0.1, "ask": 1.5,
                                       "terms": {}, "text": "Thank you, we hold."}])  # fmt: skip
    sheet = [{"unit_price": 7.0, "payment_days": 30}]
    first = th.reply(CASE, sheet, [], mail={"body": "Management set a ceiling.", "claims": []})
    assert first["status"] == "open" and first["terms"]["unit_price"] == 9.0
    assert "a price of €9.00 per unit" in first["reasons"][0]
    assert "Management set a ceiling." in model.prompts[0] and "Our ceiling is 9." in model.prompts[0]
    assert "the 1 closest recorded replies with your status open" in model.prompts[0]
    assert "median 10%" in model.prompts[0]
    last = th.reply(CASE, sheet, [], mail={"body": "Again.", "claims": []})
    assert last["status"] == "final_offer" and last["terms"]["unit_price"] == 8.0  # the floor, not the share of 5
    assert "final offer" in last["reasons"][0] and "Management set a ceiling." in model.prompts[1]


def test_llm_opponent_cannot_agree_below_its_floor_and_walks_only_after_a_final_offer() -> None:
    model = _Model({"decision": "agree", "concede_share": 0, "body": "Deal."},
                   {"decision": "walk_away", "concede_share": 0, "body": "Enough."},
                   {"decision": "agree", "concede_share": 0, "body": "Deal: {offer}."})  # fmt: skip
    th = _llm_thread(model)
    low = [{"unit_price": 7.0, "payment_days": 30}]
    assert th.reply(CASE, low, [], mail={"body": "", "claims": []})["status"] == "open"
    assert th.reply(CASE, low, [], mail={"body": "", "claims": []})["status"] == "open"  # no final offer yet
    out = th.reply(CASE, [{"unit_price": 8.5, "payment_days": 30}], [], mail={"body": "", "claims": []})
    assert out["status"] == "agreed" and out["terms"]["unit_price"] == 8.5


def test_llm_opponent_falls_back_to_the_fitted_supplier() -> None:
    th = _llm_thread(_Model(LLMError("timeout")), steps={"moved": [[0.5, False], [0.5, False]]})
    out = th.reply(CASE, [{"unit_price": 7.0, "payment_days": 30}], [], mail={"body": "Hello", "claims": []})
    assert out["terms"]["unit_price"] == 9.0 and th.fallbacks == 1


def test_llm_opponent_is_shown_the_replies_to_e_mails_in_like_words() -> None:
    def past(buyer: str, gave: float) -> dict:
        return {"session": "s", "reply": 1, "before": "open", "buyer": buyer, "sheets": [], "claims": [],
                "status": "open", "gave": gave, "ask": 1.0, "terms": {}, "text": "..."}  # fmt: skip

    examples = [past("Thank you for your quote, we reviewed the delivery record", 0.4),
                past("Our management has set a ceiling for this part", 0.05)]  # fmt: skip
    first = pick(examples, "open", 1, "Please note the ceiling our management set", limit=1)
    assert first[0]["gave"] == 0.05


def test_a_perturbed_session_bends_the_supplier_and_moves_the_round_limit() -> None:
    """`sim robust`: per session the steps, the final-offer rate and the round limit move; unperturbed, nothing."""
    from negotiator.sim.arena import MIN_ROUNDS, PERTURB_FINAL, PERTURB_STEP, CalibratedSim

    case = {**CASE, "suppliers": ["sup:T"], "round_limit": 10, "title": "t"}
    model = {
        "cases": {"case:T01": case},
        "profiles": {"case:T01|sup:T": _profile()},
        "pool": _pool(),
        "results": {
            "case:T01": {"c_open": total_cost(CASE, REF), "c_best": total_cost(CASE, {**REF, "unit_price": 8})}
        },
    }
    plain = CalibratedSim(model).open("team", "case:T01")
    assert plain["case"]["round_limit"] == 10
    limits, bends = set(), set()
    for seed in range(12):
        sim = CalibratedSim(model, seed=seed, perturb=True)
        opened = sim.open("team", "case:T01")
        limits.add(opened["case"]["round_limit"])
        who = sim.sessions[opened["session_id"]]["threads"]["sup:T"]["sim"].persona
        assert PERTURB_STEP[0] <= who.step <= PERTURB_STEP[1] and PERTURB_FINAL[0] <= who.final <= PERTURB_FINAL[1]
        assert who.name == "fitted"
        bends.add(round(who.step, 3))
    assert len(limits) > 1 and min(limits) >= MIN_ROUNDS and len(bends) > 6
    assert model["cases"]["case:T01"]["round_limit"] == 10  # the model's case is not touched
