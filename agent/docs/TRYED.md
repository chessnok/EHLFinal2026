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
| Supplier's full cost = should-cost moved with the cost drivers | practice P-15 | failed | 380.01 for P02 against a quote of 370.96; the charge would have dominated every move, so it was switched off |
| Margin charge estimated only when the quote PDF names payment terms and Incoterm | practice P-13, P-15 | failed | no PDF of P01, P02, P03 or P10 names them: the charge was 0 in our C and P02 closed at 345.39 (charge 179,204, score 0) |
| Standard terms from the supplier master data; full cost = 0.98 x own-plant should-cost; never ask under the price that minimises C | fitted on 14 recorded deals (P01, P02, P03); practice run pending | unknown | recorded charges are reproduced to within EUR 56; not yet played |
