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
