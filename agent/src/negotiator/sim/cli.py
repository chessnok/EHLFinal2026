"""`negotiator sim ...`: calibrate, check, bench and serve the local supplier simulator (see `arena.py`)."""

import json
import logging
import os
import statistics
from collections import defaultdict

from rich.console import Console
from rich.table import Table

from negotiator.config import PACKAGE_ROOT, Settings
from negotiator.sim.arena import CalibratedSim, arena_scores, bench, check, serve
from negotiator.sim.calibrate import as_objects, calibrate, load_model, load_sessions
from negotiator.sim.supplier import PERSONAS

console = Console()
MODEL = PACKAGE_ROOT / "data" / "sim" / "model.json"  # git-ignored: fitted from replays, never committed
SIM_RUNS = PACKAGE_ROOT / "runs-sim"  # apart from runs/: `negotiator stats` counts arena sessions only
SUPPLIER_LLM = "<provider>:<model> of the opponent `llm` (default: SIM_LLM, then LLM)"


def _num(value, digits: int = 3) -> str:
    return "–" if value is None else f"{value:.{digits}f}"


def _model(settings: Settings, refit: bool = False) -> dict:
    if refit or not MODEL.is_file():
        sessions = load_sessions(settings.runs_dir)
        if not sessions:
            raise SystemExit(f"no recorded arena sessions under {settings.runs_dir}: play the sandbox first")
        MODEL.parent.mkdir(parents=True, exist_ok=True)
        MODEL.write_text(json.dumps(calibrate(sessions), indent=1, ensure_ascii=False), encoding="utf-8")
    return load_model(MODEL)


def cmd_calibrate(args, settings: Settings) -> None:
    model = _model(settings, refit=True)
    table = Table(title=f"suppliers fitted from {model['sessions']} arena sessions -> {MODEL}")
    for col in ("case", "supplier", "opening", "floor", "below", "floor from", "moves seen"):
        table.add_column(col)
    for key, p in sorted(model["profiles"].items()):
        seen = sum(len(v) for k, v in p.steps.items() if "/" not in k)
        below = f"{(1 - p.floor / p.opening_value) * 100:.1f} %"
        table.add_row(*key.split("|"), _num(p.opening_value, 2), _num(p.floor, 2), below, p.floor_source, str(seen))
    console.print(table)


class SupplierModel:
    """The model behind the opponent `llm`, with a run folder of its own so that its calls and cost are measured."""

    def __init__(self, spec: str | None):
        from negotiator.llm import LLM
        from negotiator.telemetry import Recorder

        self.recorder = Recorder(SIM_RUNS, "sim-supplier-llm", logging.ERROR)
        self.llm = LLM(spec or os.environ.get("SIM_LLM"), self.recorder)

    def close(self, fallbacks: int) -> None:
        from negotiator.report import build_summary

        counters = self.recorder.metrics.snapshot()["counters"]
        self.recorder.close()
        summary = build_summary(self.recorder.dir)
        cost = summary.get("llm_cost_usd")
        tokens = f"{counters.get('llm.tokens.prompt', 0)} in / {counters.get('llm.tokens.completion', 0)} out"
        console.print(
            f"supplier model {self.llm.describe()}: {summary['llm_calls']} calls, {counters.get('llm.errors', 0)} "
            f"failed, {fallbacks} replies left to the fitted supplier; tokens {tokens}; cost "
            + ("APPROX-NOT-MEASURED" if cost is None else f"USD {cost:.4f}")
            + f" ({self.recorder.dir.name})"
        )


def _with_examples(settings: Settings, refit: bool) -> dict:
    """The model for the opponent `llm`: fitted again when the stored one predates the recorded exchanges."""
    model = _model(settings, refit=refit)
    return model if any(p.examples for p in model["profiles"].values()) else _model(settings, refit=True)


def _spread(sessions: list[dict], n: int) -> set[str]:
    """`n` sessions for a check that costs model calls: the newest of each case in turn."""
    by_case = defaultdict(list)
    for t in sessions:
        by_case[t["case"]["case_id"]].append(t["_id"])
    picked: list[str] = []
    while len(picked) < n and any(by_case.values()):
        picked += [ids.pop() for _, ids in sorted(by_case.items()) if ids]
    return set(picked[:n])


def _check_llm(args, settings: Settings) -> None:
    sessions = load_sessions(settings.runs_dir)
    only = _spread(sessions, args.sessions)
    supplier = SupplierModel(args.supplier_llm)
    fitted = check(sessions, seeds=args.seeds, only=only)
    result = check(sessions, seeds=1, llm=supplier.llm, only=only)
    if args.json:
        console.print_json(json.dumps({"fitted": fitted, "llm": result}))
    table = Table(title=f"fitted and llm opponent on the same {result['sessions']} sessions, each left out of its fit")
    for col in ("case", "sessions", "arena", "fitted", "llm", "abs error fitted", "abs error llm",
                "same status fitted", "same status llm"):  # fmt: skip
        table.add_column(col)
    before = {c["case_id"]: c for c in fitted["cases"]}
    for c in result["cases"]:
        f = before.get(c["case_id"], {})
        table.add_row(c["case_id"], str(c["sessions"]), _num(c["real"]), _num(f.get("sim")), _num(c["sim"]),
                      _num(f.get("abs_error")), _num(c["abs_error"]), _num(f.get("same_status"), 2),
                      _num(c["same_status"], 2))  # fmt: skip
    table.add_row("all", str(result["sessions"]), "", "", "", _num(fitted["abs_error"]), _num(result["abs_error"]),
                  _num(fitted["same_status"], 2), _num(result["same_status"], 2))  # fmt: skip
    console.print(table)
    console.print("The buyer's recorded e-mails are replayed; the score is of the offer standing when it accepted.")
    console.print("Same status: the share of replies with the recorded status (open, final offer, agreed).")
    supplier.close(result["fallbacks"])


def cmd_check(args, settings: Settings) -> None:
    if args.opponent == "llm":
        return _check_llm(args, settings)
    result = check(load_sessions(settings.runs_dir), seeds=args.seeds)
    if args.json:
        console.print_json(json.dumps(result))
        return
    table = Table(title="simulator against arena sessions it was not fitted on (leave one out)")
    for col in ("case", "sessions", "arena", "sim", "bias", "abs error", "arena sd between repeats"):
        table.add_column(col)
    for c in result["cases"]:
        table.add_row(c["case_id"], str(c["sessions"]), _num(c["real"]), _num(c["sim"]), _num(c["bias"]),
                      _num(c["abs_error"]), _num(c["arena_sd"]))  # fmt: skip
    table.add_row("all", str(result["sessions"]), "", "", _num(result["bias"]), _num(result["abs_error"]), "")
    console.print(table)
    console.print("The buyer's recorded e-mails are replayed; the score is of the offer standing when it accepted.")


def _pool_table(by_opponent: dict, strategies: list[str], opponents: tuple[str, ...]) -> None:
    """Per opponent: mean score / worst session / share of sessions that closed. Then, against the first strategy,
    on how many opponents each other one is ahead - a change should win on most of them, not on the average."""
    table = Table(title="per opponent: mean / worst / deals")
    table.add_column("opponent", no_wrap=True)
    for name in strategies:
        table.add_column(name, no_wrap=True)
    means = {}
    for opponent in opponents:
        cells = []
        for name in strategies:
            rows = by_opponent[(name, opponent)]
            scores = [r["score"] for r in rows]
            means[(name, opponent)] = statistics.mean(scores)
            deals = sum(r["deal"] for r in rows) / len(rows)
            cells.append(f"{means[(name, opponent)]:.2f} / {min(scores):.2f} / {deals:.0%}")
        table.add_row(opponent, *cells)
    console.print(table)
    for opponent in opponents:
        console.print(f"  {opponent}: {PERSONAS[opponent].about}")
    base = strategies[0]
    for name in strategies[1:]:
        ahead = sum(means[(name, o)] > means[(base, o)] for o in opponents)
        console.print(f"{name} is ahead of {base} on {ahead} of {len(opponents)} opponents")
    console.print("The opponent types other than `fitted` are invented, not fitted: read them as a stress test.")


def cmd_bench(args, settings: Settings) -> None:
    from negotiator.data import WorldData

    free = tuple(n for n, p in PERSONAS.items() if not p.llm)  # `all` leaves out the opponent that costs tokens
    opponents = free if "all" in args.opponents else tuple(args.opponents)
    reads = any(PERSONAS[o].llm for o in opponents)
    model = _with_examples(settings, args.refit) if reads else _model(settings, refit=args.refit)
    if args.without:  # a blind test: fitted without the sessions these strategies played, and not stored
        kept = [t for t in load_sessions(settings.runs_dir) if t["outcome"].get("strategy") not in args.without]
        model = as_objects(calibrate(kept))
        console.print(f"fitted from {len(kept)} sessions, none of them played by {', '.join(args.without)}")
    data = WorldData(settings.data_dir, settings.release_dir)
    case_ids = args.cases or sorted(model["cases"])
    console.print(f"{len(args.strategies)} strategies x {len(case_ids)} cases x {args.reps} repeats on the simulator")
    supplier = SupplierModel(args.supplier_llm) if reads else None
    out = bench(model, settings, data, args.strategies, case_ids, args.reps, SIM_RUNS, strangers=args.strangers,
                opponents=opponents, jitter=args.jitter, supplier_llm=supplier and supplier.llm)  # fmt: skip
    if supplier:
        supplier.close(out["model_replies"]["fallbacks"])
    if len(opponents) > 1 or args.jitter:
        _pool_table(out["by_opponent"], args.strategies, opponents)
        console.print(f"runs under {SIM_RUNS}")
        return
    arena = arena_scores(load_sessions(settings.runs_dir))
    table = Table(title="simulator mean (arena mean)" + (" - strangers" if args.strangers else ""))
    table.add_column("case", no_wrap=True)
    for name in args.strategies:
        table.add_column(name, no_wrap=True)
    pairs = []  # (simulator mean, arena mean) wherever the arena has played that strategy on that case
    for case_id in case_ids:
        cells = []
        for name in args.strategies:
            sim, real = statistics.mean(out["scores"][(name, case_id)]), arena.get((name, case_id))
            cells.append(f"{sim:.2f}" + (f" ({statistics.mean(real):.2f})" if real else ""))
            if real:
                pairs.append((sim, statistics.mean(real)))
        table.add_row(case_id.replace("case:", ""), *cells)
    means = [statistics.mean(statistics.mean(out["scores"][(n, c)]) for c in case_ids) for n in args.strategies]
    table.add_row("mean", *(f"{m:.3f}" for m in means))
    console.print(table)
    if len(pairs) > 1 and not args.strangers:
        gap = statistics.mean(abs(a - b) for a, b in pairs)
        console.print(f"against the arena, over {len(pairs)} strategy-case pairs: mean gap {gap:.3f} score points")
    console.print(f"runs under {SIM_RUNS} (never mix them into benchmark records: the simulator is not the arena)")
    if args.json:
        console.print_json(json.dumps({f"{n}|{c}": v for (n, c), v in out["scores"].items()}))


def cmd_serve(args, settings: Settings) -> None:
    from arena_kit.data import DataPackage

    reads = PERSONAS[args.opponent].llm
    model = _with_examples(settings, False) if reads else _model(settings)
    supplier = SupplierModel(args.supplier_llm) if reads else None
    sim = CalibratedSim(model, DataPackage(settings.data_dir).facts, args.seed, args.strangers, not args.clock,
                        persona=args.opponent, llm=supplier and supplier.llm)  # fmt: skip
    serve(sim, args.port, block=True)


def add_parser(add) -> None:
    """Registers `sim` and its subcommands; `add` is cli.build_parser's helper."""
    from negotiator.strategy import STRATEGIES

    p = add("sim", lambda args, settings: args.sim_func(args, settings), "the local supplier simulator",
            needs_client=False)  # fmt: skip
    sub = p.add_subparsers(dest="sim_cmd", required=True)
    sub.add_parser("calibrate", help="fit the suppliers from runs/").set_defaults(sim_func=cmd_calibrate)
    c = sub.add_parser("check", help="how well the fit predicts sessions it has not seen")
    c.add_argument("--seeds", type=int, default=20)
    c.add_argument("--opponent", choices=["fitted", "llm"], default="fitted",
                   help="llm: the model answers the recorded e-mails, next to the fitted supplier")  # fmt: skip
    c.add_argument("--sessions", type=int, default=20, help="with --opponent llm: sessions to replay (model calls)")
    c.add_argument("--supplier-llm", help=SUPPLIER_LLM)
    c.add_argument("--json", action="store_true")
    c.set_defaults(sim_func=cmd_check)
    b = sub.add_parser("bench", help="play strategies on the simulator, next to their arena scores")
    b.add_argument("strategies", nargs="+", choices=list(STRATEGIES))
    b.add_argument("--cases", nargs="*", help="case ids (default: every case we have recorded)")
    b.add_argument("--reps", type=int, default=5)
    b.add_argument("--strangers", action="store_true", help="each supplier behaves like another fitted supplier")
    b.add_argument("--refit", action="store_true", help="calibrate again from runs/ first")
    b.add_argument("--opponents", nargs="+", default=["fitted"], choices=[*PERSONAS, "all"],
                   help="opponent types to play against (all: the whole pool)")  # fmt: skip
    b.add_argument("--jitter", action="store_true", help="move each supplier's floor at random, per session")
    b.add_argument("--supplier-llm", help=SUPPLIER_LLM)
    b.add_argument("--without", nargs="+", default=[], metavar="STRATEGY",
                   help="fit the suppliers without the sessions these strategies played (a blind test)")  # fmt: skip
    b.add_argument("--json", action="store_true")
    b.set_defaults(sim_func=cmd_bench)
    s = sub.add_parser("serve", help="the simulator as a local arena")
    s.add_argument("--port", type=int, default=8100)
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--strangers", action="store_true")
    s.add_argument("--clock", action="store_true", help="keep the 60-second rule")
    s.add_argument("--opponent", choices=list(PERSONAS), default="fitted")
    s.add_argument("--supplier-llm", help=SUPPLIER_LLM)
    s.set_defaults(sim_func=cmd_serve)
