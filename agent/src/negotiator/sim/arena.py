"""The middle layer: the kit's `arena-sim` with suppliers fitted from our recorded arena sessions.

Same API as the arena (the kit's simulator underneath), the cases we have played, the arena's own `c_open` and
`c_best` for each as the yardstick, and per supplier a `supplier.Thread` instead of the kit's fixed script. It
costs no practice session and no token: use it to rank strategy changes before a practice run confirms them.

    negotiator sim calibrate          fit the suppliers from runs/ -> data/sim/model.json
    negotiator sim check              how well the fit predicts sessions it has not seen
    negotiator sim bench a b c        play strategies on the simulator, next to their arena scores
    negotiator sim serve              the simulator as a local arena, for `negotiator --url ...`

What the fitted supplier cannot tell you: anything about wording. It reads term sheets and cited IDs, not the
e-mail, so tone, questions, unbacked claims and leaks have no effect on it - on the arena they do. The opponent
`llm` (`llm_supplier.py`) reads the e-mail: a model answers as the supplier did in our replays, for tokens.
"""

import logging
import random
import socket
import statistics
import threading
import time
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

import arena_kit.sim as kit
from arena_kit.cost import closing_terms, cost_breakdown, must_haves_ok, score, total_cost

from negotiator.sim.calibrate import _moves, as_objects, best_cost, calibrate, estimate
from negotiator.sim.llm_supplier import LLMThread
from negotiator.sim.pricing import value_of
from negotiator.sim.supplier import PERSONAS, Profile, Thread

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
SIM_URL, SIM_KEY = "http://127.0.0.1:8100", "sim"  # where `sim serve` listens, and the key it always accepts


def price_cap(case: dict, ref: dict, c_best: float):
    """structure -> the unit price at which it costs the buyer exactly c_best (C is linear in the price)."""

    def cap(structure: dict) -> float:
        c1 = total_cost(case, {**structure, "unit_price": 1.0}, ref)
        c2 = total_cost(case, {**structure, "unit_price": 2.0}, ref)
        return 1.0 + (c_best - c1) / (c2 - c1) if c2 > c1 else 0.0

    return cap


JITTER = 0.3  # with --jitter a floor moves by up to this share of the supplier's room, either way
# `perturb`: per session the supplier's steps and its readiness to call an offer final are scaled, and the round
# limit moves - a strategy fitted to one deterministic bot shows here (the bands are a stress test, not a fit)
PERTURB_STEP = (0.8, 1.25)
PERTURB_FINAL = (0.7, 1.5)
PERTURB_ROUNDS = (-3, -2, -1, 0, 0, 1)
MIN_ROUNDS = 3


def session_profiles(model: dict, case: dict, rng: random.Random, strangers: bool, jitter: bool) -> tuple[dict, float]:
    """The suppliers of one session and the c_best that goes with them. Unchanged, that is the arena's own figure;
    with moved floors it moves by as much as the model's best package does."""
    known = model["results"][case["case_id"]]
    profiles = {sup: model["profiles"][f"{case['case_id']}|{sup}"] for sup in case["suppliers"]}
    before = min(best_cost(case, p) for p in profiles.values()) if jitter else 0.0
    for sup, p in list(profiles.items()):
        changes = {}
        if strangers:  # the same economics, the habits of another supplier
            d = model["profiles"][rng.choice(sorted(model["profiles"]))]
            changes.update(steps=d.steps, finals=d.finals, convinced=d.convinced)
        if jitter:
            changes["floor"] = p.floor + rng.uniform(-JITTER, JITTER) * (p.opening_value - p.floor)
        if changes:
            profiles[sup] = Profile(**{**p.__dict__, **changes})
    c_best = known["c_best"]
    if jitter:
        c_best += min(best_cost(case, p) for p in profiles.values()) - before
        c_best = min(c_best, known["c_open"] - 0.02 * abs(known["c_open"]))  # there is always room to negotiate
    return profiles, c_best


def new_thread(model: dict, case: dict, sup: str, rng: random.Random, profile: Profile | None = None,
               c_best: float | None = None, persona: str = "fitted", llm=None,
               bend: tuple[float, float] | None = None) -> Thread:  # fmt: skip
    """`bend`: (steps x, final-offer rate x) on top of the persona, for a perturbed session."""
    profile = profile or model["profiles"][f"{case['case_id']}|{sup}"]
    c_best = model["results"][case["case_id"]]["c_best"] if c_best is None else c_best
    cap = price_cap(case, profile.ref, c_best)
    if PERSONAS[persona].llm:  # the fitted supplier's money, a model's decisions and words
        return LLMThread(profile, model["pool"], rng, cap=cap, llm=llm)
    who = PERSONAS[persona]
    if bend:
        who = replace(who, step=who.step * bend[0], final=who.final * bend[1])
    return Thread(profile, model["pool"], rng, cap=cap, persona=who)


def _text(value):
    if isinstance(value, dict):  # an index clause, as the arena's quote PDF writes it
        return (
            f"{value['series']}, {round(value['material_share'] * 100)}% material, "
            f"deadband {float(value['deadband_pct'])} %, base {value.get('base_month')}"
        )
    return value


class CalibratedSim(kit.Sim):
    """The kit's simulator with fitted suppliers, the arena's yardstick and no practice quota."""

    def __init__(self, model: dict, facts=None, seed: int = 0, strangers: bool = False, no_clock: bool = True,
                 persona: str = "fitted", jitter: bool = False, llm=None, perturb: bool = False):  # fmt: skip
        super().__init__(model["cases"], facts, no_clock=no_clock)
        self.model, self.seed, self.strangers, self.persona, self.jitter = model, seed, strangers, persona, jitter
        self.perturb = perturb  # floors (as --jitter), step sizes, final-offer rates and the round limit move
        self.llm = llm  # the model behind the opponent `llm`
        if PERSONAS[persona].llm and llm is None:
            raise ValueError("the llm opponent needs a model")
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
        world = random.Random(f"{self.seed}/{case_id}/{self.opened[case_id]}")
        profiles, s["c_best"] = session_profiles(self.model, case, world, self.strangers, self.jitter or self.perturb)
        bend = None
        if self.perturb:
            bend = (world.uniform(*PERTURB_STEP), world.uniform(*PERTURB_FINAL))
            limit = max(MIN_ROUNDS, (case.get("round_limit") or 10) + world.choice(PERTURB_ROUNDS))
            case = s["case"] = {**case, "round_limit": limit}
        for sup in case["suppliers"]:
            rng = random.Random(f"{self.seed}/{case_id}/{self.opened[case_id]}/{sup}")
            sim = new_thread(self.model, case, sup, rng, profiles[sup], s["c_best"], self.persona, self.llm, bend)
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

    def _claims(self, s, th, msg) -> tuple[list[dict], list[str], set[str], list[str]]:
        """The cited IDs as arguments: one per kind, checked for a known ID and a first use, as the kit does;
        a rival quote above the supplier's own price is true but cannot convince. Last: the kind of each result."""
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
        return results, verified, weak, list(groups)[:MAX_CLAIMS]

    def _answer(self, s, th, msg, sheets):
        results, verified, weak, kinds = self._claims(s, th, msg)
        if isinstance(th["sim"], LLMThread):
            checked = [{"type": k, "result": r["result"]} for k, r in zip(kinds, results, strict=True)]
            mail = {"body": msg.get("body", ""), "claims": checked}
            self.lock.release()  # the model takes seconds: other sessions go on (one buyer e-mail per thread at a time)
            try:
                out = th["sim"].reply(s["case"], sheets, verified, frozenset(weak), mail)
            finally:
                self.lock.acquire()
        else:
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
             "c_open": known["c_open"], "c_deal": None, "c_alt": c_alt, "c_best": s["c_best"],
             "score": score(known["c_open"], c_alt, s["c_best"]) if c_alt else 0.0,
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


def replay(model: dict, t: dict, seed: int, llm=None) -> dict | None:
    """Feed one recorded session's buyer e-mails to the simulated suppliers. Returns the simulated and the
    recorded score of the deal the buyer closed (the same supplier, at what stood when it accepted), and in how
    many replies the simulated status was the recorded one. With `llm` the model answers, reading the e-mails."""
    case, o = t["case"], t["outcome"]
    sup = o.get("supplier_id")
    key = f"{case['case_id']}|{sup}"
    if not o.get("deal") or key not in model["profiles"]:
        return None
    th = new_thread(model, case, sup, random.Random(f"{seed}/{t['_id']}"), persona="llm" if llm else "fitted", llm=llm)
    p, real_value, standing = th.profile, th.value, dict(th.terms)
    same = replies = 0
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
        args = [case, sheets, [c["type"] for c in claims], frozenset(weak)]
        if llm:
            said = (buyer.get("interpreted") or {}).get("claims") or []
            checked = [{"type": c["type"], "result": results.get(i, "unchecked")} for i, c in enumerate(said)]
            args.append({"body": buyer.get("body") or "", "claims": checked})
        out = th.reply(*args)
        standing = out["terms"]
        same, replies = same + (out["status"] == m["status"]), replies + 1
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
        "same_status": same,
        "replies": replies,
        "fallbacks": getattr(th, "fallbacks", 0),
    }


def check(sessions: list[dict], seeds: int = 20, llm=None, only: set[str] | None = None, parallel: int = 4) -> dict:
    """Leave one session out: fit on the others, replay it, compare. Per case and overall: the error of the
    simulated score, next to how much the arena's own score varies between repeats of one strategy. `only`: the
    sessions (`_id`) to replay - each one costs model calls when `llm` answers."""
    from concurrent.futures import ThreadPoolExecutor

    def one(i: int) -> dict | None:
        t = sessions[i]
        rest = sessions[:i] + sessions[i + 1 :]
        if not any(x["case"]["case_id"] == t["case"]["case_id"] for x in rest):
            return None  # nothing else recorded for this case: no fit to test
        model = as_objects(calibrate(rest))
        got = [r for seed in range(seeds) if (r := replay(model, t, seed, llm))]
        if not got:
            return None
        return {**got[0], "session": t["_id"], "sim": statistics.mean(g["sim"] for g in got),
                "sim_sd": statistics.pstdev(g["sim"] for g in got),
                "value_error": statistics.mean(g["value_error"] for g in got),
                "same_status": sum(g["same_status"] for g in got), "replies": sum(g["replies"] for g in got),
                "fallbacks": sum(g["fallbacks"] for g in got)}  # fmt: skip

    picked = [i for i, t in enumerate(sessions) if only is None or t["_id"] in only]
    with ThreadPoolExecutor(parallel if llm else 1) as pool:
        rows = [r for r in pool.map(one, picked) if r]
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
            "same_status": sum(r["same_status"] for r in rs) / max(1, sum(r["replies"] for r in rs)),
            "arena_sd": statistics.mean(sds) if sds else None,
        })  # fmt: skip
    return {
        "cases": out,
        "sessions": len(rows),
        "same_status": sum(r["same_status"] for r in rows) / max(1, sum(r["replies"] for r in rows)),
        "replies": sum(r["replies"] for r in rows),
        "fallbacks": sum(r["fallbacks"] for r in rows),
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
    sim.teams.setdefault(SIM_KEY, "local")  # no registration: the usual commands work with `--sim`
    port = port or _free_port()
    server = uvicorn.Server(uvicorn.Config(kit.create_app(sim), host=host, port=port, log_level="warning"))
    url = f"http://{host}:{port}"
    if block:
        print(f"negotiator sim: {url}, key {SIM_KEY!r} - use the usual commands with --sim, e.g.\n"
              f"  negotiator --sim run --set practice --strategy tactical\n"
              f"  board: {url}/leaderboard   a finished case: {url}/replay/<session id>", flush=True)  # fmt: skip
        server.run()
        return url, SIM_KEY, server
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(200):
        try:
            if httpx.get(f"{url}/health", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.05)
    return url, SIM_KEY, server


def arena_scores(sessions: list[dict]) -> dict:
    """(strategy, case) -> the scores our recorded arena sessions got."""
    out = defaultdict(list)
    for t in sessions:
        out[(t["outcome"].get("strategy"), t["case"]["case_id"])].append(t["outcome"]["score"] or 0.0)
    return out


def bench(model: dict, settings, data, strategies: list[str], case_ids: list[str], reps: int, runs_dir: Path,
          strangers: bool = False, parallel: int = 8, llm=None, opponents: tuple[str, ...] = ("fitted",),
          jitter: bool = False, supplier_llm=None, perturb: bool = False) -> dict:  # fmt: skip
    """Play each strategy `reps` times on every case against every opponent; rep i meets the same supplier seed
    for every strategy. Returns (strategy, case) -> scores, (strategy, opponent) -> outcomes, and the run folders.
    `supplier_llm`: the model of the opponent `llm`."""
    from negotiator.client import ArenaClient, _Pacer
    from negotiator.config import Settings
    from negotiator.report import write_report
    from negotiator.runner import play_many
    from negotiator.strategy import STRATEGIES
    from negotiator.telemetry import Recorder

    scores, by_opponent, runs = defaultdict(list), defaultdict(list), []
    model_replies = {"calls": 0, "fallbacks": 0}  # of the opponent `llm`
    for opponent in opponents:
        for rep in range(reps):
            sim = CalibratedSim(model, getattr(data, "facts", None), rep, strangers, persona=opponent, jitter=jitter,
                                llm=supplier_llm, perturb=perturb)  # fmt: skip
            url, key, server = serve(sim)
            local = Settings(**{**settings.__dict__, "arena_url": url, "api_key": key, "runs_dir": runs_dir,
                                "final_mode": False})  # fmt: skip
            for name in strategies:
                sim.opened.clear()  # the session seed counts opened sessions: each strategy starts from the same one
                recorder = Recorder(runs_dir, f"sim-{name}-{opponent}-s{rep}", logging.ERROR)
                client = ArenaClient(local, recorder)
                client.pacer = _Pacer(1000.0)
                # a perturbed session has its own round limit: the case comes from the session, not from the model
                outcomes = play_many(client, recorder, case_ids, lambda n=name: STRATEGIES[n](data, llm), data,
                                     parallel=parallel, cases=None if perturb else model["cases"])  # fmt: skip
                recorder.close()
                write_report(recorder.dir, outcomes)
                runs.append(recorder.dir.name)
                for o in outcomes:
                    scores[(name, o["case_id"])].append(o.get("score") or 0.0)
                    by_opponent[(name, opponent)].append({"score": o.get("score") or 0.0, "deal": bool(o.get("deal"))})
            server.should_exit = True
            for th in (th for s in sim.sessions.values() for th in s["threads"].values()):
                model_replies["calls"] += getattr(th["sim"], "calls", 0)
                model_replies["fallbacks"] += getattr(th["sim"], "fallbacks", 0)
    return {"scores": scores, "by_opponent": by_opponent, "runs": runs, "model_replies": model_replies}
