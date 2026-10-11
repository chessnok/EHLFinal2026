# 2026-10-11 · tactical and the generalisation flags · no LLM

## Result and cost

Baseline: tag `final-candidate-2026-10-11d`/`e` (P-54, P-55: P01 0.970, P02 0.733, P03 0.923, P05 0.865, P07 0.740,
P08 0.626, P10 0.647, P18 0.685).

| Strategy | Cases | Scores | Against the baseline |
|---|---|---|---|
| `tactical+final_safe` | P05 | 0.865 | = |
| `tactical+own_structures` | P05 | 0.865 | = |
| `tactical+late_facts` | P07, P08, P18, P05 | 0.734, 0.593, 0.685, 0.865 | P07 −0.006, P08 −0.033 |
| `tactical+no_q1` | P08, P18 | 0.582, 0.542 | P08 −0.044, P18 −0.143 |
| `tactical+hide_own_cost` (measurement) | P01, P02, P03, P10 | 0.871, 0.599, 0.923, 0.633 | P01 −0.099, P02 −0.134, P03 =, P10 −0.014 |

12 practice sessions (balance 299 → 287 of 800), 0 LLM tokens, about 6 minutes wall time. 12 of 12 deals, no zero.

Decision (rule: no case worse than −0.02, a gain somewhere): `final_safe` adopted as default because it loses nothing
and removes a push that walked a supplier 10 of 10 times; the other three stay off. `hide_own_cost` is a measurement of
the path most hidden strategic suppliers take (no own-plant should-cost).

## Strategy

`strategy/tactical.py`, commit `e4e3073` (branch `feat/gen-safety`). The flags come from the pattern analysis of 442
practice sessions (fact per round, no question in round 1, no push after a final offer, the supplier's own priced
structures) and from the generality audit (the guessed-cost path).

## Runs

Set practice: `20261011-105647-practice-tactical+final_safe`, `-105721-practice-tactical+own_structures`,
`-105824-practice-tactical+late_facts`, `-105937-practice-tactical+no_q1`, `-110103-practice-tactical+hide_own_cost`
(`../runs.md` P-58 to P-62).
