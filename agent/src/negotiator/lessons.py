"""Lessons from a run: per case what scored, where C went and what the supplier said about each move.

Reads `runs/<run>/sessions/*.json` (written at each case's end, with the arena's trace) and writes
`lessons.md`: score and C against C_open/C_best, the biggest cost blocks, the supplier's reasons per
round, how every argument checked out, and the plan the strategy made (goal, traits). The fastest
loop: play, read lessons.md, change one thing, play again.
"""

import json
from collections import Counter, defaultdict
from pathlib import Path

REASON_CHARS = 400


def load_sessions(run_dir: Path) -> list[dict]:
    out = []
    for path in sorted((run_dir / "sessions").glob("*.json")):
        try:
            out.append(json.loads(path.read_text(encoding="utf-8")))
        except ValueError:
            continue
    return out


def plans(run_dir: Path) -> dict[tuple[str, str], dict]:
    """(session_id, supplier_id) -> the strategy's plan event."""
    path = run_dir / "events.jsonl"
    out = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            e = json.loads(line)
            if e.get("kind") == "plan":
                out[(e.get("session_id"), e.get("supplier_id"))] = e
    return out


def _eur(v) -> str:
    return "-" if v is None else f"{v:,.0f}"


def case_lessons(s: dict, plan_by: dict) -> list[str]:
    o = s.get("outcome", {})
    lines = [
        f"## {o.get('case_id')} - {o.get('title')}",
        "",
        f"type {o.get('type')} · goal **{o.get('goal')}** · strategy {o.get('strategy')} · "
        f"score **{o.get('score')}** · deal {o.get('deal')} ({o.get('end_reason')}) · {o.get('seconds')} s",
        "",
        f"C_open {_eur(o.get('c_open'))} · C_deal {_eur(o.get('c_deal'))} · C_best {_eur(o.get('c_best'))} · "
        f"C_alt {_eur(o.get('c_alt'))}",
    ]
    if o.get("c_open") and o.get("c_best") and o.get("c_deal"):
        left = o["c_deal"] - o["c_best"]
        lines.append(f"left on the table vs C_best: **{_eur(left)}** EUR")
    if bd := o.get("cost_breakdown"):
        top = sorted(((k, v) for k, v in bd.items() if v), key=lambda kv: -abs(kv[1]))[:4]
        lines.append("biggest blocks: " + ", ".join(f"{k} {_eur(v)}" for k, v in top))
    for sid, t in (o.get("threads") or {}).items():
        p = plan_by.get((o.get("session_id"), sid), {})
        traits = ",".join((p.get("profile") or {}).get("traits", [])) or "-"
        lines.append(
            f"- {sid}: {t.get('status')}, {t.get('rounds')} rounds, timeouts {t.get('timeouts')}, traits {traits}, "
            f"their prices {t.get('their_prices')}, ours {t.get('our_prices')}"
        )
    claims = Counter()
    for t in (s.get("threads") or {}).values():
        for m in t.get("messages", []):
            for c in m.get("claim_results") or []:
                claims[c.get("result")] += 1
    if claims:
        lines.append("arguments: " + ", ".join(f"{k} {v}" for k, v in claims.items()))
    trace = s.get("trace") or []
    if trace:
        lines += ["", "supplier's reasons:"]
        for step in trace:
            if step.get("actor") == "buyer" or not step.get("reasons"):
                continue
            reasons = step["reasons"]
            text = " / ".join(reasons) if isinstance(reasons, list) else str(reasons)
            lines.append(f"- r{step.get('round')} {step.get('actor')}: {text[:REASON_CHARS]}")
    if o.get("replay_url"):
        lines.append(f"\nreplay: {o['replay_url']}")
    return lines + [""]


def write_lessons(run_dir: Path) -> Path:
    sessions = load_sessions(run_dir)
    plan_by = plans(run_dir)
    by_goal: dict[str, list[float]] = defaultdict(list)
    for s in sessions:
        o = s.get("outcome", {})
        if o.get("score") is not None:
            by_goal[str(o.get("goal"))].append(o["score"])
    lines = [f"# Lessons - {run_dir.name}", ""]
    if by_goal:
        lines.append("| goal | cases | mean score |")
        lines.append("|---|---|---|")
        for goal, scores in sorted(by_goal.items()):
            lines.append(f"| {goal} | {len(scores)} | {sum(scores) / len(scores):.3f} |")
        lines.append("")
    ordered = sorted(sessions, key=lambda s: s.get("outcome", {}).get("score") or 0)
    for s in ordered:  # worst first: that is where the points are
        lines += case_lessons(s, plan_by)
    path = run_dir / "lessons.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
