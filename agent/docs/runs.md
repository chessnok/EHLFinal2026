# Run registry

Every run on the arena gets a row here: practice runs (they spend the team's quota) always, sandbox runs when they
inform a decision. Rules: [`AGENTS.md`](../../AGENTS.md#run-registry-and-pushed-code-only). Newest rows go at the bottom
of each table.

- **Commit:** the pushed commit the run used (`git rev-parse --short HEAD`).
- **Strategy:** `--strategy` value.
- **Parameters:** cases, `--llm`, flags, anything that changes behaviour.
- **Results:** per-case scores and the mean.
- **Conclusions:** what we learned and what changes because of it.

Scores are the arena's case score, 0-1. Sandbox cases are D01 (price increase, stabilise) and D02 (RFQ with two
suppliers, leverage).

**Reconstructed rows (before 10 Oct 2026, 18:30 UTC).** The registry was introduced after these runs:
- Commit and author were inferred from the session times, the commit times and the e-mail texts; the arena API does
  not record them. Inferred values are marked *likely*.
- My own sandbox runs used code that was committed later (hash shown as "uncommitted → hash").

## Practice runs (spend quota)

| # | Time (UTC) | Commit | Strategy | Parameters | Author | Description | Results | Conclusions |
|---|---|---|---|---|---|---|---|---|
| P-1 | 12:47 | none (starter kit) | kit naive agent | P01 | unknown | first try with the kit's example agent | P01 0.583 | baseline to beat |
| P-2 | 14:33 | *likely* `e8c39c9` + local `claude-code` provider (committed later in `575b78b`) | `llm` | all 10 hosted cases, `--llm claude-code:haiku` | *likely* Vector | first full practice pass of the llm strategy | P01 0.858, P02 0.156, P03 0.762, P04 0.860, P05 0.524, P07 0.695, P08 0.017, P10 0.484, P11 0.231, P18 0.000 · mean 0.459 | strong on renewals and price increases (P01, P03, P04); P08 closed on a 12-month contract (half the need uncovered); P18 accepted the opening |
| P-3 | 14:50 | same as P-2 | `llm` | all 10, `claude-code:haiku` | *likely* Vector | second full pass | P01 0.829, P02 0.255, P03 0.762, P04 0.860, P05 0.267, P07 0.650, P08 0.305, P10 0.469, P11 0.231, P18 0.252 · mean 0.488 | P08 and P18 improved by taking the index clause; P05 varies a lot between passes |
| P-4 | 14:57 | *likely* `cfad9d9` (tactical with ground truth and replay lessons) | `tactical` | P02, P08, P18 | *likely* DavidtheRavinger | tactical on the three weakest llm cases | P02 0.156, P08 0.017, P18 0.000 (no deal) | 12-month deal on P08; refused index clause on P18 → no deal |
| P-5 | 15:04 | unknown | P02 `tactical`; P08 and P18 an accept-the-price variant ("We can accept your price of EUR …") | P02, P08, P18 | *likely* DavidtheRavinger | calibration of floors and upper bounds | P02 0.268, P08 0.044, P18 0.000 (no deal) | accepting the opening price does not pay on raw-material cases |
| P-6 | 15:06 | same as P-2 | `llm` | all 10, `claude-code:haiku` | *likely* Vector | third full pass | P01 0.851, P02 0.252, P03 0.762, P04 0.860, P05 0.369, P07 0.624, P08 0.327, P10 0.477, P11 0.398, P18 0.252 · mean 0.517 | best full llm pass; P11 crumb steps; P10 accepted a round-1 final offer |
| P-7 | 15:07 | *likely* `cfad9d9` | `tactical` | P02, P08 | *likely* DavidtheRavinger | retry | P02 0.156, P08 0.000 (no deal) | – |
| P-8 | 15:10 | *likely* `cfad9d9` | `tactical` | P02, P08, P18 | *likely* DavidtheRavinger | retry after calibration | P02 0.156, P08 0.538, P18 0.319 | best P08 (index clause with 5 % deadband) and best P18 so far |
| P-9 | 16:03 | *likely* `cfad9d9` or later | `tactical` (P11, P10, P05, P18), `llm` (P02) | P02, P05, P10, P11, P18 | *likely* DavidtheRavinger / Vector | pass over the weak cases | P02 0.293 (llm), P05 0.712, P10 0.562, P11 0.147, P18 0.252 | new team bests on P05, P10 (tactical) and P02 (llm); tactical weak on P11 |
| P-10 | 16:36 | *likely* `243b294` (tactical unchanged on `feat/tactic-experiments`) | `tactical` | P02, P11, P18 | *likely* Vector | tactical after the teammate's menu, ground-truth and counter-step changes | P02 0.366, P11 0.441, P18 0.467 | new bests on P11 and P18 (index clause, final offer accepted) |
| P-11 | 16:51 | *likely* `243b294` | `tactical` | all 10 hosted cases | *likely* Vector | full tactical pass | P01 0.856, P02 0.686, P03 0.903, P04 0.860, P05 0.824, P07 0.702, P08 0.603, P10 0.555, P11 0.545, P18 0.000 (walked away) · mean 0.653 | best full pass so far; P18 walked after a 2-cent push on a final offer that said "bridge the remaining gap"; options B/C repeated unchanged; P02 varies (0.366 vs 0.686 on the same code) |
| P-12 | 19:32 | `7613d6d` | `llm` v3 on tactical mechanics | P02, P05, P08, P10, P11, P18, `--llm claude-code:opus`, `--parallel 2` | Mikhail Fadin | first practice check of llm on tactical mechanics | P02 0.366, P05 0.824, P08 0.473, P10 0.539, P11 **0.692**, P18 0.401 · mean 0.549 | new best on P11; no walk-away (P18 took its 5.60 final, R3); P10 and P18 got final offers in R1/R3 and were taken without a probe; P08 and P18 closed above the calibrated upper bound; 28 model calls, 0 fallbacks, $1.194 measured |
| P-13 | 21:18 | `96f7545` | `tactical` | all 10 hosted cases, `--parallel 5` | Vector (Claude session) | reference pass of tactical as on main, next to playbook | P01 0.856, P02 0.686, P03 0.905, P04 0.860, P05 0.742, P07 0.721, P08 0.570, P10 0.647, P11 0.545, P18 0.419 · mean 0.695 | 10 of 10 deals; no thread used more than 4 of 10 rounds; details in `backlog.md` |
| P-14 | 21:21 | `96f7545` | `playbook` | all 10 hosted cases, `--parallel 5` | Vector (Claude session) | first practice pass of the books-guide strategy with its closing offer after a final offer | P01 0.917, P02 0.385, P03 0.762, P04 0.000 (walked away), P05 0.295, P07 0.121 (walked away), P08 0.316, P10 0.568, P11 0.398, P18 0.000 (walked away) · mean 0.376 | the closing offer made 3 of 10 suppliers walk away, which the sandbox never showed; do not push past a final offer without a fallback; new best on P01 |
| P-15 | 22:14 | `fe7a9ea` | `tactical-slow25` | all 10 hosted cases, `--parallel 5`; our step a quarter of tactical's | Vector (Claude session) | slower concessions on practice, and a check of the simulator's figures written down before the run | P01 0.914, P02 0.000 (deal above C_open), P03 0.903, P04 0.860, P05 0.689, P07 0.585, P08 0.515, P10 0.647, P11 0.626, P18 0.467 · mean 0.621 | no gain over tactical (0.695); P02's price left the supplier below its sustainable margin: relationship charge 179,204, which our cost estimate had at 0; the simulator's figures did not hold |
| P-16 | 10 Oct 23:37 | `9a73f1d` | `tactical` | P02, P03 | Vector (Claude session) | margin charge in C: supplier's standard terms from master data, full cost 0.98 x should-cost, no ask under the cost minimum | P02 0.421, P03 0.903 | no zero; P02 without a clause: we went 362.11 → 367.90 → 370.36 and met its 372.62 in round 3 of 10 |
| P-17 | 10 Oct 23:44 | `d8f9f04` | `tactical` | P01, P02 | Vector (Claude session) | first ask at the cost minimum, a quarter of the step | P01 0.785, P02 0.421 | no change on P02 (same e-mails); the 0.4 % of C minimum step is 8 % of P01's room and 19 % of P02's |
| P-18 | 10 Oct 23:51 | `94310f1` | `tactical` | P01, P02, P03 | Vector (Claude session) | deep first ask on the low-price side of the cost curve, step scaled to the room | P01 0.896, P02 0.576, P03 0.828 | P01: supplier came down 138.55 → 132.50 in four replies. The deep ask went out on an index clause (P02, agreed at 356.17) and on 30 days (P03, agreed at 430.01): both dearer structures |
| P-19 | 10 Oct 23:55 | `2ec61e3` | `tactical` | P01, P02, P03 | Vector (Claude session) | deep ask only on our cheapest structures | P01 0.728, P02 0.380, P03 0.903 | P02 without a clause ends at a final offer of 372.96; P01 closed by an early price match in round 3 |
| P-20 | 11 Oct 00:01 | `023d02e` | `tactical` | P01, P02, P03, P10 | Vector (Claude session) | index clause offered at our cost minimum when the supplier argues with that index; no early price match | P01 0.733, P02 0.733, P03 0.903, P10 0.647 | P02: supplier agreed to 362.02 with a 5 % deadband in round 1. P01 took an alternative sheet in round 3 at 134.80: the upper bound had shrunk to the supplier's own offer |
| P-21 | 11 Oct 00:05 | `cdd288c` | `tactical` | P01, P02 | Vector (Claude session) | upper bound scaled to the room | P01 **0.969**, P02 0.733 | P01: final offer 131.30 after four replies; team best on P01 and P02 |
| P-22 | 11 Oct 00:16 | `7143676` | `tactical` | all 10 hosted cases, `--parallel 5` | Vector (Claude session) | full pass of the candidate, with the brief-reading fixes | P01 0.969, P02 0.733, P03 0.903, P04 0.860, P05 0.742, P07 0.663, P08 0.550, P10 0.647, P11 0.672, P18 0.618 · mean 0.736 | 10 of 10 deals, no zero; against P-13 (0.695): P01 +0.113, P02 +0.047, P11 +0.127, P18 +0.199, P07 −0.058, P08 −0.020; P07, P08, P11, P18 also carry main's changes since `96f7545`, not separated |
| P-23 | 11 Oct 00:24 | `9af44f6` | `tactical` | P11 | Vector (Claude session) | complaints (`qn:`) as further arguments in a quality case, one per round | P11 0.672 | no change: the complaint came back `duplicate` in round 4 and the supplier's offer became final; reverted |
| P-24 | 11 Oct 00:33 | `9f95282` | `tactical` | P08, P18 | Vector (Claude session) | the running contract's index clause cited against the supplier's index argument | P08 0.539, P18 0.485 | worse than P-22 (0.550, 0.618): the clause sentence got no claim result; reverted |
| P-25 | 11 Oct 00:38 | `cfd6310` | `tactical` | P07 | Vector (Claude session) | first ask at most 13 % under the quote for a `routine` goal (25 % before) | P07 **0.740** | supplier: 5.59 → 5.48 → 5.45 → final 5.42; at 25 % it was 5.69 → final 5.54 (P-22, 0.663); team best on P07 |
| P-26 | 11 Oct 00:43 | `7742d51` | `tactical` | P01, P03 | Vector (Claude session) | own-plant should-cost cited from 3 % under the quote | P01 0.952, P03 **0.923** | P03: first reply 432.15 (432.94 before), team best; P01: the should-cost took the forecast's place in round 4, final offer 131.80 (131.30 in P-22) - ranked behind the forecast afterwards |
| P-27 | 11 Oct 01:03 | `6bb73d1` | `tactical` | all 10 hosted cases, `--parallel 5` | Vector (Claude session) | full pass after merging main (`b3f06da`: equal-C options, one more ask under an open offer) with the margin-charge branch, the routine cap and the should-cost argument | P01 0.969, P02 0.733, P03 0.923, P04 0.860, P05 0.742, P07 0.740, P08 0.550, P10 0.647, P11 0.672, P18 0.618 · mean **0.746** | 10 of 10 deals, no zero; against P-22: P03 +0.020, P07 +0.078, the rest identical to the cent |

**Team best per case** (what the practice board counts), as of P-12:

| P01 | P02 | P03 | P04 | P05 | P07 | P08 | P10 | P11 | P18 | Mean ×100 |
|---|---|---|---|---|---|---|---|---|---|---|
| 0.858 (llm) | 0.686 (tactical) | 0.903 (tactical) | 0.860 | 0.824 (tactical) | 0.702 (tactical) | 0.603 (tactical) | 0.562 (tactical) | 0.692 (llm) | 0.467 (tactical) | 71.57 |

Quota after P-12: 66 used of a limit raised to 650, resetting 2026-10-11 12:47 UTC.

After P-14 the team bests are P01 0.917 (playbook), P03 0.905, P07 0.721 and P10 0.647 (tactical), the others as
above: 73.2 on the practice board. Quota after P-14: 96 used of 650.

## Sandbox runs (free)

| # | Time (UTC) | Commit | Strategy | Parameters | Author | Description | Results (D01 / D02 · mean) | Conclusions |
|---|---|---|---|---|---|---|---|---|
| S-1 | 13:00 | uncommitted → `4f3a7b0` | `baseline` v1 | D01, D02 | Mikhail Fadin | first baseline on real bots | 0.268 / 0.425 · 0.346 | concedes into the supplier's price; supplier picks its own short structure |
| S-2 | 13:29 | uncommitted → `b2d58a6` | `llm` | `--llm ollama:qwen3.6` | Mikhail Fadin | first LLM layer | 0.100 / 0.455 · 0.277 | model wrote its own prices into the text (contradicting the sheets); iso-C lever price far too low |
| S-3 | 13:34 | uncommitted → `b2d58a6` | `llm` | `ollama:qwen3.6` | Mikhail Fadin | after stripping figures and fixing the lever price | 0.210 / 0.448 · 0.329 | parity with baseline v1 |
| S-4 | 13:44 | uncommitted → `8670be2` | `baseline` v2 | D01, D02 | Mikhail Fadin | equal-C menus, deeper anchors, reciprocal concessions | **0.843 / 0.629 · 0.736** | the mechanics, not the model, drove the gain |
| S-5 | 13:44 | uncommitted → `8670be2` | `llm` on v2 | `ollama:qwen3.6` | Mikhail Fadin | llm layer on baseline v2 | 0.663 / 0.545 · 0.604 | model concedes more cautiously than these bots need |
| S-6 | 13:55 | `be8f4b5` | `tactical` | D01, D02 | Mikhail Fadin (teammate's branch) | first tactical on real bots | 0.773 / 0.505 · 0.639 | anchor cap at -15 % likely costs D02 |
| S-7 | before 14:54 | `b726d4c` / `cfad9d9` (as reported in the commit) | `tactical` | D01, D02 | DavidtheRavinger | ground truth, then replay lessons | 0.789 / 0.570 → 0.823 / 0.650 · 0.737 | figures from the commit message, not re-measured |
| S-8 | 14:49 | uncommitted → `ea0cd5c` | `decided` | Decisions API `gpt-6-luna` | Mikhail Fadin | first decided run | 0.773 / 0.000 (walked away) | runner bug: late keepalive and a lost agreed offer (fixed in `e1971eb`) |
| S-9 | 14:56 | uncommitted → `ea0cd5c` + `95c1555` | `decided`; `llm` | `gpt-6-luna`; `--llm openai:gpt-6.1-sol` | Mikhail Fadin | after the runner fix | decided 0.773 / 0.564 · 0.668; llm 0.643 / 0.524 · 0.583 | decided at least as good as tactical, below baseline v2 |
| S-10 | 15:01 | uncommitted → `ea0cd5c` | `decided` | + extra questions (near_floor, walk_risk, firmness) | Mikhail Fadin | telemetry check | 0.773 / 0.564 · 0.668 | the model reads suppliers as far from their floor (near_floor ≈ 0.2) |
| S-11 | 15:08 | uncommitted → `ea0cd5c` | `decided` | levels firm / hard / very_hard | Mikhail Fadin | stronger, always distinct levels | 0.740 / 0.553 · 0.646 | the API now picks different levels (firm 6, hard 3) |
| S-12 | 15:12 | uncommitted → `ea0cd5c` | `decided` | + C and its parts per candidate | Mikhail Fadin | money framing | 0.756 / 0.553 · 0.655 | with money shown, the model always picks the softest level |
| S-13 | 16:10 | uncommitted → `653398b` | `llm` v3 (practice feedback in the prompts) | `--llm claude-code:haiku` | Mikhail Fadin | sandbox check before practice | 0.763 / not played (429: 10 open sessions on the team key) | coordinate runs: the key allows 10 open sessions for the whole team |
| S-14 | 19:11 | uncommitted → `cae4ae9` | `llm` v3 on tactical mechanics | `--llm claude-code:opus` | Mikhail Fadin | llm now inherits tactical (ground truth, full equal-C menu, counter-steps, best sheet, written price, guarded close); no probe of a last word inside the upper bound; every option moves each round | **0.969** / 0.615 · 0.792 | D01 best ever (tactical 0.909); 15 model calls, 0 fallbacks, cost $0.502 (measured) |
| S-15 | 19:56 | uncommitted → `97e6004` | `playbook`; `playbook-noprobe` | D01, D02 | Vector (Claude session) | baseline plus a deeper anchor, a cash sheet and one closing offer after a final offer; the control leaves the closing offer out | playbook 0.943 / 0.660 · 0.801; noprobe 0.869 / 0.639 · 0.754 | the closing offer gained on both demo cases and no demo supplier walked away - practice (P-14) contradicted it |
| S-16 | 21:44 | `556a31d` | `tactical` | D01, D02 | Vector (Claude session) | control for S-17 on the current main | 0.969 / 0.587 · 0.778 | – |
| S-17 | 21:46 | uncommitted → `ef1bb70` | `tactical-slow25` | D01, D02; our step a quarter of tactical's | Vector (Claude session) | slower concessions, from `backlog.md` 2.1 | 0.957 / 0.671 · 0.814 | D02 +0.084, D01 −0.012; the simulator had pointed the same way; not played on practice |
| S-18 | 11 Oct 01:47 | uncommitted → the commit that adds this row | `urgent` | D01, D02, played twice | Vector (Claude session) | a wording nobody had played (urgency and no alternative leaked), after the simulator's llm opponent had given its figures | 0.703 / 0.461 · 0.582 (both plays) | −0.14 on both cases against S-19; the simulator had said 0.716 / 0.455 |
| S-19 | 11 Oct 01:52 | same | `baseline` | D01, D02 | Vector (Claude session) | control for S-18 in the same hour | 0.843 / 0.608 · 0.725 | – |

After P-27 (11 October, 01:05): 42 practice sessions spent by this series (P-16 to P-27). Team bests from `negotiator
me` then: P01 0.969, P02 0.733, P03 0.905, P04 0.860, P05 0.839, P07 0.721, P08 0.626, P10 0.663, P11 0.692,
P18 0.618.
