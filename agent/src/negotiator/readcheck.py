"""`negotiator readcheck`: the model's reading of logged supplier replies next to the regular expressions'.

Before a model's reading is used on the arena it is measured here: every supplier reply of our recorded sessions
(runs/) is read by both, and for each signal the table says how often they agree, what only the model found (with
the words it quoted) and what only the regular expressions found. The recorded status is the one label we have:
a reply the arena marked `final_offer` should read as a last word. Costs model calls, no practice session.
"""

import random
from collections import Counter, defaultdict
from types import SimpleNamespace

from rich.console import Console
from rich.table import Table

from negotiator.reader import Reader
from negotiator.sim.calibrate import load_sessions
from negotiator.strategy.tactical.reading import merge_hints, read_signals
from negotiator.telemetry import Recorder

console = Console()
SIGNALS = ("firm", "pending", "stated_price")


def logged_replies(runs_dir) -> list[dict]:
    """Every supplier reply after the opening: its e-mail, sheets and status, with the case and the sheet before."""
    out = []
    for t in load_sessions(runs_dir):
        for sup, thread in (t.get("threads") or {}).items():
            previous = None
            for i, m in enumerate(thread.get("messages") or []):
                if str(m.get("from", "")).startswith("buyer"):
                    continue
                sheets = m.get("term_sheets") or []
                if i and m.get("body"):
                    out.append({"case": t["case"], "supplier": sup, "session": t["_id"], "reply": m,
                                "previous": previous})  # fmt: skip
                previous = sheets[0].get("terms") if sheets else previous
    return out


def spread(replies: list[dict], n: int, seed: int = 0) -> list[dict]:
    """`n` replies, the cases in turn, distinct e-mail texts first (the bots repeat themselves)."""
    rng = random.Random(seed)
    by_case, seen = defaultdict(list), set()
    for r in replies:
        text = r["reply"].get("body")
        if text not in seen:
            seen.add(text)
            by_case[r["case"]["case_id"]].append(r)
    for rows in by_case.values():
        rng.shuffle(rows)
    picked = []
    while len(picked) < n and any(by_case.values()):
        picked += [rows.pop() for _, rows in sorted(by_case.items()) if rows]
    return picked[:n]


def check(replies: list[dict], llm, recorder: Recorder) -> dict:
    reader = Reader(llm)
    counts, examples, failed = defaultdict(Counter), defaultdict(list), 0
    for r in replies:
        case, reply = r["case"], r["reply"]
        negotiable = case.get("negotiable", [])
        regex = read_signals(reply, negotiable)
        neg = SimpleNamespace(recorder=recorder, case=case, case_id=case["case_id"])
        hints = reader.read(neg, r["supplier"], reply, r["previous"])
        if not hints:
            failed += 1
            continue
        both = merge_hints(read_signals(reply, negotiable), hints, reply, negotiable)
        final = reply.get("status") == "final_offer"
        for name in SIGNALS:
            a, b = bool(getattr(regex, name)), bool(getattr(both, name))
            counts[name]["regex" if a else "neither" if not b else "model only"] += 1
            if name == "firm":
                counts["firm, status final_offer"]["regex" if a else "model only" if b else "neither"] += final
                counts["firm, status open"]["regex" if a else "model only" if b else "neither"] += not final
            if b and not a:
                examples[name].append((r["session"], reply.get("status"), (reply.get("body") or "")[:400]))
        for lever in negotiable:
            a, b = lever in regex.requests, lever in both.requests
            if a or b:
                counts["requests"]["regex" if a else "model only"] += 1
            if b and not a:
                examples["requests"].append((r["session"], lever, (reply.get("body") or "")[:400]))
    tally = {k: dict(v) for k, v in counts.items()}
    return {"counts": tally, "examples": dict(examples), "read": len(replies) - failed, "failed": failed}


def cmd_readcheck(args, settings) -> None:
    from negotiator.llm import LLM
    from negotiator.report import build_summary

    replies = logged_replies(settings.runs_dir)
    picked = spread(replies, args.n, args.seed)
    recorder = Recorder(settings.runs_dir.parent / "runs-sim", "readcheck")
    llm = LLM(args.llm, recorder)
    console.print(
        f"{len(picked)} of {len(replies)} logged replies, read by {llm.describe()} and the regular expressions"
    )
    result = check(picked, llm, recorder)
    recorder.close()
    table = Table(title=f"{result['read']} replies read, {result['failed']} without an answer from the model")
    for col in ("signal", "regex", "model only", "neither"):
        table.add_column(col)
    for name, c in result["counts"].items():
        table.add_row(name, str(c.get("regex", 0)), str(c.get("model only", 0)), str(c.get("neither", 0)))
    console.print(table)
    for name, rows in result["examples"].items():
        console.print(f"[bold]only the model: {name}[/bold]")
        for session, what, body in rows[: args.show]:
            console.print(f"  {session} [{what}] {body!r}")
    summary = build_summary(recorder.dir)
    cost = summary.get("llm_cost_usd")
    console.print(
        f"{summary.get('llm_calls')} calls, cost " + ("APPROX-NOT-MEASURED" if cost is None else f"USD {cost:.4f}")
    )


def add_parser(add) -> None:
    p = add("readcheck", cmd_readcheck, "the model's reading of logged replies against the regular expressions'",
            needs_client=False)  # fmt: skip
    p.add_argument("--llm", help="<provider>:<model> (default: LLM from the environment)")
    p.add_argument("-n", type=int, default=40, help="replies to read (model calls)")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--show", type=int, default=5, help="examples to print per signal")
