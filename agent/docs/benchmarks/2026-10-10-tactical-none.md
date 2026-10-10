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

## Practice: the 10 hosted cases, commit `96f7545`

| Run | Mean | Deals |
|---|---|---|
| `20261010-211824-practice-tactical` | **0.695** | 10 of 10 |

Run cost: 10 practice sessions, 0 LLM tokens, 2 minutes 33 seconds wall time with `--parallel 5`. `strategy/tactical.py`
as on `main` at `96f7545`, default policies - not the code of the sandbox runs above.

| Case | Type, goal | Score | C_deal (EUR) | C_open | C_best | Rounds |
|---|---|---|---|---|---|---|
| P01 | price_increase, stabilise | 0.856 | 1,105,008 | 1,153,780 | 1,096,816 | 2 |
| P02 | price_increase, stabilise | 0.686 | 2,250,368 | 2,282,867 | 2,235,514 | 2 |
| P03 | renewal, stabilise | 0.905 | 3,941,035 | 4,246,314 | 3,909,043 | 4 |
| P04 | renewal, routine | 0.860 | 196,853 | 198,846 | 196,529 | 3 |
| P05 | rfq, leverage | 0.742 | 244,577 | 305,545 | 223,424 | 9 |
| P07 | bundling, routine | 0.721 | 324,849 | 391,027 | 299,241 | 4 |
| P08 | raw_material, leverage | 0.570 | 1,035,731 | 1,135,887 | 960,309 | 4 |
| P10 | capacity, secure_supply | 0.647 | 1,541,808 | 1,932,492 | 1,328,927 | 2 |
| P11 | quality, quality_first | 0.545 | 765,744 | 817,578 | 722,500 | 4 |
| P18 | raw_material, leverage | 0.419 | 264,784 | 295,173 | 222,651 | 3 |
| **Mean** | | **0.695** | | | | |

- Lowest: P18 and P08 (both raw_material, leverage), P11 (quality) and P10 (capacity).
- Played next to `playbook` on the same cases ([record](2026-10-10-playbook-none.md)): tactical is ahead on nine of
  ten; playbook is ahead on P01 only (0.917).
