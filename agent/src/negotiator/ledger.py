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


def _drop_evidence(data: WorldData, series: str, weight: float, cited: bool) -> Evidence | None:
    drop = recent_drop(data, series)
    if not drop:
        return None
    earlier, later, pct, months = drop
    name = series
    rows = data.query("SELECT name FROM index_series WHERE id = ?", (series,))
    if rows and rows[0]["name"]:
        name = rows[0]["name"].split(",")[0].split("(")[0].strip()
    lead = f"You cite {series}: " if cited else ""
    span = "month" if months == 1 else f"{months} months"
    return Evidence(
        kind="recent_drop",
        refs=[earlier, later],
        sentence=f"{lead}{name} fell {abs(pct):.1f}% over the last {span} ({earlier}, {later}).",
        strength=(4.0 if cited else 1.5) + weight * abs(pct),
        meta={"series": series, "pct": round(pct, 2), "months": months, "cited": cited},
    )


def data_facts(data: WorldData | None, part_ids: list[str]) -> list[Evidence]:
    """Before the first move: the part's cost drivers that have fallen recently."""
    if not data or not part_ids:
        return []
    marks = ",".join("?" for _ in part_ids)
    out = []
    for d in data.query(f"SELECT series_id, weight FROM cost_drivers WHERE part_id IN ({marks})", tuple(part_ids)):
        if e := _drop_evidence(data, d["series_id"], float(d["weight"] or 0), cited=False):
            out.append(e)
    return out


def reply_facts(data: WorldData | None, body: str) -> list[Evidence]:
    """From its e-mail: the drivers it cites that have fallen recently, its hedge, its free capacity."""
    out = []
    if data:
        for series, share in CITED_DRIVER.findall(body or ""):
            if data.query("SELECT 1 FROM index_series WHERE id = ?", (series,)):
                if e := _drop_evidence(data, series, float(share) / 100, cited=True):
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
