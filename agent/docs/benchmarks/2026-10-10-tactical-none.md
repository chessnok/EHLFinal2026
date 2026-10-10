# 2026-10-10 · tactical · no LLM

## Result and cost

| Run | D01 score | D01 C_deal (EUR) | D02 score | D02 C_deal (EUR) | Mean | Rounds D01 / D02 |
|---|---|---|---|---|---|---|
| `20261010-190527-sandbox-tactical` | 0.823 | 415,752 | 0.650 | 176,896 | 0.736 | 5 / 9 |
| `20261010-190529-sandbox-tactical` | not played | – | 0.650 | 176,896 | – | – / 9 |
| `20261010-190745-sandbox-tactical` | 0.823 | 415,752 | 0.650 | 176,896 | 0.736 | 5 / 9 |
| `20261010-191151-sandbox-tactical` | 0.823 | 415,752 | 0.650 | 176,896 | 0.736 | 5 / 9 |
| **Mean over the plays of each case** | **0.823** | | **0.650** | | **0.736** | |

Sandbox: D01 (price increase, stabilise; C_open 448,811, C_best 408,624) and D02 (RFQ with two suppliers, leverage;
C_open 214,296, C_best 156,739). "Not played": the arena refused the session (10 open sessions per key) because
several runs were started at once; such a case is left out of the means.

Run cost: 0 practice sessions (sandbox), 0 LLM tokens, 2-3 minutes wall time per run.

## Strategy

`strategy/tactical.py`, strategy name `tactical`, commit `b726d4c` plus the uncommitted branch `feat/tactic-experiments`.
Policy per category goal adjusted by supplier traits; Boulware concessions in C with tit-for-tat; equal-C menu with a trade lever; guards.

| Parameter | Value |
|---|---|
| policies | `POLICIES` in `strategy/tactical.py` as of this commit, unchanged defaults |

## Notes

- D01: five rounds from a shallow anchor (49.24) to the foundry's final 51.20 - a dearer price than the baseline's 50.50, on a structure that costs nearly the same C.
- D02: the job shop 17.10 → 14.60 by round 2; same end point as `lowball` and `questions`.
