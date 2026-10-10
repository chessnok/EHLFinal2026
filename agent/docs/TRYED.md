# Ideas we tried, and what came of them

One row per idea, newest at the bottom of each table. The rule is in [`AGENTS.md`](../../AGENTS.md#ideas-tried). A row
says what was tried, where it was measured, the result, and why it worked or failed - or "unknown" when no run has
settled it. Figures are from the run named in the row ([`runs.md`](runs.md), [`benchmarks/`](benchmarks/)).

Result: **worked** (kept), **failed** (dropped), **mixed**, **unknown** (not yet measured or not separable).

## Mechanics of the offer

| Idea | Measured on | Result | Why |
|---|---|---|---|
| Fixed concession schedule, three sheets of unequal cost (`baseline` v1) | sandbox S-1 | failed: 0.346 | conceded into the supplier's price; the supplier picked its own short structure |
| Equal-C menu, deeper anchor, reciprocal concessions (`baseline` v2) | sandbox S-4 | worked: 0.346 → 0.736 | every sheet costs us the same, so whichever the supplier takes is fine |
| Policy per category goal plus supplier traits read from the data (`tactical`) | practice P-11, P-13 | worked: 0.653, 0.695, the best full passes | 10 of 10 deals; the guards prevent zeros |
| Anchor capped at 15 % under the quote | sandbox S-6 | failed on D02 (0.505) | the floor there is 19-24 % under the opening |
| Accepting the opening price on raw-material cases | practice P-5 | failed: P08 0.044, P18 no deal | no saving against C_open |
| Refusing the index clause on P18 / a 12-month contract on P08 | practice P-4, P-2 | failed: no deal; 0.017 | both suppliers refuse a fixed price over 24 months; 12 months leaves half the need at the fallback price |
| Index clause with a 5 % deadband on P08, P18 | practice P-8, P-10 | worked: P08 0.538, P18 0.467 | the supplier requires a clause; deadband 5 is the cheapest one in C |
| Slower concessions, a quarter of the step (`tactical-slow25`) | sandbox S-17, practice P-15 | failed: sandbox 0.778 → 0.814, practice 0.695 → 0.621 | no gain without P02 (0.696 → 0.690); P02 closed below the supplier's cost and scored 0 |
| One closing offer after the supplier's final offer (`playbook`) | sandbox S-15, practice P-14 | failed: sandbox +0.047, practice 0.376 | three of ten practice suppliers walked away (P04, P07, P18); a final offer is final |
| Deep first ask, 27-34 % under the quote (`playbook`, `lowball`) | sandbox, practice P-14 | mixed: +0.02 on sandbox; worst first counters on P08 (5.71) and P18 (5.70) | P07: a 26 % ask got "not feasible" and a final offer in round 2 (0.585) against 0.721 at 13 % |
| First ask capped at 13 % under the quote for a `routine` goal | practice P-25 (P07) | worked: 0.663 → 0.740 | at 25 % the supplier answered "not feasible" with a final offer in round 2 (5.54); at 13 % it came down over four replies to 5.42 |

## Wording and arguments

| Idea | Measured on | Result | Why |
|---|---|---|---|
| Naming a budget ceiling (`budget`) | sandbox | failed: D02 0.314 against 0.629 | the supplier aims at the ceiling |
| Hard tone, "with you or without you" (`shelby`) | sandbox | failed: 0.614 against 0.736 | the supplier asks for the competitive data and gives a final offer a round earlier |
| Polite tone (`polite`) | sandbox | no effect: −0.011 | "padding does not buy price" (brief) |
| Questions to the supplier (`questions`) | sandbox | no effect: +0.003 | – |
| Refusing the minimum step, trading terms (`trade`) | sandbox | no effect: −0.015 | – |
| Price-history argument in the first e-mail | practice P-13 | failed in 5 of 5 cases | "it holds, but it does not change our calculation" |
| Forecast as proof of volume | practice P-13 | worked in 5 cases | "it holds and we took it into account"; cited again it comes back `duplicate` (P07) |
| Falling index over a short window | practice P-15 | worked on P18 and partly on P08 | "we have adjusted our pricing accordingly"; P08's AS-14404 is hedged until March, only PPI-C2431 counted |
| A rival's quote cited by ID | sandbox, practice | worked | "it holds and we took it into account" |
| The contract's own index clause cited against the supplier's index argument ("the rise is already in the price we pay", `ctr:…#3.2`) | practice P-24 (P08, P18) | failed: P08 0.550 → 0.539, P18 0.618 → 0.485 | the arena did not read it as an argument (no claim result), and it took the first e-mail's slot from one that counts |
| Own-plant should-cost cited from 3 % under the quote (12 % before) | practice P-26 (P01, P03) | mixed: P03 0.903 → 0.923, P01 0.969 → 0.952 | P03: "below this price we would need facts" - with it the first reply came at 432.15 instead of 432.94. P01: ranked ahead of the forecast it took round 4 and the final offer was 131.80 instead of 131.30; now ranked last |
| Complaints (`qn:` rows) cited one by one as further quality arguments | practice P-23 (P11) | failed: 0.672, unchanged | the first one came back `duplicate` after the scorecard's ppm figure, and the supplier called its offer final in that round |

## LLM

| Idea | Measured on | Result | Why |
|---|---|---|---|
| LLM writes the e-mail and picks the stance on `baseline` (`llm`) | sandbox S-2 to S-5, practice P-2, P-3, P-6 | failed: below the baseline it runs on; practice 0.459-0.517 | the model concedes more cautiously than the bots need; early versions wrote prices that contradicted the sheets |
| LLM picks among prepared moves (`decided`) | sandbox S-8 to S-12 | failed: 0.646-0.668 against 0.736 | shown the money, the model always picks the softest level |
| LLM on `tactical` mechanics (`llm` v3, opus) | sandbox S-14, practice P-12 | mixed: D01 0.969, P11 0.692 (team best); mean 0.549 on six cases | better text on P11; no gain elsewhere |

## Cost model and tooling

| Idea | Measured on | Result | Why |
|---|---|---|---|
| Supplier simulator fitted from replays as a score predictor | `negotiator sim check`, practice P-15 | failed as a predictor, kept as a smoke test | its figures for slow25 did not hold on practice |
| A model as the simulated supplier, shown that supplier's recorded exchanges and the brief's list of signals (`sim --opponents llm`) | blind test of 11 October, `gpt-6.1-sol`: eight wordings on D01 and D02, `playbook` on practice (`simulator.md`) | failed as a clone of the arena, kept as an alarm for leaks | sees a named budget and urgency; punishes `trade` and `shelby` on D02 where the arena does not (0.236, 0.244 against 0.587, 0.566); no walk-aways for `playbook` (P04 0.860 against 0.000); mean gap 0.073, the fitted supplier 0.071 |
| Leaking urgency and a missing alternative (`urgent`) | sandbox S-18, S-19 | failed: 0.582 against 0.725 for the baseline | both suppliers held a higher price; DEMO-C1 raised its price and walked away |
| Supplier's full cost = should-cost moved with the cost drivers | practice P-15 | failed | 380.01 for P02 against a quote of 370.96; the charge would have dominated every move, so it was switched off |
| Margin charge estimated only when the quote PDF names payment terms and Incoterm | practice P-13, P-15 | failed | no PDF of P01, P02, P03 or P10 names them: the charge was 0 in our C and P02 closed at 345.39 (charge 179,204, score 0) |
| Margin charge in our C: standard terms from the supplier master data, full cost = 0.98 x own-plant should-cost | fitted on 14 recorded deals; practice P-16 to P-22 | worked: no deal above C_open in 26 sessions | the recorded charges of P01, P02, P03 are reproduced to within EUR 56; `c_best` of P01 equals the minimum of C with the charge ([`investigation-2026-10-10.md`](investigation-2026-10-10.md)) |
| First ask at the price that minimises C, usual 0.4 % of C step | practice P-16, P-17 | failed: P02 0.421, P01 0.785 | near the minimum C is flat in the price, so a small step in C is a large step in price; we met the supplier in round 3 of 10 |

## Strategic cases (`stabilise`, `secure_supply`)

| Idea | Measured on | Result | Why |
|---|---|---|---|
| Deep first ask on the low-price side of the cost curve (a deal on it costs at most a quarter of the room), rising in small steps | practice P-18, P-21, P-22 | worked on P01: 0.856 → 0.896 → 0.969 | the supplier came down 138.55 → 131.30 in four replies while our rising ask cost us nothing; this is the "ask for less than we will take" idea, bounded by the charge |
| The same deep ask on every structure | practice P-18 | failed: P02 0.576, P03 0.828 | the supplier agreed at once to the deep sheet on a dearer structure (index clause; 30 days' payment) |
| Minimum step and upper bound as shares of the room instead of C | practice P-20 → P-21 | worked: P01 0.733 → 0.969 | 1 % and 6 % of C are more than the whole room; the bound had become the supplier's own offer and its alternative sheet was taken in round 3 |
| Our step at 0.1 % of C | sandbox D01 | failed: 0.809 against 0.969 | the supplier answered in crumbs of 0.1 a reply |
| P02 without an index clause | practice P-16, P-19 | failed: 0.421, 0.380 | it stops at 372.62-372.96 at 90 days whatever we ask |
| P02: index clause (5 % deadband) at the price that minimises our C | practice P-20 to P-22 | worked: 0.733 three times | it gives 9-22 off its price for a clause; under 361 the margin charge eats the gain (358.45 → 0.686, 356.17 → 0.576, 345.39 → 0) |
| Early price match at the assumed floor (1 % under the quote) | practice P-19 | failed: P01 0.728 | P01's supplier goes 4-5 % under its quote; matching 133.50 in round 3 ended the talks |

## Read from the replays, not yet played

| Idea | Evidence | Result |
|---|---|---|
| "We have alternatives" without naming one, indifference | sandbox `shelby`: the supplier asks for the competitive data, final offer a round earlier, 0.614 against 0.736; brief: an unsupported claim "gives nothing" | unknown on practice; the sandbox says no |
| P11: three sheets at chargeback 0 with ppm 300 / 800 / 1500 | its scorecard ppm is 2376: a EUR 500 chargeback costs it about 1.19 a unit and us 0.135; it priced 800 ppm / 0 at 46.50 against 300 ppm / 0 at 47.00 | unknown |
| P11, P01: one fresh citable argument per round, never an empty round | each accepted argument moved P11's price by 0.50; a round without one got a final offer | unknown |
| P08, P18: first ask 18-20 % under the quote instead of 25-34 %, short-window index falls in the first e-mail | first counters 5.41-5.46 (P08) and 5.40-5.60 (P18) against 5.71 and 5.70 after a 30 % ask | unknown |
| P10: accept the alternative sheet by its own ID instead of resending it | the alternative has an ID of its own (54 days) | unknown |
| P05: offers that arrive after a timeout move are lost | the arena trace shows 14 such offers over 6 P05 sessions; our counter says 0 | unknown |
| LLM as reader and writer around `tactical` (`tactical-llm`, `tactical-llm+reader`; numbers stay with `tactical`; validator, a 10 s budget per e-mail, template as fallback) | sandbox, 4 runs; practice P-28 (P11, P08) | no gain: sandbox 0.618 in every run, the same as `tactical` to the cent; practice P11 0.672 (same), P08 0.507 against 0.550 | the suppliers' price paths did not change with the wording on D01, D02 and P11; the validator refused 3-4 of 7-9 texts; `claude-code:haiku` needs 11-14 s per e-mail and never fits 10 s, `gpt-4o-mini` and `gpt-4o` take 1-5 s |
