"""The data package as an in-memory SQLite database plus the citable facts (facts.json).

Loads `data/*.csv` of package v1 (the submodule's `data/` folder is the same as package.zip) and, once
downloaded, the Sunday release. Hidden cases may carry their own `facts`; `with_case` returns a view that adds them.

The `evidence_*` helpers return arguments the arena can check: the IDs and the figure computed here,
one sentence each - the strategy decides which to use.
"""

import copy
import csv
import json
import sqlite3
import threading
from dataclasses import dataclass, field
from pathlib import Path

MAX_ROWS = 500


@dataclass
class Evidence:
    """One checkable argument: a sentence with its figure next to the IDs it rests on."""

    kind: str  # index | scorecard | quality | rival_offer | quote | should_cost | notice | forecast
    refs: list[str]
    sentence: str
    strength: float = 0.0  # how much it should help us, for ranking
    meta: dict = field(default_factory=dict)


class WorldData:
    def __init__(self, root: Path, release: Path | None = None) -> None:
        self.root = Path(root)
        if not (self.root / "facts.json").is_file():
            raise FileNotFoundError(f"no facts.json in {self.root}")
        self.facts: dict[str, dict] = json.loads((self.root / "facts.json").read_text(encoding="utf-8"))
        self.release = release if release and (release / "facts.json").is_file() else None
        self._lock = threading.Lock()
        self.db = sqlite3.connect(":memory:", check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        roots = [self.root] + ([self.release] if self.release else [])
        for base in roots:
            for path in sorted((base / "data").glob("*.csv")):
                self._load_csv(path)
        if self.release:
            self.facts |= json.loads((self.release / "facts.json").read_text(encoding="utf-8"))

    def _load_csv(self, path: Path) -> None:
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        if not rows:
            return
        table, columns = path.stem, list(rows[0].keys())
        existing = {r[1] for r in self.db.execute(f'PRAGMA table_info("{table}")')}
        if not existing:
            self.db.execute(f'CREATE TABLE "{table}" ({", ".join(f"{_q(c)}" for c in columns)})')
        else:  # the release adds rows to a table of the package; add columns it lacks
            for c in columns:
                if c not in existing:
                    self.db.execute(f'ALTER TABLE "{table}" ADD COLUMN {_q(c)}')
        marks = ", ".join("?" for _ in columns)
        names = ", ".join(_q(c) for c in columns)
        self.db.executemany(
            f'INSERT INTO "{table}" ({names}) VALUES ({marks})',
            [[_typed(row[c]) for c in columns] for row in rows],
        )

    # ------------------------------------------------------------------ generic access
    def query(self, sql: str, params: tuple | dict = (), limit: int = MAX_ROWS) -> list[dict]:
        if sql.lstrip().split(None, 1)[0].lower() not in {"select", "with"}:
            raise ValueError("read-only: SELECT or WITH only")
        with self._lock:
            return [dict(r) for r in self.db.execute(sql, params).fetchmany(limit)]

    def tables(self) -> dict[str, int]:
        names = [r["name"] for r in self.query("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        return {n: self.query(f'SELECT count(*) AS n FROM "{n}"')[0]["n"] for n in names}

    def fact(self, ref: str) -> dict | None:
        return self.facts.get(ref)

    def with_case(self, case: dict) -> "WorldData":
        """A view for one case: its own facts (the package's plus the case's), the tables shared.

        The final plays cases in parallel on one WorldData: merging a hidden case's facts into it would make
        them citable - and wrong - in every other case. The caller must use the returned view."""
        view = copy.copy(self)
        view.facts = {**self.facts, **(case.get("facts") or {})}
        return view

    def document_text(self, doc_id: str) -> str | None:
        rows = self.query("SELECT file FROM documents WHERE id = ?", (doc_id,))
        for base in [self.root] + ([self.release] if self.release else []):
            if rows and rows[0]["file"] and (base / rows[0]["file"]).is_file():
                return (base / rows[0]["file"]).read_text(encoding="utf-8")
        return None

    # ------------------------------------------------------------------ dossier
    def supplier(self, supplier_id: str) -> dict:
        rows = self.query("SELECT * FROM suppliers WHERE id = ?", (supplier_id,))
        intel = self.query("SELECT * FROM supplier_intel WHERE supplier_id = ?", (supplier_id,))
        return {**(rows[0] if rows else {"id": supplier_id}), "intel": intel[0] if intel else None}

    def dossier(self, supplier_id: str, part_ids: list[str]) -> dict:
        """Everything the data says about one supplier and the case's parts, for the transcript."""
        q = self.query
        parts = ",".join("?" for _ in part_ids) or "''"
        return {
            "supplier": self.supplier(supplier_id),
            "scorecards": q(
                "SELECT * FROM scorecards WHERE supplier_id = ? ORDER BY quarter DESC LIMIT 4", (supplier_id,)
            ),
            "contracts": q("SELECT * FROM contracts WHERE supplier_id = ?", (supplier_id,)),
            "price_history": q(
                f"SELECT * FROM price_conditions WHERE supplier_id = ? AND part_id IN ({parts}) ORDER BY valid_from",
                (supplier_id, *part_ids),
            ),
            "negotiations": q(
                "SELECT * FROM negotiation_history WHERE supplier_id = ? ORDER BY date DESC LIMIT 10",
                (supplier_id,),
            ),
            "documents": q(
                "SELECT id, date, kind, subject FROM documents WHERE supplier_id = ? ORDER BY date",
                (supplier_id,),
            ),
            "news": q(
                "SELECT id, date, topic, headline FROM news WHERE supplier_id = ? ORDER BY date",
                (supplier_id,),
            ),
            "should_cost": q(f"SELECT * FROM should_cost WHERE part_id IN ({parts})", tuple(part_ids)),
            "cost_drivers": q(f"SELECT * FROM cost_drivers WHERE part_id IN ({parts})", tuple(part_ids)),
        }

    # ------------------------------------------------------------------ checkable arguments
    def index_change(self, series: str, months: int = 12) -> tuple[str, str, float] | None:
        """(earlier id, later id, change %) over the last `months` of the series."""
        rows = self.query(
            "SELECT id, month, value FROM index_values WHERE series_id = ? ORDER BY month DESC",
            (series,),
            limit=months + 1,
        )
        if len(rows) < 2:
            return None
        later, earlier = rows[0], rows[min(months, len(rows) - 1)]
        if not earlier["value"]:
            return None
        return earlier["id"], later["id"], (later["value"] / earlier["value"] - 1) * 100

    def evidence_indices(self, part_ids: list[str], asked_pct: float | None = None) -> list[Evidence]:
        """The part's cost drivers whose index rose less than the supplier asks (or fell)."""
        out = []
        drivers = self.query(
            f"SELECT d.series_id, d.weight, s.name FROM cost_drivers d LEFT JOIN index_series s ON s.id = d.series_id "
            f"WHERE d.part_id IN ({','.join('?' for _ in part_ids)})",
            tuple(part_ids),
        )
        for d in drivers:
            change = self.index_change(d["series_id"])
            if not change:
                continue
            earlier, later, pct = change
            gap = (asked_pct if asked_pct is not None else 0.0) - pct
            if gap <= 0 or pct > 0:
                # a driver that rose supports the supplier even when it rose less than it asks: case:P10
                # answered "your figures confirm our case: that driver rose" - only falling drivers argue for us
                continue
            m0, m1 = earlier.split("@")[1], later.split("@")[1]
            name = (d["name"] or d["series_id"]).split(",")[0].split("(")[0].strip()
            out.append(
                Evidence(
                    kind="index",
                    refs=[earlier, later],
                    sentence=f"{name} changed {pct:+.1f}% from {m0} to {m1} ({earlier}, {later}).",
                    strength=float(d["weight"] or 0) * gap,
                    meta={"series": d["series_id"], "weight": d["weight"], "change_pct": round(pct, 2)},
                )
            )
        return sorted(out, key=lambda e: -e.strength)

    def evidence_scorecard(self, supplier_id: str) -> list[Evidence]:
        rows = self.query(
            "SELECT * FROM scorecards WHERE supplier_id = ? ORDER BY quarter DESC LIMIT 1", (supplier_id,)
        )
        if not rows:
            return []
        sc, out = rows[0], []
        if sc["otd_pct"] is not None and sc["otd_pct"] < 95:
            out.append(
                Evidence(
                    kind="scorecard",
                    refs=[sc["id"]],
                    sentence=f"Your on-time delivery was {sc['otd_pct']:.1f}% in the twelve months to {sc['quarter']} "
                    f"({sc['id']}), against our target of 95%.",
                    strength=(95 - sc["otd_pct"]) / 5,
                    meta={"otd_pct": sc["otd_pct"]},
                )
            )
        if sc["ppm"] and sc["ppm"] > 500:
            out.append(
                Evidence(
                    kind="quality",
                    refs=[sc["id"]],
                    sentence=f"Your quality was {sc['ppm']:.0f} ppm in the twelve months to {sc['quarter']} "
                    f"({sc['id']}).",
                    strength=sc["ppm"] / 1000,
                    meta={"ppm": sc["ppm"]},
                )
            )
        return out

    def evidence_notice(self, trigger_doc: str | None, supplier_id: str) -> list[Evidence]:
        """A price letter that gives less notice than the framework contract requires."""
        doc = self.fact(trigger_doc) if trigger_doc else None
        if not doc or doc.get("days") is None:
            return []
        for ctr in self.query("SELECT id, notice_days FROM contracts WHERE supplier_id = ?", (supplier_id,)):
            agreed = ctr["notice_days"]
            if agreed and doc["days"] < agreed:
                return [
                    Evidence(
                        kind="notice",
                        refs=[trigger_doc, ctr["id"]],
                        sentence=f"Your letter gives {doc['days']} days' notice ({trigger_doc}), while our framework "
                        f"agreement requires {agreed} days ({ctr['id']}).",
                        strength=(agreed - doc["days"]) / 30,
                        meta={"given": doc["days"], "agreed": agreed},
                    )
                ]
        return []

    def evidence_should_cost(
        self, part_ids: list[str], price: float, supplier_id: str | None = None, margin: float = 1.12
    ) -> list[Evidence]:
        out = []
        for row in self.query(
            f"SELECT id, unit_cost, supplier_id FROM should_cost WHERE part_id IN ({','.join('?' for _ in part_ids)})",
            tuple(part_ids),
        ):
            # the estimate of this supplier's own plant counts from 3 % under its quote: P10's supplier "took
            # it into account", the arena's worked example on P01 cites it at 4.5 % (competitions-info.md).
            # Another plant's estimate (error 5-15 %) only from `margin`
            own = bool(supplier_id) and row["supplier_id"] == supplier_id
            if row["unit_cost"] and price > row["unit_cost"] * (min(margin, 1.03) if own else margin):
                out.append(
                    Evidence(
                        kind="should_cost",
                        refs=[row["id"]],
                        sentence=f"Our should-cost estimate for this part is EUR {row['unit_cost']:.2f} ({row['id']}).",
                        # under 12 % it is a weak argument and goes last: ahead of the forecast it took P01's
                        # fourth round and the final offer came at 131.80 instead of 131.30 (P-26)
                        strength=(price / row["unit_cost"] - 1) * 5 if price > row["unit_cost"] * 1.12 else 0.1,
                        meta={"unit_cost": row["unit_cost"]},
                    )
                )
        return out

    def evidence_complaints(self, part_ids: list[str], supplier_id: str, since: str) -> list[Evidence]:
        """Our quality notifications on these parts from this supplier since `since`, newest first: each one
        a fresh, checkable argument (its own ID, date and ppm) for a later round."""
        parts = set(part_ids)
        rows = [
            (ref, f)
            for ref, f in self.facts.items()
            if ref.startswith("qn:")
            and f.get("part") in parts
            and f.get("supplier") == supplier_id
            and (f.get("date") or "") >= since
            and f.get("ppm")
        ]
        rows.sort(key=lambda r: r[1]["date"], reverse=True)
        return [
            Evidence(
                kind="complaint",
                refs=[ref],
                sentence=f"Our quality notification of {f['date']} on this part found {f['ppm']:,} ppm ({ref}).",
                strength=1.5,
            )
            for ref, f in rows
        ]

    def evidence_forecast(self, part_ids: list[str]) -> list[Evidence]:
        """Our latest demand forecast per part (shared with suppliers): the answer to "which volume can you commit to?"
        when volume is not negotiable. The arena checks the recorded change in %."""
        out = []
        for part in part_ids:
            refs = sorted(r for r in self.facts if r.startswith(f"fc:{part.split(':')[-1]}@"))
            fact = self.facts.get(refs[-1]) if refs else None
            if not fact or fact.get("change_pct") is None:
                continue
            volume = fact.get("volume_per_year", "the stated")
            out.append(
                Evidence(
                    kind="forecast",
                    refs=[refs[-1]],
                    sentence=f"Our latest forecast puts our need at {volume} units a year, "
                    f"a change of {fact['change_pct']:+.1f}% ({refs[-1]}).",
                    strength=0.2,
                    meta={"change_pct": fact["change_pct"], "volume_per_year": fact.get("volume_per_year")},
                )
            )
        return out

    def evidence_orders(self, part_ids: list[str], supplier_id: str, price: float | None) -> list[Evidence]:
        """Our last orders of this part from this supplier, by ID - what we pay today, checked by the arena."""
        if not price or len(part_ids) != 1:
            return []
        rows = self.query(
            "SELECT id, price FROM po_lines WHERE part_id = ? AND supplier_id = ? ORDER BY order_date DESC LIMIT 3",
            (part_ids[0], supplier_id),
        )
        rows = [r for r in rows if self.fact(r["id"])]
        if len(rows) < 2 or len({r["price"] for r in rows}) != 1 or rows[0]["price"] >= price:
            return []
        paid = rows[0]["price"]
        ids = [r["id"] for r in rows]
        return [
            Evidence(
                kind="orders",
                refs=ids,
                sentence=f"Our last orders for this part were at EUR {paid:,.2f} ({', '.join(ids)}).",
                strength=3.0 + (price / paid - 1) * 20,
                meta={"paid": paid},
            )
        ]

    def evidence_orders_per_part(self, part_ids: list[str], supplier_id: str) -> list[Evidence]:
        """A bundle: our last orders of each part from this supplier, one argument per part ("order lines of
        different parts are separate arguments", api.md). The bundle's price is not the parts' prices, so there is no
        comparison with the quote - the orders say what we pay today, checked by the arena."""
        if len(part_ids) < 2:
            return []
        out = []
        for part in part_ids:
            rows = self.query(
                "SELECT id, price FROM po_lines WHERE part_id = ? AND supplier_id = ? ORDER BY order_date DESC LIMIT 3",
                (part, supplier_id),
            )
            rows = [r for r in rows if self.fact(r["id"])]
            if len(rows) < 2 or len({r["price"] for r in rows}) != 1:
                continue
            ids = [r["id"] for r in rows]
            per = self.fact(ids[0]).get("price_unit") or 1
            unit = f" per {per:,}" if per != 1 else ""
            out.append(
                Evidence(
                    kind="orders",
                    refs=ids,
                    sentence=f"Our last orders for {part} were at EUR {rows[0]['price']:,.2f}{unit} "
                    f"({', '.join(ids)}).",
                    strength=0.5,
                    meta={"paid": rows[0]["price"], "part": part, "price_unit": per},
                )
            )
        return out

    def evidence_quote(self, quote_id: str | None) -> list[Evidence]:
        """The buyer's alternative quote, if the case has one."""
        q = self.fact(quote_id) if quote_id else None
        if not q or q.get("unit_price") is None:
            return []
        return [
            Evidence(
                kind="quote",
                refs=[quote_id],
                sentence=f"We hold another quote at EUR {q['unit_price']:.2f} ({quote_id}).",
                strength=1.0,
                meta={"unit_price": q["unit_price"]},
            )
        ]


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _typed(value: str):
    if value == "":
        return None
    try:
        return int(value) if value.lstrip("-").isdigit() else float(value)
    except ValueError:
        return value
