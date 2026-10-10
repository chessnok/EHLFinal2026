# 2026-10-10 · lowball · no LLM

## Result and cost

| Run | D01 score | D01 C_deal (EUR) | D02 score | D02 C_deal (EUR) | Mean | Rounds D01 / D02 |
|---|---|---|---|---|---|---|
| `20261010-175634-sandbox-lowball` | 0.863 | 414,144 | 0.650 | 176,896 | 0.756 | 3 / 7 |
| `20261010-191031-sandbox-lowball` | 0.863 | 414,144 | 0.650 | 176,896 | 0.756 | 3 / 7 |
| `20261010-191037-sandbox-lowball` | 0.863 | 414,144 | 0.650 | 176,896 | 0.756 | 3 / 7 |
| **Mean over the plays of each case** | **0.863** | | **0.650** | | **0.756** | |

Sandbox: D01 (price increase, stabilise; C_open 448,811, C_best 408,624) and D02 (RFQ with two suppliers, leverage;
C_open 214,296, C_best 156,739). "Not played": the arena refused the session (10 open sessions per key) because
several runs were started at once; such a case is left out of the means.

Run cost: 0 practice sessions (sandbox), 0 LLM tokens, 2-3 minutes wall time per run.

## Strategy

`strategy/experiments.py`, strategy name `lowball`, commit `b726d4c` plus the uncommitted branch `feat/tactic-experiments`.
Baseline with a 1.5 times deeper opening anchor: ask for less than we need, so the middle lands in our favour.

| Parameter | Value |
|---|---|
| `anchor_scale` | 1.5 (leverage 27 %, stabilise 12 %) |
| everything else | baseline v2: anchors (leverage 18 %, routine 12 %, stabilise 8 %), reciprocity 1.0, minimum step 0.4 %, equal-C menu |

## Notes

- Best of the eight on the sandbox, by a small margin over the baseline (+0.02).
- D02: the job shop went 17.10 → 15.80 → 14.80 → 14.60 in three rounds (baseline: 14.70 in four); the second bidder came down to 15.80 (baseline: 16.10).
- D01: the foundry's final offer was 50.40 (baseline: 50.50). The deeper anchor did not provoke a walk-away or an early final offer in either case.
