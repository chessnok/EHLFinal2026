"""Reports: one run (summary.json + report.md) and statistics across all runs.

A run's report reads its folder - sessions/*.json (outcomes), events.jsonl, http.jsonl, metrics.json -
so it can be rebuilt any time with `negotiator report <run>`.
"""

import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from negotiator.telemetry import summarize


def load_outcomes(run_dir: Path) -> list[dict]:
    out = []
    for path in sorted((run_dir / "sessions").glob("*.json")):
        try:
            out.append(json.loads(path.read_text(encoding="utf-8"))["outcome"])
        except (ValueError, KeyError):
            continue
    return out


def _jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def build_summary(run_dir: Path, extra: list[dict] | None = None) -> dict:
    outcomes = load_outcomes(run_dir)
    failures = [e for e in (extra or []) if "error" in e]
    http = _jsonl(run_dir / "http.jsonl")
    events = _jsonl(run_dir / "events.jsonl")
    metrics = json.loads((run_dir / "metrics.json").read_text()) if (run_dir / "metrics.json").is_file() else {}
    scores = [o["score"] for o in outcomes if o.get("score") is not None]
    by_endpoint: dict[str, list[float]] = defaultdict(list)
    for h in http:
        by_endpoint[f"{h['method']} {h['endpoint']}"].append(h["ms"] / 1000)
    claims = Counter()
    for o in outcomes:
        claims.update(o.get("claims") or {})
    by_type: dict[str, list[float]] = defaultdict(list)
    for o in outcomes:
        if o.get("score") is not None:
            by_type[o.get("type") or "?"].append(o["score"])
    return {
        "run_id": run_dir.name,
        "cases": len(outcomes),
        "failed": failures,
        "deals": sum(1 for o in outcomes if o.get("deal")),
        "mean_score": round(statistics.fmean(scores), 4) if scores else None,
        "total_points": round(statistics.fmean(scores) * 100, 1) if scores else None,
        "saved_eur": round(sum(o.get("saved_eur") or 0 for o in outcomes), 2),
        "rounds": sum(o.get("rounds") or 0 for o in outcomes),
        "claims": dict(claims),
        "score_by_type": {k: round(statistics.fmean(v), 3) for k, v in sorted(by_type.items())},
        "end_reasons": dict(Counter(o.get("end_reason") for o in outcomes)),
        "http": {
            "calls": len(http),
            "errors": dict(Counter(h["status"] for h in http if h["status"] >= 400 or h["status"] == 0)),
            "retries": sum(1 for h in http if h.get("attempt")),
            "latency_by_endpoint": {k: summarize(v) for k, v in sorted(by_endpoint.items())},
        },
        "events": dict(Counter(e["kind"] for e in events)),
        "metrics": metrics,
        "outcomes": outcomes,
    }


def _fmt(value, digits: int = 2) -> str:
    if value is None:
        return "–"
    if isinstance(value, float):
        return f"{value:,.{digits}f}"
    return str(value)


def render_markdown(summary: dict) -> str:
    s = summary
    lines = [
        f"# Run {s['run_id']}",
        "",
        f"**Cases:** {s['cases']} · **deals:** {s['deals']} · **mean score:** {_fmt(s['mean_score'], 3)} "
        f"(**{_fmt(s['total_points'], 1)} points**) · **saved vs. opening:** EUR {_fmt(s['saved_eur'])} · "
        f"**rounds:** {s['rounds']}",
        "",
        "## Cases",
        "",
        "| Case | Type | Goal | Deal | Supplier | Score | C_open | C_deal | C_best | C_alt | Rounds | Claims "
        "| End | Time s | Replay |",
        "|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|---|",
    ]
    for o in sorted(s["outcomes"], key=lambda o: o.get("case_id") or ""):
        claims = ", ".join(f"{k} {v}" for k, v in sorted((o.get("claims") or {}).items())) or "–"
        replay = f"[link]({o['replay_url']})" if o.get("replay_url") else "–"
        lines.append(
            f"| {o.get('case_id')} | {o.get('type')} | {o.get('goal')} | {'yes' if o.get('deal') else 'no'} "
            f"| {o.get('supplier_id') or '–'} | {_fmt(o.get('score'), 3)} | {_fmt(o.get('c_open'))} "
            f"| {_fmt(o.get('c_deal'))} | {_fmt(o.get('c_best'))} | {_fmt(o.get('c_alt'))} | {o.get('rounds')} "
            f"| {claims} | {o.get('end_reason')} | {_fmt(o.get('seconds'), 0)} | {replay} |"
        )
    if s["failed"]:
        lines += ["", "## Failed", ""] + [f"- {f.get('case_id')}: {f.get('error')}" for f in s["failed"]]
    if s["score_by_type"]:
        lines += ["", "## Score by case type", "", "| Type | Mean score |", "|---|---:|"]
        lines += [f"| {k} | {v:.3f} |" for k, v in s["score_by_type"].items()]
    lines += ["", "## Negotiation detail", ""]
    for o in sorted(s["outcomes"], key=lambda o: o.get("case_id") or ""):
        lines.append(f"### {o.get('case_id')} – {o.get('title')}")
        lines.append("")
        for sid, t in (o.get("threads") or {}).items():
            theirs = " → ".join(_fmt(p) for p in t.get("their_prices", []))
            ours = " → ".join(_fmt(p) for p in t.get("our_prices", []))
            lines.append(
                f"- **{sid}**: {t.get('rounds')} rounds, status {t.get('status')}, timeouts "
                f"{t.get('timeouts')}  \n  supplier: {theirs or '–'}  \n  us: {ours or '–'}"
            )
        if o.get("terms"):
            lines.append(f"- deal terms: `{json.dumps(o['terms'], ensure_ascii=False)}`")
        if o.get("cost_breakdown"):
            parts = ", ".join(f"{k} {v:,.0f}" for k, v in o["cost_breakdown"].items() if v)
            lines.append(f"- cost breakdown: {parts}")
        lines.append("")
    h = s["http"]
    lines += [
        "## HTTP",
        "",
        f"Calls {h['calls']}, retries {h['retries']}, errors {h['errors'] or 'none'}.",
        "",
        "| Endpoint | n | p50 s | p95 s | max s |",
        "|---|---:|---:|---:|---:|",
    ]
    for k, v in h["latency_by_endpoint"].items():
        lines.append(f"| `{k}` | {v['n']} | {v['p50']} | {v['p95']} | {v['max']} |")
    timings = (s.get("metrics") or {}).get("timings", {})
    keys = ["supplier.reply_seconds", "decision.seconds_after_reply", "strategy.decide", "case.seconds"]
    lines += [
        "",
        "## Timings",
        "",
        "| Metric | n | mean | p50 | p95 | max |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for k in keys:
        if timings.get(k, {}).get("n"):
            v = timings[k]
            lines.append(f"| {k} | {v['n']} | {v['mean']} | {v['p50']} | {v['p95']} | {v['max']} |")
    counters = (s.get("metrics") or {}).get("counters", {})
    if counters:
        lines += ["", "## Counters", "", "| Counter | Value |", "|---|---:|"]
        lines += [f"| {k} | {v} |" for k, v in counters.items() if not k.startswith("event.")]
    lines.append("")
    return "\n".join(lines)


def write_report(run_dir: Path, extra: list[dict] | None = None) -> dict:
    summary = build_summary(run_dir, extra)
    (run_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / "report.md").write_text(render_markdown(summary), encoding="utf-8")
    return summary


def history(runs_dir: Path) -> dict:
    """Across all runs: per case its plays, best and mean score, and the latest strategy that played it."""
    per_case: dict[str, list[dict]] = defaultdict(list)
    for run in sorted(p for p in runs_dir.iterdir() if p.is_dir()) if runs_dir.is_dir() else []:
        for o in load_outcomes(run):
            per_case[o["case_id"]].append(o)
    rows = []
    for case_id, plays in sorted(per_case.items()):
        scores = [p["score"] for p in plays if p.get("score") is not None]
        rows.append(
            {
                "case_id": case_id,
                "set": plays[-1].get("set"),
                "type": plays[-1].get("type"),
                "plays": len(plays),
                "best": max(scores) if scores else None,
                "mean": round(statistics.fmean(scores), 3) if scores else None,
                "last": scores[-1] if scores else None,
                "deals": sum(1 for p in plays if p.get("deal")),
                "strategy": plays[-1].get("strategy"),
                "last_run": plays[-1].get("run_id"),
            }
        )
    return {"cases": rows}
