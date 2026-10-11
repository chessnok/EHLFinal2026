"""Does the agent read a case brief correctly? Offline: no arena call, no session, no practice quota.

Each variant (brief_variants.py: the recorded cases and changed copies of them) goes through the step where
`tactical` digests a case - `prepare` - and through the construction of its first e-mail, and what the agent
derived is compared with answers computed with `arena_kit.cost` alone:

  - C of the opening (`c_open`), C of the alternative (`c_alt`), the must-have verdict of each opening;
  - the plan: finite numbers in a sensible order (target <= upper <= opening, upper <= alternative);
  - the first ask: a valid term sheet (exactly the negotiable fields, allowed values, must-haves kept), a
    positive price not above the opening's, cheaper for us than the opening, and for a relationship goal not
    below the strategy's own floor;
  - an unknown `type`, `category_goal` or field: no crash, a default policy, no relationship charge.

It judges the reading of a brief, not the strategy: no supplier answers here. A finding that is a known fault of
the agent turns the variant into an xfail with its reason (KNOWN); anything else fails. Without recorded sessions
(`runs/` is not in the repository) the module skips.
"""

import json
import math
import traceback
from dataclasses import dataclass
from pathlib import Path

import pytest
from arena_kit.cost import OPS, closing_terms, total_cost
from brief_variants import OFF_DATA, Variant, build_negotiation, expected, load_bases, sheet_faults, variants

from negotiator.config import PACKAGE_ROOT
from negotiator.guards import accept_problems, clean_message, sheet_problems
from negotiator.strategy import TacticalStrategy
from negotiator.strategy.baseline import SANE_PRICE
from negotiator.strategy.tactical import ANCHOR_SLACK, RELATIONSHIP_COST_FLOOR, UNDER_FLOOR

RUNS = PACKAGE_ROOT / "runs"
BASES = load_bases(RUNS) if RUNS.is_dir() else {}
VARIANTS = variants(BASES) if BASES else []
EUR = 0.011  # C is rounded to cents

# Finding code -> the fault of the agent behind it. A variant whose findings are all listed here is an xfail;
# when the fault is fixed the finding disappears and the variant passes. "verified": the arena's own records or
# its published rules show the agent is wrong. "suspicion": a brief outside what api.md describes, where the
# agent's reaction is doubtful but nothing recorded says what the arena would do.
KNOWN: dict[str, str] = {
    "c_open:no-opening-keeps-must-haves": (
        "verified - session.py Negotiation.c_open is inf when no opening keeps the must-haves; the arena's c_open "
        "is then the cheapest opening of all (recorded c_open of case:P10 and case:P11)"
    ),
    "send_guard:must-have-on-standard-term": (
        "verified - guards.py sheet_problems calls must_haves_ok(case, terms) without the supplier's standard "
        "terms: a must-have on a field that is neither negotiable nor fixed counts as broken on every sheet, and "
        "clean_message strips all term sheets from the e-mail"
    ),
    "no_first_move:last-round": (
        "suspicion - tactical.py decide holds when one round is left ('keep it for the close'): with round_limit 1 "
        "it never sends an offer; api.md says an accept is still possible after the round limit"
    ),
    "price_fixed": (
        "suspicion - a case whose unit_price is in fixed_terms: session.py Negotiation.cost returns inf for a "
        "sheet without unit_price although the cost function prices it, so c_open is inf and the agent holds"
    ),
    "sheet_null_for_optionless_field": (
        "suspicion - a negotiable field with no term_options, no value on the opening and none in the standard "
        "terms goes out as None (arena_kit complete_offer); guards.py sheet_problems does not object"
    ),
    "crash:prepare:_full_cost": (
        "verified crash, trigger unconfirmed - tactical.py prepare reads case.get('parts', []), which is None for "
        "an explicit null (the arena sends null for other optional fields); _full_cost then takes len(None)"
    ),
    "crash:decide:decide": (
        "verified crash, trigger unconfirmed - tactical.py decide computes case.get('round_limit', 10) - "
        "rounds_used, a TypeError when round_limit is an explicit null"
    ),
    "no_first_move:no-options-for-must-have-field": (
        "suspicion - the opening breaks a must-have on a negotiable field without term_options: the agent never "
        "proposes a value of its own for it (the must-have's) and holds the thread"
    ),
}


# a known crash is known only in the variant that provokes it: the same function failing elsewhere is news
ONLY_IN = {"crash:prepare:_full_cost": "-null-parts", "crash:decide:decide": "-null-round_limit"}


@dataclass
class Finding:
    code: str
    text: str

    def __str__(self) -> str:
        return f"[{self.code}] {self.text}"


def _where(e: BaseException) -> str:
    """The innermost frame of ours that raised: file:line in function."""
    frames = [f for f in traceback.extract_tb(e.__traceback__) if "/negotiator/" in f.filename]
    f = (frames or traceback.extract_tb(e.__traceback__))[-1]
    return f"{Path(f.filename).name}:{f.lineno} in {f.name}: {type(e).__name__}: {e}"


def _same(a: float, b: float) -> bool:
    return (math.isinf(a) and math.isinf(b)) or (math.isfinite(a) and math.isfinite(b) and abs(a - b) <= EUR)


def _breaks(case: dict, m: dict, closing: dict) -> bool:
    value = closing.get(m["field"])
    if value is None and m["op"] not in ("==", "!="):
        return True
    return not OPS[m["op"]](value, m["value"])


def _hold_reason(v: Variant, sid: str, standard: dict) -> str | None:
    """Why no term sheet of ours can repair this supplier's opening - then holding the thread is right."""
    closing = closing_terms(v.case, v.openings.get(sid) or {}, standard)
    options = v.case.get("term_options") or {}
    for m in v.buyer.get("must_haves") or []:
        if not _breaks(v.case, m, closing):
            continue
        if m["field"] not in v.case["negotiable"]:
            return "unfixable"  # its standard or a fixed term breaks a must-have
        if not options.get(m["field"]):
            return "no-options-for-must-have-field"
    return None


def _plan_events(neg) -> dict[str, dict]:
    path = neg.recorder.dir / "events.jsonl"
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {e["supplier_id"]: e for e in events if e.get("kind") == "plan"}


def examine(v: Variant, world, runs_dir: Path) -> list[Finding]:
    out: list[Finding] = []

    def found(code: str, text: str) -> None:
        out.append(Finding(code, text))

    exp = expected(v)
    if v.arena:  # the check checks itself: on an unchanged case the arena's own numbers are the answer
        assert _same(exp["c_open"], v.arena["c_open"]), f"expected c_open {exp['c_open']} != arena {v.arena['c_open']}"
        arena_alt = v.arena["c_alt"] if v.arena["c_alt"] is not None else math.inf
        assert _same(exp["c_alt"], arena_alt), f"expected c_alt {exp['c_alt']} != arena {v.arena['c_alt']}"

    neg = build_negotiation(runs_dir, world, v)

    # ---- the brief as the session reads it, before any strategy
    try:
        if not _same(neg.c_alt, exp["c_alt"]):
            found("c_alt", f"neg.c_alt {neg.c_alt} != {exp['c_alt']}")
    except Exception as e:
        found("crash:c_alt", _where(e))
    try:
        if not _same(neg.c_open, exp["c_open"]):
            code = "c_open:no-opening-keeps-must-haves" if math.isinf(neg.c_open) else "c_open"
            found(code, f"neg.c_open {neg.c_open} != {exp['c_open']}")
    except Exception as e:
        found("crash:c_open", _where(e))
    for sid, s in exp["suppliers"].items():
        terms = v.openings.get(sid) or {}
        try:
            if neg.threads[sid].standard_terms != s["standard"]:
                found("standard_terms", f"{sid}: read {neg.threads[sid].standard_terms}, quote says {s['standard']}")
            if not _same(neg.cost(sid, terms), s["c"]):
                found("opening_cost", f"{sid}: neg.cost {neg.cost(sid, terms)} != {s['c']}")
            if neg.keeps_must_haves(sid, terms) != s["must_haves_ok"]:
                found("must_have_verdict", f"{sid}: keeps_must_haves != {s['must_haves_ok']}")
            standing = neg.threads[sid].standing[0]
            if s["priced"] and not s["must_haves_ok"] and not accept_problems(neg, sid, standing):
                found("accept_guard", f"{sid}: the opening breaks a must-have and the accept guard lets it pass")
        except Exception as e:
            found("crash:read", f"{sid}: {_where(e)}")

    # ---- prepare
    strategy = TacticalStrategy(neg.data)  # the case's view of the data, with its own facts
    try:
        strategy.prepare(neg)
    except Exception as e:
        found(f"crash:prepare:{_where(e).split(' in ')[1].split(':')[0]}", _where(e))
        return out
    events = _plan_events(neg)
    for sid, s in exp["suppliers"].items():
        plan = strategy.tplans.get(sid)
        if plan is None or sid not in events:
            found("plan_missing", f"{sid}: no plan / no plan event")
            continue
        if not exp["relationship_goal"] and neg.supplier_estimates:
            found("relationship_misread", f"{sid}: a supplier estimate (relationship charge) without such a goal")
        pol = plan.policy
        if not (0 < pol.anchor < 0.5 and pol.beta > 0 and 0 < pol.reciprocity <= 1):
            found("policy", f"{sid}: {pol}")
        if not s["priced"]:
            continue
        # an unchanged case: the arena's c_open carries no margin charge at the opening, so neither may ours
        charged = exp["relationship_goal"] and "base" not in v.tags
        ok_open = plan.open_c + EUR >= s["c"] if charged else _same(plan.open_c, s["c"])
        if not math.isfinite(plan.open_c) or not ok_open:
            found("plan_open_c", f"{sid}: open_c {plan.open_c} vs C of the opening {s['c']}")
        if math.isnan(plan.lower_c) or not all(math.isfinite(x) and x > 0 for x in (plan.target_c, plan.upper_c)):
            found("plan_not_finite", f"{sid}: target {plan.target_c} lower {plan.lower_c} upper {plan.upper_c}")
            continue
        if plan.target_c >= exp["c_alt"] - EUR:
            continue  # by its own estimate no deal beats the alternative: nothing to order, and holding is right
        if not plan.target_c <= plan.upper_c + EUR <= plan.open_c + 2 * EUR:
            found("plan_order", f"{sid}: target {plan.target_c} upper {plan.upper_c} open {plan.open_c}")
        if plan.upper_c > exp["c_alt"] + EUR:
            found("plan_order", f"{sid}: upper {plan.upper_c} above the alternative {exp['c_alt']}")
        if plan.lower_c > plan.upper_c + EUR:
            found("plan_lower_above_upper", f"{sid}: lower {plan.lower_c} > upper {plan.upper_c}")

    # ---- the first move
    for sid, s in exp["suppliers"].items():
        plan = strategy.tplans.get(sid)
        if plan is None:
            continue
        try:
            decision = strategy.decide(neg, sid)
        except Exception as e:
            found(f"crash:decide:{_where(e).split(' in ')[1].split(':')[0]}", f"{sid}: {_where(e)}")
            continue
        if not s["priced"]:
            if decision.kind == "message" and decision.message.get("term_sheets"):
                found("ask_without_price", f"{sid}: a term sheet although the supplier quoted no price")
            continue
        if decision.kind != "message":
            why = _hold_reason(v, sid, s["standard"])
            if why == "unfixable" or (math.isfinite(plan.target_c) and plan.target_c >= exp["c_alt"] - EUR):
                continue
            if "last round" in str(decision.rationale.get("why")):
                why = "last-round"
            found(f"no_first_move:{why}" if why else "no_first_move", f"{sid}: {decision.kind} - {decision.rationale}")
            continue
        sheets = decision.message.get("term_sheets") or []
        if not 1 <= len(sheets) <= 3:
            found("sheet_count", f"{sid}: {len(sheets)} sheets")
            continue
        try:
            cleaned, removed = clean_message(neg, sid, decision.message)
            if len(cleaned.get("term_sheets") or []) != len(sheets):
                valid = all(not sheet_faults(v.case, sh["terms"], s["standard"]) for sh in sheets)
                standard_only = any(
                    m["field"] not in v.case["negotiable"] and m["field"] not in (v.case.get("fixed_terms") or {})
                    for m in v.buyer.get("must_haves") or []
                )
                code = "send_guard:must-have-on-standard-term" if valid and standard_only else "send_guard"
                found(code, f"{sid}: the send guard removes {removed}")
        except Exception as e:
            found("crash:clean_message", f"{sid}: {_where(e)}")
        hard_floor = round(plan.full_cost * RELATIONSHIP_COST_FLOOR, 2) if plan.full_cost else None
        soft_floor = plan.floor_price * (1 - UNDER_FLOOR - 0.01) if plan.floor_price else None
        for i, sheet in enumerate(sheets):
            terms = sheet["terms"]
            faults = sheet_faults(v.case, terms, s["standard"])
            if faults:
                code = "sheet_invalid" if sheet_problems(neg.case, terms) else "sheet_invalid:guard-passes-it"
                if all(f.endswith("is None") for f in faults):
                    code = "sheet_null_for_optionless_field"
                found(code, f"{sid}: {terms}: {'; '.join(faults)}")
                continue
            price = terms.get("unit_price", s["price"])  # a price the enquiry fixed is not on the sheet
            if i == 0 and price > s["price"] + 0.005:
                found("ask_above_opening", f"{sid}: asks {price}, the opening is {s['price']}")
            if price < s["price"] * SANE_PRICE:
                found("ask_too_deep", f"{sid}: asks {price}, under {SANE_PRICE:.0%} of the opening {s['price']}")
            c = total_cost(v.case, terms, s["standard"])
            if not c < s["c"]:
                found("ask_not_cheaper", f"{sid}: {terms} costs {c}, the opening {s['c']}")
            if exp["relationship_goal"]:
                if hard_floor and price < min(hard_floor, s["price"]) - 0.005:
                    found("ask_below_cost_floor", f"{sid}: asks {price}, the 95 % should-cost floor is {hard_floor}")
                elif soft_floor and price < min(soft_floor, s["price"]) - 0.005:
                    # a deep first ask may sit under the sustainable-margin price where the margin charge is in
                    # C (tactical._sheets): at or above the price that costs us least on its structure, or at
                    # most ANCHOR_SLACK of the room dearer than that structure's cheapest price
                    cheapest = strategy._cheapest_price(neg, sid, terms)
                    least = neg.cost(sid, {**terms, "unit_price": cheapest})
                    limit = least + ANCHOR_SLACK * max(0.0, plan.open_c - plan.target_c)
                    bounded = price >= cheapest - 0.01 or neg.cost(sid, terms) <= limit * (1 + 1e-4)
                    if not neg.supplier_estimates.get(sid) or not bounded:
                        found(
                            "ask_below_margin_floor",
                            f"{sid}: asks {price}; plan.floor_price (sustainable margin) is {plan.floor_price}, "
                            f"the opening {s['price']}; C {neg.cost(sid, terms):,.0f} against a limit of "
                            f"{limit:,.0f}",
                        )
    if "unit_price" not in v.case["negotiable"]:
        out = [Finding("price_fixed", str(f)) for f in out]
    return out


def _cases():
    for v in VARIANTS:
        for with_data in (True, False):
            if with_data and OFF_DATA in v.tags:
                continue  # its prices or parts contradict the data package: the data would mislead, not the brief
            yield pytest.param(v, with_data, id=f"{v.id}-{'data' if with_data else 'nodata'}")


@pytest.mark.skipif(not VARIANTS, reason=f"no recorded sessions under {RUNS}")
def test_variants_cover_the_brief() -> None:
    """The generator is deterministic and wide enough to mean something."""
    again = variants(load_bases(RUNS))
    assert [(v.id, v.case, v.openings, v.standards) for v in again] == [
        (v.id, v.case, v.openings, v.standards) for v in VARIANTS
    ]
    changed = [v for v in VARIANTS if "base" not in v.tags]
    assert 30 <= len(changed), len(changed)
    assert any(len(v.case["suppliers"]) > 1 for v in changed) and any(len(v.case["suppliers"]) == 1 for v in changed)
    assert sum("unknown" in v.tags for v in changed) >= 8


@pytest.mark.skipif(not VARIANTS, reason=f"no recorded sessions under {RUNS}")
@pytest.mark.parametrize(("v", "with_data"), list(_cases()))
def test_brief_is_read_correctly(v: Variant, with_data: bool, world, tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)  # offline: no tracing sink
    findings = examine(v, world if with_data else None, tmp_path)
    if not findings:
        return
    report = f"{v.id} ({v.what}):\n  " + "\n  ".join(str(f) for f in findings)
    unknown = [f for f in findings if f.code not in KNOWN or not v.id.endswith(ONLY_IN.get(f.code, ""))]
    if unknown:
        pytest.fail(report, pytrace=False)
    pytest.xfail("; ".join(sorted({KNOWN[f.code] for f in findings})) + "\n" + report)
