# 2026-10-11 · urgent · no LLM

## Result and cost

| Run | D01 score | D01 C_deal (EUR) | D02 score | D02 C_deal (EUR) | Mean | Rounds D01 / D02 |
|---|---|---|---|---|---|---|
| `20261011-014752-sandbox-urgent` | 0.703 | 420,565 | 0.461 | 187,768 | 0.582 | 3 / 9 |
| `20261011-015411-sandbox-urgent` | 0.703 | 420,565 | 0.461 | 187,768 | 0.582 | 3 / 9 |
| baseline, same hour: `20261011-015200-sandbox-baseline` | 0.843 | 414,947 | 0.608 | 179,312 | 0.725 | 3 / 8 |

Against the baseline: D01 −0.140, D02 −0.147, mean −0.143. Run cost: 0 practice sessions (sandbox), 0 LLM tokens,
about 7 minutes wall time for the three runs.

## Strategy

`strategy/experiments.py`, strategy name `urgent`, the commit that adds this record. Baseline with an opening and a
closing sentence that leak urgency and a missing alternative ("we have to place this order by the end of this week,
and you are the only supplier qualified for this part").

| Parameter | Value |
|---|---|
| `tone` | `urgent` (texts in `TONES`) |
| everything else | baseline v2, as in `2026-10-10-baseline-none.md` |

## Notes

- **Not a candidate: a probe for the simulator.** The wording had never been played; the simulator's figures were
  taken first (`sim bench baseline urgent --opponents llm --supplier-llm claude-code:sonnet`, three repeats), then
  the sandbox was played. Comparison in `../simulator.md`.
- Leaking urgency and a missing alternative costs 0.14 on both demo cases - the brief's "don't leak", measured.
- Both `urgent` runs gave the same scores: the same e-mails got the same replies.
