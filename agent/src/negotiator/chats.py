"""Chats: every negotiation as a readable e-mail thread, to see after a session what went wrong.

Written automatically - `sessions/<sid>.md` as each case ends, `chats.md` (all cases, worst first) at the
end of a run - and on demand with `negotiator chats [run_id|latest]`. Per supplier, round by round: the
e-mail both ways, the term sheets with their C, the argument checks, the supplier's reasons in words (from
the arena's trace) and why we made each move (the strategy's rationale).
"""

import json
from pathlib import Path

from negotiator.lessons import load_sessions
from negotiator.telemetry import safe_name

RATIONALE_SKIP = {"c_sheets", "round"}


def _eur(v) -> str:
    return "-" if v is None else f"{v:,.0f}"


def _terms(terms: dict) -> str:
    return ", ".join(f"{k}={json.dumps(v, ensure_ascii=False)}" for k, v in terms.items() if v is not None)


def _quote(text: str) -> list[str]:
    return [f"> {line}" if line.strip() else ">" for line in (text or "").strip().splitlines()]


def session_chat(s: dict) -> list[str]:
    o, result = s.get("outcome", {}), s.get("result") or {}
    lines = [
        f"# {o.get('case_id')} - {o.get('title')}",
        "",
        f"type {o.get('type')} · goal **{o.get('goal')}** · strategy {o.get('strategy')} · "
        f"score **{o.get('score')}** · deal {o.get('deal')} ({o.get('end_reason')})",
        "",
        f"C_open {_eur(o.get('c_open'))} · C_deal {_eur(o.get('c_deal'))} · C_best {_eur(o.get('c_best'))} · "
        f"C_alt {_eur(o.get('c_alt'))}",
    ]
    if result.get("terms"):
        lines.append(f"deal with {result.get('supplier_id')}: `{_terms(result['terms'])}`")
    if bd := result.get("cost_breakdown") or o.get("cost_breakdown"):
        lines.append("cost blocks: " + ", ".join(f"{k} {_eur(v)}" for k, v in bd.items() if v))
    if o.get("replay_url"):
        lines.append(f"replay: {o['replay_url']}")

    reasons: dict[tuple[str, int], list] = {}
    for step in s.get("trace") or []:
        if step.get("actor") != "buyer" and step.get("reasons"):
            reasons[(step["actor"], step.get("round"))] = step["reasons"]
    moves: dict[tuple[str, int], dict] = {}
    closing: dict[str, list[dict]] = {}
    for d in s.get("decisions") or []:
        r = d.get("rationale") or {}
        if d.get("action") == "message" and r.get("round") is not None:
            moves[(d.get("supplier_id"), r["round"])] = d
        else:
            closing.setdefault(d.get("supplier_id"), []).append(d)

    for sid, thread in (s.get("threads") or {}).items():
        lines += ["", f"## {sid}", ""]
        rnd = 0
        for m in thread.get("messages", []):
            buyer = m.get("from") == "buyer"
            if buyer:
                lines.append(f"### R{rnd} - us")
            else:
                lines.append(f"### R{rnd} - {m.get('from_name') or sid} · status `{m.get('status')}`")
            lines.append("")
            lines += _quote(m.get("body"))
            lines.append("")
            move = moves.get((sid, rnd)) if buyer else None
            c_sheets = ((move or {}).get("rationale") or {}).get("c_sheets") or []
            for i, sheet in enumerate(m.get("term_sheets") or []):
                c = f" · C {_eur(c_sheets[i])}" if i < len(c_sheets) else ""
                lines.append(f"- sheet {chr(65 + i)}: `{_terms(sheet.get('terms') or {})}`{c}")
            if m.get("refs"):
                lines.append(f"- data cited: {', '.join(m['refs'])}")
            if m.get("claim_results"):
                lines.append(
                    "- argument checks: "
                    + ", ".join(f"#{c.get('index')} {c.get('result')}" for c in m["claim_results"])
                )
            if move:
                why = {k: v for k, v in move["rationale"].items() if k not in RATIONALE_SKIP}
                lines.append(f"- **why we moved:** `{json.dumps(why, ensure_ascii=False, default=str)}`")
            if not buyer and reasons.get((sid, rnd)):
                lines.append("- **supplier's reasons:**")
                lines += [f"  - {r}" for r in reasons[(sid, rnd)]]
            lines.append("")
            if not buyer:
                rnd += 1
        for d in closing.get(sid, []):
            why = json.dumps(d.get("rationale") or {}, ensure_ascii=False, default=str)
            lines.append(f"**{d.get('action')}** at {d.get('t')} s: `{why}`")
        if thread.get("closed") or thread.get("timeouts"):
            lines.append(f"thread closed: {thread.get('closed')} · timeouts {thread.get('timeouts')}")
    return lines + [""]


def write_session_chat(run_dir: Path, session: dict) -> Path:
    """`sessions/<sid>.md` next to the session's JSON."""
    path = run_dir / "sessions" / f"{safe_name(str(session.get('outcome', {}).get('session_id')))}.md"
    path.write_text("\n".join(session_chat(session)), encoding="utf-8")
    return path


def write_chats(run_dir: Path) -> Path:
    """`chats.md`: every case of the run, worst score first, and a `sessions/<sid>.md` per case."""
    sessions = sorted(load_sessions(run_dir), key=lambda s: s.get("outcome", {}).get("score") or 0)
    lines = [f"# Chats - {run_dir.name}", ""]
    for s in sessions:
        write_session_chat(run_dir, s)
        lines += session_chat(s) + ["---", ""]
    path = run_dir / "chats.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
