"""`negotiator` command line: every API call, playing cases with telemetry, reports and statistics.

  negotiator me | health | cases | case <id> | sessions | session <sid> | thread <sid> <supplier>
  negotiator backoffice <sid> | attachment <sid> <attachment_id> -o FILE | board | data
  negotiator play <case_id> [--strategy tactical]       one case, full telemetry, report at the end
  negotiator run --set practice|sandbox [--cases ...]    many cases in parallel
  negotiator final                                       the Live Final (NEGOTIATOR_FINAL=1)
  negotiator report [run_id|latest] | stats              reports and statistics across runs
  negotiator lessons [run_id|latest]                     what each case taught: scores, costs, supplier reasons
  negotiator sim calibrate | check | bench <strategies> | serve     the local supplier simulator (no quota)
Global: --url (e.g. http://127.0.0.1:8000 for arena-sim), --key, --json.
"""

import argparse
import io
import json
import logging
import sys
import zipfile
from pathlib import Path

from rich.console import Console
from rich.table import Table

from negotiator.client import ArenaClient, ArenaError
from negotiator.config import Settings
from negotiator.data import WorldData
from negotiator.lessons import write_lessons
from negotiator.llm import LLM
from negotiator.report import history, write_report
from negotiator.runner import play_case, play_final, play_many
from negotiator.sim.cli import add_parser as add_sim_parser
from negotiator.strategy import NEEDS_LLM, STRATEGIES
from negotiator.telemetry import Recorder

console = Console()


def _settings(args) -> Settings:
    overrides = {}
    if args.url:
        overrides["arena_url"] = args.url.rstrip("/")
    if args.key:
        overrides["api_key"] = args.key
    return Settings.from_env(**overrides)


def _print(args, obj, table: Table | None = None) -> None:
    if args.json or table is None:
        console.print_json(json.dumps(obj, ensure_ascii=False, default=str))
    else:
        console.print(table)


def _data(settings: Settings) -> WorldData | None:
    try:
        return WorldData(settings.data_dir, settings.release_dir)
    except FileNotFoundError as e:
        console.print(f"[yellow]no data package: {e} - strategies run without data[/]")
        return None


def _strategy_factory(args, data: WorldData | None, recorder: Recorder):
    name = args.strategy
    if name not in STRATEGIES:
        raise SystemExit(f"unknown strategy {name!r}; known: {', '.join(STRATEGIES)}")
    llm = None
    if name in NEEDS_LLM:
        llm = LLM(getattr(args, "llm", None), recorder)
        recorder.event("llm_config", model=llm.describe(), base_url=llm.base_url, reasoning=llm.reasoning)
        console.print(f"LLM {llm.describe()}: warming up ...")
        console.print(f"LLM ready in {llm.warm_up():.1f}s")
    return lambda: STRATEGIES[name](data, llm)


def _find_case(client: ArenaClient, case_id: str) -> dict | None:
    """The case file before opening a session (practice, sandbox), so the strategy can read first."""
    for set_ in ("practice", "sandbox"):
        try:
            for c in client.cases(set_):
                if c["case_id"] == case_id:
                    return c
        except ArenaError:
            continue
    return None


def _finish(recorder: Recorder, outcomes: list[dict]) -> None:
    recorder.close()
    summary = write_report(recorder.dir, outcomes)
    write_lessons(recorder.dir)
    table = Table(title=f"run {recorder.run_id}")
    for col in ("case", "deal", "score", "C_open", "C_deal", "C_best", "rounds", "end", "replay"):
        table.add_column(col)
    for o in summary["outcomes"]:
        table.add_row(
            o["case_id"],
            "yes" if o["deal"] else "no",
            _num(o.get("score"), 3),
            _num(o.get("c_open")),
            _num(o.get("c_deal")),
            _num(o.get("c_best")),
            str(o.get("rounds")),
            str(o.get("end_reason")),
            o.get("replay_url") or "",
        )
    console.print(table)
    console.print(
        f"mean score [bold]{_num(summary['mean_score'], 3)}[/] · deals {summary['deals']}/"
        f"{summary['cases']} · claims {summary['claims']} · report: {recorder.dir / 'report.md'}"
    )
    if summary.get("llm_calls"):
        cost = "not priced" if summary["llm_cost_usd"] is None else f"USD {summary['llm_cost_usd']:.4f}"
        console.print(f"llm: {summary['llm_calls']} calls · {cost}")


def _num(value, digits: int = 2) -> str:
    return "–" if value is None else f"{value:,.{digits}f}"


# ---------------------------------------------------------------------- commands
def cmd_health(args, client: ArenaClient) -> None:
    _print(args, {"health": client.health(), "data": client.data_index()})


def cmd_me(args, client: ArenaClient) -> None:
    me = client.me()
    table = Table(title=f"{me.get('team_name')} ({me.get('status')})")
    for col in ("used", "left", "limit", "resets_at"):
        table.add_column(col)
    p = me.get("practice") or {}
    table.add_row(*(str(p.get(c)) for c in ("used", "left", "limit", "resets_at")))
    _print(args, me, table)
    if not args.json and me.get("best"):
        console.print({k: round(v, 3) for k, v in me["best"].items()})


def cmd_cases(args, client: ArenaClient) -> None:
    cases = client.cases(args.set)
    table = Table(title=f"{args.set} cases")
    for col in ("case", "hosted", "type", "goal", "suppliers", "negotiable", "title"):
        table.add_column(col)
    for c in cases:
        table.add_row(
            c["case_id"],
            str(c.get("hosted", "")),
            c["type"],
            c["buyer"].get("category_goal"),
            str(len(c["suppliers"])),
            ", ".join(c["negotiable"]),
            c["title"],
        )
    _print(args, cases, table)


def cmd_case(args, client: ArenaClient) -> None:
    for set_ in ("practice", "sandbox", "final"):
        try:
            for c in client.cases(set_):
                if c["case_id"] == args.case_id:
                    return _print(args, c)
        except ArenaError:
            continue
    raise SystemExit(f"{args.case_id} not found")


def cmd_sessions(args, client: ArenaClient) -> None:
    rows = client.sessions(args.set)
    table = Table(title=f"{args.set} sessions")
    for col in ("session", "case", "status", "end", "deal", "score", "rounds", "created"):
        table.add_column(col)
    for s in rows:
        table.add_row(
            s["session_id"],
            s["case_id"],
            s["status"],
            str(s.get("end_reason")),
            str(s.get("deal")),
            _num(s.get("score"), 3),
            str(s.get("rounds")),
            str(s.get("created_at")),
        )
    _print(args, rows, table)


def cmd_session(args, client: ArenaClient) -> None:
    _print(args, client.session(args.session_id))


def cmd_thread(args, client: ArenaClient) -> None:
    _print(args, client.thread(args.session_id, args.supplier_id))


def cmd_backoffice(args, client: ArenaClient) -> None:
    _print(args, client.backoffice(args.session_id))


def cmd_attachment(args, client: ArenaClient) -> None:
    blob = client.attachment(args.session_id, args.attachment_id)
    Path(args.output).write_bytes(blob)
    console.print(f"{len(blob)} bytes -> {args.output}")


def cmd_board(args, client: ArenaClient) -> None:
    _print(args, client.leaderboard(args.set))


def cmd_data(args, client: ArenaClient) -> None:
    """Download package v1 and the Sunday release (once public) into agent/data/."""
    settings = client.settings
    index = client.data_index()
    target = settings.release_dir.parent
    for name, meta in index.items():
        if not meta.get("url"):
            console.print(f"{name}: not public yet ({meta.get('at')})")
            continue
        blob = client.download_data(name)
        dest = target / name
        dest.mkdir(parents=True, exist_ok=True)
        zipfile.ZipFile(io.BytesIO(blob)).extractall(dest)
        console.print(f"{name}: {len(blob):,} bytes -> {dest}")


def _new_run(args, settings: Settings, label: str) -> tuple[Recorder, ArenaClient]:
    recorder = Recorder(settings.runs_dir, label, logging.DEBUG if args.verbose else logging.INFO)
    return recorder, ArenaClient(settings, recorder)


def cmd_play(args, settings: Settings) -> None:
    recorder, client = _new_run(args, settings, args.case_id.replace("case:", ""))
    data = _data(settings)
    factory = _strategy_factory(args, data, recorder)
    outcome = play_case(client, recorder, args.case_id, factory, data, case=_find_case(client, args.case_id))
    if client.practice_remaining is not None:
        console.print(f"practice sessions left: {client.practice_remaining}")
    _finish(recorder, [outcome])


def cmd_run(args, settings: Settings) -> None:
    probe = ArenaClient(settings)
    cases = probe.cases(args.set)
    ids = args.cases or [c["case_id"] for c in cases if c.get("hosted", True)]
    console.print(f"{len(ids)} case(s): {', '.join(ids)}")
    recorder, client = _new_run(args, settings, f"{args.set}-{args.strategy}")
    data = _data(settings)
    factory = _strategy_factory(args, data, recorder)
    outcomes = play_many(
        client, recorder, ids, factory, data, parallel=args.parallel, cases={c["case_id"]: c for c in cases}
    )
    if client.practice_remaining is not None:
        console.print(f"practice sessions left: {client.practice_remaining}")
    _finish(recorder, outcomes)


def cmd_final(args, settings: Settings) -> None:
    settings = Settings(**{**settings.__dict__, "final_mode": True})
    recorder, client = _new_run(args, settings, f"final-{args.strategy}")
    data = _data(settings)
    outcomes = play_final(client, recorder, _strategy_factory(args, data, recorder), data, parallel=args.parallel)
    _finish(recorder, outcomes)


def cmd_report(args, settings: Settings) -> None:
    runs = sorted(p for p in settings.runs_dir.iterdir() if p.is_dir()) if settings.runs_dir.is_dir() else []
    if not runs:
        raise SystemExit("no runs yet")
    run = runs[-1] if args.run in (None, "latest") else settings.runs_dir / args.run
    summary = write_report(run)
    console.print((run / "report.md").read_text(encoding="utf-8") if not args.json else "")
    if args.json:
        _print(args, summary)


def cmd_lessons(args, settings: Settings) -> None:
    runs = sorted(p for p in settings.runs_dir.iterdir() if p.is_dir()) if settings.runs_dir.is_dir() else []
    if not runs:
        raise SystemExit("no runs yet")
    run = runs[-1] if args.run in (None, "latest") else settings.runs_dir / args.run
    console.print(write_lessons(run).read_text(encoding="utf-8"))


def cmd_stats(args, settings: Settings) -> None:
    stats = history(settings.runs_dir)
    table = Table(title="all runs")
    for col in ("case", "set", "type", "plays", "deals", "best", "mean", "last", "strategy"):
        table.add_column(col)
    for r in stats["cases"]:
        table.add_row(
            r["case_id"],
            str(r["set"]),
            str(r["type"]),
            str(r["plays"]),
            str(r["deals"]),
            _num(r["best"], 3),
            _num(r["mean"], 3),
            _num(r["last"], 3),
            str(r["strategy"]),
        )
    _print(args, stats, table)


def cmd_register(args, client: ArenaClient) -> None:
    _print(args, client.register(args.team_name, args.event_code))


# ---------------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    def options(defaults: bool) -> argparse.ArgumentParser:
        # The same options before and after the command; after it they must not reset what came before.
        p = argparse.ArgumentParser(add_help=False)
        kw = {} if defaults else {"default": argparse.SUPPRESS}
        p.add_argument("--url", help="arena base URL (default ARENA_URL or https://arena.tacto.ai)", **kw)
        p.add_argument("--key", help="API key (default ARENA_API_KEY)", **kw)
        p.add_argument("--json", action="store_true", help="print raw JSON", **kw)
        p.add_argument("-v", "--verbose", action="store_true", help="debug logging on the console", **kw)
        return p

    common = options(defaults=False)
    ap = argparse.ArgumentParser(
        prog="negotiator",
        parents=[options(defaults=True)],
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, func, help_, needs_client=True):
        p = sub.add_parser(name, parents=[common], help=help_)
        p.set_defaults(func=func, needs_client=needs_client)
        return p

    add("health", cmd_health, "is the arena up; the data downloads")
    add("me", cmd_me, "team, practice quota, best scores")
    add("cases", cmd_cases, "case files").add_argument(
        "--set", default="practice", choices=["practice", "sandbox", "final"]
    )
    add("case", cmd_case, "one case file").add_argument("case_id")
    add("sessions", cmd_sessions, "our sessions").add_argument(
        "--set", default="practice", choices=["practice", "sandbox", "final"]
    )
    add("session", cmd_session, "session state, result and trace").add_argument("session_id")
    p = add("thread", cmd_thread, "one thread")
    p.add_argument("session_id")
    p.add_argument("supplier_id")
    add("backoffice", cmd_backoffice, "the supplier's back office after the case").add_argument("session_id")
    p = add("attachment", cmd_attachment, "download a supplier attachment")
    p.add_argument("session_id")
    p.add_argument("attachment_id")
    p.add_argument("-o", "--output", required=True)
    add("board", cmd_board, "leaderboard (for people; blocked in final mode)").add_argument(
        "--set", default="practice", choices=["practice", "final"]
    )
    add("data", cmd_data, "download the data package and the Sunday release")
    p = add("register", cmd_register, "arena-sim only: get a simulator key")
    p.add_argument("team_name")
    p.add_argument("event_code")

    p = add("play", cmd_play, "play one case with telemetry and a report", needs_client=False)
    p.add_argument("case_id")
    p.add_argument("--strategy", default="tactical", choices=list(STRATEGIES))
    p.add_argument("--llm", help="<provider>:<model>, e.g. ollama:qwen3.6:latest or anthropic:claude-haiku-4-5")
    p = add("run", cmd_run, "play many cases in parallel", needs_client=False)
    p.add_argument("--set", default="sandbox", choices=["practice", "sandbox"])
    p.add_argument("--cases", nargs="*", help="case ids (default: every hosted case of the set)")
    p.add_argument("--strategy", default="tactical", choices=list(STRATEGIES))
    p.add_argument("--llm", help="<provider>:<model>, e.g. ollama:qwen3.6:latest or anthropic:claude-haiku-4-5")
    p.add_argument("--parallel", type=int, default=4)
    p = add("final", cmd_final, "the Live Final: waves, in parallel", needs_client=False)
    p.add_argument("--strategy", default="tactical", choices=list(STRATEGIES))
    p.add_argument("--llm", help="<provider>:<model>, e.g. ollama:qwen3.6:latest or anthropic:claude-haiku-4-5")
    p.add_argument("--parallel", type=int, default=10)
    add("report", cmd_report, "rebuild and show a run's report", needs_client=False).add_argument(
        "run", nargs="?", default="latest"
    )
    add(
        "lessons", cmd_lessons, "per case: score, cost blocks, the supplier's reasons", needs_client=False
    ).add_argument("run", nargs="?", default="latest")
    add("stats", cmd_stats, "scores across all runs", needs_client=False)
    add_sim_parser(add)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = _settings(args)
    try:
        if args.needs_client:
            args.func(args, ArenaClient(settings))
        else:
            args.func(args, settings)
    except ArenaError as e:
        console.print(f"[red]{e}[/]")
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
