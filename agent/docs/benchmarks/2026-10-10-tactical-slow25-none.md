# 2026-10-10 · tactical-slow25 · no LLM

## Result and cost

| Run | Strategy | D01 score | D01 C_deal (EUR) | D02 score | D02 C_deal (EUR) | Mean | Rounds D01 / D02 |
|---|---|---|---|---|---|---|---|
| `20261010-214628-sandbox-tactical-slow25` | `tactical-slow25` | 0.957 | 410,370 | 0.671 | 175,688 | **0.814** | 5 / 10 |
| `20261010-214434-sandbox-tactical` | `tactical` (control, same commit) | 0.969 | 409,883 | 0.587 | 180,520 | 0.778 | 5 / 10 |

Sandbox: D01 (price increase, stabilise; C_open 448,811, C_best 408,624) and D02 (RFQ with two suppliers, leverage;
C_open 214,296, C_best 156,739). Run cost: 0 practice sessions, 0 LLM tokens, about 2 minutes wall time per run.
Practice: see the section at the end.

## Strategy

`strategy/patient.py`, strategy name `tactical-slow25`, commit `556a31d` plus the uncommitted `patient.py`.
`tactical` with one change: our step towards the supplier is a quarter of what `tactical` would take, and at least
the minimum step of 0.4 % of C.

| Parameter | Value |
|---|---|
| `scale` | 0.25 (`tactical-slow50`: 0.5, played on the simulator only) |
| everything else | `tactical` as on `556a31d` |

## Notes

- The change comes from [`../backlog.md`](../backlog.md) 2.1: on practice case P18 the supplier agreed as soon as our
  rising offer reached what it would take (5.00 → 5.25 → 5.50).
- D02 gained 0.084, D01 lost 0.012. One run each on two demo cases.
- **The simulator pointed the same way before the sandbox run.** `negotiator sim bench tactical tactical-slow50
  tactical-slow25 --reps 5`, fitted on all sessions up to 21:40: D02 0.54 → 0.66, D01 0.84 → 0.85. For the ten
  practice cases it gave a mean of 0.618 for `tactical` and 0.644 for `tactical-slow25`, with P02 0.34 → 0.51,
  P05 0.53 → 0.60 and P08 0.52 → 0.38. Those are simulator figures, not arena results; its error on single practice
  cases was 0.1 to 0.35 against the arena run of the same evening.

## Practice: the 10 hosted cases, commit `fe7a9ea`

| Run | Strategy | Mean | Deals |
|---|---|---|---|
| `20261010-221425-practice-tactical-slow25` | `tactical-slow25` | **0.621** | 10 of 10 |
| `20261010-211824-practice-tactical` (commit `96f7545`) | `tactical` | 0.695 | 10 of 10 |

Run cost: 10 practice sessions, 0 LLM tokens, about 3 minutes wall time.

| Case | tactical | tactical-slow25 | Difference | C_deal slow25 (EUR) | Rounds |
|---|---|---|---|---|---|
| P01 | 0.856 | 0.914 | +0.058 | 1,101,713 | 4 |
| P02 | 0.686 | 0.000 | −0.686 | 2,314,646 | 4 |
| P03 | 0.905 | 0.903 | −0.002 | 3,941,630 | 3 |
| P04 | 0.860 | 0.860 | 0.000 | 196,853 | 3 |
| P05 | 0.742 | 0.689 | −0.054 | 249,002 | 7 |
| P07 | 0.721 | 0.585 | −0.136 | 337,365 | 2 |
| P08 | 0.570 | 0.515 | −0.055 | 1,045,379 | 3 |
| P10 | 0.647 | 0.647 | 0.000 | 1,541,808 | 2 |
| P11 | 0.545 | 0.626 | +0.081 | 758,033 | 4 |
| P18 | 0.419 | 0.467 | +0.048 | 261,308 | 2 |
| **Mean** | **0.695** | **0.621** | −0.074 | | |

- **Slower concessions do not pay on practice.** Without P02 the nine other cases give 0.690 against 0.696.
- **P02 scored 0 with a deal.** We accepted EUR 345.39 with a copper index clause. Our own cost for that sheet was
  2,135,441; the arena's is 2,314,646, above C_open (2,282,867). The difference is the relationship charge of 179,204:
  P02 is a `stabilise` case and the price leaves the supplier below its sustainable margin. In the `tactical` run the
  deal at 358.45 carried a relationship charge of 56,127. Our estimate of that charge was 0 in both.
- **The simulator's figures for this run did not hold** (`../simulator.md`, open check): it gave 0.656 against 0.603
  for `tactical`; the arena gave 0.621 against 0.695.
