# 2026-10-11 · tactical-ev and tactical on `refactor/strategy-review` · no LLM

## Result and cost

All ten hosted practice cases, one session each, `--parallel 5`. `main at the fork` is `tactical` on `ec948f4`
(`../runs.md` P-49, P-50, the same morning; P03, P04, P07, P10, P18 from P-43 to P-48, message-identical there).

| Case | `tactical-ev` first table (`ed34340`) | `tactical-ev` (`1d30525`) | `tactical` (`1d30525`) | main at the fork |
|---|---|---|---|---|
| P01 | 0.934 | 0.855 | 0.924 | 0.924 |
| P02 | 0.733 | 0.733 | 0.733 | 0.733 |
| P03 | 0.923 | 0.923 | 0.923 | 0.923 |
| P04 | 0.860 | 0.860 | 0.860 | 0.860 |
| P05 | 0.865 | 0.865 | 0.865 | 0.865 |
| P07 | 0.715 | 0.728 | 0.728 | 0.740 |
| P08 | 0.571 | 0.670 | 0.571 | 0.626 |
| P10 | 0.647 | 0.647 | 0.647 | 0.647 |
| P11 | 0.710 | 0.710 | 0.626 | 0.710 |
| P18 | 0.532 | 0.552 | 0.618 | 0.685 |
| **Mean** | **0.749** | **0.754** | **0.750** | **0.771** |

C of the deals, `tactical-ev` on `1d30525`: P01 1,105,084, P02 2,248,174, P03 3,935,069, P04 196,853, P05 234,490,
P07 324,253, P08 1,018,176, P10 1,541,808, P11 750,083, P18 255,156. 10 of 10 deals in each run, no walk-away.
Run cost: 30 practice sessions, 0 LLM tokens, about 2.5 minutes wall time per run.

Sandbox, one run each on `2d0af0b` (the first table): `tactical` D01 0.669, D02 0.660; `tactical-ev` D01 0.669,
D02 0.702 (main, S-35: 0.669 / 0.587).

Neither variant of this branch reaches main at the fork. Both lose on P18 and P07; `tactical` also on P08 and P11,
`tactical-ev` on P01, and `tactical-ev` wins P08 (0.670, with the team's best).

## Strategy

`strategy/tactical/` (the package that replaced `tactical.py`), commit `1d30525`.

- `tactical`: main's `tactical` at `36a9752` with the review's fixes (a message without arguments clears
  `last_claims`; one cash-short rate, 1.2; stalls and the supplier's step read from its best sheet for us; state
  reset in `prepare`; dead anchor code removed), the flags settled (`clause_rel_only`, `cheap_yes`, `fast_pay` part
  of the strategy, the other fourteen deleted) and claim results matched through `ledger.arguments_read`.
- `tactical-ev`: the same, with the round's choice (take, ask and how much, probe) by expected cost
  (`tactical/choice.py`). The first table keyed the supplier's response on the share of the distance between us that
  our ask closes; the second on our step against the supplier's room to its estimated stop.

Not separated by these runs: which of the fixes costs `tactical` P08, P11 and P18. The three suppliers send
alternative sheets, and reading their step from the best sheet changes our own step from round 2 on; the other
fixes change no message in a single-supplier thread without a guess floor. This is a reading of the code and the
traces, not a measurement.

## Runs

`runs/20261011-112039-practice-tactical-ev` (first table), `runs/20261011-113019-practice-tactical-ev`,
`runs/20261011-113256-practice-tactical`; sandbox `runs/20261011-110839-sandbox-tactical`,
`runs/20261011-110922-sandbox-tactical-ev`.
