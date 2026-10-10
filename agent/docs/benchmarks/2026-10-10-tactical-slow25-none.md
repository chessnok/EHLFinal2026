# 2026-10-10 · tactical-slow25 · no LLM

## Result and cost

| Run | Strategy | D01 score | D01 C_deal (EUR) | D02 score | D02 C_deal (EUR) | Mean | Rounds D01 / D02 |
|---|---|---|---|---|---|---|---|
| `20261010-214628-sandbox-tactical-slow25` | `tactical-slow25` | 0.957 | 410,370 | 0.671 | 175,688 | **0.814** | 5 / 10 |
| `20261010-214434-sandbox-tactical` | `tactical` (control, same commit) | 0.969 | 409,883 | 0.587 | 180,520 | 0.778 | 5 / 10 |

Sandbox: D01 (price increase, stabilise; C_open 448,811, C_best 408,624) and D02 (RFQ with two suppliers, leverage;
C_open 214,296, C_best 156,739). Run cost: 0 practice sessions, 0 LLM tokens, about 2 minutes wall time per run.
Not played on practice.

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
