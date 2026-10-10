# 2026-10-10 · baseline · no LLM

## Result and cost

| Run | D01 score | D01 C_deal (EUR) | D02 score | D02 C_deal (EUR) | Mean | Rounds D01 / D02 |
|---|---|---|---|---|---|---|
| `20261010-190527-sandbox-baseline` | 0.843 | 414,947 | 0.629 | 178,104 | 0.736 | 3 / 8 |
| `20261010-190531-sandbox-baseline` | 0.843 | 414,947 | not played | – | – | 3 / – |
| `20261010-190737-sandbox-baseline` | 0.843 | 414,947 | 0.629 | 178,104 | 0.736 | 3 / 8 |
| `20261010-191150-sandbox-baseline` | 0.843 | 414,947 | 0.629 | 178,104 | 0.736 | 3 / 8 |
| **Mean over the plays of each case** | **0.843** | | **0.629** | | **0.736** | |

Sandbox: D01 (price increase, stabilise; C_open 448,811, C_best 408,624) and D02 (RFQ with two suppliers, leverage;
C_open 214,296, C_best 156,739). "Not played": the arena refused the session (10 open sessions per key) because
several runs were started at once; such a case is left out of the means.

Run cost: 0 practice sessions (sandbox), 0 LLM tokens, 2-3 minutes wall time per run.

## Strategy

`strategy/baseline.py`, strategy name `baseline`, commit `b726d4c` plus the uncommitted branch `feat/tactic-experiments`.
The control: data-backed anchor, reciprocal concession schedule, three term sheets of equal C, cost-based close.

| Parameter | Value |
|---|---|
| anchor | leverage 18 %, routine 12 %, stabilise 8 %, quality_first 6 %, secure_supply 5 % |
| reciprocity / minimum step | 1.0 / 0.4 % |
| close enough | 0.5 % |

## Notes

- The control for the single-tactic experiments in `strategy/experiments.py`.
- Every complete run gave the same scores: for an identical sequence of e-mails the sandbox bots answer identically, so repeating a no-LLM strategy adds no information.
- D01: the foundry's final offer 50.50 after three rounds. D02: the job shop (DEMO-J1) 17.10 → 14.70; the second bidder (DEMO-C1) stays above 16.
