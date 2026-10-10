"""Fit the simulated suppliers from our recorded arena sessions (`runs/*/sessions/*.json`).

Per supplier and case: its opening and standard terms (as quoted), its pricing rates (from the alternatives
it quoted in one e-mail), its floor (the price at which the best package it could still accept costs exactly
the `c_best` the arena published for the case), and tables of what it did after each kind of buyer move.
The result is a JSON file under `agent/data/` (git-ignored): values from replays never enter the code.
"""

import itertools
import json
import statistics
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

from arena_kit.cost import closing_terms, must_haves_ok, relationship_cost, total_cost
from arena_kit.docs import quote_terms

from negotiator.sim.pricing import FEATURES, features, fit_rates, freight_leg, price_for, value_of
from negotiator.sim.supplier import Profile

POOL_RIDGE, OWN_RIDGE = 1e-4, 2e-4
CLARIFY = "clarify this internally"
TOOK = "took it into account"
FLOOR_MARGIN = 0.25  # an unidentified floor sits this share of the observed give below the lowest offer seen


def load_sessions(runs_dir: Path) -> list[dict]:
    """Every recorded arena session with a result (simulator runs are kept elsewhere)."""
    out = []
    for path in sorted(runs_dir.glob("*/sessions/*.json")):
        t = json.loads(path.read_text(encoding="utf-8"))
        if t.get("trace") and (t.get("outcome") or {}).get("c_best") is not None:
            t["_id"] = f"{path.parent.parent.name}/{path.stem}"
            out.append(t)
    return out


def opening_of(t: dict, sup: str) -> tuple[dict, dict, dict]:
    """A supplier's opening sheet, its standard terms and its opening structure in full."""
    case, first = t["case"], t["threads"][sup]["messages"][0]
    text = next((a.get("text") for a in first.get("attachments") or [] if a.get("text")), "") or ""
    standard = quote_terms(text).get("standard", {})
    opening = first["term_sheets"][0]["terms"]
    return opening, standard, closing_terms(case, opening, {**standard, **case.get("fixed_terms", {})})


def _moves(t: dict, sup: str):
    """The thread as (buyer move or None, supplier move, reasons), the opening first."""
    buyer = None
    for e in t["trace"]:
        m = e["move"]
        if e["actor"] == "buyer":
            if m.get("supplier_id") == sup and m.get("type") in ("message", "timeout"):
                buyer = m
        elif e["actor"] == sup:
            yield buyer, m, e.get("reasons") or []
            buyer = None


def _rates(sessions: list[dict]) -> tuple[dict, dict]:
    pairs = defaultdict(list)
    for t in sessions:
        case = t["case"]
        for sup in t["threads"]:
            ref = opening_of(t, sup)[2]
            for _, m, _ in _moves(t, sup):
                for alt in m.get("alternatives") or []:
                    a = alt.get("terms", alt)
                    if a.get("unit_price") is None or m["terms"].get("unit_price") is None:
                        continue
                    pairs[(case["case_id"], sup)].append(
                        (
                            features(case, m["terms"], ref),
                            m["terms"]["unit_price"] - freight_leg(case, m["terms"], ref),
                            features(case, a, ref),
                            a["unit_price"] - freight_leg(case, a, ref),
                        )
                    )
    pool = fit_rates([p for v in pairs.values() for p in v], {}, POOL_RIDGE)
    return pool, {k: fit_rates(v, pool, OWN_RIDGE) for k, v in pairs.items()}


def combos(case: dict, min_lead: int | None = None):
    """Every structure the case allows (without a price) that keeps the must-haves."""
    fields = [f for f in case["negotiable"] if f != "unit_price"]
    options = [case["term_options"].get(f) or [None] for f in fields]
    for values in itertools.product(*options):
        terms = dict(zip(fields, values, strict=True))
        if min_lead is not None and (terms.get("lead_time_days") or min_lead) < min_lead:
            continue
        yield terms


def best_cost(case: dict, p: Profile, value: float | None = None) -> float:
    """C of the best package the supplier accepts at `value` (default: its floor), every lever applied."""
    value, best = p.floor if value is None else value, float("inf")
    for terms in combos(case, p.min_lead):
        sheet = {**terms, "unit_price": round(price_for(case, p.rates, p.ref, value, terms), 2)}
        if must_haves_ok(case, sheet, p.ref):
            best = min(best, total_cost(case, sheet, p.ref))
    return best


def _floor_for(case: dict, p: Profile, c_best: float) -> float:
    """The value at which the supplier's best package costs exactly c_best (bisection: C rises with the value)."""
    lo, hi = p.opening_value * 0.3, p.opening_value * 1.2
    for _ in range(50):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if best_cost(case, p, mid) < c_best else (lo, mid)
    return hi


def _kind(case, p: Profile, buyer, reasons, prev_status, prev_reasons, best_buyer) -> tuple[str, float | None]:
    """What the buyer did before a recorded supplier move, in the words of `supplier.KINDS`."""
    sheets = [s["terms"] for s in (buyer or {}).get("term_sheets") or [] if s["terms"].get("unit_price")]
    top = max((value_of(case, p.rates, p.ref, s) for s in sheets), default=None)
    moved = top is not None and (best_buyer is None or top > best_buyer + 1e-9)
    text = " ".join(reasons)
    if prev_status == "final_offer":
        return "final", top
    if any(CLARIFY in r for r in prev_reasons):
        return "pending", top
    if "rival quote data you cited; it holds and" in text:
        return "rival", top
    if TOOK in text:
        return "claim", top
    return ("moved" if moved else "still"), top


def calibrate(sessions: list[dict]) -> dict:
    """The model: one profile per (case, supplier), the pool over all of them, and the cases themselves."""
    pool_rates, own_rates = _rates(sessions)
    profiles: dict[str, Profile] = {}
    cases, results, seen = {}, {}, defaultdict(list)
    for t in sessions:
        case, o = t["case"], t["outcome"]
        cases[case["case_id"]] = case
        results[case["case_id"]] = {"c_open": o["c_open"], "c_best": o["c_best"], "c_alt": o.get("c_alt")}
        for sup in t["threads"]:
            key = f"{case['case_id']}|{sup}"
            if key not in profiles:
                opening, standard, ref = opening_of(t, sup)
                rates = own_rates.get((case["case_id"], sup), pool_rates)
                profiles[key] = Profile(sup, opening, ref, standard, rates, floor=0.0)
            seen[key].append(t)

    # what each supplier showed: its lowest value, its price steps, the fastest delivery it refused to beat
    lowest = {}
    for key, p in profiles.items():
        case = cases[key.split("|")[0]]
        prices, refused = [], []
        for t in seen[key]:
            for buyer, m, _ in _moves(t, p.supplier_id):
                if m["terms"].get("unit_price") is None:
                    continue
                prices.append(m["terms"]["unit_price"])
                asked = [s["terms"].get("lead_time_days") for s in (buyer or {}).get("term_sheets") or []]
                got = m["terms"].get("lead_time_days")
                if got is not None and asked and all(a is not None and a < got for a in asked):
                    refused.append(got)
        p.min_lead = min(refused) if refused else None
        p.quantum = 0.1 if all(abs(x * 10 - round(x * 10)) < 1e-6 for x in prices) else 0.01
        lowest[key] = min(
            value_of(case, p.rates, p.ref, m["terms"])
            for t in seen[key]
            for _, m, _ in _moves(t, p.supplier_id)
            if m["terms"].get("unit_price") is not None
        )

    # floors: per case the supplier whose floor explains c_best, the others below what they showed
    for case_id, case in cases.items():
        keys = [k for k in profiles if k.startswith(case_id + "|")]
        r = results[case_id]
        by_alt = r["c_alt"] is not None and abs(r["c_alt"] - r["c_best"]) < 0.02
        fits = {} if by_alt else {k: _floor_for(case, profiles[k], r["c_best"]) for k in keys}
        able = {k: f for k, f in fits.items() if f < lowest[k]}
        maker = min(able, key=lambda k: best_cost(case, profiles[k], lowest[k])) if able else None
        for k in keys:
            p = profiles[k]
            if k == maker:
                p.floor, p.floor_source = fits[k], "c_best"
            else:
                guess = lowest[k] - FLOOR_MARGIN * (p.opening_value - lowest[k])
                p.floor, p.floor_source = max(guess, fits.get(k, 0.0)), "below the lowest offer seen"
            p.floor = round(min(p.floor, lowest[k]), 4)

    # the tables: steps per kind, final offers per reply number, arguments that convinced
    for key, p in profiles.items():
        case = cases[key.split("|")[0]]
        steps, finals, convinced = defaultdict(list), defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
        costs, walks = [], [0, 0]
        for t in seen[key]:
            value, status, prev_reasons, best_buyer, n = p.opening_value, "open", [], None, 0
            for buyer, m, reasons in _moves(t, p.supplier_id):
                if status == "final_offer" and buyer and buyer.get("term_sheets") and m["status"] != "agreed":
                    walks[0] += m["status"] == "walked_away"
                    walks[1] += 1
                if buyer is None or m["terms"].get("unit_price") is None:
                    prev_reasons = reasons
                    continue
                kind, top = _kind(case, p, buyer, reasons, status, prev_reasons, best_buyer)
                best_buyer = max(x for x in (best_buyer, top) if x is not None) if top is not None else best_buyer
                new = value_of(case, p.rates, p.ref, m["terms"])
                gap = value - p.floor
                if m["status"] != "agreed" and gap > p.quantum / 2:
                    share = min(1.0, max(0.0, (value - new) / gap))
                    clarify = any(CLARIFY in r for r in reasons)
                    steps[kind].append([round(share, 4), clarify])
                    if n == 0:
                        steps[kind + "/first"].append([round(share, 4), clarify])
                if status != "final_offer" and m["status"] != "agreed":
                    slot = finals[f"{min(n + 1, 9)}/{'still' if kind == 'still' else 'move'}"]
                    slot[0] += m["status"] == "final_offer"
                    slot[1] += 1
                for c in (buyer.get("interpreted") or {}).get("claims") or []:
                    label = c["type"].replace("_", " ")
                    checked = [r for r in reasons if f"the {label} data you cited" in r]
                    if checked:
                        convinced[c["type"]][0] += any(TOOK in r for r in checked)
                        convinced[c["type"]][1] += 1
                value, status, prev_reasons, n = new, m["status"], reasons, n + 1
            charge = (t["outcome"].get("cost_breakdown") or {}).get("relationship") or 0
            if charge > 0 and t["outcome"].get("supplier_id") == p.supplier_id:
                costs.append(_full_cost(case, p, t["outcome"]["terms"], charge))
        p.steps, p.finals, p.convinced, p.walks = dict(steps), dict(finals), dict(convinced), walks
        p.full_cost = round(statistics.median(costs), 4) if costs else None

    pool = Profile("pool", {"unit_price": 1.0}, {}, {}, pool_rates, floor=0.0)
    pool.walks = [sum(p.walks[i] for p in profiles.values()) for i in (0, 1)]
    for table in ("steps", "finals", "convinced"):
        merged: dict = {}
        for p in profiles.values():
            for k, v in getattr(p, table).items():
                if table == "steps":
                    merged[k] = merged.get(k, []) + v
                else:
                    merged[k] = [a + b for a, b in zip(merged.get(k, [0, 0]), v, strict=True)]
        setattr(pool, table, merged)
    return {
        "cases": cases,
        "results": results,
        "profiles": {k: asdict(p) for k, p in profiles.items()},
        "pool": asdict(pool),
        "sessions": len(sessions),
        "features": list(FEATURES),
    }


def _full_cost(case: dict, p: Profile, terms: dict, charge: float) -> float:
    """The supplier's full cost per unit that makes the kit's relationship term equal the recorded charge."""
    lo, hi = 0.0, terms["unit_price"] * 1.5
    for _ in range(50):
        mid = (lo + hi) / 2
        got = relationship_cost(case, terms, supplier=estimate(p, mid))
        lo, hi = (mid, hi) if got < charge else (lo, mid)
    return hi


def estimate(p: Profile, full_cost: float | None = None) -> dict | None:
    """The kit's `supplier` argument for the relationship term of C, where the full cost is known."""
    cost = p.full_cost if full_cost is None else full_cost
    if cost is None:
        return None
    return {"standard": p.ref, "interest_rate": max(0.0, p.rates.get("pay", 0.08)), "full_cost": cost}


def load_model(path: Path) -> dict:
    return as_objects(json.loads(path.read_text(encoding="utf-8")))


def as_objects(model: dict) -> dict:
    """A model as the simulator uses it: profiles as objects (also for a freshly calibrated one)."""
    raw = json.loads(json.dumps(model))
    raw["profiles"] = {k: Profile(**v) for k, v in raw["profiles"].items()}
    raw["pool"] = Profile(**raw["pool"])
    return raw
