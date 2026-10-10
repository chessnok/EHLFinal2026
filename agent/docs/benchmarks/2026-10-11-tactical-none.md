# 2026-10-11 · tactical · no LLM

## Result and cost

| Case | Score | C_deal (EUR) | Rounds | `tactical` on `96f7545` (P-13) | Difference |
|---|---|---|---|---|---|
| P01 | 0.969 | 1,098,584 | 4 | 0.856 | +0.113 |
| P02 | 0.733 | 2,248,174 | 1 | 0.686 | +0.047 |
| P03 | 0.903 | 3,941,630 | 2 | 0.905 | −0.002 |
| P04 | 0.860 | 196,853 | 3 | 0.860 | 0.000 |
| P05 | 0.742 | 244,577 | 9 | 0.742 | 0.000 |
| P07 | 0.663 | 330,213 | 2 | 0.721 | −0.058 |
| P08 | 0.550 | 1,039,279 | 3 | 0.570 | −0.020 |
| P10 | 0.647 | 1,541,808 | 2 | 0.647 | 0.000 |
| P11 | 0.672 | 753,660 | 5 | 0.545 | +0.127 |
| P18 | 0.618 | 250,342 | 4 | 0.419 | +0.199 |
| **Mean** | **0.736** | | | **0.695** | +0.041 |

10 of 10 deals, no walk-away, no zero. Run cost: 10 practice sessions, 0 LLM tokens, about 2 minutes wall time
(`--parallel 5`). The six partial runs that led to this commit spent 16 more sessions (`../runs.md` P-16 to P-21).

## Strategy

`strategy/tactical.py`, strategy name `tactical`, commit `7143676` (branch `fix/relationship-charge`). `tactical` as
on main (`0dfc9d2`) with the margin charge of `stabilise` and `secure_supply` cases in our C, and what follows from it:

| Parameter | Value |
|---|---|
| supplier's standard terms | quote PDF, then the `suppliers` table, then its opening sheet |
| `SHOULD_COST_SHARE` | 0.98: full cost as a share of the own-plant should-cost |
| `CASH_SHORT_RATE` | 1.2 x our interest rate for a supplier short of cash |
| `ANCHOR_SLACK` | 0.25: a deal on the deep first ask may cost a quarter of the room |
| `RELATIONSHIP_STEP`, `RELATIONSHIP_MIN_STEP` | 0.25 of the usual step, at least 0.05 of the room |
| `STOP_ROOM`, `UPPER_ROOM_SHARE` | 0.05, 0.15: the upper bound as shares of the room |
| index clause | offered at our cost minimum when the supplier's opening argues with the clause's series |

## Runs

Set practice, the 10 hosted cases: `20261011-001629-practice-tactical`. Partial runs: `20261010-233708`, `-234407`,
`-235150`, `-235539`, `20261011-000105`, `-000543` (all `-practice-tactical`).

## Notes

- **P01, P02, P03 and P10 are the cases this change touches.** P07, P08, P11 and P18 differ from P-13 too; they also
  carry main's changes between `96f7545` and `0dfc9d2`, and the index-clause rule fires on P08 and P18. No run
  separates these.
- **P01:** asks 126.12 → 126.80 → 127.64 against the supplier's 136.00 → 134.40 → 133.60, then its final offer of
  131.30. The arena's margin charge on the deal: 10,826.
- **P02:** the supplier agreed to 362.02 with a 5 % deadband clause in its first reply. Charge 32,091, index risk
  17,696. Without a clause it stopped at 372.96 (P-19, 0.380).
- **The same code gave P01 0.969 twice** (P-21, P-22) and P02 0.733 three times (P-20 to P-22): the same e-mails got
  the same replies.

## Second full pass, commit `6bb73d1` (after merging main)

| Run | Mean | Deals | P01 | P02 | P03 | P04 | P05 | P07 | P08 | P10 | P11 | P18 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `20261011-010356-practice-tactical` | **0.746** | 10 of 10 | 0.969 | 0.733 | 0.923 | 0.860 | 0.742 | 0.740 | 0.550 | 0.647 | 0.672 | 0.618 |

Run cost: 10 practice sessions, 0 LLM tokens, about 3 minutes wall time. Added since `7143676`: main's `b3f06da`
(options of one message within 0.5 % of each other's C; one more ask under an open offer), `ANCHOR_ROUTINE` 0.13
(first ask for a `routine` goal), and the own-plant should-cost cited from 3 % under the quote, ranked last. Eight
cases repeat the first pass to the cent; P03 and P07 are the two the later changes touch.

