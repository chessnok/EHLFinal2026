# 2026-10-10 · polite · no LLM

## Result and cost

| Run | D01 score | D01 C_deal (EUR) | D02 score | D02 C_deal (EUR) | Mean | Rounds D01 / D02 |
|---|---|---|---|---|---|---|
| `20261010-190534-sandbox-polite` | not played | – | 0.608 | 179,312 | – | – / 8 |
| `20261010-191036-sandbox-polite` | 0.843 | 414,947 | 0.608 | 179,312 | 0.725 | 3 / 8 |
| **Mean over the plays of each case** | **0.843** | | **0.608** | | **0.725** | |

Sandbox: D01 (price increase, stabilise; C_open 448,811, C_best 408,624) and D02 (RFQ with two suppliers, leverage;
C_open 214,296, C_best 156,739). "Not played": the arena refused the session (10 open sessions per key) because
several runs were started at once; such a case is left out of the means.

Run cost: 0 practice sessions (sandbox), 0 LLM tokens, 2-3 minutes wall time per run.

## Strategy

`strategy/experiments.py`, strategy name `polite`, commit `b726d4c` plus the uncommitted branch `feat/tactic-experiments`.
Baseline with a warm, appreciative opening and closing sentence.

| Parameter | Value |
|---|---|
| `tone` | `polite` (texts in `TONES`) |
| everything else | baseline v2: anchors (leverage 18 %, routine 12 %, stabilise 8 %), reciprocity 1.0, minimum step 0.4 %, equal-C menu |

## Notes

- No measurable effect on D01 (0.843, as the baseline); D02 0.02 below the baseline (job shop at 14.80 instead of 14.70).
