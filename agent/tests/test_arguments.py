"""Arguments the arena still counts: its reading of our e-mails, fresh arguments per round (`fresh_args`)."""

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


def test_bundle_orders_are_one_argument_per_part(world: WorldData) -> None:
    rows = world.query(
        "SELECT supplier_id, part_id FROM po_lines GROUP BY supplier_id, part_id HAVING count(*) >= 3 "
        "AND count(DISTINCT price) = 1"
    )
    by_supplier: dict[str, list[str]] = {}
    for r in rows:
        by_supplier.setdefault(r["supplier_id"], []).append(r["part_id"])
    sid, parts = next((s, p) for s, p in by_supplier.items() if len(p) >= 2)
    out = world.evidence_orders_per_part(parts[:2], sid)
    assert len(out) == 2 and {e.meta["part"] for e in out} == set(parts[:2])
    assert {argument_key(e.refs[0], world.facts) for e in out} == {("orders", p) for p in parts[:2]}
    assert world.evidence_orders_per_part(parts[:1], sid) == []  # one part: `evidence_orders` does it


# ---------------------------------------------------------------- choosing fresh arguments
def _ev(kind: str, refs: list[str], strength: float) -> Evidence:
    return Evidence(kind=kind, refs=refs, sentence=f"{kind} {' '.join(refs)}", strength=strength)


def _setup(tmp_path: Path, world: WorldData, **flags):
    neg, sid = negotiation(tmp_path, world, case(), {"unit_price": 17.47, "payment_days": 30})
    strategy = TacticalStrategy(world, **flags)
    strategy.prepare(neg)
    plan = strategy.tplans[sid]
    plan.counters, plan.banned_kinds = [], set()
    plan.evidence = [
        _ev("index", ["idx:TA@2025-08", "idx:TA@2026-08"], 5.0),
        _ev("quote", ["quote:TQ"], 4.0),
        _ev("forecast", ["fc:T1@2026-09"], 3.0),
        _ev("recent_drop", ["idx:TA@2026-02", "idx:TA@2026-05"], 2.0),  # a second window of the same series
    ]
    return neg, sid, strategy, plan


def test_first_email_keeps_one_argument_back(tmp_path, world) -> None:
    neg, sid, strategy, plan = _setup(tmp_path, world, fresh_args=True)
    picked = strategy._choose_claims(neg, sid, plan, first=True)
    # three counted arguments (TA, the quote, the forecast): two now, one for round 2; never TA twice
    assert [e.kind for e in picked] == ["index", "quote"]
    neg2, sid2, old, plan2 = _setup(tmp_path / "old", world)
    assert [e.kind for e in old._choose_claims(neg2, sid2, plan2, first=True)] == ["index", "quote", "forecast"]


def test_later_rounds_skip_what_the_arena_counted(tmp_path, world) -> None:
    neg, sid, strategy, plan = _setup(tmp_path, world, fresh_args=True)
    t = neg.threads[sid]
    t.messages.append({"from": "buyer", "body": "Our forecast rose 5% (fc:T0@2026-09).", "refs": ["fc:T0@2026-09"]})
    t.messages.append({"from": f"sales@{sid}", "status": "open", "term_sheets": t.messages[0]["term_sheets"]})
    plan.evidence = [e for e in plan.evidence if e.kind != "index"]  # TA's first window went out in round 1 ...
    t.messages[1]["body"] += "\nTA changed -3% (idx:TA@2025-08, idx:TA@2026-08)."
    picked = strategy._choose_claims(neg, sid, plan, first=False)
    # ... so neither its second window nor a second forecast (another part's) is fresh: the quote is
    assert [e.kind for e in picked] == ["quote"]
    picked = strategy._choose_claims(neg, sid, plan, first=False)
    assert picked == []  # nothing fresh left: no duplicate instead


def test_a_duplicate_spends_the_kind(tmp_path, world) -> None:
    neg, sid, strategy, plan = _setup(tmp_path, world, fresh_args=True)
    t = neg.threads[sid]
    body = "TA changed -3% (idx:TA@2025-08, idx:TA@2026-08).\nOrders (po:T1-10, po:T2-10)."
    t.messages.append({"from": "buyer", "body": body, "refs": []})
    reply = {
        "from": f"sales@{sid}",
        "status": "open",
        "term_sheets": t.messages[0]["term_sheets"],
        "claim_results": [{"index": 0, "result": "duplicate"}, {"index": 1, "result": "duplicate"}],
    }
    t.messages.append(reply)
    strategy._learn_claims(t, plan, reply)
    # orders of another part would be counted again; an index series is counted by series, not by kind
    assert plan.spent_kinds == {"orders"}
