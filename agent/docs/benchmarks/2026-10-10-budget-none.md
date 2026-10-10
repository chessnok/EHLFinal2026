# 2026-10-10 · budget · no LLM

## Result and cost

| Run | D01 score | D01 C_deal (EUR) | D02 score | D02 C_deal (EUR) | Mean | Rounds D01 / D02 |
|---|---|---|---|---|---|---|
| `20261010-175634-sandbox-budget` | 0.863 | 414,144 | 0.314 | 196,224 | 0.588 | 3 / 8 |
| `20261010-191032-sandbox-budget` | 0.863 | 414,144 | 0.314 | 196,224 | 0.588 | 3 / 8 |
| `20261010-191039-sandbox-budget` | not played | – | 0.314 | 196,224 | – | – / 9 |
| **Mean over the plays of each case** | **0.863** | | **0.314** | | **0.588** | |

Sandbox: D01 (price increase, stabilise; C_open 448,811, C_best 408,624) and D02 (RFQ with two suppliers, leverage;
C_open 214,296, C_best 156,739). "Not played": the arena refused the session (10 open sessions per key) because
several runs were started at once; such a case is left out of the means.

Run cost: 0 practice sessions (sandbox), 0 LLM tokens, 2-3 minutes wall time per run.

## Strategy

`strategy/experiments.py`, strategy name `budget`, commit `b726d4c` plus the uncommitted branch `feat/tactic-experiments`.
Baseline plus a ceiling set by a third party in every e-mail ("management has released at most EUR X per unit"); our offers never cross it.

| Parameter | Value |
|---|---|
| `budget_share` | 0.5 (ceiling = target + 0.5 x (opening - target); D01 48.80, D02 15.56 / 14.56) |
| everything else | baseline v2: anchors (leverage 18 %, routine 12 %, stabilise 8 %), reciprocity 1.0, minimum step 0.4 %, equal-C menu |

## Notes

- The clear loser: D02 drops from 0.629 (baseline) to 0.314.
- D02: the job shop stopped at 16.20 as its final offer (baseline: 14.70). Our offers (14.02 → 14.78) never reached the ceiling of 15.56, so the stated budget itself is the only difference to the baseline - naming a ceiling gave the supplier a number to aim at.
- D01: no harm; the foundry's final offer was 50.40.
