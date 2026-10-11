"""The must-haves: guards that prevent a zero, the supplier profile, the concession logic, end to end."""

import json
import time
from pathlib import Path

from negotiator.chats import write_chats
from negotiator.client import ArenaClient
from negotiator.config import REPO_ROOT, Settings
from negotiator.data import WorldData
from negotiator.guards import accept_problems, clean_message, sheet_problems
from negotiator.lessons import write_lessons
from negotiator.profile import build_profile
from negotiator.report import write_report
from negotiator.runner import play_many
from negotiator.session import Negotiation, ThreadState
from negotiator.strategy import TacticalStrategy
from negotiator.strategy.tactical import POLICIES, parse_breakdown
from negotiator.telemetry import Recorder

SIM_CASES = REPO_ROOT / "negotiation-arena-kit" / "starter-kit" / "arena_kit" / "sim_cases"
QUOTE_TEXT = """Quotation
Offered terms
Unit price (EUR) 17.47
Our standard terms
Payment terms (days net) 30
Lead time (days) 70
Incoterm FCA
"""


def case(**buyer_overrides) -> dict:
    c = json.loads((SIM_CASES / "S01.json").read_text(encoding="utf-8"))
    c["buyer"].update(buyer_overrides)
    return c


def negotiation(tmp_path: Path, world: WorldData | None, c: dict, offer: dict, std_text: str = QUOTE_TEXT):
    neg = Negotiation(None, Recorder(tmp_path), world)  # type: ignore[arg-type]
    neg.case, neg.case_id, neg.session_id = c, c["case_id"], "s1"
    sid = c["suppliers"][0]
    t = ThreadState(sid)
    t.messages.append(
        {
            "from": f"sales@{sid}",
            "status": "open",
            "term_sheets": [{"term_sheet_id": "offer:x-0", "terms": offer}],
            "attachments": [{"name": "quote-0.pdf", "text": std_text}] if std_text else [],
        }
    )
    neg.threads[sid] = t
    return neg, sid


# ---------------------------------------------------------------- guards
def test_accept_guard_passes_a_good_sheet(tmp_path, world) -> None:
    neg, sid = negotiation(tmp_path, world, case(), {"unit_price": 16.0, "payment_days": 60})
    assert accept_problems(neg, sid, "offer:x-0") == []


def test_accept_guard_refuses_a_stale_sheet(tmp_path, world) -> None:
    neg, sid = negotiation(tmp_path, world, case(), {"unit_price": 16.0, "payment_days": 60})
    assert accept_problems(neg, sid, "offer:x-old")


def test_accept_guard_refuses_a_broken_must_have(tmp_path, world) -> None:
    c = case(must_haves=[{"field": "payment_days", "op": ">=", "value": 45}])
    neg, sid = negotiation(tmp_path, world, c, {"unit_price": 16.0, "payment_days": 30})
    assert any("must-have" in p for p in accept_problems(neg, sid, "offer:x-0"))


def test_accept_guard_reads_must_haves_on_the_standard_terms(tmp_path, world) -> None:
    """lead_time_days is not on the sheet and not fixed: it closes on the quote PDF's 70 days."""
    c = case(must_haves=[{"field": "lead_time_days", "op": "<=", "value": 50}])
    del c["fixed_terms"]["lead_time_days"]
    neg, sid = negotiation(tmp_path, world, c, {"unit_price": 16.0, "payment_days": 60})
    assert any("must-have" in p for p in accept_problems(neg, sid, "offer:x-0"))


def test_accept_guard_refuses_an_unknown_must_have_field(tmp_path, world) -> None:
    """No quote PDF: the closing lead time is unknown - the plan's default must not pass it."""
    c = case(must_haves=[{"field": "lead_time_days", "op": "<=", "value": 50}])
    del c["fixed_terms"]["lead_time_days"]
    neg, sid = negotiation(tmp_path, world, c, {"unit_price": 16.0, "payment_days": 60}, std_text="")
    assert any("unknown" in p for p in accept_problems(neg, sid, "offer:x-0"))


def test_accept_guard_refuses_a_deal_dearer_than_the_alternative(tmp_path, world) -> None:
    c = case(alternative={"kind": "quote", "ref": None, "terms": {"unit_price": 15.0, "payment_days": 60}})
    neg, sid = negotiation(tmp_path, world, c, {"unit_price": 16.0, "payment_days": 60})
    assert any("alternative" in p for p in accept_problems(neg, sid, "offer:x-0"))


def test_send_guard_drops_bad_sheets_and_unknown_ids(tmp_path, world) -> None:
    c = case(must_haves=[{"field": "payment_days", "op": ">=", "value": 45}])
    neg, sid = negotiation(tmp_path, world, c, {"unit_price": 16.0, "payment_days": 60})
    msg = {
        "subject": "x",
        "body": "Index fell (idx:PPI-D351@2025-08, idx:NOPE@2026-08).",
        "refs": ["sc:70270@2026Q3", "qn:does-not-exist"],
        "term_sheets": [
            {"terms": {"unit_price": 15.0, "payment_days": 60}},
            {"terms": {"unit_price": 14.0, "payment_days": 30}},  # breaks the must-have
            {"terms": {"unit_price": 14.0, "payment_days": 61}},  # not an option
        ],
    }
    out, removed = clean_message(neg, sid, msg)
    assert out["term_sheets"] == [{"terms": {"unit_price": 15.0, "payment_days": 60}}]
    assert out["refs"] == ["sc:70270@2026Q3"]
    assert "idx:NOPE" not in out["body"] and "idx:PPI-D351@2025-08" in out["body"]
    assert len(removed) == 4


def test_send_guard_drops_claims_without_source_and_empty_threats(tmp_path, world) -> None:
    neg, sid = negotiation(tmp_path, world, case(), {"unit_price": 16.0, "payment_days": 60})
    body = (
        "Dear team,\n\nThe index fell 4 % (idx:NOPE@2026-08). Steel eased (idx:PPI-D351@2025-08). "
        "A competitor offers EUR 15.70. Otherwise we will walk away.\n\nOur proposal: below."
    )
    out, removed = clean_message(neg, sid, {"subject": "x", "body": body, "refs": []})
    assert out["body"] == "Dear team,\n\nSteel eased (idx:PPI-D351@2025-08).\n\nOur proposal: below."
    assert sum(r.startswith("unsupported sentence") for r in removed) == 3
    clean = "Dear team,\n\nThank you. Our proposal: below."
    assert clean_message(neg, sid, {"subject": "x", "body": clean})[0]["body"] == clean  # nothing to drop: unchanged


def test_sheet_needs_exactly_the_negotiable_fields() -> None:
    assert sheet_problems(case(), {"unit_price": 15.0})
    assert not sheet_problems(case(), {"unit_price": 15.0, "payment_days": 60})


# ---------------------------------------------------------------- profile
def test_profile_reads_the_notes(world) -> None:
    assert build_profile(world, "sup:70170").has("cash_short")  # "could you pay our invoices within 10 days"
    assert build_profile(world, "sup:70520").has("approval_ladder")  # pricing committee
    assert build_profile(world, "sup:70110").has("below_cost")  # renewals settled below full cost
    for trait, refs in build_profile(world, "sup:70170").traits.items():
        assert refs, trait


def test_policy_follows_goal_and_traits(world) -> None:
    s = TacticalStrategy(world)
    lev = s._policy("leverage", build_profile(world, "sup:70640"))  # idle second shift
    stab = s._policy("stabilise", build_profile(world, "sup:70110"))
    assert lev.anchor > POLICIES["leverage"].anchor and lev.beta > POLICIES["leverage"].beta
    assert stab.anchor <= POLICIES["stabilise"].anchor and "contract_months" in stab.trade_first
    cash = s._policy("routine", build_profile(world, "sup:70170"))
    assert cash.trade_first[0] == "payment_days"


def test_full_cost_is_only_this_suppliers_plant(world) -> None:
    s = TacticalStrategy(world)
    assert s._full_cost(["part:310010"], "sup:70110") == 132.64
    assert s._full_cost(["part:310010"], "sup:70140") is None  # another plant: no guess


def test_parse_breakdown_skips_margin_and_totals() -> None:
    text = (
        "[Cost breakdown]\nElement | EUR per unit | Share of price\nMaterial | 50.0 | =B2/B6\n"
        "Conversion | 30.0 | =B3/B6\nOverhead | 15.0 | =B4/B6\nMargin | 5.0 | =B5/B6\nUnit price | =SUM(B2:B5) | 1"
    )
    assert parse_breakdown(text) == 95.0


# ---------------------------------------------------------------- end to end
def test_tactical_closes_every_sim_case_fast_and_clean(sim: Settings, world: WorldData) -> None:
    recorder = Recorder(sim.runs_dir, "pytest-tactical")
    client = ArenaClient(sim, recorder)
    case_ids = [c["case_id"] for c in client.cases("practice")]
    start = time.time()
    outcomes = play_many(client, recorder, case_ids, lambda: TacticalStrategy(world), world, parallel=3)
    recorder.close()
    summary = write_report(recorder.dir, outcomes)
    lessons = write_lessons(recorder.dir)
    chats = write_chats(recorder.dir)

    assert summary["cases"] == len(case_ids) and not summary["failed"], summary["failed"]
    assert all(o["deal"] and o["must_haves_ok"] is not False for o in summary["outcomes"]), [
        (o["case_id"], o["deal"], o["end_reason"], o["score"]) for o in summary["outcomes"]
    ]
    assert all(o["score"] is not None and o["score"] > 0 for o in summary["outcomes"])
    assert summary["claims"].get("contradicted", 0) == 0
    assert time.time() - start < 120
    decide = recorder.metrics.snapshot()["timings"]["strategy.decide"]
    assert decide["max"] < 2.0  # the 60 s clock: deciding must never be the slow part
    assert lessons.is_file()
    assert "supplier's reasons" in chats.read_text(encoding="utf-8")
    assert len(list((recorder.dir / "sessions").glob("*.md"))) == len(case_ids)  # one chat per case
    asks: dict[tuple, list[float]] = {}
    for line in (recorder.dir / "events.jsonl").read_text(encoding="utf-8").splitlines():
        e = json.loads(line)
        if e.get("kind") == "decision" and e.get("action") == "message" and "ask_c" in e.get("rationale", {}):
            asks.setdefault((e["session_id"], e["supplier_id"]), []).append(e["rationale"]["ask_c"])
    backwards = {k: a for k, a in asks.items() if any(b < x for x, b in zip(a, a[1:], strict=False))}
    assert not backwards, backwards  # a step back below our own last ask reads as reneging


# ---------------------------------------------------------------- ground truth
def test_ground_truth_p01_floor_follows_the_case_type(world) -> None:
    """Calibrated on practice C_best: a price increase barely moves (P01's floor ~ its quote)."""
    from negotiator.groundtruth import estimate

    case_ = {
        "type": "price_increase",
        "parts": ["part:310010"],
        "suppliers": ["sup:70110"],
        "trigger_doc": "doc:20260911-70110-P01",
        "buyer": {"current_unit_price": 126.53, "category_goal": "stabilise"},
    }
    gt = estimate(world, case_, "sup:70110", 138.55, ("below_cost",))
    assert gt.asked_pct == 9.5 and round(gt.justified_pct, 1) == 2.3  # still an argument for the e-mail
    assert gt.full_cost_source == "own plant"
    assert gt.lower <= gt.upper <= 138.55
    assert 136 <= gt.lower <= 138  # practice: the price that reached C_best was 138.20
    assert not gt.market_supports_ask


def test_ground_truth_rfq_floor_sits_far_under_the_quotes(world) -> None:
    from negotiator.groundtruth import estimate

    case_ = {"type": "rfq", "parts": ["part:320070"], "suppliers": ["sup:70210", "sup:70240"], "buyer": {}}
    gt = estimate(world, case_, "sup:70210", 36.0)
    assert gt.lower < 36.0 * 0.9  # competition is a lever: the floor sits well under the quote


def test_ground_truth_p02_keeps_index_arguments_out(world) -> None:
    """Copper rose 48 %: the cost drivers support more than Nordmark asks - citing them would hurt us."""
    from negotiator.groundtruth import estimate

    case_ = {"parts": ["part:350011"], "trigger_doc": "doc:20260914-70510-P02", "buyer": {"current_unit_price": 348.32}}
    gt = estimate(world, case_, "sup:70510", 370.96)
    assert gt.justified_pct > gt.asked_pct and gt.market_supports_ask
    assert gt.lower <= gt.upper <= 370.96


def test_ground_truth_bounds_hold_without_data() -> None:
    from negotiator.groundtruth import estimate

    gt = estimate(None, {"parts": ["part:x"], "buyer": {"current_unit_price": 10.0}}, "sup:x", 11.0)
    assert gt.lower is not None and gt.lower <= gt.upper <= 11.0


def test_accept_guard_refuses_worse_than_opening_when_walking_is_safe(tmp_path, world) -> None:
    c = case(alternative={"kind": "quote", "ref": None, "terms": {"unit_price": 30.0, "payment_days": 60}})
    neg, sid = negotiation(tmp_path, world, c, {"unit_price": 16.0, "payment_days": 60})
    t = neg.threads[sid]
    t.messages.append(
        {
            "from": f"sales@{sid}",
            "status": "final_offer",
            "term_sheets": [{"term_sheet_id": "offer:x-1", "terms": {"unit_price": 17.0, "payment_days": 60}}],
        }
    )
    assert any("opening" in p for p in accept_problems(neg, sid, "offer:x-1"))


def test_round_limit_one_still_sends_the_first_offer(tmp_path, world) -> None:
    """With one round the last round is the first: holding it for the close would never make an offer."""
    c = case()
    c["round_limit"] = 1
    neg, sid = negotiation(tmp_path, world, c, {"unit_price": 17.47, "payment_days": 30})
    strategy = TacticalStrategy(world)
    strategy.prepare(neg)
    first = strategy.decide(neg, sid)
    assert first.kind == "message" and first.message["term_sheets"]
    neg.threads[sid].messages.append({"from": "buyer", **first.message})  # the round is spent
    assert strategy.decide(neg, sid).kind != "message"


def _strategic(world, tmp_path, offer=None, **buyer):
    """S01 as a stabilise case: a margin charge in C, the supplier's own plant without a should-cost."""
    c = case(**{"category_goal": "stabilise", "sustainable_margin_pct": 4, "relationship_eur_per_point": 5000, **buyer})
    neg, sid = negotiation(tmp_path, world, c, offer or {"unit_price": 17.47, "payment_days": 30})
    strategy = TacticalStrategy(world)
    strategy.prepare(neg)
    return neg, sid, strategy


def test_strategic_supplier_without_should_cost_gets_a_guess_floor(tmp_path, world) -> None:
    """No should-cost of its plant (P06): its cost is guessed from its opening and serves as a floor only - C and
    the target stay without the guessed charge, every sheet sits at or above the price that costs us least with it."""
    from negotiator.strategy.tactical import SHOULD_COST_SHARE

    neg, sid, strategy = _strategic(None, tmp_path)
    plan = strategy.tplans[sid]
    assert plan.guess["full_cost"] == round(17.47 * 0.96 * SHOULD_COST_SHARE, 2)
    assert not neg.supplier_estimates.get(sid) and plan.full_cost is None  # not in C
    first = strategy.decide(neg, sid)
    assert first.kind == "message"
    for sheet in first.message["term_sheets"]:
        terms = sheet["terms"]
        assert strategy._guess_floor(neg, sid, plan, terms) - 0.005 <= terms["unit_price"] <= 17.47


def test_the_guess_uses_the_main_sheet_of_the_first_message(tmp_path) -> None:
    """A cheaper alternative on another structure would set the guess too low - the dangerous direction."""
    from negotiator.strategy.tactical import SHOULD_COST_SHARE

    c = case(category_goal="stabilise", sustainable_margin_pct=4, relationship_eur_per_point=5000)
    neg, sid = negotiation(tmp_path, None, c, {"unit_price": 17.47, "payment_days": 30})
    sheets = neg.threads[sid].messages[0]["term_sheets"]
    sheets.append({"term_sheet_id": "offer:x-0b", "terms": {"unit_price": 15.0, "payment_days": 90}})
    cost, _ = TacticalStrategy(None)._fallback_full_cost(neg, sid)
    assert cost == round(17.47 * 0.96 * SHOULD_COST_SHARE, 2)


def test_an_offer_under_the_guess_floor_gets_the_floor(tmp_path) -> None:
    """It offers a price under the guess floor: we propose the floor on its terms instead of taking it."""
    neg, sid, strategy = _strategic(None, tmp_path)
    plan = strategy.tplans[sid]
    low = {"unit_price": 15.0, "payment_days": 30}
    neg.threads[sid].messages.append(
        {"from": f"sales@{sid}", "status": "open", "term_sheets": [{"term_sheet_id": "offer:x-1", "terms": low}]}
    )
    floor = strategy._guess_floor(neg, sid, plan, low)
    assert 15.0 < floor < 17.47
    d = strategy.decide(neg, sid)
    assert d.kind == "message" and d.message["term_sheets"][0]["terms"]["unit_price"] == floor


def test_own_plant_should_cost_is_not_replaced_by_the_guess(tmp_path, world) -> None:
    from negotiator.strategy.tactical import SHOULD_COST_SHARE

    c = case(category_goal="stabilise", sustainable_margin_pct=3, relationship_eur_per_point=5000)
    c["parts"], c["suppliers"] = ["part:310010"], ["sup:70110"]
    neg, sid = negotiation(tmp_path, world, c, {"unit_price": 138.55, "payment_days": 30})
    strategy = TacticalStrategy(world)
    strategy.prepare(neg)
    own = world.query("SELECT unit_cost FROM should_cost WHERE part_id = 'part:310010' AND supplier_id = 'sup:70110'")
    assert strategy.tplans[sid].full_cost == round(own[0]["unit_cost"] * SHOULD_COST_SHARE, 2)
    assert neg.supplier_estimates[sid]["full_cost"] == strategy.tplans[sid].full_cost
    assert strategy.tplans[sid].guess is None
    _, theirs = neg.threads[sid].standing
    # with the own plant's cost in C the re-anchor stays as measured (P01 0.969, runs.md P-29; 0.901 without it)
    assert strategy._reanchor(neg, sid, strategy.tplans[sid], theirs, neg.cost(sid, theirs)) is not None


def test_own_plant_cost_leaves_the_opening_its_sustainable_margin(tmp_path, world) -> None:
    """The arena's recorded charges put every strategic supplier at or above its sustainable margin at its own
    opening: where the should-cost says otherwise (H03) the cost comes down until the opening carries no charge."""
    from negotiator.strategy.tactical import SHOULD_COST_SHARE

    c = case(category_goal="stabilise", sustainable_margin_pct=3, relationship_eur_per_point=5000)
    c["parts"], c["suppliers"] = ["part:310010"], ["sup:70110"]
    own = world.query("SELECT unit_cost FROM should_cost WHERE part_id = 'part:310010' AND supplier_id = 'sup:70110'")
    should = round(own[0]["unit_cost"] * SHOULD_COST_SHARE, 2)
    opening = {"unit_price": round(should, 2), "payment_days": 30}  # no margin at all by the should-cost
    neg, sid = negotiation(tmp_path, world, c, opening)
    strategy = TacticalStrategy(world)
    strategy.prepare(neg)
    plan = strategy.tplans[sid]
    assert plan.full_cost < should and neg.supplier_estimates[sid]["full_cost"] == plan.full_cost
    assert neg.breakdown(sid, opening)["relationship"] == 0
    assert neg.breakdown(sid, {**opening, "unit_price": opening["unit_price"] * 0.97})["relationship"] > 0


def test_no_margin_estimate_without_the_cases_charge_parameters(tmp_path, world) -> None:
    """A strategic goal without `relationship_eur_per_point`: cost.py charges nothing, so no estimate - with one the
    price that costs us least was 0 and no sheet was left to send."""
    c = case(category_goal="stabilise", sustainable_margin_pct=3)
    c["parts"], c["suppliers"] = ["part:310010"], ["sup:70110"]
    neg, sid = negotiation(tmp_path, world, c, {"unit_price": 138.55, "payment_days": 30})
    strategy = TacticalStrategy(world)
    strategy.prepare(neg)
    assert not neg.supplier_estimates.get(sid) and strategy.tplans[sid].full_cost
    first = strategy.decide(neg, sid)
    assert first.kind == "message"
    assert all(0 < sh["terms"]["unit_price"] < 138.55 for sh in first.message["term_sheets"])


def test_lower_bound_never_above_the_upper_one(tmp_path) -> None:
    """An alternative cheaper than the supplier's estimated floor: an offer above our upper bound is no undercut of
    that floor, so the lower bound stays at or under the upper one."""
    c = case()
    alt = {"unit_price": 15.0, "payment_days": 30, "lead_time_days": 42, "volume_per_year": 6650}
    c["buyer"]["alternative"] = {"kind": "quote", "ref": "quote:x", "terms": {**alt, "contract_months": 12}}
    neg, sid = negotiation(tmp_path, None, c, {"unit_price": 17.47, "payment_days": 30})
    strategy = TacticalStrategy(None)
    strategy.prepare(neg)
    plan = strategy.tplans[sid]
    assert neg.c_alt < neg.cost(sid, strategy._ideal(neg, sid, {"payment_days": 30}, plan.gt.lower))
    assert plan.lower_c <= plan.upper_c <= neg.c_alt


def test_reanchor_on_a_strategic_supplier_only_with_a_guess(tmp_path) -> None:
    """No estimate at all: no 10 % ask under a strategic supplier's price. A guess: allowed, clamped to the floor."""
    neg, sid, strategy = _strategic(None, tmp_path, sustainable_margin_pct=None)
    assert not neg.supplier_estimates.get(sid) and strategy.tplans[sid].guess is None
    _, theirs = neg.threads[sid].standing
    plan = strategy.tplans[sid]
    assert strategy._reanchor(neg, sid, plan, theirs, neg.cost(sid, theirs)) is None and not plan.reanchored

    neg, sid, strategy = _strategic(None, tmp_path)
    plan = strategy.tplans[sid]
    d = strategy._reanchor(neg, sid, plan, theirs, neg.cost(sid, theirs))
    assert plan.reanchored and d is not None and d.kind == "message"
    assert all(
        sh["terms"]["unit_price"] >= strategy._guess_floor(neg, sid, plan, sh["terms"]) - 0.005
        for sh in d.message["term_sheets"]
    )


def test_reply_signals_tell_room_from_a_last_word() -> None:
    from negotiator.strategy.tactical import reply_signals

    soft = "We now look forward to a more significant step from your side to bridge the remaining gap."
    firm = "We have made all possible concessions to reach this point and cannot reduce the price further."
    assert reply_signals(soft) == {"room": True, "firm": False}
    assert reply_signals(firm)["firm"] and not reply_signals(firm)["room"]
    assert reply_signals("We have free capacity for your parts.")["room"]


def test_timeout_answers_become_the_standing_offer() -> None:
    """case:P05: the agreed sheet existed only in `timeouts`; accepting the stale id failed with a 422."""
    from negotiator.session import timeout_messages

    thread = {
        "messages": [{"from": "sales@x", "message_id": "msg:x-3-6", "term_sheets": [{"term_sheet_id": "offer:x-3"}]}],
        "timeouts": [
            {"offer_id": "offer:x-4", "round": 4, "status": "agreed", "terms": {"unit_price": 29.09}},
            {"offer_id": "offer:x-2", "round": 2, "status": "open", "terms": {"unit_price": 30.0}},
        ],
    }
    out = timeout_messages(thread, "sup:x")
    assert [m["term_sheets"][0]["term_sheet_id"] for m in out] == ["offer:x-4"]
    assert out[0]["status"] == "agreed"


def test_ledger_turns_a_cited_driver_and_reads_a_hedge(world) -> None:
    from negotiator.ledger import reply_facts

    body = (
        "AS-14404 rose 5.9 % in twelve months and is 45 % of our cost. "
        "Our fixed-price material coverage only extends to March 2027."
    )
    facts = reply_facts(world, body)
    kinds = {f.kind for f in facts}
    assert "their_hedge" in kinds
    drops = [f for f in facts if f.kind == "recent_drop"]
    assert drops and drops[0].sentence.startswith("You cite AS-14404") and " fell -" not in drops[0].sentence
    assert all(world.fact(r) for f in drops for r in f.refs)  # every figure checkable by ID


def test_margin_charge_is_priced_without_payment_terms_in_the_quote_pdf(tmp_path) -> None:
    # P02: the quote PDF named no payment terms, the charge stayed out of C and a deal at 345.39 scored 0
    c = case(category_goal="stabilise", sustainable_margin_pct=3, relationship_eur_per_point=15000)
    neg, sid = negotiation(tmp_path, None, c, {"unit_price": 17.47, "payment_days": 30}, std_text="")
    strategy = TacticalStrategy()
    strategy._estimate_supplier(neg, sid, 16.5, build_profile(None, sid, c))
    assert neg.supplier_estimates[sid]["standard"]["payment_days"] == 30  # from its opening sheet
    terms = {"unit_price": 17.47, "payment_days": 60}
    assert neg.breakdown(sid, {**terms, "unit_price": 15.0})["relationship"] > 0
    cheapest = strategy._cheapest_price(neg, sid, terms)
    assert 15.0 < cheapest < 17.47
    # an ask no price can reach: we stop at the price that costs us least, not under it
    assert strategy._iso_cost_price(neg, sid, terms, 0.0) >= round(cheapest, 2) - 0.01
    assert neg.cost(sid, {**terms, "unit_price": cheapest}) < neg.cost(sid, {**terms, "unit_price": 15.0})


def test_accept_guard_counts_only_a_rival_with_a_price(tmp_path, world) -> None:
    """C >= C_open is refused while a real rival bid stands; a rival thread with no priced sheet is no rival."""
    c = case(alternative=None)
    c["suppliers"] = [c["suppliers"][0], "sup:rival"]
    neg, sid = negotiation(tmp_path, world, c, {"unit_price": 17.47, "payment_days": 30})
    rival = ThreadState("sup:rival")
    rival.messages.append({"from": "sales@sup:rival", "status": "open", "term_sheets": []})
    neg.threads["sup:rival"] = rival
    assert not any("opening" in p for p in accept_problems(neg, sid, "offer:x-0"))
    rival.messages.append(
        {
            "from": "sales@sup:rival",
            "status": "open",
            "term_sheets": [{"term_sheet_id": "offer:r-0", "terms": {"unit_price": 18.0, "payment_days": 30}}],
        }
    )
    assert any("opening" in p for p in accept_problems(neg, sid, "offer:x-0"))
