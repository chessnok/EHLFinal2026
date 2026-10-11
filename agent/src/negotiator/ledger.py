"""The argument ledger: every fact that plays into our hands, collected from the data and from the supplier's
own e-mails as the case goes on, each used once (the arena counts an ID once per case) and spent where it answers
what the supplier just said.

Sources, all cheap (SQL and regular expressions, milliseconds):
  data       a cost driver of the part that fell over the latest months - a recent window ending at the series'
             latest month, checkable by two index IDs (an honest "now", not a window picked from the past)
  its words  the drivers it cites ("AS-14404 rose 5.9 % in twelve months and is 45 % of our cost"): if the very
             driver it names has fallen recently, that is the strongest answer we have - its own argument, turned;
             its hedge ("coverage only extends to March 2027": market moves reach it later); free capacity
Each fact carries its sentence and the IDs the arena checks; a sentence without an ID states no figure.
"""

import re

from negotiator.data import Evidence, WorldData

CITED_DRIVER = re.compile(
    r"\b([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+)\s+rose\s+[\d.,]+\s?%\s+in twelve months and is\s+(\d+)\s?%", re.I
)
HEDGE = re.compile(
    r"(?:coverage|covered|bought (?:\w+ )?forward|fixed prices?)[^.]{0,60}?(?:until|extends to|to)\s+"
    r"((?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{4})",
    re.I,
)
FREE_CAPACITY = re.compile(r"free capacity|spare capacity|capacity available", re.I)
MIN_DROP = 0.5  # % - a smaller move is noise, not an argument

# ---------------------------------------------------------------- what the arena counts as one argument
DATA_ID = re.compile(r"\b(?:idx|sc|po|fc|qn|offer|quote|cost|doc|ctr|news):[A-Za-z0-9@._:-]*[A-Za-z0-9]")
# The arena reads the cited IDs of a message into arguments of one kind each, merges the IDs of one kind (two
# windows of one index series, a scorecard and a complaint), orders them by kind and reads at most three. This
# model reproduces the arena's own reading (`interpreted.claims` in the trace) of 1031 of the 1033 buyer messages
# in our 293 practice replays (one-off script over agent/data/replays, 11 Oct 2026).
KIND_ORDER = {"index": 0, "rival": 1, "record": 2, "orders": 3, "forecast": 4, "should_cost": 5, "notice": 6}
# Kinds the arena counts once per supplier whatever the ID: a second forecast (fc:360011 after fc:360010 on
# case P07, 33 times) and a complaint after the scorecard or another complaint (P08, P11) came back `duplicate`.
# An index counts once per series (runs.md P-33), orders once per part (api.md), a rival offer once per ID.


def argument_key(ref: str, facts: dict | None = None) -> tuple:
    """The unit the arena counts an argument by: the kind, plus the series, part or ID where those count apart."""
    prefix = ref.split(":", 1)[0]
    if prefix == "idx":
        return ("index", ref.split(":", 1)[1].split("@")[0])
    if prefix in ("offer", "quote"):
        return ("rival", ref)
    if prefix in ("sc", "qn"):
        return ("record",)
    if prefix == "po":
        return ("orders", ((facts or {}).get(ref) or {}).get("part") or ref)
    if prefix == "fc":
        return ("forecast",)
    if prefix == "cost":
        return ("should_cost",)
    if prefix in ("doc", "ctr"):
        return ("notice",)
    return (prefix, ref)


def arguments_read(body: str, refs: list[str] | None, facts: dict | None = None) -> list[tuple[tuple, set[str]]]:
    """The arguments the arena reads from one of our messages, in the order of its `claim_results`."""
    ids = DATA_ID.findall(body or "")
    ids += [r for r in refs or [] if r not in ids]
    groups: dict[tuple, set[str]] = {}
    for ref in ids:
        groups.setdefault(argument_key(ref, facts), set()).add(ref)
    seen = {k: i for i, k in enumerate(groups)}
    order = sorted(groups, key=lambda k: (KIND_ORDER.get(k[0], 9), k[1] if k[0] == "index" else "", seen[k]))
    return [(k, groups[k]) for k in order][:3]


def recent_drop(data: WorldData, series: str) -> tuple[str, str, float, int] | None:
    """The steepest fall of a series over a window that ends at its latest month (1-12 months)."""
    rows = data.query(
        "SELECT id, month, value FROM index_values WHERE series_id = ? ORDER BY month DESC", (series,), limit=13
    )
    if len(rows) < 2 or not rows[0]["value"]:
        return None
    later = rows[0]
    best = None
    for k, earlier in enumerate(rows[1:], 1):
        if not earlier["value"]:
            continue
        pct = (later["value"] / earlier["value"] - 1) * 100
        if best is None or pct < best[2]:
            best = (earlier["id"], later["id"], pct, k)
    return best if best and best[2] <= -MIN_DROP else None


# api.md, "What counts": an index argument is "2 × `idx`, one series, ≤ 12 months apart, ending within the last 12
# months of the data". The window may end before the series' latest month; we keep its end one month inside that
# bound (the data's latest month over all series, not this series'), since a window "too old" is `irrelevant` and an
# irrelevant result bans the kind for the supplier.
MAX_SPAN = 12  # months between the two IDs
MAX_AGE = 10  # months the window's end may lie before the data's latest month


def _month_no(month: str) -> int:
    year, mon = month.split("-")[:2]
    return int(year) * 12 + int(mon) - 1


def steepest_drop(data: WorldData, series: str) -> tuple[str, str, float, int] | None:
    """The steepest fall of a series over any window the arena accepts (`MAX_SPAN`, `MAX_AGE`), not only one that
    ends at its latest month: P02's copper notation fell 2.2 % from 2026-01 to 2026-03 and has risen since."""
    end = data.query("SELECT max(month) AS m FROM index_values")
    if not end or not end[0]["m"]:
        return None
    last = _month_no(end[0]["m"])
    rows = [
        (r["id"], _month_no(r["month"]), r["value"])
        for r in data.query(
            "SELECT id, month, value FROM index_values WHERE series_id = ? ORDER BY month DESC",
            (series,),
            limit=MAX_SPAN + MAX_AGE + 2,
        )
        if r["value"]
    ]
    best = None
    for later_id, later_no, later_value in rows:
        if later_no < last - MAX_AGE:
            continue
        for earlier_id, earlier_no, earlier_value in rows:
            if 1 <= later_no - earlier_no <= MAX_SPAN:
                pct = (later_value / earlier_value - 1) * 100
                if best is None or pct < best[2]:
                    best = (earlier_id, later_id, pct, later_no - earlier_no)
    return best if best and best[2] <= -MIN_DROP else None


def _drop_evidence(
    data: WorldData, series: str, weight: float, cited: bool, all_windows: bool = False
) -> Evidence | None:
    drop = steepest_drop(data, series) if all_windows else recent_drop(data, series)
    if not drop:
        return None
    earlier, later, pct, months = drop
    name = series
    rows = data.query("SELECT name FROM index_series WHERE id = ?", (series,))
    if rows and rows[0]["name"]:
        name = rows[0]["name"].split(",")[0].split("(")[0].strip()
    lead = f"You cite {series}: " if cited else ""
    span = "month" if months == 1 else f"{months} months"
    latest = data.query("SELECT max(month) AS m FROM index_values WHERE series_id = ?", (series,))
    if all_windows and latest and later.split("@")[-1] != latest[0]["m"]:
        window = f"from {earlier.split('@')[-1]} to {later.split('@')[-1]}"  # not "the last" months: it rose since
    else:
        window = f"over the last {span}"
    return Evidence(
        kind="recent_drop",
        refs=[earlier, later],
        sentence=f"{lead}{name} fell {abs(pct):.1f}% {window} ({earlier}, {later}).",
        strength=(4.0 if cited else 1.5) + weight * abs(pct),
        meta={"series": series, "pct": round(pct, 2), "months": months, "cited": cited},
    )


def data_facts(data: WorldData | None, part_ids: list[str], all_windows: bool = False) -> list[Evidence]:
    """Before the first move: the part's cost drivers that have fallen recently (`all_windows`: over any window the
    arena accepts, one per series)."""
    if not data or not part_ids:
        return []
    marks = ",".join("?" for _ in part_ids)
    out, seen = [], set()
    for d in data.query(f"SELECT series_id, weight FROM cost_drivers WHERE part_id IN ({marks})", tuple(part_ids)):
        if all_windows and d["series_id"] in seen:
            continue  # the arena counts one argument per series
        seen.add(d["series_id"])
        if e := _drop_evidence(data, d["series_id"], float(d["weight"] or 0), cited=False, all_windows=all_windows):
            out.append(e)
    return out


def reply_facts(data: WorldData | None, body: str, all_windows: bool = False) -> list[Evidence]:
    """From its e-mail: the drivers it cites that have fallen recently, its hedge, its free capacity."""
    out = []
    if data:
        for series, share in CITED_DRIVER.findall(body or ""):
            if data.query("SELECT 1 FROM index_series WHERE id = ?", (series,)):
                if e := _drop_evidence(data, series, float(share) / 100, cited=True, all_windows=all_windows):
                    out.append(e)
    if m := HEDGE.search(body or ""):
        out.append(
            Evidence(
                kind="their_hedge",
                refs=[],
                sentence=f"As you wrote, your material is covered until {m.group(1)}: market moves do not reach "
                "your costs before then.",
                strength=3.0,
            )
        )
    if FREE_CAPACITY.search(body or ""):
        out.append(
            Evidence(
                kind="their_capacity",
                refs=[],
                sentence="You mention free capacity: our order fills it from the first call-off.",
                strength=1.0,
            )
        )
    return out
