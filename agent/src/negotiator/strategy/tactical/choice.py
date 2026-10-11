"""One choice by expected cost: take its offer, ask (and for how much), or probe a last word.

`tactical`'s `_choose` is a chain of rules in order (last word, price match, stalls, Boulware step, patient gap),
each with thresholds fitted to the cases where it mattered. Here the same choice is made once, from a belief
about where the supplier stops and a model of how the arena's suppliers answer:

  belief    S, the C at which this supplier stops with us: the floor belief's estimate (`plan.stop_c`, belief.py)
            with the error that estimate has shown, never above its standing offer;
  response  to our next ask (pooled over every supplier of the tuning cases, 828 recorded replies; the held-out
            cases P02, P03 and P18 are not in the tables - `RESPONSE` below):
              - it gives a share of its room to S that depends on how much of the distance between us our ask
                closes: next to nothing for a crumb, the most from a tenth of the distance on;
              - it calls its offer final with a chance that depends on the number of the reply;
              - if our ask reaches what it would have offered, it agrees to our ask - our concession is taken;
              - after a final offer a further sheet moves it a little or makes it walk away.

Each candidate (hold = take its standing offer, or close a share of the distance) is played forward over the
rounds left, for each S of the belief; the candidate with the lowest expected C wins. Nothing here names a case:
the tables are the arena's habits, the belief is this supplier's.
"""

import math

# share of the distance between our last ask and its offer that our next ask closes -> (up to this share, the
# share of its room to S it then gives). Tuning cases, replies to an open thread that were no agreement:
# under 2 %: 0.133 (n 153), 2-10 %: 0.158 (n 191), 10-25 %: 0.309 (n 156), 25-50 %: 0.336 (n 32), over: 0.316 (n 22)
RESPONSE = ((0.02, 0.13), (0.10, 0.16), (math.inf, 0.31))
PENDING_GIVES = 0.55  # the second half of a step it had approved ("pending", n 61): whatever we send
# its reply number n (to our n-th e-mail) is a final offer: 0.04, 0.03, 0.40, 0.81, 0.88 (n 253, 221, 205, 116, 17)
FINAL_BY_REPLY = (0.04, 0.03, 0.40, 0.81, 0.88, 1.0)
AFTER_FINAL_GIVES = 0.07  # a sheet sent after its final offer: mean share of its room it still gave (n 79) ...
AFTER_FINAL_WALKS = 0.16  # ... and how often it walked away
STEPS = (0.02, 0.05, 0.10, 0.15, 0.25, 0.40, 0.60)  # candidate shares of the distance to close
CONTINUE = 0.10  # ... and the share the rounds after this one are played with: where its full step begins
# the stop estimate's error as a share of C, by replies seen (reading.py `_update_upper`: within 8 % before the
# first reply, 1-3 % by rounds 3-4), and on which side it erred (too high: backlog.md 2.2)
STOP_ERROR = (0.08, 0.05, 0.03, 0.02)
STOP_BIAS = -0.5  # in errors: the estimate sat above the real stopping point more often than below
QUANTILES = ((-1.5, 0.13), (-0.75, 0.24), (0.0, 0.26), (0.75, 0.24), (1.5, 0.13))  # (errors, weight)
WORTH_A_ROUND = 0.002  # a round is played for an expected gain of at least this share of the room


def gives(share_closed: float) -> float:
    return next(g for upto, g in RESPONSE if share_closed < upto)


def stops(stop_c: float, their_c: float, target_c: float, replies: int) -> list[tuple[float, float]]:
    """The belief about S as weighted points: around the estimate, between our first ask and its offer."""
    centre = stop_c if math.isfinite(stop_c) else (their_c + target_c) / 2
    centre = min(centre, their_c)
    error = STOP_ERROR[min(replies, len(STOP_ERROR) - 1)] * abs(centre)
    low = min(target_c, their_c)
    return [(min(their_c, max(low, centre + (z + STOP_BIAS) * error)), w) for z, w in QUANTILES]


def played(their_c: float, ask: float, stop: float, step: float, reply: int, rounds: int, pending: bool) -> float:
    """Expected C when our next ask closes `step` of the distance and every later one `CONTINUE`, against a
    supplier that stops at `stop`."""
    if rounds <= 0:
        return their_c
    ask = ask + step * (their_c - ask)
    room = max(0.0, their_c - stop)
    offer = their_c - (PENDING_GIVES if pending else gives(step)) * room
    if ask >= offer:
        return ask  # our ask reaches what it would have offered: it agrees to ours
    final = FINAL_BY_REPLY[min(reply, len(FINAL_BY_REPLY) - 1)]
    return final * offer + (1 - final) * played(offer, ask, stop, CONTINUE, reply + 1, rounds - 1, False)


def best_step(their_c: float, ask: float, belief: list[tuple[float, float]], reply: int, rounds: int,
              pending: bool = False) -> tuple[float | None, dict]:  # fmt: skip
    """The share of the distance to close with the lowest expected C - None: take its offer. On a tie the smaller
    step: what we do not concede cannot be taken. Returns the expected C of every candidate too."""
    expected = {
        step: sum(w * played(their_c, ask, stop, step, reply, rounds, pending) for stop, w in belief) for step in STEPS
    }
    best = min(expected, key=lambda step: (round(expected[step], 2), step))
    return (best if expected[best] < their_c else None), expected


def probe_pays(their_c: float, floor_c: float, walk_c: float) -> bool:
    """A sheet after its last word: the little it may still give against what its walking away would cost."""
    gain = (1 - AFTER_FINAL_WALKS) * AFTER_FINAL_GIVES * max(0.0, their_c - floor_c)
    return gain > AFTER_FINAL_WALKS * max(0.0, walk_c - their_c)


class ChoiceMixin:
    """`_choose` by expected cost (see the module): mixed in before `ConcessionMixin`, whose chain it replaces."""

    def _choose(self, neg, supplier_id: str, plan, theirs: dict, their_c: float, last_word: bool,
                rest_pending: bool):  # fmt: skip
        from negotiator.strategy.base import Decision
        from negotiator.strategy.tactical.plan import DONE_EPS, PATIENT_GAP
        from negotiator.strategy.tactical.reading import APPROVAL_PENDING

        t = neg.threads[supplier_id]
        if last_word:
            # where it would stop if pushed: the belief around its standing offer, not our anchor - a floor we only
            # guessed (a re-anchor sits 10 % under its price) made every last word look worth a push
            replies = len(t.supplier_messages) - 1
            floor_c = sum(w * stop for stop, w in stops(plan.stop_c, their_c, plan.target_c, replies))
            walk_c = self._walk_c(neg, supplier_id)
            if (
                not plan.probed_final
                and self._may_push(neg, supplier_id)
                and math.isfinite(walk_c)
                and probe_pays(their_c, floor_c, walk_c)
            ):
                plan.probed_final = True
                last = plan.our_c[-1] if plan.our_c else plan.target_c
                ask_c = last + 0.5 * max(0.0, their_c - last)  # a real step: a crumb reads as a refusal
                return self._offer(neg, supplier_id, plan, theirs, ask_c, their_c, probe=True)
            return Decision.hold(supplier_id, "last word: take it", their_c=their_c)
        if not plan.our_c:  # the first ask is the plan's: the anchor is not this choice
            first = plan.target_c if plan.target_c < their_c * (1 - DONE_EPS) else their_c * (1 - PATIENT_GAP)
            return self._offer(neg, supplier_id, plan, theirs, first, their_c)
        last = plan.our_c[-1]
        if last >= their_c * (1 - DONE_EPS):
            return Decision.hold(supplier_id, "their offer meets our ask", ask_c=last, their_c=their_c)
        rounds = self._round_budget(neg, supplier_id) - t.rounds_used - 1  # the last round is kept for the close
        replies = len(t.supplier_messages) - 1
        belief = stops(plan.stop_c, their_c, plan.target_c, replies)
        if plan.stalls:  # every reply without a move says it stands nearer to its stop
            belief = [(their_c - (their_c - stop) * 0.5**plan.stalls, w) for stop, w in belief]
            plan.lever_turn = True  # a structure it has not seen carries our step
        pending = rest_pending or bool(APPROVAL_PENDING.search(t.latest.get("body", "")))
        step, expected = best_step(their_c, last, belief, t.rounds_used, rounds, pending)
        room = max(0.0, plan.open_c - plan.target_c)
        neg.recorder.event(
            "choice",
            session_id=neg.session_id,
            supplier_id=supplier_id,
            their_c=round(their_c, 2),
            last_ask=round(last, 2),
            stops=[round(stop, 2) for stop, _ in belief],
            rounds=rounds,
            pending=pending,
            expected={str(k): round(v, 2) for k, v in expected.items()},
            step=step,
        )
        if step is None or their_c - expected[step] < WORTH_A_ROUND * room:
            return Decision.hold(supplier_id, "no ask is expected to beat its offer", their_c=their_c)
        return self._offer(neg, supplier_id, plan, theirs, last + step * (their_c - last), their_c)

    def _walk_c(self, neg, sid: str) -> float:
        """What we are left with if this supplier walks away: the cheapest safe offer of another live bidder that
        is not being probed itself, else no deal - which scores 0 whatever our alternative costs, as a deal at the
        opening's C would."""
        from negotiator.guards import accept_problems

        best = math.inf
        for other, ot in neg.threads.items():
            if other == sid or not ot.live:
                continue
            if self.tplans[other].probed_final:
                return math.inf  # one bidder is being pushed already: this one stays the safe one
            if ot.standing[0] and not accept_problems(neg, other, ot.standing[0]):
                best = min(best, neg.cost(other, ot.standing[1]))
        return min(best, neg.c_open)
