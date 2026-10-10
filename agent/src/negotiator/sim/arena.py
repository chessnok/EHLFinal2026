"""The middle layer: the kit's `arena-sim` with suppliers fitted from our recorded arena sessions.

Same API as the arena (the kit's simulator underneath), the cases we have played, the arena's own `c_open` and
`c_best` for each as the yardstick, and per supplier a `supplier.Thread` instead of the kit's fixed script. It
costs no practice session and no token: use it to rank strategy changes before a practice run confirms them.

    negotiator sim calibrate          fit the suppliers from runs/ -> data/sim/model.json
    negotiator sim check              how well the fit predicts sessions it has not seen
    negotiator sim bench a b c        play strategies on the simulator, next to their arena scores
    negotiator sim serve              the simulator as a local arena, for `negotiator --url ...`

What it cannot tell you: anything about wording. The simulated supplier reads term sheets and cited IDs, not
the e-mail, so tone, questions, unbacked claims and leaks have no effect here - on the arena they do.
"""

import logging
import random
import socket
import statistics
import threading
import time
from collections import defaultdict
from pathlib import Path

import arena_kit.sim as kit
from arena_kit.cost import closing_terms, cost_breakdown, must_haves_ok, score, total_cost

from negotiator.sim.calibrate import _moves, as_objects, calibrate, estimate
from negotiator.sim.pricing import value_of
from negotiator.sim.supplier import Profile, Thread

CLAIM_TYPES = {
    "idx": "index_change",
    "quote": "rival_quote",
    "offer": "rival_quote",
    "sc": "delivery_record",
    "qn": "quality_record",
    "cost": "should_cost",
    "doc": "notice_period",
    "ctr": "notice_period",
    "po": "order_prices",
    "fc": "forecast",
    "news": "news",
}
MAX_CLAIMS = 3


def price_cap(case: dict, ref: dict, c_best: float):
    """structure -> the unit price at which it costs the buyer exactly c_best (C is linear in the price)."""

    def cap(structure: dict) -> float:
        c1 = total_cost(case, {**structure, "unit_price": 1.0}, ref)
        c2 = total_cost(case, {**structure, "unit_price": 2.0}, ref)
        return 1.0 + (c_best - c1) / (c2 - c1) if c2 > c1 else 0.0

    return cap


def new_thread(model: dict, case: dict, sup: str, rng: random.Random, stranger: bool = False) -> Thread:
    profile: Profile = model["profiles"][f"{case['case_id']}|{sup}"]
    if stranger:  # the same economics, the habits of another supplier
        donor = rng.choice(sorted(model["profiles"]))
        d = model["profiles"][donor]
        profile = Profile(**{**profile.__dict__, "steps": d.steps, "finals": d.finals, "convinced": d.convinced})
    cap = price_cap(case, profile.ref, model["results"][case["case_id"]]["c_best"])
    return Thread(profile, model["pool"], rng, cap=cap)


def _text(value):
    if isinstance(value, dict):  # an index clause, as the arena's quote PDF writes it
        return (
            f"{value['series']}, {round(value['material_share'] * 100)}% material, "
            f"deadband {float(value['deadband_pct'])} %, base {value.get('base_month')}"
        )
    return value


class CalibratedSim(kit.Sim):
    """The kit's simulator with fitted suppliers, the arena's yardstick and no practice quota."""

    def __init__(self, model: dict, facts=None, seed: int = 0, strangers: bool = False, no_clock: bool = True):
        super().__init__(model["cases"], facts, no_clock=no_clock)
        self.model, self.seed, self.strangers = model, seed, strangers
        self.opened = defaultdict(int)

    def practice(self, team):
        return {"used": 0, "left": kit.PRACTICE_LIMIT, "limit": kit.PRACTICE_LIMIT, "resets_at": None}

    def open(self, team, case_id):
        case = self.cases.get(case_id)
        if case is None:
            raise kit.Fail(404, "no such case")
        if sum(s["status"] == "open" for s in self._mine(team)) >= kit.MAX_OPEN:
            raise kit.Fail(429, f"at most {kit.MAX_OPEN} open sessions per key")
        sid = f"sim{next(self.ids)}"
        self.opened[case_id] += 1
        s = {"id": sid, "team": team, "case": case, "status": "open", "end_reason": None, "threads": {},
             "files": {}, "offers": {}, "used": set(), "result": None, "trace": [], "moves": [],
             "created_at": self.clock(), "late": set()}  # fmt: skip
        fixed = case.get("fixed_terms", {})
        for sup in case["suppliers"]:
            rng = random.Random(f"{self.seed}/{case_id}/{self.opened[case_id]}/{sup}")
            sim = new_thread(self.model, case, sup, rng, self.strangers)
            p = sim.profile
            standard = {k: v for k, v in p.ref.items() if k not in fixed and k != "unit_price"}
            th = s["threads"][sup] = {"key": sup.split(":", 1)[1], "round": 0, "n": 0, "timeouts": 0,
                                      "closed": None, "last_at": self.clock(), "messages": [], "late": [],
                                      "standard": standard, "opening": p.opening_value, "sim": sim}  # fmt: skip
            self._mail(s, th, "open", dict(p.opening), "Our quote is attached.", ["quote.pdf"])
            s["trace"].append({"round": 0, "actor": sup, "move": kit.structured(th["messages"][0], 0), "reasons": []})
        self.sessions[sid] = s
        return {
            "session_id": sid,
            "case": case,
            "opening": {k: kit.structured(th["messages"][0], 0) for k, th in s["threads"].items()},
            "threads": {k: list(th["messages"]) for k, th in s["threads"].items()},
        }

    def _claims(self, s, th, msg) -> tuple[list[dict], list[str], set[str]]:
        """The cited IDs as arguments: one per kind, checked for a known ID and a first use, as the kit does;
        a rival quote above the supplier's own price is true but cannot convince."""
        refs = list(dict.fromkeys(msg.get("refs", []) + kit.ID_RE.findall(msg.get("body", ""))))
        groups: dict[str, list[str]] = {}
        for ref in refs:
            groups.setdefault(CLAIM_TYPES.get(ref.split(":", 1)[0], "other"), []).append(ref)
        results, verified, weak = [], [], set()
        own = {m["term_sheets"][0]["term_sheet_id"] for m in th["messages"] if m.get("term_sheets") and "status" in m}
        for i, (kind, ids) in enumerate(list(groups.items())[:MAX_CLAIMS]):
            known = all(r in self.facts or r in s["case"].get("facts", {}) or r in s["offers"] for r in ids)
            seen = [(th["key"], r) if kind == "rival_quote" else r for r in ids]
            fresh = any(x not in s["used"] for x in seen)
            if kind == "rival_quote" and all(r in own for r in ids):
                result = "irrelevant"
            else:
                result = "contradicted" if not known else "verified" if fresh else "duplicate"
            results.append({"index": i, "result": result})
            if known:
                s["used"].update(seen)
            if result == "verified":
                verified.append(kind)
                if kind == "rival_quote":
                    prices = [(s["offers"].get(r) or self.facts.get(r) or {}).get("unit_price") for r in ids]
                    if not any(p is not None and p < th["stated"]["unit_price"] for p in prices):
                        weak.add(kind)
        return results, verified, weak

    def _answer(self, s, th, msg, sheets):
        results, verified, weak = self._claims(s, th, msg)
        out = th["sim"].reply(s["case"], sheets, verified, frozenset(weak))
        files = ["quote.pdf"] if out["status"] in ("agreed", "final_offer") else []
        if out["status"] == "walked_away":
            th["closed"] = "walked_away"
        reply = self._mail(s, th, out["status"], out["terms"], " ".join(out["reasons"]) or "Our offer.", files)
        reply["claim_results"] = results
        s["trace"].append(
            {
                "round": th["round"],
                "actor": f"sup:{th['key']}",
                "move": kit.structured(reply, th["round"]),
                "reasons": out["reasons"],
            }  # fmt: skip
        )
        return reply

    def _end(self, s, reason, sup):
        case, ths = s["case"], s["threads"]
        known = self.model["results"][case["case_id"]]
        alt = case["buyer"].get("alternative") or {}
        c_alt = total_cost(case, alt["terms"]) if (alt.get("terms") or {}).get("unit_price") else None
        r = {"ended": True, "deal": False, "supplier_id": None, "offer_id": None, "terms": None,
             "c_open": known["c_open"], "c_deal": None, "c_alt": c_alt, "c_best": known["c_best"],
             "score": score(known["c_open"], c_alt, known["c_best"]) if c_alt else 0.0,
             "must_haves_ok": None, "cost_breakdown": None, "trace": []}  # fmt: skip
        if sup:
            t = closing_terms(case, ths[sup]["stated"], ths[sup]["standard"])
            who = estimate(ths[sup]["sim"].profile)
            ok = must_haves_ok(case, t)
            r.update(deal=True, supplier_id=sup, offer_id=ths[sup]["offer_id"], terms=t, must_haves_ok=ok)
            r.update(c_deal=total_cost(case, t, supplier=who), cost_breakdown=cost_breakdown(case, t, supplier=who))
            r["score"] = score(r["c_open"], r["c_deal"], r["c_best"]) if ok else 0.0
        s.update(status="ended", end_reason=reason, result=r)
        for th in ths.values():
            th["closed"] = th["closed"] or reason

    def attachment(self, team, sid, att):
        s = self.session(team, sid)
        if att not in s["files"]:
            raise kit.Fail(404, "no such attachment in this session")
        kind, stated, standard = s["files"][att]
        if kind.endswith(".xlsx"):
            return kit.xlsx(stated["unit_price"]), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        show = lambda terms: {k: _text(v) for k, v in terms.items()}  # noqa: E731
        fixed = s["case"].get("fixed_terms", {})
        if kind.startswith("order"):
            agreed = show({**fixed, **standard, **stated})
            return kit.pdf("Order confirmation", [("Agreed terms", agreed)]), "application/pdf"
        sections = [
            ("Offered terms", show(stated)),
            (
                "Our standard terms (apply to everything not stated above)",
                show({k: v for k, v in standard.items() if k not in stated}),
            ),  # fmt: skip
            ("Terms fixed by your enquiry", show(fixed)),
        ]
        return kit.pdf("Quote - simulated supplier", sections), "application/pdf"


# -- check: does the fit predict sessions it has not seen? ---------------------------------------------


def replay(model: dict, t: dict, seed: int) -> dict | None:
    """Feed one recorded session's buyer e-mails to the simulated suppliers. Returns the simulated and the
    recorded score of the deal the buyer closed (the same supplier, at what stood when it accepted)."""
    case, o = t["case"], t["outcome"]
    sup = o.get("supplier_id")
    key = f"{case['case_id']}|{sup}"
    if not o.get("deal") or key not in model["profiles"]:
        return None
    th = new_thread(model, case, sup, random.Random(f"{seed}/{t['_id']}"))
    p, real_value, standing = th.profile, th.value, dict(th.terms)
    for buyer, m, _ in _moves(t, sup):
        if buyer is None or m["terms"].get("unit_price") is None:
            continue
        sheets = [x["terms"] for x in buyer.get("term_sheets") or [] if x["terms"].get("unit_price")]
        results = {c["index"]: c["result"] for c in m.get("claim_results") or []}
        claims = [c for i, c in enumerate((buyer.get("interpreted") or {}).get("claims") or [])
                  if results.get(i) == "verified"]  # fmt: skip
        weak = {c["type"] for c in claims if c["type"] == "rival_quote"
                and min((c.get("asserted") or {}).values(), default=0) >= standing.get("unit_price", 0)}  # fmt: skip
        if th.status in ("agreed", "walked_away"):
            break
        standing = th.reply(case, sheets, [c["type"] for c in claims], frozenset(weak))["terms"]
        real_value = value_of(case, p.rates, p.ref, m["terms"])
    r = model["results"][case["case_id"]]
    c_sim = total_cost(case, closing_terms(case, standing, p.ref), supplier=estimate(p))
    gap = max(p.opening_value - p.floor, p.quantum)
    return {
        "case_id": case["case_id"],
        "strategy": o.get("strategy"),
        "real": o["score"],
        "sim": score(r["c_open"], c_sim, r["c_best"]),
        "value_error": (th.value - real_value) / gap,  # in shares of the supplier's whole room to move
    }


def check(sessions: list[dict], seeds: int = 20) -> dict:
    """Leave one session out: fit on the others, replay it, compare. Per case and overall: the error of the
    simulated score, next to how much the arena's own score varies between repeats of one strategy."""
    rows = []
    for i, t in enumerate(sessions):
        rest = sessions[:i] + sessions[i + 1 :]
        if not any(x["case"]["case_id"] == t["case"]["case_id"] for x in rest):
            continue  # nothing else recorded for this case: no fit to test
        model = as_objects(calibrate(rest))
        got = [r for seed in range(seeds) if (r := replay(model, t, seed))]
        if got:
            rows.append({**got[0], "sim": statistics.mean(g["sim"] for g in got),
                         "sim_sd": statistics.pstdev(g["sim"] for g in got),
                         "value_error": statistics.mean(g["value_error"] for g in got)})  # fmt: skip
    by_case = defaultdict(list)
    for r in rows:
        by_case[r["case_id"]].append(r)
    noise = defaultdict(list)  # the arena against itself: repeats of one strategy on one case
    for t in sessions:
        noise[(t["case"]["case_id"], t["outcome"].get("strategy"))].append(t["outcome"]["score"] or 0.0)
    out = []
    for case_id, rs in sorted(by_case.items()):
        sds = [statistics.pstdev(v) for (c, _), v in noise.items() if c == case_id and len(v) > 1]
        out.append({
            "case_id": case_id,
            "sessions": len(rs),
            "real": statistics.mean(r["real"] for r in rs),
            "sim": statistics.mean(r["sim"] for r in rs),
            "bias": statistics.mean(r["sim"] - r["real"] for r in rs),
            "abs_error": statistics.mean(abs(r["sim"] - r["real"]) for r in rs),
            "arena_sd": statistics.mean(sds) if sds else None,
        })  # fmt: skip
    return {
        "cases": out,
        "sessions": len(rows),
        "bias": statistics.mean(r["sim"] - r["real"] for r in rows) if rows else None,
        "abs_error": statistics.mean(abs(r["sim"] - r["real"]) for r in rows) if rows else None,
        "rows": rows,
    }


# -- bench: strategies on the simulator ----------------------------------------------------------------


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def serve(sim: CalibratedSim, port: int | None = None, host: str = "127.0.0.1", block: bool = False):
    """The simulator as a local arena. Returns (url, key of a registered team, server)."""
    import httpx
    import uvicorn

    kit.MAX_CALLS = 10**6  # no calls-per-second limit on a laptop
    port = port or _free_port()
    server = uvicorn.Server(uvicorn.Config(kit.create_app(sim), host=host, port=port, log_level="warning"))
    url = f"http://{host}:{port}"
    if block:
        print(f"negotiator sim: {url}  (register a key: negotiator --url {url} register <team> sim)", flush=True)
        server.run()
        return url, None, server
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(200):
        try:
            if httpx.get(f"{url}/health", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.05)
    key = httpx.post(f"{url}/v1/register", json={"team_name": "bench", "event_code": "sim"}).json()["api_key"]
    return url, key, server


def arena_scores(sessions: list[dict]) -> dict:
    """(strategy, case) -> the scores our recorded arena sessions got."""
    out = defaultdict(list)
    for t in sessions:
        out[(t["outcome"].get("strategy"), t["case"]["case_id"])].append(t["outcome"]["score"] or 0.0)
    return out


def bench(model: dict, settings, data, strategies: list[str], case_ids: list[str], reps: int, runs_dir: Path,
          strangers: bool = False, parallel: int = 8, llm=None) -> dict:  # fmt: skip
    """Play each strategy `reps` times on every case; rep i meets the same supplier seed for every strategy.
    Returns (strategy, case) -> scores, and the run folders under `runs_dir`."""
    from negotiator.client import ArenaClient, _Pacer
    from negotiator.config import Settings
    from negotiator.report import write_report
    from negotiator.runner import play_many
    from negotiator.strategy import STRATEGIES
    from negotiator.telemetry import Recorder

    scores, runs = defaultdict(list), []
    for rep in range(reps):
        url, key, server = serve(CalibratedSim(model, getattr(data, "facts", None), seed=rep, strangers=strangers))
        local = Settings(**{**settings.__dict__, "arena_url": url, "api_key": key, "runs_dir": runs_dir,
                            "final_mode": False})  # fmt: skip
        for name in strategies:
            recorder = Recorder(runs_dir, f"sim-{name}-s{rep}", logging.ERROR)
            client = ArenaClient(local, recorder)
            client.pacer = _Pacer(1000.0)
            outcomes = play_many(client, recorder, case_ids, lambda n=name: STRATEGIES[n](data, llm), data,
                                 parallel=parallel, cases=model["cases"])  # fmt: skip
            recorder.close()
            write_report(recorder.dir, outcomes)
            runs.append(recorder.dir.name)
            for o in outcomes:
                scores[(name, o["case_id"])].append(o.get("score") or 0.0)
        server.should_exit = True
    return {"scores": scores, "runs": runs}
