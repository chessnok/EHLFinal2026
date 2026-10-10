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

**Team best per case** (what the practice board counts), as of P-11:

| P01 | P02 | P03 | P04 | P05 | P07 | P08 | P10 | P11 | P18 | Mean ×100 |
|---|---|---|---|---|---|---|---|---|---|---|
| 0.858 (llm) | 0.686 (tactical) | 0.903 (tactical) | 0.860 | 0.824 (tactical) | 0.702 (tactical) | 0.603 (tactical) | 0.562 (tactical) | 0.545 (tactical) | 0.467 (tactical) | 70.10 |

Quota after P-11: 60 used of a limit raised to 650, resetting 2026-10-11 12:47 UTC.

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
| S-14 | 19:11 | uncommitted → `b8889e3` | `llm` v3 on tactical mechanics | `--llm claude-code:opus` | Mikhail Fadin | llm now inherits tactical (ground truth, full equal-C menu, counter-steps, best sheet, written price, guarded close); no probe of a last word inside the upper bound; every option moves each round | **0.969** / 0.615 · 0.792 | D01 best ever (tactical 0.909); 15 model calls, 0 fallbacks, cost $0.502 (measured) |
