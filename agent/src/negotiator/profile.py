"""What the data says about a supplier: its situation (traits) and what will move it.

Call notes, letters, e-mails and news in the package follow recognisable patterns - "could you pay
our invoices within 10 days", "price changes above 2 % need the approval of their pricing committee",
"they bought their copper forward". Each pattern is a trait; the strategy turns traits into tactics
(which levers to offer, which arguments to use or skip, how fast to move). Pure SQL and regular
expressions: fast enough to run after the session opened, no language model on the clock.

Traits:
  cash_short          wants to be paid early; a shorter payment term is worth more to it than to us
  approval_ladder     bigger price moves need a committee: expect small steps, keep asking
  wants_volume        reviews small accounts / calls us "not strategic": volume and term buy price
  underutilised       idle capacity: needs the work, price can move
  full_order_book     fully booked: wants firm long commitments, price moves little
  open_book           offered to show its calculation: ask for the cost breakdown, cite should-cost
  not_tracking_costs  does not follow its own cost indices: index figures disarm it
  hedged              bought forward / fixed prices: market index figures are "not its reality"
  price_frozen        no room on list price: trade payment, term, logistics instead
  relationship        reminds us of partnership / calls us a reference customer: tone matters
  below_cost          past renewals settled below its full cost: little room left, do not squeeze
  we_pay_late         Hollerau paid it late: goodwill is low, keeping our payment terms helps
"""

import re
from dataclasses import dataclass, field

from negotiator.data import WorldData

PATTERNS: dict[str, list[str]] = {
    "cash_short": [
        r"pay (?:our invoices|earlier)",
        r"cash discount",
        r"cash and the banks",
        r"bank is watching",
        r"short[- ]time work",
        r"short hours",
    ],
    "approval_ladder": [r"pricing committee", r"approval of (?:their|our|the) (?:pricing|board|head office)"],
    "wants_volume": [
        r"customers with volume",
        r"not strategic",
        r"reorganising our range around our key accounts",
        r"sharpens its focus",
    ],
    "underutilised": [
        r"take additional parts at short notice",
        r"second shift has been on hold",
        r"shop floor was idle",
        r"short[- ]time work",
    ],
    "full_order_book": [
        r"order intake is very strong",
        r"very high capacity utilisation",
        r"fully booked",
        r"firm, long-term commitments",
        r"binding \d+-month commitment",
    ],
    "open_book": [r"walk us through their calculation", r"hourly rates and material"],
    "not_tracking_costs": [
        r"not followed his material and energy prices",
        r"own spreadsheet",
        r"office manager does the costing",
    ],
    "hedged": [r"bought .* forward", r"covered at fixed prices", r"not our reality"],
    "price_frozen": [
        r"no room on price",
        r"frozen all price reductions",
        r"price list applies to all customers",
        r"standard items are not discounted",
        r"list conditions",
    ],
    "relationship": [r"expects partnership", r"important reference customer", r"kept supplying at the old price"],
    "below_cost": [r"accepted below full cost"],
    "we_pay_late": [r"invoices are overdue"],
}
NEWS_TOPICS = {
    "short_time_work": ["cash_short", "underutilised"],
    "free_capacity": ["underutilised"],
    "restructuring": ["cash_short"],
    "refocus": ["wants_volume"],
    "full_order_book": ["full_order_book"],
    "succession": ["relationship"],
}
COMPILED = {trait: [re.compile(p, re.I) for p in pats] for trait, pats in PATTERNS.items()}
CREDIT_RISKY = 300  # Creditreform-style index: higher is worse; above ~300 money is tight


@dataclass
class SupplierProfile:
    supplier_id: str
    traits: dict[str, list[str]] = field(default_factory=dict)  # trait -> the IDs that show it
    otd_pct: float | None = None
    ppm: float | None = None
    colour: str | None = None
    credit_index: float | None = None
    equity_ratio_pct: float | None = None
    typical_give_pct: float | None = None  # past renewals: asked minus settled change, in % points
    owner_type: str | None = None

    def has(self, trait: str) -> bool:
        return trait in self.traits

    def summary(self) -> dict:
        return {
            "traits": sorted(self.traits),
            "otd_pct": self.otd_pct,
            "ppm": self.ppm,
            "colour": self.colour,
            "credit_index": self.credit_index,
            "typical_give_pct": self.typical_give_pct,
            "owner_type": self.owner_type,
        }


def build_profile(data: WorldData | None, supplier_id: str, case: dict | None = None) -> SupplierProfile:
    profile = SupplierProfile(supplier_id)
    if not data:
        return profile

    def mark(trait: str, ref: str) -> None:
        refs = profile.traits.setdefault(trait, [])
        if ref and ref not in refs:
            refs.append(ref)

    texts: list[tuple[str, str]] = []  # (id, text)
    for doc in data.query("SELECT id, subject FROM documents WHERE supplier_id = ?", (supplier_id,)):
        texts.append((doc["id"], f"{doc['subject'] or ''}\n{data.document_text(doc['id']) or ''}"))
    for news in data.query("SELECT id, topic, headline, body FROM news WHERE supplier_id = ?", (supplier_id,)):
        texts.append((news["id"], f"{news['headline'] or ''}\n{news['body'] or ''}"))
        for trait in NEWS_TOPICS.get(news["topic"] or "", []):
            mark(trait, news["id"])
    for ev in data.query("SELECT event_id, note FROM negotiation_history WHERE supplier_id = ?", (supplier_id,)):
        if ev["note"]:
            texts.append((ev["event_id"], ev["note"]))
    # hidden cases may carry their own documents as facts: read whatever text they hold
    for ref, fact in ((case or {}).get("facts") or {}).items():
        if isinstance(fact, dict) and fact.get("supplier") == supplier_id:
            texts.append((ref, " ".join(str(v) for v in fact.values() if isinstance(v, str))))

    for ref, text in texts:
        for trait, patterns in COMPILED.items():
            if any(p.search(text) for p in patterns):
                mark(trait, ref)

    intel = data.supplier(supplier_id).get("intel") or {}
    profile.owner_type = intel.get("owner_type")
    profile.credit_index = intel.get("credit_index")
    profile.equity_ratio_pct = intel.get("equity_ratio_pct")
    if profile.credit_index and profile.credit_index >= CREDIT_RISKY:
        mark("cash_short", f"sup:{supplier_id.split(':')[-1]}")

    sc = data.query("SELECT * FROM scorecards WHERE supplier_id = ? ORDER BY quarter DESC LIMIT 1", (supplier_id,))
    if sc:
        profile.otd_pct, profile.ppm, profile.colour = sc[0]["otd_pct"], sc[0]["ppm"], sc[0]["colour"]

    gives = [
        r["asked_pct"] - r["settled_pct"]
        for r in data.query(
            "SELECT asked_pct, settled_pct FROM negotiation_history WHERE supplier_id = ? "
            "AND asked_pct IS NOT NULL AND settled_pct IS NOT NULL",
            (supplier_id,),
        )
    ]
    if gives:
        profile.typical_give_pct = round(sum(gives) / len(gives), 2)
    return profile
