"""A stand-in for the hosted arena's clock, for tests: what it was measured to do with a move that is late.

Measured on the arena (sandbox probe of 11 October 2026, session 09fb6286fa8615dd, and the practice traces
in runs/, e.g. 91dbf752ed31c16a) - the kit's `arena-sim` differs in the points marked (*):

- one call of a session is answered at a time; a supplier's answer takes seconds, and every other call of
  the session waits for it;
- each thread has a clock of 60 s, from the opening and then from each answer of its supplier;
- when a clock runs out the arena plays a `timeout` for us (*on its own, not at our next call): the round
  is used, the supplier answers, and the clock starts again. The answer is not in the thread's `messages`
  and in no reply to us: it is in the thread's `timeouts`, in the session's `moves`, and it is the thread's
  standing `offer_id`;
- (*) our next e-mail to that thread is taken as the next round (200) - the kit answers 409 once;
- the third timeout in a row ends the thread (`walked_away`); the arena then refuses to walk away through
  that thread (422).

The suppliers here are scripts: a price that falls by a fixed share per round, down to a floor.
"""

import threading
import time
from types import SimpleNamespace

from negotiator.client import ArenaError

QUOTE = """Quotation
Offered terms
Unit price (EUR) 17.47
Our standard terms
Payment terms (days net) 30
Lead time (days) 70
Incoterm FCA
"""


class FakeArena:
    def __init__(
        self,
        case: dict,
        reply_s: dict[str, float],
        *,
        limit_s: float = 1.0,
        opening: float = 17.0,
        step: float = 0.02,
        timeout_step: float = 0.03,
        final_after: dict[str, int] | None = None,
        delay_reply: dict[tuple[str, int], float] | None = None,
    ) -> None:
        self.case, self.reply_s, self.limit_s = case, reply_s, limit_s
        self.step, self.timeout_step = step, timeout_step
        self.final_after = final_after or {}  # supplier -> the round from which it says "final offer"
        self.delay_reply = delay_reply or {}  # (supplier, round) -> the reply reaches us this much later
        self.settings = SimpleNamespace(arena_url="http://fake", final_mode=False)
        self.lock = threading.Lock()  # one call at a time
        self.status, self.end_reason, self.result = "open", None, None
        self.moves: list[dict] = []
        self.calls: list[tuple[str, str]] = []
        self.stale_moves: list[dict] = []  # e-mails written for an offer that no longer stood
        self.threads: dict[str, dict] = {}
        now = time.monotonic()
        for i, sup in enumerate(case["suppliers"]):
            th = {"key": sup.split(":", 1)[1], "round": 0, "n": 0, "in_a_row": 0, "closed": None, "clock": now,
                  "messages": [], "timeouts": [], "status": "open", "price": round(opening + i, 2)}  # fmt: skip
            self.threads[sup] = th
            th["messages"].append(self._mail(th, with_quote=True))

    # ------------------------------------------------------------------ the supplier
    def _terms(self, th: dict) -> dict:
        return {"unit_price": th["price"], "payment_days": 60}

    def _offer_id(self, th: dict) -> str | None:
        return None if th["closed"] else f"offer:{th['key']}-{th['round']}"

    def _mail(self, th: dict, with_quote: bool = False) -> dict:
        th["n"] += 1
        return {
            "message_id": f"msg:{th['key']}-{th['round']}-{th['n']}",
            "from": f"sales@{th['key']}",
            "status": th["status"],
            "body": "Our offer.",
            "term_sheets": [{"term_sheet_id": self._offer_id(th), "terms": self._terms(th)}],
            "attachments": [{"name": "quote-0.pdf", "text": QUOTE}] if with_quote else [],
            "claim_results": [],
            "missing_fields": [],
        }

    def _move(self, sup: str, th: dict, share: float) -> None:
        th["round"] += 1
        if th["round"] >= self.final_after.get(sup, 99):
            th["status"] = "final_offer"
        else:
            th["price"] = round(th["price"] * (1 - share), 2)

    def _tick(self) -> None:
        """Play the timeouts that fell due, each at the moment its clock ran out."""
        now = time.monotonic()
        for sup, th in self.threads.items():
            while self.status == "open" and not th["closed"] and now >= th["clock"] + self.limit_s:
                th["clock"] += self.limit_s
                th["in_a_row"] += 1
                if th["in_a_row"] >= 3:
                    th["round"] += 1
                    th["status"] = th["closed"] = "walked_away"
                else:
                    self._move(sup, th, self.timeout_step)
                answer = {
                    "offer_id": self._offer_id(th),
                    "round": th["round"],
                    "status": th["status"],
                    "terms": {} if th["closed"] else self._terms(th),
                    "alternatives": [],
                    "missing_fields": [],
                    "claim_results": [],
                    "text": "Without movement from your side we cannot move either.",
                }
                th["timeouts"].append(answer)
                self.moves.append({"supplier_id": sup, "move": {"type": "timeout"}, "reply": answer})
        if self.status == "open" and all(th["closed"] for th in self.threads.values()):
            self._end("timeout", None)

    def _end(self, reason: str, sup: str | None) -> None:
        self.status, self.end_reason = "ended", reason
        self.result = {"deal": bool(sup), "end_reason": reason, "supplier_id": sup, "score": 0.5 if sup else 0.0}
        if sup:
            self.result.update(terms=self._terms(self.threads[sup]), offer_id=self._offer_id(self.threads[sup]))

    # ------------------------------------------------------------------ the API the agent uses
    def open_session(self, case_id: str) -> dict:
        return {
            "session_id": "fake1",
            "case": self.case,
            "threads": {sup: list(th["messages"]) for sup, th in self.threads.items()},
        }

    def send_message(self, session_id: str, supplier_id: str, message: dict) -> dict:
        with self.lock:
            self._tick()
            path = f"/v1/sessions/{session_id}/threads/{supplier_id}/messages"
            action = (message.get("action") or {}).get("type")
            self.calls.append((action or "message", supplier_id))
            th = self.threads[supplier_id]
            if self.status != "open":
                raise ArenaError(409, f"the session has ended: {self.end_reason}", "POST", path)
            if action == "walk_away":
                if th["closed"]:
                    raise ArenaError(422, f"the thread with {supplier_id} has ended (timeout)", "POST", path)
                self._end("walked_away", None)
                return {"result": self.result}
            if action == "accept":
                if th["closed"] or message["action"].get("term_sheet_id") != self._offer_id(th):
                    raise ArenaError(422, "not a standing offer in this session", "POST", path)
                self._end("accepted", supplier_id)
                return {**self._mail(th), "status": "agreed", "result": self.result}
            if th["closed"]:
                raise ArenaError(409, f"the thread with {supplier_id} has ended: {th['closed']}", "POST", path)
            if th["round"] >= self.case["round_limit"]:
                raise ArenaError(409, "round limit reached: accept the standing offer or walk away", "POST", path)
            answers_to = message.get("answers_offer")  # the test strategies say which offer they answer
            if answers_to is not None and answers_to != self._offer_id(th):
                self.stale_moves.append({"supplier": supplier_id, "answers": answers_to, "stands": self._offer_id(th)})
            th["messages"].append({k: v for k, v in message.items() if k != "answers_offer"} | {"from": "buyer"})
            self._move(supplier_id, th, self.step if message.get("term_sheets") else 0.0)
            th["in_a_row"] = 0
            time.sleep(self.reply_s[supplier_id])  # the supplier writes; every other call of the session waits
            th["clock"] = time.monotonic()
            reply = self._mail(th)
            th["messages"].append(reply)
            late = self.delay_reply.pop((supplier_id, th["round"]), 0.0)
        if late:  # the answer exists at the arena, but reaches us late (a retried POST)
            time.sleep(late)
        return dict(reply)

    def session(self, session_id: str) -> dict:
        with self.lock:
            self._tick()
            self.calls.append(("session", ""))
            now = time.monotonic()
            out = {
                "session_id": session_id,
                "case_id": self.case["case_id"],
                "status": self.status,
                "end_reason": self.end_reason,
                "rounds": sum(th["round"] for th in self.threads.values()),
                "threads": {
                    sup: {
                        "offer_id": self._offer_id(th),
                        "status": th["status"],
                        "offers": th["round"] - len(th["timeouts"]),
                        "closed": th["closed"],
                        "seconds_left": None if th["closed"] else max(0.0, th["clock"] + self.limit_s - now),
                    }
                    for sup, th in self.threads.items()
                },
                "moves": list(self.moves),
            }
            if self.result:
                out["result"] = self.result
            return out

    def thread(self, session_id: str, supplier_id: str) -> dict:
        with self.lock:
            self._tick()
            self.calls.append(("thread", supplier_id))
            th = self.threads[supplier_id]
            return {
                "supplier_id": supplier_id,
                "offer_id": self._offer_id(th),
                "status": th["status"],
                "closed": th["closed"],
                "messages": [dict(m) for m in th["messages"]],
                "timeouts": [dict(a) for a in th["timeouts"]],
            }

    def backoffice(self, session_id: str) -> dict:
        return {}

    def replay_url(self, session_id: str) -> str:
        return f"http://fake/replay/{session_id}"

    def counted(self) -> dict[str, int]:
        """The arena's own count of timeouts per supplier."""
        return {sup: len(th["timeouts"]) for sup, th in self.threads.items()}
