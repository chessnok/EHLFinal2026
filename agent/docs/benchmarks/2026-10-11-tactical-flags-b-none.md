# 2026-10-11 · tactical and block B's flags · no LLM

## Result and cost

| Strategy | P07 | P08 | P02 | Mean |
|---|---|---|---|---|
| `tactical` (control) | 0.740 | 0.550 | 0.733 | 0.674 |
| `tactical+fresh_args` | 0.721 | 0.528 | 0.733 | 0.661 |
| `tactical+all_windows` | 0.753 | 0.528 | 0.733 | 0.671 |
| `tactical+cheap_alt` | 0.740 | **0.560** | 0.733 | **0.678** |

C_deal in EUR, the same in both runs of each strategy:

| Strategy | P07 | P08 | P02 |
|---|---|---|---|
| `tactical` | 323,061 | 1,039,278 | 2,248,174 |
| `tactical+fresh_args` | 324,849 | 1,043,113 | 2,248,174 |
| `tactical+all_windows` | 321,869 | 1,043,113 | 2,248,174 |
| `tactical+cheap_alt` | 323,061 | 1,037,632 | 2,248,174 |

Every strategy ran twice; the second run returned the same scores and C_deal on every case. 24 of 24 deals.
Run cost: 24 practice sessions (balance 346 → 322 of 650), 0 LLM tokens, about 4 minutes wall time.

Decision (rule of `../gameplan-2026-10-11.md`: no case worse than −0.02, a gain somewhere): `cheap_alt` adopted as
default; `fresh_args` (−0.019 P07, −0.022 P08) and `all_windows` (−0.022 P08) stay off.

## Strategy

`strategy/tactical.py`, commit `94a612b` (branch `fix/final-robustness`): `tactical` with the review's block A, and
three flags off by default:

| Flag | What it does |
|---|---|
| `fresh_args` | never an argument the arena already counted (one per kind, index series, part); arguments held back from the first e-mail for rounds 2-4 |
| `all_windows` | an index fall over the steepest window api.md accepts, one per series |
| `cheap_alt` | the supplier's alternative sheet taken when it saves 0.1 % of the room (at least EUR 10) instead of 0.2 % of C, and only when the sheet we send for it still beats its primary one |

## Runs

Set practice, cases P07, P08, P02 (`../runs.md` P-34 to P-41): `20261011-052429-practice-tactical`,
`-052433-practice-tactical+fresh_args`, `-052549-practice-tactical+all_windows`, `-052701-practice-tactical+cheap_alt`,
`-052714-practice-tactical`, `-052717-practice-tactical+fresh_args`, `-052721-practice-tactical+all_windows`,
`-052724-practice-tactical+cheap_alt`.
