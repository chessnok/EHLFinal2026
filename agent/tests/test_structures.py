"""Flags around the supplier's own sheets: no push after a final offer, its own cheap structures, fast payment."""

import json
from pathlib import Path

from negotiator.config import REPO_ROOT
from negotiator.data import WorldData
from negotiator.session import Negotiation, ThreadState
from negotiator.strategy import TacticalStrategy
from negotiator.telemetry import Recorder

SIM_CASES = REPO_ROOT / "negotiation-arena-kit" / "starter-kit" / "arena_kit" / "sim_cases"


def rfq(**buyer_overrides) -> dict:
    c = json.loads((SIM_CASES / "S02.json").read_text(encoding="utf-8"))
    c["buyer"].update(buyer_overrides)
    return c


def opened(tmp_path: Path, world: WorldData | None, c: dict, offers: dict[str, list[dict]]) -> Negotiation:
    """A negotiation whose suppliers each sent one message with these sheets (primary first)."""
    neg = Negotiation(None, Recorder(tmp_path), world)  # type: ignore[arg-type]
    neg.case, neg.case_id, neg.session_id = c, c["case_id"], "s1"
    for sid, sheets in offers.items():
        t = ThreadState(sid)
        t.messages.append(reply(sid, "open", sheets, n=0))
        neg.threads[sid] = t
    return neg


def reply(sid: str, status: str, sheets: list[dict], n: int, body: str = "") -> dict:
    return {
        "from": f"sales@{sid}",
        "status": status,
        "body": body,
        "term_sheets": [
            {"term_sheet_id": f"offer:{sid[4:]}-{n}{chr(97 + i)}", "terms": s} for i, s in enumerate(sheets)
        ],
    }


def answer(neg: Negotiation, strategy: TacticalStrategy, sid: str, status: str, sheets: list[dict], body: str = ""):
    """We send what the strategy decides, the supplier answers with `sheets`."""
    d = strategy.decide(neg, sid)
    assert d.kind == "message"
    t = neg.threads[sid]
    t.messages.append({"from": "buyer", **d.message})
    t.messages.append(reply(sid, status, sheets, n=len(t.messages), body=body))
    return d


# ---------------------------------------------------------------- final_safe
def _final_offer_behind_a_rival(tmp_path, world, **flags):
    """Two bidders; the dearer one calls 15.40 final while the other stands at 14.00 - the probe's case."""
    c = rfq()
    a, b = c["suppliers"]
    neg = opened(
        tmp_path,
        world,
        c,
        {
            a: [{"unit_price": 16.0, "payment_days": 60, "lead_time_days": 42}],
            b: [{"unit_price": 15.0, "payment_days": 60, "lead_time_days": 42}],
        },
    )
    strategy = TacticalStrategy(world, **flags)
    strategy.prepare(neg)
    # our estimate of where it stops sits under its final offer (P05's Hrvelec: final 33.00-33.50, upper ~30)
    strategy._update_upper = lambda *_: None
    answer(neg, strategy, b, "open", [{"unit_price": 14.0, "payment_days": 60, "lead_time_days": 42}])
    answer(neg, strategy, a, "final_offer", [{"unit_price": 15.4, "payment_days": 60, "lead_time_days": 42}])
    return neg, a, strategy


def test_without_final_safe_a_final_offer_behind_a_rival_is_probed(tmp_path, world) -> None:
    neg, sid, strategy = _final_offer_behind_a_rival(tmp_path, world)
    d = strategy.decide(neg, sid)
    assert d.kind == "message" and d.rationale["probe"]
    assert d.message["term_sheets"][0]["terms"]["unit_price"] < 15.4


def test_final_safe_never_pushes_a_final_offer(tmp_path, world) -> None:
    neg, sid, strategy = _final_offer_behind_a_rival(tmp_path, world, final_safe=True)
    d = strategy.decide(neg, sid)
    assert d.kind != "message" and not strategy.tplans[sid].probed_final


def test_final_safe_still_sends_back_its_own_cheaper_alternative(tmp_path, world) -> None:
    c = rfq()
    sid = c["suppliers"][0]
    neg = opened(
        tmp_path,
        world,
        {**c, "suppliers": [sid]},
        {sid: [{"unit_price": 16.0, "payment_days": 60, "lead_time_days": 42}]},
    )
    strategy = TacticalStrategy(world, final_safe=True)
    strategy.prepare(neg)
    alternative = {"unit_price": 15.2, "payment_days": 60, "lead_time_days": 42}
    answer(
        neg, strategy, sid, "final_offer", [{"unit_price": 15.4, "payment_days": 60, "lead_time_days": 42}, alternative]
    )
    d = strategy.decide(neg, sid)
    assert d.kind == "message" and d.rationale["move"] == "take its alternative"
    assert d.message["term_sheets"][0]["terms"]["unit_price"] == 15.2


# ---------------------------------------------------------------- own_structures
def _its_longer_lead_time(tmp_path, world, must_haves=(), **flags):
    """One supplier: 15.80 at 42 days, or 14.30 at 56 - a value we cannot sign (P05 Hrvelec: 35.00 at 35 days, 31.50
    at 52 under a 42-day must-have). 49 days, seven over our need, cost us EUR 1,400 in all, 0.04 a unit; at its
    rate it gives 0.75 for them."""
    c = rfq(must_haves=list(must_haves))
    sid = c["suppliers"][0]
    primary = {"unit_price": 16.0, "payment_days": 60, "lead_time_days": 42}
    neg = opened(tmp_path, world, {**c, "suppliers": [sid]}, {sid: [primary]})
    strategy = TacticalStrategy(world, **flags)
    strategy.prepare(neg)
    moved = {**primary, "unit_price": 15.8}  # it moves: no stall that would close the thread on its alternative
    answer(neg, strategy, sid, "open", [moved, {"unit_price": 14.3, "payment_days": 60, "lead_time_days": 56}])
    return neg, sid, strategy


def test_its_own_cheap_lead_time_joins_at_our_cost(tmp_path, world) -> None:
    from negotiator.strategy.tactical import EQUAL_C

    neg, sid, strategy = _its_longer_lead_time(tmp_path, world, own_structures=True)
    assert strategy._own_rates(neg, sid) == {"lead_time_days": (42, 56, 1.5)}
    d = strategy.decide(neg, sid)
    sheets = [sh["terms"] for sh in d.message["term_sheets"]]
    assert sheets[1]["lead_time_days"] == 49  # option B: the option nearest to its 56 days
    cost = [neg.cost(sid, t) for t in sheets]
    assert max(cost) <= min(cost) * (1 + EQUAL_C)  # every option costs us the same
    assert sheets[1]["unit_price"] < sheets[0]["unit_price"]


def test_without_own_structures_the_menu_keeps_our_lead_time(tmp_path, world) -> None:
    neg, sid, strategy = _its_longer_lead_time(tmp_path, world)
    d = strategy.decide(neg, sid)
    assert all(sh["terms"]["lead_time_days"] <= 42 for sh in d.message["term_sheets"])


def test_its_own_structure_snaps_to_what_we_may_sign(tmp_path, world) -> None:
    must = [{"field": "lead_time_days", "op": "<=", "value": 35}]
    neg, sid, strategy = _its_longer_lead_time(tmp_path, world, must_haves=must, own_structures=True)
    d = strategy.decide(neg, sid)
    sheets = [sh["terms"] for sh in d.message["term_sheets"]]
    assert all(t["lead_time_days"] <= 35 for t in sheets)
    assert 35 in {t["lead_time_days"] for t in sheets}


# ---------------------------------------------------------------- fast_pay
def _asks_for_faster_payment(tmp_path, world, payment_options):
    c = rfq()
    c["term_options"]["payment_days"] = payment_options
    a, b = c["suppliers"]
    sheet = {"unit_price": 16.0, "payment_days": 60, "lead_time_days": 42}
    neg = opened(tmp_path, world, c, {a: [sheet], b: [{**sheet, "unit_price": 15.0}]})
    strategy = TacticalStrategy(world)  # fast_pay is on by default
    strategy.prepare(neg)
    said = (
        "We see your figures, but we cannot give up margin right now. Faster payment would help us more than anything."
    )
    answer(neg, strategy, a, "open", [{**sheet, "unit_price": 15.8}], body=said)
    return neg, a, strategy


def test_fast_pay_offers_the_shortest_term_the_case_allows(tmp_path, world) -> None:
    for options, fastest in (([14, 30, 45, 60, 90], 14), ([7, 30, 60, 90], 7)):
        neg, sid, strategy = _asks_for_faster_payment(tmp_path, world, options)
        d = strategy.decide(neg, sid)
        days = [sh["terms"]["payment_days"] for sh in d.message["term_sheets"]]
        assert fastest in days, (options, days)
        assert all(day in options for day in days)


# ---------------------------------------------------------------- hide_own_cost
def test_hide_own_cost_runs_an_own_plant_supplier_on_the_guess(tmp_path, world) -> None:
    """P01's supplier has its own plant's should-cost; hidden, it gets the guess floor most strategic suppliers get."""
    c = json.loads((SIM_CASES / "S01.json").read_text(encoding="utf-8"))
    c["buyer"].update(category_goal="stabilise", sustainable_margin_pct=3, relationship_eur_per_point=5000)
    c["parts"], c["suppliers"] = ["part:310010"], ["sup:70110"]
    offer = [{"unit_price": 138.55, "payment_days": 30}]
    for hide in (False, True):
        neg = opened(tmp_path, world, c, {"sup:70110": offer})
        strategy = TacticalStrategy(world, hide_own_cost=hide)
        strategy.prepare(neg)
        plan = strategy.tplans["sup:70110"]
        if hide:
            assert plan.full_cost is None and not neg.supplier_estimates.get("sup:70110")
            assert plan.guess and plan.guess["full_cost"] > 0
        else:
            assert plan.full_cost and neg.supplier_estimates["sup:70110"] and plan.guess is None
