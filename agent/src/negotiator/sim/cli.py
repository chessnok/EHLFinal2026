"""`negotiator sim ...`: calibrate, check, bench and serve the local supplier simulator (see `arena.py`)."""

import json
import statistics

from rich.console import Console
from rich.table import Table

from negotiator.config import PACKAGE_ROOT, Settings
from negotiator.sim.arena import CalibratedSim, arena_scores, bench, check, serve
from negotiator.sim.calibrate import calibrate, load_model, load_sessions
from negotiator.sim.supplier import PERSONAS
from negotiator.tracing import enabled as tracing_enabled

console = Console()
MODEL = PACKAGE_ROOT / "data" / "sim" / "model.json"  # git-ignored: fitted from replays, never committed
SIM_RUNS = PACKAGE_ROOT / "runs-sim"  # apart from runs/: `negotiator stats` counts arena sessions only


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


def cmd_check(args, settings: Settings) -> None:
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

    if not tracing_enabled():
        raise SystemExit("no LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY in .env: AGENTS.md forbids a run without them")

    model = _model(settings, refit=args.refit)
    data = WorldData(settings.data_dir, settings.release_dir)
    case_ids = args.cases or sorted(model["cases"])
    console.print(f"{len(args.strategies)} strategies x {len(case_ids)} cases x {args.reps} repeats on the simulator")
    opponents = tuple(PERSONAS) if "all" in args.opponents else tuple(args.opponents)
    out = bench(model, settings, data, args.strategies, case_ids, args.reps, SIM_RUNS, strangers=args.strangers,
                opponents=opponents, jitter=args.jitter)  # fmt: skip
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

    model = _model(settings)
    sim = CalibratedSim(model, DataPackage(settings.data_dir).facts, args.seed, args.strangers, not args.clock)
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
    b.add_argument("--json", action="store_true")
    b.set_defaults(sim_func=cmd_bench)
    s = sub.add_parser("serve", help="the simulator as a local arena")
    s.add_argument("--port", type=int, default=8100)
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--strangers", action="store_true")
    s.add_argument("--clock", action="store_true", help="keep the 60-second rule")
    s.set_defaults(sim_func=cmd_serve)
