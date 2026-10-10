# 2026-10-10 · trade · no LLM

## Result and cost

| Run | D01 score | D01 C_deal (EUR) | D02 score | D02 C_deal (EUR) | Mean | Rounds D01 / D02 |
|---|---|---|---|---|---|---|
| `20261010-190735-sandbox-trade` | 0.863 | 414,144 | 0.587 | 180,520 | 0.725 | 3 / 8 |
| `20261010-190815-sandbox-trade` | 0.843 | 414,947 | 0.587 | 180,520 | 0.715 | 3 / 7 |
| `20261010-191147-sandbox-trade` | 0.863 | 414,144 | 0.587 | 180,520 | 0.725 | 3 / 8 |
| **Mean over the plays of each case** | **0.856** | | **0.587** | | **0.721** | |

Sandbox: D01 (price increase, stabilise; C_open 448,811, C_best 408,624) and D02 (RFQ with two suppliers, leverage;
C_open 214,296, C_best 156,739). "Not played": the arena refused the session (10 open sessions per key) because
several runs were started at once; such a case is left out of the means.

Run cost: 0 practice sessions (sandbox), 0 LLM tokens, 2-3 minutes wall time per run.

## Strategy

`strategy/experiments.py`, strategy name `trade`, commit `b726d4c` plus the uncommitted branch `feat/tactic-experiments`.
Baseline that does not move at all unless the supplier moved, and says that every option is a trade.

| Parameter | Value |
|---|---|
| `conditional` | true (supplier's price unchanged -> our price unchanged; the 0.4 % minimum step is off) |
| everything else | baseline v2: anchors (leverage 18 %, routine 12 %, stabilise 8 %), reciprocity 1.0, minimum step 0.4 %, equal-C menu |

## Notes

- About the baseline: D01 equal or 0.02 better, D02 0.04 worse.
- D02: when the job shop repeated 14.90 we repeated 14.27, and it called 14.90 final; the baseline's 0.4 % minimum step bought a further move to 14.70.
- The baseline already concedes only as far as the supplier's last step, so this variant mostly tests refusing the minimum step - which does not pay here.
