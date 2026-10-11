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
| Re-anchoring never asks below our own last ask | sandbox S-22, practice P-29 | worked: D01 0.649 → 0.749; practice unchanged on all 10 cases | where the first ask was capped (strategic, 4 %), the re-anchor's halfway ask fell under it; the step back read as reneging ("we cannot accept a reduction") and closed D01 at R1's price |
| Hold for the rest of a rival-quote step (`rival_rest`, now default) | practice P-31 (P05) | worked: P05 0.742 → 0.824 | the back office: "half the step now, the rest after the check" - the rest came (30.50 → 28.00) while we moved 0.4 %; the same rule ran for four suppliers in P05 and D02 (`bot-mechanics.md`) |
| Counter-steps of 1-3 % of C outside strategic cases (`band_steps`) | practice P-30 (P04, P05, P07, P08, P11, P18) | failed: P18 0.618 → 0.485, P08 0.550 → 0.528, rest equal | the 1 % floor met the suppliers sooner; the replay correlation (small steps held more often) did not carry over |

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
| Answer a supplier's hedge with our term's dates (`hedge_turn`: "21 of our 24 months come after your cover") | practice P-32 (P08) | failed: P08 0.550, the same price path as P-29 | the supplier agreed and turned it into a reason for the index clause ("you correctly note that the index clause will reflect market movements"); only P08's supplier writes about a hedge |
| Cite an accepted cost driver again over a window with new IDs (`more_drops`, P08: PPI-C2431 05 → 07) | practice P-33 (P08) | failed: P08 0.550 → 0.528 | `duplicate`: "this kind of fact was already taken into account" - the arena counts one argument per index series per case, not per ID; it also took the slot of the forecast |
| A `news` item about the supplier's idle capacity cited by ID from round 2, beside the round's other arguments (`tactical+news`; the one checkable type we never cited, [`argument-audit.md`](argument-audit.md)) | sandbox S-37 to S-40 (D02, `news:N-0412`); practice: not played (only P05's `news:20260309-03` qualifies) | worked on the sandbox: D02 0.587 → 0.713 in 4 of 4 runs on the default before `632048c`, 0.660 → 0.681 on the default after it (S-41), D01 unchanged; unknown on practice | DEMO-J1: `verified`, "the news about Kurzarbeit is true, so we have machines ready", final offer 13.90 instead of 14.50. Cited to the bidder it is not about it comes back `irrelevant` (S-38) |

## LLM

| Idea | Measured on | Result | Why |
|---|---|---|---|
| LLM writes the e-mail and picks the stance on `baseline` (`llm`) | sandbox S-2 to S-5, practice P-2, P-3, P-6 | failed: below the baseline it runs on; practice 0.459-0.517 | the model concedes more cautiously than the bots need; early versions wrote prices that contradicted the sheets |
| LLM picks among prepared moves (`decided`) | sandbox S-8 to S-12 | failed: 0.646-0.668 against 0.736 | shown the money, the model always picks the softest level |
| LLM on `tactical` mechanics (`llm` v3, opus) | sandbox S-14, practice P-12 | mixed: D01 0.969, P11 0.692 (team best); mean 0.549 on six cases | better text on P11; no gain elsewhere |
| `llm` v4: tactical decides, the model writes each e-mail and may ask for one more round where tactical stops on its estimate while the supplier is open | sandbox, 6 runs (`claude-code:opus`) | no gain: D01 0.649 in 5 of 6 runs (0.689 once, the supervisor's extra round), D02 0.587-0.650, once 0 (a held rival's final offer walked while the model wrote) | wording does not move these suppliers' prices (as `tactical-llm`); not committed |

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
| Margin charge without an own-plant should-cost: full cost guessed as opening x (1 - sustainable margin) x 0.98 and put into C (re-anchor off, at most 5 % lower towards a German-base should-cost) | sandbox S-26; `sim bench tactical` | failed: sandbox D01 0.749 → 0.627, sim D01 0.809 → 0.671 | with the guessed charge in C the room between our ask and its 51.50 was EUR 2,170, so we moved 50.74 → 51.41 in one round; the generic should-cost always took the full 5 % drop on P06 |
| The same guess as a floor only: C, targets and concessions without the guessed charge, re-anchor allowed, every ask (and a counter to an offer under it) at or above the price that costs us least with the guessed charge; guess from the main sheet of the first message, no generic should-cost | offline: brief variants (P01, P02, P03, P10 with data unchanged); `sim bench tactical --cases case:D01` against the commit before A3: 0.81 → 0.73, strangers 0.75 → 0.64, jitter 0.74 → 0.67; every other case the same | unknown | the floor binds where the supplier sells under the guess (D01 floor 50.75 at 30 days, the arena charged 0 at 50.80) |
| Re-anchor off for every strategic supplier, sheets capped at its cheapest alternative's price (part of A3, `f526df0`) | practice P-42 (P01) | failed: P01 0.969 → 0.901 | with the own plant's cost in C the re-anchor was what moved P01 (P-29: 133.6 → final 131.30); now off only without any estimate, capped at the standing price (`05a31ea`) |
| Three quick retries of a dropped connection (0.5, 1, 2 s) | practice P-42 (P05) | failed: P05 no deal | a ~15 s DNS outage outlasted them; 45 s of retries with the same X-Move-Id (`d6d3d12`) |

## Read from the replays, not yet played

| Idea | Evidence | Result |
|---|---|---|
| "We have alternatives" without naming one, indifference | sandbox `shelby`: the supplier asks for the competitive data, final offer a round earlier, 0.614 against 0.736; brief: an unsupported claim "gives nothing" | unknown on practice; the sandbox says no |
| P11: three sheets at chargeback 0 with ppm 300 / 800 / 1500 | its scorecard ppm is 2376: a EUR 500 chargeback costs it about 1.19 a unit and us 0.135; it priced 800 ppm / 0 at 46.50 against 300 ppm / 0 at 47.00 | unknown; in the code as `tactical+ppm_ladder` since 11 October (one sheet per allowed ppm level in every message, lowest chargeback, option A's C). Our 43 P11 sessions read on 11 October: no offer under 45.50 at any ppm or chargeback; 800 ppm stood 0.50 under 300 ppm in the same reply (47.00 / 46.50, 46.00 / 45.50); since `cheap_yes` rounds 3-4 carried the 300 ppm sheet alone. `sim bench tactical tactical+ppm_ladder --cases case:P11`: 0.71 both |
| P11, P01: one fresh citable argument per round, never an empty round | each accepted argument moved P11's price by 0.50; a round without one got a final offer | unknown |
| P08, P18: first ask 18-20 % under the quote instead of 25-34 %, short-window index falls in the first e-mail | first counters 5.41-5.46 (P08) and 5.40-5.60 (P18) against 5.71 and 5.70 after a 30 % ask | unknown; in the code as `tactical+anchor18` since 11 October (leverage goal: first ask at most 18 % under the quote). Our 59 P08 sessions read on 11 October: 56 got the final offer in round 3; the one with an 18 % first ask (4.96) got it in round 4. `sim bench tactical tactical+anchor18 --cases case:P08`: 0.54 → 0.50 |
| P10: accept the alternative sheet by its own ID instead of resending it | the alternative has an ID of its own (54 days) | unknown |
| P05: offers that arrive after a timeout move are lost | the arena trace shows 14 such offers over 6 P05 sessions; our counter says 0 | unknown |
| LLM as reader and writer around `tactical` (`tactical-llm`, `tactical-llm+reader`; numbers stay with `tactical`; validator, a 10 s budget per e-mail, template as fallback) | sandbox, 4 runs; practice P-28 (P11, P08) | no gain: sandbox 0.618 in every run, the same as `tactical` to the cent; practice P11 0.672 (same), P08 0.507 against 0.550 | the suppliers' price paths did not change with the wording on D01, D02 and P11; the validator refused 3-4 of 7-9 texts; `claude-code:haiku` needs 11-14 s per e-mail and never fits 10 s, `gpt-4o-mini` and `gpt-4o` take 1-5 s |
| P08: a narrow deadband (0) sells cheaper | 293 replays (`bot-mechanics.md`) | failed to generalise: P08 deadband 0 deals 0.543 vs 5 0.558; P18 0.386 vs 0.583; P02 0.067 vs 0.670 | P08's 0.626 sessions were one path, not a rule |
| P08: a structure the supplier values more than we pay (payment, deadband, contract length) | the supplier's own alternatives in 31 P08 replays | failed: none - deadband 0 → 5 +0.12 per unit against 0.122 in our C, payment 90 → 30 days −0.065 against 0.072, 36 months priced like 24 | it prices each structure as our C does; the gap to the best teams is in the price level |
| Ask beyond the supplier's band so its pricing committee is asked (P02, P03, P10) | back offices of 10 such sessions | failed: approved in 7 of 10, but the price did not fall after (P03 held 432.87 four rounds; P02 rose 367.95 → 372.76) | approval is not a concession |
| Never an argument the arena already counted (one forecast, one scorecard/complaint, one window per index series, orders per part), at least one held back from the first e-mail for rounds 2-4, a bundle's orders per part (`tactical+fresh_args`) | 293 replays: a round-2+ reply to a verified argument was a final offer 4-7 % of the time, without one 53 %, to a duplicate alone 94 %; P07's second to fourth forecasts all `duplicate`. `sim bench tactical tactical+fresh_args --reps 3`: mean 0.729 both (P08 0.56 → 0.69, P10 0.84 → 0.71: a held-back argument is lost when the thread closes after round 1) | failed: practice P-34 to P-41 (P07, P08, P02, two runs each, identical): P07 0.740 → 0.721, P08 0.550 → 0.528, P02 0.733 = | the held-back argument weakened the first reply, which sets the price (P08 5.42 → 5.44; P07 C 323,061 → 324,849); no `duplicate` left, but nothing gained from it |
| An index fall over the steepest window the arena accepts (at most 12 months apart, ending at most 10 months before the data's latest month), not only one ending at the series' latest month; one per series and supplier (`tactical+all_windows`) | api.md's rule for index arguments; P02's CU-NOTATION fell 2.2 % (2026-01 → 2026-03) and PPI-C241 4.0 % (2024-11 → 2025-11), none ends at the latest month. `sim bench tactical tactical+all_windows --reps 3`: 0.724 → 0.729 (P02 0.65 → 0.69, P05 0.82 → 0.86, P11 0.67 → 0.63) | mixed, dropped: practice P-34 to P-41: P07 0.740 → 0.753, P08 0.550 → 0.528, P02 0.733 = | P08 loses more than the case rule allows (−0.022); P02's older falls did not move the supplier |
| Take the supplier's alternative sheet when it saves 0.1 % of the room (`c_open` − the floor estimate, at least EUR 10) instead of 0.2 % of C, and only when the completed sheet we send still costs less than its primary one (`tactical+cheap_alt`) | P08: the 5 % deadband alternative in its final offer saved EUR 1,647-1,681 (0.16 % of C, 0.0094 of the score) and was passed over in 4 of 4 sessions; on our recorded practice sessions the new bar takes those four and P01's 0.12 % alternative, the old one did not (one-off replay script). `sim bench tactical tactical+cheap_alt --reps 3`: 0.724 → 0.729, only P05 differs (0.82 → 0.86; P05 alone moved as much between two runs of `tactical`) | worked, now default: practice P-34 to P-41: P08 0.550 → 0.560 (C 1,039,278 → 1,037,632, its 5 % deadband sheet), P07 and P02 unchanged | the arena's C of the alternative is lower; resending it costs one round, the supplier agreed |
| P08: ask for the calculation with the date of the call in which its owner offered to show it, not for "a cost breakdown" (`tactical+owner_offer`) | call note `doc:20260421-70710-M2` (trait `open_book`); the plain question was answered "company policy prevents us from sharing a detailed cost breakdown" or "more detail we do not share" in our 59 P08 sessions. `sim bench tactical tactical+owner_offer --cases case:P08`: 0.54 both (the simulator does not read wording) | unknown |
