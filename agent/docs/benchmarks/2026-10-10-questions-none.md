# 2026-10-10 · questions · no LLM

## Result and cost

| Run | D01 score | D01 C_deal (EUR) | D02 score | D02 C_deal (EUR) | Mean | Rounds D01 / D02 |
|---|---|---|---|---|---|---|
| `20261010-190530-sandbox-questions` | 0.823 | 415,749 | 0.650 | 176,896 | 0.736 | 3 / 8 |
| `20261010-190531-sandbox-questions` | 0.843 | 414,947 | not played | – | – | 3 / – |
| `20261010-191035-sandbox-questions` | 0.823 | 415,749 | not played | – | – | 3 / – |
| `20261010-191041-sandbox-questions` | 0.823 | 415,749 | 0.650 | 176,896 | 0.736 | 3 / 8 |
| **Mean over the plays of each case** | **0.828** | | **0.650** | | **0.739** | |

Sandbox: D01 (price increase, stabilise; C_open 448,811, C_best 408,624) and D02 (RFQ with two suppliers, leverage;
C_open 214,296, C_best 156,739). "Not played": the arena refused the session (10 open sessions per key) because
several runs were started at once; such a case is left out of the means.

Run cost: 0 practice sessions (sandbox), 0 LLM tokens, 2-3 minutes wall time per run.

## Strategy

`strategy/experiments.py`, strategy name `questions`, commit `b726d4c` plus the uncommitted branch `feat/tactic-experiments`.
Baseline plus three questions in every e-mail, cycling through a list of nine.

| Parameter | Value |
|---|---|
| `questions_per_round` | 3 |
| everything else | baseline v2: anchors (leverage 18 %, routine 12 %, stabilise 8 %), reciprocity 1.0, minimum step 0.4 %, equal-C menu |

## Notes

- No measurable effect: D02 ends 0.02 above the baseline, D01 0.02 below in three of four plays.
- The bots answer the questions (lead time, material share, capacity) but the price path is the baseline's within 0.10 per unit.
- The questions did not cost rounds, because every e-mail still carried term sheets.
