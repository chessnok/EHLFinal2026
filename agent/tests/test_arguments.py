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


# ---------------------------------------------------------------- index falls over any valid window (`all_windows`)
def _drivers(world: WorldData) -> list[str]:
    return [r["series_id"] for r in world.query("SELECT DISTINCT series_id FROM cost_drivers")]


def test_steepest_drop_keeps_the_arenas_window_rule(world) -> None:
    from negotiator.ledger import MAX_AGE, MAX_SPAN, MIN_DROP, _month_no, recent_drop, steepest_drop

    last = _month_no(world.query("SELECT max(month) AS m FROM index_values")[0]["m"])
    found = 0
    for series in _drivers(world):
        drop = steepest_drop(world, series)
        if not drop:
            continue
        found += 1
        earlier, later, pct, months = drop
        m0, m1 = _month_no(earlier.split("@")[1]), _month_no(later.split("@")[1])
        assert 1 <= m1 - m0 <= MAX_SPAN and m1 >= last - MAX_AGE and pct <= -MIN_DROP and months == m1 - m0
        assert world.fact(earlier) and world.fact(later)
        recent = recent_drop(world, series)
        assert not recent or pct <= recent[2] + 1e-9  # never shallower than the window ending at the latest month
    assert found


def test_all_windows_finds_falls_that_have_risen_since(world) -> None:
    from negotiator.ledger import _drop_evidence, recent_drop, steepest_drop

    series = next(s for s in _drivers(world) if not recent_drop(world, s) and steepest_drop(world, s))
    assert _drop_evidence(world, series, 0.3, cited=False) is None
    e = _drop_evidence(world, series, 0.3, cited=False, all_windows=True)
    assert e and " from " in e.sentence and "over the last" not in e.sentence


def test_all_windows_gives_one_fall_per_series(world) -> None:
    from negotiator.ledger import data_facts

    shared = world.query(
        "SELECT series_id, group_concat(part_id) AS parts FROM cost_drivers GROUP BY series_id HAVING count(*) >= 2"
    )
    parts = sorted({p for r in shared for p in r["parts"].split(",")})[:20]
    facts = data_facts(world, parts, all_windows=True)
    series = [e.meta["series"] for e in facts]
    assert len(series) == len(set(series))


def test_all_windows_cites_a_series_once_per_supplier(tmp_path, world) -> None:
    neg, sid, strategy, plan = _setup(tmp_path, world, all_windows=True)
    t = neg.threads[sid]
    t.messages.append({"from": "buyer", "body": "TA fell 3% (idx:TA@2025-01, idx:TA@2025-07).", "refs": []})
    t.messages.append({"from": f"sales@{sid}", "status": "open", "term_sheets": t.messages[0]["term_sheets"]})
    picked = strategy._choose_claims(neg, sid, plan, first=False)
    assert all("idx:TA" not in r for e in picked for r in e.refs)  # another window of TA is a duplicate


# ---------------------------------------------------------------- its cheaper alternative sheet (`cheap_alt`)
def _with_alternative(tmp_path: Path, world: WorldData, alternative: dict, **flags):
    neg, sid = negotiation(tmp_path, world, case(), {"unit_price": 17.0, "payment_days": 14})
    strategy = TacticalStrategy(world, **flags)
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


def test_cheap_alt_takes_an_alternative_under_the_old_bar(tmp_path, world) -> None:
    alternative = {"unit_price": 16.98, "payment_days": 14}
    neg, sid, old, plan = _with_alternative(tmp_path / "old", world, alternative)
    saving = neg.cost(sid, {"unit_price": 17.0, "payment_days": 14}) - neg.cost(sid, alternative)
    assert 0 < saving < 0.002 * neg.cost(sid, alternative)  # under 0.2 % of C: the old rule passes it over
    assert old._take_alternative(neg, sid, plan) is None
    neg, sid, new, plan = _with_alternative(tmp_path / "new", world, alternative, cheap_alt=True)
    assert saving > new._alt_margin(neg, plan, neg.cost(sid, alternative))
    taken = new._take_alternative(neg, sid, plan)
    assert taken and taken.message["term_sheets"][0]["terms"]["unit_price"] == 16.98


def test_cheap_alt_needs_the_completed_sheet_to_be_cheaper(tmp_path, world) -> None:
    # without payment terms the alternative closes on the standard 30 days and looks cheaper; the sheet we would
    # send for it takes the primary's 14 days and is the primary offer again
    neg, sid, strategy, plan = _with_alternative(tmp_path, world, {"unit_price": 17.0}, cheap_alt=True)
    assert neg.cost(sid, {"unit_price": 17.0}) < neg.cost(sid, {"unit_price": 17.0, "payment_days": 14}) - 100
    assert strategy._take_alternative(neg, sid, plan) is None
