"""Augmented case briefs for `test_brief_variants.py`: does the agent read a brief it has never seen correctly?

Everything here is derived at run time from the recorded sessions under `runs/` (the case file, each supplier's
opening sheet and its quote PDF text, the arena's own `c_open` and `c_alt`); no value of a case is written in
this file. `variants()` changes one thing of a recorded case at a time - prices, volumes, horizon, rates, freight,
which fields are fixed or negotiable, must-haves, the alternative, the category goal, the index clause, missing
optional fields, incomplete openings, the number of suppliers, unknown `type` / `category_goal` / fields.

`expected()` computes the right answers with `arena_kit.cost` alone, never through `negotiator.session`.
"""

import copy
import json
import math
import random
from dataclasses import dataclass, field
from pathlib import Path

from arena_kit.cost import RELATIONSHIP_GOALS, closing_terms, must_haves_ok, total_cost
from arena_kit.docs import LABELS, quote_terms

from negotiator.session import Negotiation, ThreadState
from negotiator.telemetry import Recorder

SEED = 20261010
GOALS = ["leverage", "routine", "stabilise", "secure_supply", "quality_first"]
NEUTRAL_BODY = "Dear Sir or Madam,\n\nour quote is attached.\n\nKind regards"
FIELD_LABEL = {name: label for label, name in LABELS.items()}
# tags
OFF_DATA = "off_data"  # prices or parts no longer match the data package: run without it
UNKNOWN = "unknown"  # a type, goal or field the agent has never seen


@dataclass
class Variant:
    id: str
    base: str
    what: str
    case: dict
    openings: dict[str, dict]  # supplier -> the terms on its opening sheet ({} = it sent no sheet)
    standards: dict[str, dict]  # supplier -> its standard terms, as its quote PDF states them
    texts: dict[str, str | None] = field(default_factory=dict)  # supplier -> the recorded quote text; None: render
    bodies: dict[str, str] = field(default_factory=dict)
    offer_ids: dict[str, str] = field(default_factory=dict)
    arena: dict = field(default_factory=dict)  # the arena's own c_open / c_alt for an unchanged case
    tags: frozenset = frozenset()
    quote_attached: bool = True

    @property
    def buyer(self) -> dict:
        return self.case["buyer"]


# ---------------------------------------------------------------------------------------- recorded cases
def load_bases(runs_dir: Path) -> dict[str, Variant]:
    """One recorded session per case: the first (by path) that ended with a result."""
    bases: dict[str, Variant] = {}
    for path in sorted(Path(runs_dir).glob("*/sessions/*.json")):
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        case, state, result = d.get("case") or {}, d.get("state") or {}, d.get("result") or {}
        cid = case.get("case_id")
        opening = state.get("opening") or {}
        if not cid or cid in bases or not opening or result.get("c_open") is None:
            continue
        if set(opening) != set(case.get("suppliers", [])):
            continue
        v = Variant(f"{cid.split(':')[-1]}-base", cid, "the recorded case, unchanged", case, {}, {})
        for sid, o in opening.items():
            first = ((d.get("threads") or {}).get(sid) or {}).get("messages") or [{}]
            text = next(
                (
                    a.get("text")
                    for a in first[0].get("attachments") or []
                    if a.get("name", "").startswith("quote") and a.get("text")
                ),
                None,
            )
            if text is None:
                break
            v.openings[sid] = o["terms"]
            v.texts[sid] = text
            v.standards[sid] = quote_terms(text).get("standard", {})  # the kit's parser, not ours
            v.bodies[sid] = first[0].get("body") or NEUTRAL_BODY
            v.offer_ids[sid] = o.get("offer_id") or f"offer:{sid.split(':')[-1]}-0"
        else:
            v.arena = {"c_open": result["c_open"], "c_alt": result.get("c_alt")}
            v.tags = frozenset({"base"})
            bases[cid] = v
    return bases


# ---------------------------------------------------------------------------------------- the quote PDF
def _fmt(name: str, value) -> str | None:
    if name == "index_clause":
        if not value:
            return "none"
        return (
            f"{value['series']}, {round(value['material_share'] * 100)}% material, "
            f"deadband {float(value['deadband_pct'])} %, base {value.get('base_month')}"
        )
    if value is None:
        return None
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def quote_text(case: dict, offered: dict, standard: dict) -> str:
    """A quote PDF's text in the arena's layout (labels from `arena_kit.docs`): offered, standard, fixed."""
    lines = ["Supplier", "Angebot / Quote"]
    sections = [
        ("Offered terms", offered),
        ("Our standard terms (apply to everything not stated above)", standard),
        ("Terms fixed by your enquiry", case.get("fixed_terms") or {}),
    ]
    for head, terms in sections:
        lines.append(head)
        for name, value in terms.items():
            text = _fmt(name, value)
            if name in FIELD_LABEL and text is not None:
                lines.append(f"{FIELD_LABEL[name]} {text}")
    lines.append("Validity: 30 days.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------------------- the negotiation
def build_negotiation(runs_dir: Path, world, v: Variant) -> Negotiation:
    """The state right after `POST /v1/sessions`, without a client: the case and each supplier's opening e-mail."""
    case = copy.deepcopy(v.case)
    neg = Negotiation(None, Recorder(runs_dir), world)  # type: ignore[arg-type]
    neg.case, neg.case_id, neg.session_id = case, case.get("case_id", ""), f"brief-{v.id}"
    if world:
        world.with_case(case)
    for sid in case["suppliers"]:
        terms = copy.deepcopy(v.openings.get(sid) or {})
        text = v.texts.get(sid) or quote_text(case, terms, v.standards.get(sid) or {})
        offer_id = v.offer_ids.get(sid) or f"offer:{sid.split(':')[-1]}-0"
        t = ThreadState(sid)
        t.messages.append(
            {
                "from": f"sales@{sid.split(':')[-1]}",
                "subject": case.get("title") or "Quote",
                "body": v.bodies.get(sid, NEUTRAL_BODY),
                "status": "open",
                "term_sheets": [{"term_sheet_id": offer_id, "terms": terms}] if terms else [],
                "attachments": [{"name": "quote-0.pdf", "type": "pdf", "text": text}] if v.quote_attached else [],
                "missing_fields": [f for f in case["negotiable"] if f not in terms],
                "claim_results": [],
            }
        )
        neg.threads[sid] = t
    return neg


# ---------------------------------------------------------------------------------------- the right answers
def expected(v: Variant) -> dict:
    """What a correct reading of the brief gives - `arena_kit.cost` only."""
    case = v.case
    alt = (v.buyer.get("alternative") or {}).get("terms") or {}
    out = {
        "c_alt": total_cost(case, alt) if alt.get("unit_price") is not None else math.inf,
        "relationship_goal": v.buyer.get("category_goal") in RELATIONSHIP_GOALS,
        "suppliers": {},
    }
    for sid in case["suppliers"]:
        terms = v.openings.get(sid) or {}
        std = (v.standards.get(sid) or {}) if v.quote_attached else {}
        price = closing_terms(case, terms, std).get("unit_price") if terms else None
        out["suppliers"][sid] = {
            "priced": price is not None,
            "price": price,
            "standard": std,
            "c": total_cost(case, terms, std) if price is not None else math.inf,
            "must_haves_ok": must_haves_ok(case, terms, std),
        }
    costs = [s["c"] for s in out["suppliers"].values() if s["priced"]]
    kept = [s["c"] for s in out["suppliers"].values() if s["priced"] and s["must_haves_ok"]]
    # api.md: "the cheapest opening quote (among those that keep the must-haves)". Where no opening keeps them
    # the arena takes the cheapest opening of all: the recorded c_open of the cases whose only opening breaks a
    # must-have is that opening's C (test_brief_variants checks this rule against every recorded c_open).
    out["c_open_kept"] = min(kept, default=math.inf)
    out["c_open"] = min(kept or costs, default=math.inf)
    return out


def sheet_faults(case: dict, terms: dict, standard: dict) -> list[str]:
    """Why the arena would refuse this term sheet or score a deal on it 0 (api.md, Terms) - our own check,
    next to `guards.sheet_problems`."""
    faults = []
    if set(terms) != set(case["negotiable"]):
        faults.append(f"fields {sorted(terms)} are not the negotiable {sorted(case['negotiable'])}")
    price = terms.get("unit_price")
    if "unit_price" in case["negotiable"]:
        if not isinstance(price, int | float) or isinstance(price, bool) or not math.isfinite(price) or price <= 0:
            faults.append(f"unit_price {price!r}")
        elif round(price, 2) != price:
            faults.append(f"unit_price {price!r} has more than 2 decimals")
    options = case.get("term_options") or {}
    for name, value in terms.items():
        if name == "unit_price":
            continue
        allowed = list(options.get(name) or [])
        if name in standard:
            allowed.append(standard[name])  # "... or the supplier's standard value"
        if options.get(name) and value not in allowed:
            faults.append(f"{name}={value!r} is not one of {options[name]}")
        if value is None and name != "index_clause":
            faults.append(f"{name} is None")
    try:
        if not must_haves_ok(case, terms, standard):
            faults.append("breaks a must-have")
    except TypeError as e:
        faults.append(f"must-have not comparable: {e}")
    return faults


# ---------------------------------------------------------------------------------------- the variants
def _mut(base: Variant, name: str, what: str, *tags: str) -> Variant:
    """A deep copy of a recorded case to change; its quote text is rendered again from the changed terms."""
    v = copy.deepcopy(base)
    v.id = f"{base.base.split(':')[-1]}-{name}"
    v.what, v.arena = what, {}
    v.tags = frozenset(tags)
    v.texts = {}
    v.case["case_id"] = f"{base.base}-{name}"
    return v


def _scale_prices(v: Variant, k: float) -> None:
    b = v.buyer
    for key in ("current_unit_price", "fallback_unit_price"):
        if b.get(key) is not None:
            b[key] = round(b[key] * k, 2)
    alt = (b.get("alternative") or {}).get("terms") or {}
    if alt.get("unit_price") is not None:
        alt["unit_price"] = round(alt["unit_price"] * k, 2)
    for terms in v.openings.values():
        if terms.get("unit_price") is not None:
            terms["unit_price"] = round(terms["unit_price"] * k, 2)
    v.bodies = {}


def _scale_volume(v: Variant, k: float) -> None:
    def s(x):
        return max(1, round(x * k)) if isinstance(x, int | float) and x is not None else x

    b = v.buyer
    b["need_per_year"] = s(b["need_per_year"])
    fixed, options = v.case.get("fixed_terms", {}), v.case.get("term_options", {})
    if "volume_per_year" in fixed:
        fixed["volume_per_year"] = s(fixed["volume_per_year"])
    if options.get("volume_per_year"):
        options["volume_per_year"] = [s(x) for x in options["volume_per_year"]]
    for m in b.get("must_haves") or []:
        if m["field"] == "volume_per_year":
            m["value"] = s(m["value"])
    alt = (b.get("alternative") or {}).get("terms") or {}
    for terms in [alt, *v.openings.values(), *v.standards.values()]:
        if terms.get("volume_per_year") is not None:
            terms["volume_per_year"] = s(terms["volume_per_year"])


def _horizon(v: Variant, years: int) -> None:
    """The need runs over `years`; the contract term becomes negotiable up to it."""
    v.buyer["horizon_years"] = years
    v.case.get("fixed_terms", {}).pop("contract_months", None)
    if "contract_months" not in v.case["negotiable"]:
        v.case["negotiable"].append("contract_months")
    v.case.setdefault("term_options", {})["contract_months"] = [12, 24, 36]
    for terms in v.openings.values():
        if terms:
            terms["contract_months"] = 12
    alt = (v.buyer.get("alternative") or {}).get("terms") or {}
    if alt:
        alt["contract_months"] = 12 * years


def _to_negotiable(v: Variant, name: str, options: list, opening=None) -> None:
    fixed = v.case.get("fixed_terms", {})
    start = fixed.pop(name, None)
    if name not in v.case["negotiable"]:
        v.case["negotiable"].append(name)
    v.case.setdefault("term_options", {})[name] = options
    for sid, terms in v.openings.items():
        if not terms:
            continue
        if opening is not None:
            terms[name] = opening
        elif start is not None:
            v.standards.setdefault(sid, {})[name] = start  # left off the sheet: it closes on its standard


def _to_fixed(v: Variant, name: str, value) -> None:
    if name in v.case["negotiable"]:
        v.case["negotiable"].remove(name)
    v.case.get("term_options", {}).pop(name, None)
    v.case.setdefault("fixed_terms", {})[name] = value
    for terms in [*v.openings.values(), *v.standards.values()]:
        terms.pop(name, None)


def _index_clause(v: Variant, series: str, path: float | None, risk: float | None, opening_has: bool) -> None:
    clauses = [{"series": series, "material_share": 0.3, "deadband_pct": d, "base_month": "2026-08"} for d in (0, 2, 5)]
    v.case.get("fixed_terms", {}).pop("index_clause", None)
    if "index_clause" not in v.case["negotiable"]:
        v.case["negotiable"].append("index_clause")
    v.case.setdefault("term_options", {})["index_clause"] = [None, *clauses]
    if path is None:
        v.buyer.pop("index_paths", None)
    else:
        v.buyer["index_paths"] = {series: path}
    if risk is None:
        v.buyer.pop("index_risk_pct", None)
    else:
        v.buyer["index_risk_pct"] = risk
    for terms in v.openings.values():
        if terms:
            terms["index_clause"] = copy.deepcopy(clauses[0]) if opening_has else None


def _add_supplier(v: Variant, factor: float, tag: str = "NEW1") -> str:
    first = v.case["suppliers"][0]
    new = f"sup:{tag}"
    v.case["suppliers"].append(new)
    v.openings[new] = copy.deepcopy(v.openings[first])
    if v.openings[new].get("unit_price") is not None:
        v.openings[new]["unit_price"] = round(v.openings[new]["unit_price"] * factor, 2)
    v.standards[new] = copy.deepcopy(v.standards.get(first) or {})
    return new


def _only_supplier(v: Variant, sid: str) -> None:
    v.case["suppliers"] = [sid]
    v.openings = {sid: v.openings[sid]}
    v.standards = {sid: v.standards.get(sid) or {}}


def _cheapest_incoterm(v: Variant) -> str:
    freight = v.buyer["freight_eur_per_unit"]
    return min(freight, key=freight.get)


def variants(bases: dict[str, Variant], seed: int = SEED) -> list[Variant]:
    """The recorded cases and some 90 changed copies of them. Deterministic: the same recordings and seed give the same
    list. A change that needs a kind of case the recordings do not hold is left out."""
    rng = random.Random(seed)
    out: list[Variant] = [bases[k] for k in sorted(bases)]
    order = sorted(bases)

    def pick(test=lambda b: True) -> Variant | None:
        fitting = [bases[k] for k in order if test(bases[k])]
        return rng.choice(fitting) if fitting else None

    def add(v: Variant | None) -> None:
        if v is not None:
            out.append(v)

    def multi(b):
        return len(b.case["suppliers"]) > 1

    def single(b):
        return len(b.case["suppliers"]) == 1

    def relationship(b):
        return b.buyer.get("category_goal") in RELATIONSHIP_GOALS

    def has_alt(b):
        return ((b.buyer.get("alternative") or {}).get("terms") or {}).get("unit_price") is not None

    def negotiable(name):
        return lambda b: name in b.case["negotiable"]

    def fixed(name):
        return lambda b: name in b.case.get("fixed_terms", {})

    # ---- prices and volumes
    for k in (0.37, 4.2):
        if b := pick():
            v = _mut(b, f"price-x{k}", f"every price times {k}", OFF_DATA)
            _scale_prices(v, k)
            add(v)
    if b := pick(relationship):
        v = _mut(b, "price-x2.5-rel", "a relationship case, every price times 2.5", OFF_DATA)
        _scale_prices(v, 2.5)
        add(v)
    for k in (0.1, 12):
        if b := pick():
            v = _mut(b, f"volume-x{k}", f"need, volumes and volume options times {k}")
            _scale_volume(v, k)
            add(v)

    # ---- horizon, rates
    for years in (1, 2, 3):
        if b := pick(lambda b: "contract_months" not in b.case["negotiable"]):
            v = _mut(b, f"horizon-{years}y", f"a {years}-year need, contract term negotiable (12/24/36)")
            _horizon(v, years)
            add(v)
    if b := pick(negotiable("contract_months")):
        v = _mut(b, "horizon-3y-own-options", "a 3-year need on the case's own contract options")
        v.buyer["horizon_years"] = 3
        add(v)
    for rate, days in ((0.02, 30), (0.18, 90), (0.0, 0)):
        if b := pick(negotiable("payment_days")):
            v = _mut(b, f"rate-{rate}-ref-{days}", f"interest {rate}, reference payment {days} days")
            v.buyer["interest_rate"], v.buyer["reference_payment_days"] = rate, days
            add(v)

    # ---- freight and incoterms
    if b := pick(fixed("incoterm")):
        v = _mut(b, "incoterm-negotiable", "incoterm negotiable, the supplier's standard is the dearest")
        v.buyer["freight_eur_per_unit"] = {"EXW": 1.5, "FCA": 0.9, "DAP": 0.0}
        _to_negotiable(v, "incoterm", ["EXW", "FCA", "DAP"])
        for sid in v.standards:
            v.standards[sid]["incoterm"] = "EXW"
        add(v)
    if b := pick(fixed("incoterm")):
        v = _mut(b, "freight-dap-dearest", "a freight table where DAP costs most; two incoterm options, one opened")
        v.buyer["freight_eur_per_unit"] = {"EXW": 0.0, "FCA": 0.4, "DAP": 2.1}
        _to_negotiable(v, "incoterm", ["EXW", "DAP"], opening="DAP")
        add(v)
    if b := pick(fixed("incoterm")):
        v = _mut(b, "incoterm-unknown-cif", "a fourth incoterm (CIF) in the freight table and the options", UNKNOWN)
        v.buyer["freight_eur_per_unit"] = {**v.buyer["freight_eur_per_unit"], "CIF": 0.2}
        _to_negotiable(v, "incoterm", ["CIF", "FCA", "DAP"], opening="CIF")
        add(v)

    # ---- fixed and negotiable
    if b := pick(negotiable("payment_days")):
        v = _mut(b, "payment-fixed", "payment days fixed instead of negotiable")
        _to_fixed(v, "payment_days", 45)
        add(v)
    if b := pick(fixed("lead_time_days")):
        v = _mut(b, "leadtime-negotiable", "lead time negotiable, the opening is later than the need")
        need = v.buyer["need_lead_time_days"]
        _to_negotiable(v, "lead_time_days", [need - 7, need, need + 14], opening=need + 14)
        add(v)
    if b := pick(lambda b: len(b.case["negotiable"]) > 2):
        v = _mut(b, "price-only", "only the price is negotiable; everything else fixed at the opening's value")
        first = v.case["suppliers"][0]
        plan = closing_terms(v.case, v.openings[first], v.standards[first])
        for name in [n for n in v.case["negotiable"] if n != "unit_price"]:
            _to_fixed(v, name, plan.get(name))
        add(v)
    if b := pick(fixed("tooling_eur")):
        v = _mut(b, "quality-levers", "ppm commitment, chargeback and tooling negotiable")
        v.buyer["cost_per_defect"] = max(v.buyer.get("cost_per_defect") or 0, 120)
        _to_negotiable(v, "tooling_eur", [0, 5000, 20000], opening=20000)
        _to_negotiable(v, "ppm_commitment", [100, 500, 2000], opening=2000)
        _to_negotiable(v, "chargeback_eur_per_complaint", [0, 60, 200], opening=0)
        add(v)

    # ---- must-haves
    if b := pick(lambda b: negotiable("payment_days")(b) and not b.buyer.get("must_haves")):
        v = _mut(b, "musthave-payment", "a must-have the opening breaks: payment days >= the reference")
        v.buyer["must_haves"] = [{"field": "payment_days", "op": ">=", "value": v.buyer["reference_payment_days"]}]
        add(v)
    if b := pick(lambda b: b.buyer.get("must_haves")):
        v = _mut(b, "musthave-removed", "the case's must-haves removed")
        v.buyer["must_haves"] = []
        add(v)
    if b := pick(lambda b: not b.buyer.get("must_haves")):
        v = _mut(b, "musthave-standard-term", "a must-have on a field only the quote PDF's standard terms state")
        for sid in v.standards:
            v.standards[sid]["ppm_commitment"] = 400  # kept - but only the quote PDF says so
        v.buyer["must_haves"] = [{"field": "ppm_commitment", "op": "<=", "value": 500}]
        _to_fixed(v, "chargeback_eur_per_complaint", 0)  # ppm is neither negotiable nor fixed
        v.case["fixed_terms"].pop("ppm_commitment", None)
        if "ppm_commitment" in v.case["negotiable"]:
            v.case["negotiable"].remove("ppm_commitment")
            v.case.get("term_options", {}).pop("ppm_commitment", None)
            for terms in v.openings.values():
                terms.pop("ppm_commitment", None)
        add(v)
    if b := pick(lambda b: fixed("incoterm")(b) and not b.buyer.get("must_haves")):
        v = _mut(b, "musthave-eq-fixed", "an == must-have on a fixed term, and a != one")
        v.buyer["must_haves"] = [
            {"field": "incoterm", "op": "==", "value": v.case["fixed_terms"]["incoterm"]},
            {"field": "incoterm", "op": "!=", "value": "XXX"},
        ]
        add(v)
    if b := pick(lambda b: negotiable("contract_months")(b) and not b.buyer.get("must_haves")):
        v = _mut(b, "musthave-contract", "a must-have on the contract term the opening breaks (>= 24 months)")
        v.buyer["must_haves"] = [{"field": "contract_months", "op": ">=", "value": 24}]
        add(v)

    # ---- the alternative
    if b := pick(has_alt):
        v = _mut(b, "alt-none", "the alternative removed (kind none, no terms)")
        v.buyer["alternative"] = {"kind": "none", "ref": None, "terms": {}}
        add(v)
    if b := pick(has_alt):
        v = _mut(b, "alt-key-absent", "no `alternative` key at all")
        v.buyer.pop("alternative", None)
        add(v)
    if b := pick(lambda b: not has_alt(b)):
        v = _mut(b, "alt-added", "an alternative added: a full sheet 6 % above the cheapest opening")
        first = min(
            (s for s in v.case["suppliers"] if v.openings[s].get("unit_price") is not None),
            key=lambda s: v.openings[s]["unit_price"],
        )
        terms = closing_terms(v.case, v.openings[first], v.standards[first])
        terms["unit_price"] = round(terms["unit_price"] * 1.06, 2)
        terms["incoterm"] = _cheapest_incoterm(v)
        v.buyer["alternative"] = {"kind": "quote", "ref": None, "terms": terms}
        add(v)
    if b := pick(has_alt):
        v = _mut(b, "alt-cheaper", "the alternative costs less than the opening (price 8 % under it)", OFF_DATA)
        first = v.case["suppliers"][0]
        v.buyer["alternative"]["terms"]["unit_price"] = round(v.openings[first]["unit_price"] * 0.92, 2)
        add(v)

    # ---- the category goal, relationship parameters
    for goal in GOALS:
        if b := pick(lambda b, goal=goal: b.buyer.get("category_goal") != goal):
            v = _mut(b, f"goal-{goal}", f"category_goal {b.buyer.get('category_goal')} -> {goal}")
            v.buyer["category_goal"] = goal
            if goal in RELATIONSHIP_GOALS:
                v.buyer.setdefault("sustainable_margin_pct", 6)
                v.buyer.setdefault("relationship_eur_per_point", 9000)
            else:
                v.buyer.pop("sustainable_margin_pct", None)
                v.buyer.pop("relationship_eur_per_point", None)
            add(v)
    if b := pick(relationship):
        v = _mut(b, "rel-params-absent", "a relationship goal without margin and EUR-per-point parameters")
        v.buyer.pop("sustainable_margin_pct", None)
        v.buyer.pop("relationship_eur_per_point", None)
        add(v)
    if b := pick(lambda b: not relationship(b)):
        v = _mut(b, "rel-params-on-leverage", "relationship parameters present although the goal is not one")
        v.buyer["category_goal"] = "leverage"
        v.buyer["sustainable_margin_pct"], v.buyer["relationship_eur_per_point"] = 8, 20000
        add(v)
    if b := pick(relationship):
        v = _mut(b, "rel-margin-high", "a relationship goal with a 25 % sustainable margin")
        v.buyer["sustainable_margin_pct"] = 25
        add(v)

    # ---- index clause
    if b := pick(lambda b: not negotiable("index_clause")(b)):
        v = _mut(b, "index-falling", "index clause negotiable, the index is expected to fall 8 %")
        _index_clause(v, "IDX-TEST", -0.08, 2, opening_has=False)
        add(v)
    if b := pick(lambda b: not negotiable("index_clause")(b)):
        v = _mut(b, "index-rising-opened", "the opening carries an index clause, the index is expected to rise 12 %")
        _index_clause(v, "IDX-TEST", 0.12, 3, opening_has=True)
        add(v)
    if b := pick(negotiable("index_clause")):
        v = _mut(b, "index-no-paths", "index clause options but no `index_paths` and no `index_risk_pct`")
        v.buyer.pop("index_paths", None)
        v.buyer.pop("index_risk_pct", None)
        add(v)

    # ---- missing optional fields
    if b := pick():
        v = _mut(b, "buyer-optionals-absent", "every optional buyer field absent (cost.py reads them with .get)")
        for key in ("current_unit_price", "fallback_risk_pct", "index_risk_pct", "late_cost_per_day",
                    "cost_per_defect", "index_paths", "must_haves", "sustainable_margin_pct",
                    "relationship_eur_per_point"):  # fmt: skip
            v.buyer.pop(key, None)
        add(v)
    if b := pick():
        v = _mut(b, "case-optionals-absent", "no title, briefing, trigger_doc, refs, round_limit, set")
        for key in ("title", "briefing", "trigger_doc", "refs", "round_limit", "set"):
            v.case.pop(key, None)
        add(v)
    if b := pick(lambda b: len(b.case.get("term_options", {})) >= 2):
        v = _mut(b, "options-missing-for-field", "a negotiable field without `term_options`")
        name = next(n for n in v.case["negotiable"] if n != "unit_price" and v.case["term_options"].get(n))
        v.case["term_options"].pop(name)
        add(v)
    if b := pick(lambda b: len(b.case["negotiable"]) > 1):
        v = _mut(b, "no-term-options-no-fixed", "no `term_options` and no `fixed_terms` keys")
        v.case.pop("term_options", None)
        fixed_terms = v.case.pop("fixed_terms", {})
        for sid in v.standards:  # what the enquiry fixed is now the supplier's standard
            v.standards[sid] = {**fixed_terms, **v.standards[sid]}
        add(v)

    # ---- incomplete openings
    if b := pick(lambda b: any(len(t) > 1 for t in b.openings.values())):
        v = _mut(b, "opening-price-only", "the opening sheet states a price and nothing else; no standard terms")
        for sid in v.openings:
            v.openings[sid] = {"unit_price": v.openings[sid]["unit_price"]}
            v.standards[sid] = {}
        add(v)
    if b := pick(negotiable("payment_days")):
        v = _mut(b, "opening-no-payment", "the opening leaves payment days out; its standard is 14 days")
        for sid in v.openings:
            v.openings[sid].pop("payment_days", None)
            v.standards[sid]["payment_days"] = 14
        add(v)
    if b := pick():
        v = _mut(b, "no-quote-pdf", "the opening e-mail carries no quote PDF")
        v.quote_attached = False
        add(v)
    if b := pick(single):
        v = _mut(b, "opening-no-price", "the only supplier quotes no price")
        for sid in v.openings:
            v.openings[sid].pop("unit_price", None)
        add(v)
    if b := pick(single):
        v = _mut(b, "opening-no-sheet", "the only supplier sends no term sheet at all")
        for sid in v.openings:
            v.openings[sid] = {}
        add(v)

    # ---- suppliers
    if b := pick(single):
        v = _mut(b, "second-supplier", "a second, unknown supplier quoting 7 % less")
        _add_supplier(v, 0.93)
        add(v)
    if b := pick(single):
        v = _mut(b, "three-suppliers-one-unpriced", "three suppliers: one dearer, one that quotes no price")
        _add_supplier(v, 1.08, "NEW1")
        silent = _add_supplier(v, 1.0, "NEW2")
        v.openings[silent].pop("unit_price", None)
        add(v)
    if b := pick(multi):
        v = _mut(b, "single-supplier", "an RFQ cut down to its dearest supplier")
        dearest = max(v.case["suppliers"], key=lambda s: v.openings[s].get("unit_price") or 0)
        _only_supplier(v, dearest)
        add(v)
    if b := pick(lambda b: single(b) and negotiable("payment_days")(b) and not b.buyer.get("must_haves")):
        v = _mut(b, "cheapest-breaks-musthave", "two suppliers; the cheaper opening breaks a must-have")
        first = v.case["suppliers"][0]
        days = sorted(v.case["term_options"]["payment_days"])
        new = _add_supplier(v, 0.9)
        v.openings[first]["payment_days"], v.openings[new]["payment_days"] = days[-1], days[0]
        v.buyer["must_haves"] = [{"field": "payment_days", "op": ">=", "value": days[-1]}]
        add(v)

    # ---- things the agent has never seen
    if b := pick():
        v = _mut(b, "type-unknown", "an unknown case `type`", UNKNOWN)
        v.case["type"] = "consignment_stock"
        add(v)
    if b := pick():
        v = _mut(b, "type-absent", "no `type` key", UNKNOWN)
        v.case.pop("type", None)
        add(v)
    if b := pick():
        v = _mut(b, "goal-unknown", "an unknown `category_goal`", UNKNOWN)
        v.buyer["category_goal"] = "dual_source"
        add(v)
    if b := pick(relationship):
        v = _mut(b, "goal-unknown-rel-params", "an unknown `category_goal` with relationship parameters", UNKNOWN)
        v.buyer["category_goal"] = "partnership"
        add(v)
    if b := pick():
        v = _mut(b, "goal-absent", "no `category_goal` key", UNKNOWN)
        v.buyer.pop("category_goal", None)
        add(v)
    if b := pick():
        v = _mut(b, "goal-null", "`category_goal` is null", UNKNOWN)
        v.buyer["category_goal"] = None
        add(v)
    if b := pick(multi):
        v = _mut(b, "type-and-goal-unknown", "unknown `type` and `category_goal` in an RFQ", UNKNOWN)
        v.case["type"], v.buyer["category_goal"] = "reverse_auction", "cost_out"
        add(v)
    if b := pick():
        v = _mut(b, "field-unknown-options", "an unknown negotiable field with options", UNKNOWN)
        v.case["negotiable"].append("warranty_months")
        v.case.setdefault("term_options", {})["warranty_months"] = [12, 24, 36]
        for sid in v.openings:
            v.openings[sid]["warranty_months"] = 12
        add(v)
    if b := pick():
        v = _mut(b, "field-unknown-no-options", "an unknown negotiable field without options, not on the opening",
                 UNKNOWN)  # fmt: skip
        v.case["negotiable"].append("consignment_days")
        add(v)
    if b := pick():
        v = _mut(b, "fixed-unknown", "an unknown fixed term and an unknown buyer field", UNKNOWN)
        v.case.setdefault("fixed_terms", {})["packaging"] = "returnable"
        v.buyer["carbon_eur_per_unit"] = 0.4
        add(v)
    if b := pick():
        v = _mut(b, "parts-empty", "`parts` is empty", UNKNOWN)
        v.case["parts"] = []
        add(v)
    if b := pick():
        v = _mut(b, "parts-absent", "no `parts` key", UNKNOWN)
        v.case.pop("parts", None)
        add(v)
    if b := pick(single):
        v = _mut(b, "parts-unknown", "a part the data package does not know", UNKNOWN, OFF_DATA)
        v.case["parts"] = ["part:UNSEEN-1"]
        add(v)
    if b := pick(single):
        v = _mut(b, "supplier-unknown", "the supplier is not in the data package", UNKNOWN)
        old, new = v.case["suppliers"][0], "sup:UNSEEN-9"
        v.case["suppliers"] = [new]
        v.openings, v.standards = {new: v.openings[old]}, {new: v.standards.get(old) or {}}
        v.bodies, v.offer_ids = {}, {}
        add(v)

    # ---- further shapes the API allows (added last: the picks above keep their recorded case)
    if b := pick(lambda b: multi(b) and not relationship(b)):
        v = _mut(b, "musthave-standard-one-fails", "an RFQ must-have on a standard term: one supplier's breaks it")
        _to_fixed(v, "chargeback_eur_per_complaint", 0)
        v.case["fixed_terms"].pop("ppm_commitment", None)
        for i, sid in enumerate(v.case["suppliers"]):
            v.standards[sid]["ppm_commitment"] = 400 if i else 900
        v.buyer["must_haves"] = [
            *(v.buyer.get("must_haves") or []),
            {"field": "ppm_commitment", "op": "<=", "value": 500},
        ]
        add(v)
    if b := pick(fixed("incoterm")):
        v = _mut(b, "musthave-eq-negotiable", "an == must-have on a negotiable incoterm the opening breaks")
        v.buyer["freight_eur_per_unit"] = {"EXW": 0.0, "FCA": 0.5, "DAP": 1.4}
        _to_negotiable(v, "incoterm", ["EXW", "FCA", "DAP"], opening="EXW")
        v.buyer["must_haves"] = [*(v.buyer.get("must_haves") or []), {"field": "incoterm", "op": "==", "value": "DAP"}]
        add(v)
    if b := pick(negotiable("index_clause")):
        v = _mut(b, "musthave-no-index", "a must-have: index_clause == null")
        v.buyer["must_haves"] = [
            *(v.buyer.get("must_haves") or []),
            {"field": "index_clause", "op": "==", "value": None},
        ]
        add(v)
    if b := pick(negotiable("contract_months")):
        v = _mut(b, "contract-single-order", "contract_months options include 0 (a single order), opened at 0")
        v.case["term_options"]["contract_months"] = [0, 12, 24]
        for terms in v.openings.values():
            terms["contract_months"] = 0
        add(v)
    if b := pick():
        v = _mut(b, "horizon-1.5y", "a fractional horizon of 1.5 years")
        v.buyer["horizon_years"] = 1.5
        add(v)
    if b := pick(lambda b: "unit_price" in b.case["negotiable"] and len(b.case["negotiable"]) > 1):
        v = _mut(b, "price-fixed", "the price is fixed by the enquiry; only the other terms are negotiable", UNKNOWN)
        first = v.case["suppliers"][0]
        _to_fixed(v, "unit_price", v.openings[first]["unit_price"])
        add(v)
    for limit in (1, 2):
        if b := pick():
            v = _mut(b, f"round-limit-{limit}", f"round_limit {limit}")
            v.case["round_limit"] = limit
            add(v)
    if b := pick(has_alt):
        v = _mut(b, "alt-without-price", "an alternative of kind quote whose terms carry no price")
        v.buyer["alternative"]["terms"].pop("unit_price", None)
        add(v)
    if b := pick():
        v = _mut(b, "case-facts", "a hidden case's own `facts` and a trigger_doc that exists only there")
        v.case["facts"] = {"doc:HIDDEN-LETTER-1": {"type": "doc", "supplier": v.case["suppliers"][0]}}
        v.case["trigger_doc"] = "doc:HIDDEN-LETTER-1"
        v.case["refs"] = ["doc:HIDDEN-LETTER-1"]
        add(v)
    if b := pick(negotiable("volume_per_year")):
        v = _mut(b, "volume-options-above-need", "volume options above the need, opened at the largest")
        need = v.buyer["need_per_year"]
        v.case["term_options"]["volume_per_year"] = [need, round(need * 1.3), round(need * 1.8)]
        v.buyer["must_haves"] = []
        for terms in v.openings.values():
            terms["volume_per_year"] = round(need * 1.8)
        add(v)

    for key in ("type", "title", "trigger_doc", "refs", "parts", "round_limit"):
        if b := pick():
            v = _mut(b, f"null-{key}", f"`{key}` is null", UNKNOWN)
            v.case[key] = None
            add(v)
    for key in ("current_unit_price", "alternative"):
        if b := pick(has_alt):
            v = _mut(b, f"null-{key}", f"buyer `{key}` is null", UNKNOWN)
            v.buyer[key] = None
            add(v)
    if b := pick(negotiable("effective_date")):
        v = _mut(b, "effective-date-no-current-price", "effective date negotiable, no current price")
        v.buyer["current_unit_price"] = None
        add(v)
    if b := pick(lambda b: fixed("effective_date")(b) and b.buyer.get("current_unit_price")):
        v = _mut(b, "effective-date-negotiable", "effective date negotiable with a must-have on it (ISO dates)")
        start = v.case["fixed_terms"]["effective_date"]
        year, rest = int(start[:4]), start[4:]
        dates = [start, f"{year}-07-01" if rest < "-07-01" else f"{year + 1}-01-01", f"{year + 1}-06-01"]
        _to_negotiable(v, "effective_date", dates, opening=dates[0])
        v.buyer["must_haves"] = [
            *(v.buyer.get("must_haves") or []),
            {"field": "effective_date", "op": ">=", "value": dates[1]},
        ]
        add(v)
    if b := pick():
        v = _mut(b, "goal-other-case", "the category goal in another spelling (upper case)", UNKNOWN)
        v.buyer["category_goal"] = str(v.buyer.get("category_goal")).upper()
        add(v)

    ids = [v.id for v in out]
    assert len(ids) == len(set(ids)), "variant ids must be unique"
    return out
