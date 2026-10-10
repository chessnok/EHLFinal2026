# Benchmarks

One record per strategy, day and model: `<date>-<strategy>-<model>.md` (`none`: no LLM). The rule is in the
repository's `AGENTS.md`. This page is the overview; the records hold the runs, parameters and notes.

## Best full practice pass so far

As of 11 October 2026, 01:05 UTC. One strategy version in one pass over the 10 hosted cases - not the best score per
case picked from different runs. Source: `summary.json` of each run under `agent/runs/`, and `../runs.md`.

| Run | Strategy | Mean | Deals | Run ID |
|---|---|---|---|---|
| P-27 | tactical (`6bb73d1`, merged with main, routine cap, should-cost argument) | **0.746** | 10 of 10 | `20261011-010356-practice-tactical` |
| P-22 | tactical (`7143676`, margin charge in C) | 0.736 | 10 of 10 | `20261011-001629-practice-tactical` |
| P-13 | tactical (`96f7545`) | 0.695 | 10 of 10 | `20261010-211824-practice-tactical` |
| P-11 | tactical | 0.653 | 9 of 10 | – |
| P-15 | tactical-slow25 (`fe7a9ea`) | 0.621 | 10 of 10 | `20261010-221425-practice-tactical-slow25` |
| P-6 | llm (`claude-code:haiku`) | 0.517 | 10 of 10 | `20261010-180637-practice-llm` |
| P-14 | playbook | 0.376 | 7 of 10 | `20261010-212101-practice-playbook` |

P-27 per case: P01 0.969, P02 0.733, P03 0.923, P04 0.860, P05 0.742, P07 0.740, P08 0.550, P10 0.647, P11 0.672,
P18 0.618. Its record is `2026-10-11-tactical-none.md`. The `llm` strategy on tactical's mechanics (P-12,
`claude-code:opus`) played six cases only: mean 0.549, P11 0.692.

## 2026-10-10 · sandbox (D01, D02) · no LLM

| Strategy | D01 | D02 | Mean | vs. baseline | Record |
|---|---|---|---|---|---|
| playbook | 0.943 | 0.660 | **0.801** | +0.065 | [record](2026-10-10-playbook-none.md) |
| lowball | 0.863 | 0.650 | 0.756 | +0.020 | [record](2026-10-10-lowball-none.md) |
| playbook-noprobe | 0.869 | 0.639 | 0.754 | +0.018 | [record](2026-10-10-playbook-none.md) |
| questions | 0.828 | 0.650 | 0.739 | +0.003 | [record](2026-10-10-questions-none.md) |
| tactical | 0.823 | 0.650 | 0.736 | 0.000 | [record](2026-10-10-tactical-none.md) |
| baseline (control) | 0.843 | 0.629 | 0.736 | – | [record](2026-10-10-baseline-none.md) |
| polite | 0.843 | 0.608 | 0.725 | −0.011 | [record](2026-10-10-polite-none.md) |
| trade | 0.856 | 0.587 | 0.721 | −0.015 | [record](2026-10-10-trade-none.md) |
| shelby | 0.663 | 0.566 | 0.614 | −0.122 | [record](2026-10-10-shelby-none.md) |
| budget | 0.863 | 0.314 | 0.588 | −0.148 | [record](2026-10-10-budget-none.md) |

Scores are means over one to four plays of each case. Cost of all runs: 0 practice sessions, 0 LLM tokens.

- **One tactic helps on the sandbox and loses on practice:** a closing offer after the supplier's final offer
  (`playbook`). No demo supplier walked away from it; three of ten practice suppliers did (see below).
- **Two tactics clearly hurt:** naming a budget ceiling (the supplier aims at it) and the hard tone (the family
  foundry closes a round earlier, at a dearer price).
- **One helps a little:** the deeper anchor. Neither bot punished it.
- **The rest is within 0.02 of the baseline:** questions, a polite tone, refusing the minimum step.
- **Repetitions of a no-LLM strategy are nearly identical** on the sandbox (the same e-mails get the same replies), so
  one run per strategy is enough there. The differences above are real for these two cases - and only for them:
  two demo cases and three suppliers say little about the ten practice cases.

## 2026-10-10 · sandbox, `tactical` as on `556a31d` · no LLM

| Strategy | D01 | D02 | Mean | Record |
|---|---|---|---|---|
| tactical-slow25 | 0.957 | 0.671 | **0.814** | [record](2026-10-10-tactical-slow25-none.md) |
| tactical | 0.969 | 0.587 | 0.778 | [record](2026-10-10-tactical-slow25-none.md) |

`tactical` changed during the day, so these two rows do not compare with the table at the top.

## 2026-10-10 · practice (10 hosted cases) · no LLM

| Strategy | Mean | Deals | Record |
|---|---|---|---|
| tactical (`96f7545`) | **0.695** | 10 of 10 | [record](2026-10-10-tactical-none.md) |
| tactical-slow25 (`fe7a9ea`) | 0.621 | 10 of 10 | [record](2026-10-10-tactical-slow25-none.md) |
| playbook | 0.376 | 7 of 10 | [record](2026-10-10-playbook-none.md) |

One run each, 30 practice sessions in total. `tactical-slow25` gained on the sandbox and lost on practice: P02 closed
at a price that cost a relationship charge of 179,204 and scored 0. Playbook's closing offer made three suppliers walk away (P04, P07, P18);
scored at the suppliers' final offers the same run gives 0.539, still behind tactical.

## 2026-10-11 · sandbox (D01, D02) · no LLM · a probe for the simulator

| Strategy | D01 | D02 | Mean | vs. baseline | Record |
|---|---|---|---|---|---|
| baseline (same hour) | 0.843 | 0.608 | 0.725 | – | [record](2026-10-11-urgent-none.md) |
| urgent | 0.703 | 0.461 | 0.582 | −0.143 | [record](2026-10-11-urgent-none.md) |

Two plays of `urgent`, one of the baseline; 0 practice sessions, 0 LLM tokens. Leaking urgency and a missing
alternative costs 0.14 on both cases.

## 2026-10-11 · practice (10 hosted cases) · no LLM

| Strategy | Mean | Deals | Record |
|---|---|---|---|
| tactical+rival_rest (`a252253`), P05 only: 0.824 against 0.742 | – | 1 of 1 | [record](2026-10-11-tactical-none.md) |
| tactical+band_steps (`3a6471d`), six non-strategic cases: P18 −0.133, P08 −0.022, rest equal | – | 6 of 6 | [record](2026-10-11-tactical-none.md) |
| tactical (`17fc8ad`, re-anchor never below our last ask) | **0.746** | 10 of 10 | [record](2026-10-11-tactical-none.md) |
| tactical (`6bb73d1`, merged with main, routine cap, should-cost argument) | **0.746** | 10 of 10 | [record](2026-10-11-tactical-none.md) |
| tactical (`7143676`, margin charge in C) | **0.736** | 10 of 10 | [record](2026-10-11-tactical-none.md) |

Two full runs, 20 practice sessions, and 22 sessions of partial runs (`../runs.md` P-16 to P-27).

## 2026-10-11 · sandbox and two practice cases · `tactical-llm`

| Strategy | D01 | D02 | Mean | Record |
|---|---|---|---|---|
| tactical (main `9d75396`) | 0.649 | 0.587 | 0.618 | [record](2026-10-11-tactical-llm-gpt-4o.md) |
| tactical-llm, tactical-llm+reader (haiku, gpt-4o-mini, gpt-4o) | 0.649 | 0.587 | 0.618 | [record](2026-10-11-tactical-llm-gpt-4o.md) |

Practice with gpt-4o: P11 0.672 (as `tactical`), P08 0.507 (`tactical` 0.550).

