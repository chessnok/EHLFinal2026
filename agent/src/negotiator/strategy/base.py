"""The strategy interface. The runner calls it; `Negotiation` holds the state it reads.

Per thread the runner asks `decide(neg, supplier_id)`:
  message    send this e-mail (subject, body, term sheets, refs)
  hold       this thread is settled for now (agreed, final offer, close enough, out of rounds)
  drop       this thread is over for us (walked away, no bid, hopeless)
  accept     close the case on this supplier's standing term sheet
  walk_away  close the case without a deal
When every thread is held or dropped, `conclude(neg)` makes the closing move (accept or walk away).
While other threads still negotiate, a held thread's 60 s clock keeps running: `keepalive` returns a
message that keeps it alive (or None to let it be).
"""

from dataclasses import dataclass, field
from typing import Literal, Protocol

from negotiator.session import Negotiation

Kind = Literal["message", "hold", "drop", "accept", "walk_away"]


@dataclass
class Decision:
    kind: Kind
    supplier_id: str | None = None
    message: dict | None = None
    term_sheet_id: str | None = None
    rationale: dict = field(default_factory=dict)

    @classmethod
    def hold(cls, supplier_id: str, why: str, **extra) -> "Decision":
        return cls("hold", supplier_id, rationale={"why": why, **extra})

    @classmethod
    def drop(cls, supplier_id: str, why: str, **extra) -> "Decision":
        return cls("drop", supplier_id, rationale={"why": why, **extra})


class Strategy(Protocol):
    name: str

    def prepare(self, neg: Negotiation) -> None: ...

    def decide(self, neg: Negotiation, supplier_id: str) -> Decision: ...

    def conclude(self, neg: Negotiation) -> Decision: ...

    def keepalive(self, neg: Negotiation, supplier_id: str) -> dict | None: ...
