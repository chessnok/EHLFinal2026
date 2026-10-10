# Benchmarks

One record per strategy, day and model: `<date>-<strategy>-<model>.md` (`none`: no LLM). The rule is in the
repository's `AGENTS.md`. This page is the overview; the records hold the runs, parameters and notes.

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

## 2026-10-10 · practice (10 hosted cases) · no LLM

| Strategy | Mean | Deals | Record |
|---|---|---|---|
| tactical (`96f7545`) | **0.695** | 10 of 10 | [record](2026-10-10-tactical-none.md) |
| playbook | 0.376 | 7 of 10 | [record](2026-10-10-playbook-none.md) |

One run each, 20 practice sessions in total. Playbook's closing offer made three suppliers walk away (P04, P07, P18);
scored at the suppliers' final offers the same run gives 0.539, still behind tactical.
