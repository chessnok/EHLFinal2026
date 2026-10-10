# Backlog: where we lose score, and what to work on

As of 10 October 2026, 21:30. Source: the `tactical` run over the 10 hosted practice cases
(`20261010-211824-practice-tactical`, commit `96f7545`, mean 0.695), its trace and events, and the practice
leaderboard read at 21:35 (we are 5th of 22 with 73.2 points over our best scores; the leader has 79.0).

Every figure below is from that run unless a source is named. The "why" of each problem is read from the trace and
the `thread_hold` events; the rule in `tactical.py` behind each stop has not been traced line by line.

## 1. The cases by lever, with what the run lost

| Lever | Case | Score | EUR above C_best | Rounds used of 10 | How the thread ended |
|---|---|---|---|---|---|
| Price increase | P01 | 0.856 | 8,192 | 2 | held: "their offer meets our ask", supplier still `open` |
| Price increase (copper) | P02 | 0.686 | 14,854 | 2 | supplier `agreed` to our sheet |
| Raw-material surcharge | P08 | 0.570 | 75,422 | 4 | held: "last word: take it" on a `final_offer` |
| Raw-material surcharge | P18 | 0.419 | 42,133 | 3 | supplier `agreed`: we went 5.00 → 5.25 → 5.50, its price |
| Renewal | P03 | 0.905 | 31,992 | 4 | held: "the supplier stopped moving" |
| Renewal | P04 | 0.860 | 324 | 3 | held: "last word: take it" on a `final_offer` |
| RFQ | P05 | 0.742 | 21,153 | 3 | supplier `agreed`: we went 30.46 → 28.00 against its 28.79 |
| Bundling | P07 | 0.721 | 25,607 | 4 | held: "last word: take it" on a `final_offer` |
| Capacity | P10 | 0.647 | 212,881 | 2 | `final_offer` in its first reply (33.80, alternative 31.90); we took the alternative |
| Quality | P11 | 0.545 | 43,244 | 4 | held: "last word: take it", supplier still `open` |

## 2. The problems, largest first

### 2.1 We stop after two to four of ten rounds

No thread used more than four rounds. In P18 and P05 the supplier agreed to our own rising offer (P18: 5.00 → 5.25
→ 5.50 against its 5.60); in P01 and P11 the thread was held while the supplier's status was still `open`.

- P18: deal 264,784, our upper bound 259,433, C_best 222,651.
- P10 is a different case: the supplier called its first reply final (33.80, with an alternative at 31.90) and we
  took the alternative. The deal costs 1,541,808 against our upper bound of 1,374,881 and C_best 1,328,927; what
  would have moved it is not in the trace.
- P02 closed in round 2 below our own ask (358.45 against 361.34), after we offered an index clause.

### 2.2 Our estimate of what is reachable is too high in leverage cases

The upper bound (`plan` event) against the arena's C_best:

| Case | Upper bound | C_best | Upper bound above C_best |
|---|---|---|---|
| P05 | 272,392 | 223,424 | 21.9 % |
| P18 | 259,433 | 222,651 | 16.5 % |
| P08 | 1,028,315 | 960,309 | 7.1 % |
| P07 | 319,069 | 299,241 | 6.6 % |
| P03 | 4,102,637 | 3,909,043 | 5.0 % |
| P01 | 1,143,596 | 1,096,816 | 4.3 % |
| P10 | 1,374,881 | 1,328,927 | 3.5 % |
| P04 | 197,524 | 196,529 | 0.5 % |
| P02 | 2,282,867 | 2,235,514 | 2.1 % |
| P11 | 710,733 | 722,500 | -1.6 % |

An offer inside a bound that is too high counts as good enough, so the thread closes early (2.1).

### 2.3 A lever the supplier names is not pulled

P11: the supplier wrote "Faster payment would help us more than anything" in four replies, and "If you want a lower
price, we need to drop the chargebacks". The profile had it as `cash_short`. Its price went 47.00 → 48.50 → 47.00 →
46.50 → 46.50 and we took it with six rounds left. P07: "A binding higher volume would help us and can improve the
price" in round 4.

### 2.4 Arguments that are spent for nothing

- The price-history argument came back "it holds, but it does not change our calculation" in five cases (P18, P08,
  P10, P02, P11). It takes one of the three argument slots of the first e-mail each time.
- P07: the forecast was cited in four e-mails; three came back `duplicate`, and the supplier answered "that volume
  change was already factored into our previous calculation" three times.

### 2.5 What is no longer a problem: the volume question

On 10 October in the afternoon the most common supplier sentence was "Which volume can you commit to?", unanswered
(`rejections.md`, row 1). In this run the forecast argument came back "it holds and we took it into account" in P18,
P08, P02, P07 and P11.

### 2.6 A final offer is final on practice

`playbook`'s closing offer after a final offer made three suppliers walk away (P04, P07, P18):
[`benchmarks/2026-10-10-playbook-none.md`](benchmarks/2026-10-10-playbook-none.md). Problem 2.1 is about the rounds
before a final offer, not about pushing past one.

## 3. Work items

| # | Item | Cases it concerns | Evidence |
|---|---|---|---|
| 1 | Concede more slowly while the supplier is `open` and rounds are left (`tactical-slow25`: sandbox D02 0.587 → 0.671, not played on practice) | P18, P05 | 2.1 |
| 2 | Do not hold a thread on "last word" or "meets our ask" while the status is `open` and the supplier names a lever | P11, P01 | 2.1, 2.3 |
| 3 | Lower the upper bound for leverage cases, or stop using it as a reason to close | P05, P18, P08, P07 | 2.2 |
| 4 | When a supplier names a lever twice, send a sheet that gives it (shortest payment, no chargeback) at its price | P11, P07 | 2.3 |
| 5 | Drop the price-history argument from the first e-mail; never cite one ID twice | all | 2.4 |

## 4. How to test changes

- **Holdout.** Tune on P01, P04, P05, P07, P08, P10 and P11. Do not look at P02, P03 and P18 until a change is
  finished: each has a twin of the same lever in the tuning set (P01, P04, P08), so a gain that does not carry over
  to them is fitted to a case, not to a lever.
- **Cost.** One run over the seven tuning cases is 7 sessions; the holdout 3. `tactical` uses no LLM, so one run per
  change is enough.
- **Variations.** The arena cannot be given changed cases. `negotiator sim bench --jitter --strangers` moves the
  floors and swaps the suppliers' habits on the same scenarios; use it as a gate (a change must not lose there), not
  as a score. Its error on practice cases is in [`simulator.md`](simulator.md).
