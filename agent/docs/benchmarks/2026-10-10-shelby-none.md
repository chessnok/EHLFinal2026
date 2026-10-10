# 2026-10-10 · shelby · no LLM

## Result and cost

| Run | D01 score | D01 C_deal (EUR) | D02 score | D02 C_deal (EUR) | Mean | Rounds D01 / D02 |
|---|---|---|---|---|---|---|
| `20261010-190733-sandbox-shelby` | 0.663 | 422,171 | 0.566 | 181,728 | 0.614 | 2 / 9 |
| `20261010-190816-sandbox-shelby` | 0.663 | 422,171 | 0.566 | 181,728 | 0.614 | 2 / 9 |
| `20261010-191145-sandbox-shelby` | 0.663 | 422,171 | 0.566 | 181,728 | 0.614 | 2 / 9 |
| **Mean over the plays of each case** | **0.663** | | **0.566** | | **0.614** | |

Sandbox: D01 (price increase, stabilise; C_open 448,811, C_best 408,624) and D02 (RFQ with two suppliers, leverage;
C_open 214,296, C_best 156,739). "Not played": the arena refused the session (10 open sessions per key) because
several runs were started at once; such a case is left out of the means.

Run cost: 0 practice sessions (sandbox), 0 LLM tokens, 2-3 minutes wall time per run.

## Strategy

`strategy/experiments.py`, strategy name `shelby`, commit `b726d4c` plus the uncommitted branch `feat/tactic-experiments`.
Baseline with a curt, hard tone and a threat to place the order elsewhere.

| Parameter | Value |
|---|---|
| `tone` | `shelby` (texts in `TONES`) |
| everything else | baseline v2: anchors (leverage 18 %, routine 12 %, stabilise 8 %), reciprocity 1.0, minimum step 0.4 %, equal-C menu |

## Notes

- Hurts in both cases: D01 0.663 (baseline 0.843), D02 0.566 (baseline 0.629).
- D01: the foundry - a family business that values the relationship - gave its final offer after two rounds at 51.40, a round earlier and 0.90 per unit dearer than with the baseline's wording.
- D02: the job shop still moved, but more slowly (15.00 after five rounds; baseline 14.70 after four).
