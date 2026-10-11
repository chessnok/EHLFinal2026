"""Tactical with a model as writer (and, optionally, reader): `tactical-llm`, `tactical-llm+reader`.

Every number is tactical's. `decide` runs tactical's `decide` unchanged and takes its decision as it is: the term
sheets, the cited IDs, hold or accept. Only when that decision is an ordinary offer e-mail does the writer
(`negotiator.writer`) reword the text between the greeting and the options; code checks the result and sends
tactical's own e-mail whenever the model is slow, fails or writes something the check refuses. E-mails that carry an
acceptance or a closing promise ("we accept your alternative", "one last step and we can sign", the price match)
are never rewritten - their words are the commitment.

With `reader=True` a model also reads each new reply (`negotiator.reader`) before tactical decides, and may add a
requested lever to `plan.requests` where the regular expressions missed it. It changes nothing else.

All model calls of one outgoing e-mail share one wall-clock budget, `LLM_MESSAGE_BUDGET_S` (default 10 s): the
arena allows 60 s per move. The budget also ends 45 s after the supplier's reply came in, whatever was spent before
the strategy was asked. When it is spent the template goes out and `writer.fallback.deadline` counts it.

Without a model (`llm=None`, e.g. `negotiator sim bench`) this is tactical, e-mail for e-mail.
"""

import time

from negotiator.data import WorldData
from negotiator.reader import Reader
from negotiator.session import Negotiation
from negotiator.strategy.base import Decision
from negotiator.strategy.tactical import TacticalStrategy
from negotiator.telemetry import log
from negotiator.writer import Writer, WriterSettings

SEND_BY_S = 45.0  # of the arena's 60 s per move: the latest moment after a reply at which a model call may end


class WrittenStrategy(TacticalStrategy):
    name = "tactical-llm"

    def __init__(self, data: WorldData | None = None, llm=None, reader: bool = False) -> None:
        super().__init__(data, None)
        self.settings = WriterSettings.from_env()
        self.writer = Writer(llm, self.settings) if llm else None
        self.reader = Reader(llm) if llm and reader else None
        self.name = "tactical-llm+reader" if reader else "tactical-llm"
        self.hints: dict[str, dict] = {}  # supplier -> what the reader found in its latest reply
        self.deadlines: dict[str, float] = {}  # supplier -> perf_counter() at which this e-mail's budget ends

    def decide(self, neg: Negotiation, supplier_id: str) -> Decision:
        start = time.perf_counter()
        # the budget for this e-mail's model calls - and never past SEND_BY_S after the supplier's reply came in:
        # reading its attachments has used part of the arena's 60 s before we decide
        since_reply = neg.threads[supplier_id].seconds_since_reply()
        self.deadlines[supplier_id] = start + min(self.settings.message_budget_s, SEND_BY_S - since_reply)
        decision = super().decide(neg, supplier_id)
        if self.writer is None or decision.kind != "message" or not self._rewritable(decision):
            return decision
        message = decision.message
        body, record = self.writer.write(
            neg, supplier_id, message, self.hints.get(supplier_id), self.deadlines[supplier_id]
        )
        seconds = time.perf_counter() - start  # reader + tactical + writer: what this e-mail took before sending
        neg.recorder.metrics.observe("writer.message_seconds", seconds)
        neg.recorder.event(
            "writer",
            session_id=neg.session_id,
            case_id=neg.case_id,
            supplier_id=supplier_id,
            round=neg.threads[supplier_id].rounds_used + 1,
            message_seconds=round(seconds, 2),
            **record,
        )
        decision.rationale["writer"] = {k: record[k] for k in ("used", "reason")}
        if body is None:
            log.warning(
                "%s: writer fell back to the template (%s): %s", supplier_id, record["reason"], record["problems"]
            )
            return decision
        decision.message = {**message, "body": body}
        return decision

    @staticmethod
    def _rewritable(decision: Decision) -> bool:
        """An ordinary offer from `_offer` (it alone records the claims); not the probe of a final offer, whose
        "one last step and we can sign" is a promise, and none of the e-mails that accept something."""
        r = decision.rationale
        return "claims" in r and not r.get("probe") and "move" not in r
