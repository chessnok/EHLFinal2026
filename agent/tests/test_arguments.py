"""The arena's reading of our e-mails (the ledger), and the supplier's cheaper alternative sheet."""

from pathlib import Path

from test_tactical import case, negotiation

from negotiator.data import Evidence, WorldData
from negotiator.ledger import argument_key, arguments_read
from negotiator.strategy import TacticalStrategy


# ---------------------------------------------------------------- the arena's reading of one e-mail
def test_arguments_read_merges_one_kind_and_orders_by_kind() -> None:
    body = (
        "Your on-time delivery was 63.5% (sc:1@2026Q3).\n"
        "Your quality was 2376 ppm (sc:1@2026Q3).\n"
        "Our last orders were at EUR 45.15 (po:1-10, po:2-10).\n"
        "X changed -6.1% (idx:X@2025-08, idx:X@2026-08).\n"
        "X fell 6.1% (idx:X@2025-11, idx:X@2026-08).\n"
    )
    read = arguments_read(body, ["po:1-10", "po:2-10"])
    # index first, then the record, then the orders - the two scorecard lines and the two windows are one each
    assert [k for k, _ in read] == [("index", "X"), ("record",), ("orders", "po:1-10")]
    assert read[0][1] == {"idx:X@2025-08", "idx:X@2025-11", "idx:X@2026-08"}


def test_arguments_read_reads_three_and_ids_only_in_refs() -> None:
    body = "A (idx:A@2026-01, idx:A@2026-03).\nB (idx:B@2026-01, idx:B@2026-03).\nC (cost:1)."
    read = arguments_read(body, ["fc:1@2026-09", "quote:9"])
    assert [k for k, _ in read] == [("index", "A"), ("index", "B"), ("rival", "quote:9")]


def test_argument_key_counts_orders_per_part_and_a_forecast_per_kind(world: WorldData) -> None:
    po = next(r for r in world.facts if r.startswith("po:"))
    assert argument_key(po, world.facts) == ("orders", world.facts[po]["part"])
    assert argument_key("fc:1@2026-09") == argument_key("fc:2@2026-09") == ("forecast",)
    assert argument_key("qn:1") == argument_key("sc:1@2026Q3") == ("record",)


def test_a_contract_clause_without_a_letter_is_not_read() -> None:
    assert arguments_read("The contract says 90 days (ctr:7#3.2).", []) == []
    read = arguments_read("Your letter gives 30 days (doc:1-M2) against 90 (ctr:7#3.2).", [])
    assert [k for k, _ in read] == [("notice",)]


# ---------------------------------------------------------------- its cheaper alternative sheet
def _with_alternative(tmp_path: Path, world: WorldData, alternative: dict):
    neg, sid = negotiation(tmp_path, world, case(), {"unit_price": 17.0, "payment_days": 14})
    strategy = TacticalStrategy(world)
    strategy.prepare(neg)
    neg.threads[sid].messages.append(
        {
            "from": f"sales@{sid}",
            "status": "final_offer",
            "term_sheets": [
                {"term_sheet_id": "offer:x-1", "terms": {"unit_price": 17.0, "payment_days": 14}},
                {"term_sheet_id": "offer:x-1b", "terms": alternative},
            ],
        }
    )
    return neg, sid, strategy, strategy.tplans[sid]


def test_an_alternative_under_the_old_bar_is_taken(tmp_path, world) -> None:
    alternative = {"unit_price": 16.98, "payment_days": 14}
    neg, sid, new, plan = _with_alternative(tmp_path, world, alternative)
    saving = neg.cost(sid, {"unit_price": 17.0, "payment_days": 14}) - neg.cost(sid, alternative)
    assert 0 < saving < 0.002 * neg.cost(sid, alternative)  # under 0.2 % of C: the old rule passed it over
    assert saving > new._alt_margin(neg, plan, neg.cost(sid, alternative))
    taken = new._take_alternative(neg, sid, plan)
    assert taken and taken.message["term_sheets"][0]["terms"]["unit_price"] == 16.98


def test_an_alternative_needs_the_completed_sheet_to_be_cheaper(tmp_path, world) -> None:
    # without payment terms the alternative closes on the standard 30 days and looks cheaper; the sheet we would
    # send for it takes the primary's 14 days and is the primary offer again
    neg, sid, strategy, plan = _with_alternative(tmp_path, world, {"unit_price": 17.0})
    assert neg.cost(sid, {"unit_price": 17.0}) < neg.cost(sid, {"unit_price": 17.0, "payment_days": 14}) - 100
    assert strategy._take_alternative(neg, sid, plan) is None


def test_claim_results_are_matched_the_way_the_arena_reads_our_email(tmp_path, world) -> None:
    """The arena's `index` counts its arguments, not our sentences: an irrelevant second argument bans its kind."""
    neg, sid = negotiation(tmp_path, world, case(), {"unit_price": 17.47, "payment_days": 30})
    strategy = TacticalStrategy(world)
    strategy.prepare(neg)
    plan, t = strategy.tplans[sid], neg.threads[sid]
    plan.last_claims = [
        Evidence(kind="index", refs=["idx:TA@2025-08", "idx:TA@2026-08"], sentence="TA fell."),
        Evidence(kind="forecast", refs=["fc:T1@2026-09"], sentence="Forecast."),
    ]
    body = "TA changed -3% (idx:TA@2025-08, idx:TA@2026-08).\nOur forecast rose 5% (fc:T1@2026-09)."
    t.messages.append({"from": "buyer", "body": body, "refs": []})
    read = arguments_read(body, [], world.facts)
    reply = {
        "from": f"sales@{sid}",
        "status": "open",
        "term_sheets": t.messages[0]["term_sheets"],
        "claim_results": [
            {"index": next(i for i, (k, _) in enumerate(read) if k == ("forecast",)), "result": "irrelevant"}
        ],
    }
    t.messages.append(reply)
    strategy._learn_claims(t, plan, reply)
    assert plan.banned_kinds >= {"forecast"} and "index" not in plan.banned_kinds
