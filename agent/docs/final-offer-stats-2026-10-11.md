# Final offers, late concessions and supplier movement in our practice records (11 October 2026)

Counts from the arena's trace of every recorded practice session; no forecast in this file.

## Source and method

- **Sessions:** all 90 files `agent/runs/*practice*/sessions/*.json` (15 runs, 104 supplier threads), read on
  11 October 2026. Strategy from `outcome.strategy`: `tactical` 40 and `tactical-slow25` 10 (family *tactical*),
  `playbook` 10, `llm` 30.
- **Moves:** the `trace` in each session file (the arena's own record: every supplier message with status, terms
  and alternative sheets; every buyer move, timeouts included). Our own thread copies were not used - they miss
  the supplier's answers to timeouts (case:P05).
- **Price** is the `unit_price` of the supplier's primary sheet. **C** is our cost of that sheet from the `reply`
  events in `events.jsonl` (`c`), where the event exists. **Hold reason** is `why` of the last `thread_hold`
  event for that supplier.
- **Round** is the arena's round of the supplier message (a timeout uses a round). Round limit: 10 in every case.
- **Alternative sheet:** a final offer can carry a second sheet. In case:P10 the final offer of round 1 is
  EUR 33.80 at 42 days lead time, with the alternative EUR 31.90 at 54 days. A next supplier message at the price
  of that alternative is counted as *restated its alternative*, not as a price move.
- Case goals: P01, P02, P03 `stabilise`; P10 `secure_supply`; P05, P08, P18 `leverage`; P04, P07 `routine`;
  P11 `quality_first`.
- Sessions per case and family: tactical P01 9, P02 9, P03 8, P04 3, P05 3, P07 3, P08 4, P10 4, P11 3, P18 4;
  playbook 1 per case; llm 3 per case.

## A. Final offers

### Final offers in rounds 1-2

| Strategy family | Final-offer replies | Threads | We accepted | Accepted its alternative | Asked for its alternative | Another offer | Question, no sheet | Timeout | None (closed elsewhere) |
|---|---|---|---|---|---|---|---|---|---|
| tactical | 7 | 7 | 3 | 0 | 4 | 0 | 0 | 0 | 0 |
| playbook | 4 | 4 | 0 | 0 | 0 | 4 | 0 | 0 | 0 |
| llm | 8 | 8 | 8 | 0 | 0 | 0 | 0 | 0 | 0 |

After a further buyer message (another offer, a question, or asking for the alternative):

| Strategy family | Further messages | Lower price, same terms | Lower price, other terms | Restated its alternative | Same price | Higher price | Walked away | No reply |
|---|---|---|---|---|---|---|---|---|
| tactical | 4 | 0 | 0 | 4 | 0 | 0 | 0 | 0 |
| playbook | 4 | 1 | 0 | 0 | 0 | 0 | 3 | 0 |
| llm | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

By case (family: replies → what followed a further message):

| Case | Type, goal | Family | Final-offer replies | Accepted | Further message | Lower (same terms) | Lower (other terms) | Restated alternative | Same | Higher | Walked |
|---|---|---|---|---|---|---|---|---|---|---|---|
| P04 | renewal, routine | playbook | 1 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 1 |
| P04 | renewal, routine | llm | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| P07 | bundling, routine | tactical | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| P07 | bundling, routine | playbook | 1 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 1 |
| P10 | capacity, secure_supply | tactical | 4 | 0 | 4 | 0 | 0 | 4 | 0 | 0 | 0 |
| P10 | capacity, secure_supply | playbook | 1 | 0 | 1 | 1 | 0 | 0 | 0 | 0 | 0 |
| P10 | capacity, secure_supply | llm | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| P18 | raw_material, leverage | tactical | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| P18 | raw_material, leverage | playbook | 1 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 1 |
| P18 | raw_material, leverage | llm | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

### Final offers in rounds 3+

| Strategy family | Final-offer replies | Threads | We accepted | Accepted its alternative | Asked for its alternative | Another offer | Question, no sheet | Timeout | None (closed elsewhere) |
|---|---|---|---|---|---|---|---|---|---|
| tactical | 20 | 20 | 16 | 0 | 2 | 0 | 0 | 0 | 2 |
| playbook | 6 | 4 | 2 | 0 | 0 | 4 | 0 | 0 | 0 |
| llm | 17 | 14 | 10 | 0 | 0 | 1 | 2 | 0 | 4 |

After a further buyer message (another offer, a question, or asking for the alternative):

| Strategy family | Further messages | Lower price, same terms | Lower price, other terms | Restated its alternative | Same price | Higher price | Walked away | No reply |
|---|---|---|---|---|---|---|---|---|
| tactical | 2 | 0 | 0 | 2 | 0 | 0 | 0 | 0 |
| playbook | 4 | 2 | 0 | 0 | 2 | 0 | 0 | 0 |
| llm | 3 | 1 | 0 | 0 | 2 | 0 | 0 | 0 |

By case (family: replies → what followed a further message):

| Case | Type, goal | Family | Final-offer replies | Accepted | Further message | Lower (same terms) | Lower (other terms) | Restated alternative | Same | Higher | Walked |
|---|---|---|---|---|---|---|---|---|---|---|---|
| P01 | price_increase, stabilise | tactical | 5 | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| P01 | price_increase, stabilise | playbook | 1 | 0 | 1 | 1 | 0 | 0 | 0 | 0 | 0 |
| P01 | price_increase, stabilise | llm | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| P02 | price_increase, stabilise | tactical | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| P04 | renewal, routine | tactical | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| P04 | renewal, routine | llm | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| P05 | rfq, leverage | tactical | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| P05 | rfq, leverage | playbook | 2 | 1 | 1 | 0 | 0 | 0 | 1 | 0 | 0 |
| P05 | rfq, leverage | llm | 9 | 2 | 3 | 1 | 0 | 0 | 2 | 0 | 0 |
| P07 | bundling, routine | tactical | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| P07 | bundling, routine | llm | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| P08 | raw_material, leverage | tactical | 4 | 4 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| P08 | raw_material, leverage | playbook | 1 | 0 | 1 | 1 | 0 | 0 | 0 | 0 | 0 |
| P08 | raw_material, leverage | llm | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| P11 | quality, quality_first | tactical | 2 | 1 | 1 | 0 | 0 | 1 | 0 | 0 | 0 |
| P11 | quality, quality_first | playbook | 2 | 1 | 1 | 0 | 0 | 0 | 1 | 0 | 0 |
| P11 | quality, quality_first | llm | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| P18 | raw_material, leverage | tactical | 1 | 0 | 1 | 0 | 0 | 1 | 0 | 0 | 0 |

### Every further message after a final offer

| Case | Strategy | Session | Round of the final | Its price | Alternatives on it | What we sent | What the supplier did | Prices | Case score |
|---|---|---|---|---|---|---|---|---|---|
| P01 | playbook | `134ff5ef09203be7` | 4 | 135.1 | 0 | another offer | lower price | 135.1 → 134.42 (-0.5 %), then `agreed` | 0.917 |
| P04 | playbook | `3bf0807b2eebd8b1` | 2 | 4.94 | 0 | another offer | walked away |  | 0.000 |
| P05 | llm | `ee3698e32f613305` | 3 | 35.0 | 0 | question, no sheet | same price | 35 → 35 (+0.0 %), then `final_offer` | 0.267 |
| P05 | llm | `ee3698e32f613305` | 3 | 35.0 | 0 | question, no sheet | same price | 35 → 35 (+0.0 %), then `final_offer` | 0.267 |
| P05 | llm | `146b65f28b6e91ed` | 4 | 34.0 | 1 | another offer | lower price | 34 → 33.5 (-1.5 %), then `final_offer` | 0.524 |
| P05 | playbook | `43856ed872c5c373` | 4 | 33.0 | 0 | another offer | same price | 33 → 33 (+0.0 %), then `final_offer` | 0.295 |
| P07 | playbook | `6bcba80947d374a4` | 2 | 5.52 | 1 | another offer | walked away |  | 0.121 |
| P08 | playbook | `8868848caac84892` | 3 | 5.61 | 1 | another offer | lower price | 5.61 → 5.56 (-0.9 %), then `agreed` | 0.316 |
| P10 | playbook | `c0d7c5ea297a4de4` | 1 | 33.8 | 1 | another offer | lower price | 33.8 → 33.63 (-0.5 %), then `agreed` | 0.568 |
| P10 | tactical | `6122063d95709e15` | 1 | 33.8 | 1 | asked for its alternative sheet | restated its alternative | 33.8 → 31.9 (-5.6 %), then `agreed` | 0.647 |
| P10 | tactical-slow25 | `1e88d4350a05e9e3` | 1 | 33.8 | 1 | asked for its alternative sheet | restated its alternative | 33.8 → 31.9 (-5.6 %), then `agreed` | 0.647 |
| P10 | tactical | `c975cb89eced1845` | 1 | 33.8 | 1 | asked for its alternative sheet | restated its alternative | 33.8 → 31.9 (-5.6 %), then `agreed` | 0.647 |
| P10 | tactical | `5dd7f9f888de86ad` | 1 | 33.8 | 1 | asked for its alternative sheet | restated its alternative | 33.8 → 31.9 (-5.6 %), then `agreed` | 0.647 |
| P11 | playbook | `e29528f223b3fcf8` | 4 | 47.5 | 0 | another offer | same price | 47.5 → 47.5 (+0.0 %), then `final_offer` | 0.398 |
| P11 | tactical | `a0ad5de90040eabf` | 4 | 46.0 | 1 | asked for its alternative sheet | restated its alternative | 46 → 45.5 (-1.1 %), then `agreed` | 0.672 |
| P18 | playbook | `e594a9b8afd6dc18` | 2 | 5.7 | 0 | another offer | walked away |  | 0.000 |
| P18 | tactical | `1190864f00363d5c` | 3 | 5.2 | 1 | asked for its alternative sheet | restated its alternative | 5.2 → 5.2 (+0.0 %), then `agreed` | 0.618 |

What the tables above contain, in counts:

- **Rounds 1-2:** 19 final-offer replies. We wrote again 8 times. The four `tactical` messages (all P10) asked for
  the supplier's own alternative sheet and got it (`agreed`). The four `playbook` messages were counter-offers:
  three suppliers walked away (P04, P07, P18 - `routine`, `routine`, `leverage`; case scores 0.000, 0.121, 0.000)
  and one lowered its price by 0.5 % (P10, `secure_supply`). `llm` accepted all eight.
- **Rounds 3+:** 43 final-offer replies. We wrote again 9 times: 3 price drops on the same terms (0.5 %, 1.5 %,
  0.9 %), 4 unchanged, 2 restated alternatives, no walk-away.
- No record exists of a message without a new term sheet after a final offer in rounds 1-2, and none of any
  message after an early final offer by `tactical` or `llm` other than the P10 alternative.

## B. Accepted while the supplier was still conceding

Deals in which the supplier's last message before our accept had a lower price than its message before, or a lower C for us at the same or a higher price.

| Case | Goal | Strategy | Session | Last two supplier prices | Drop | Our C, last two | C drop | Its status | Rounds used of limit | Hold reason | Score |
|---|---|---|---|---|---|---|---|---|---|---|---|
| P01 | stabilise | llm | `ce54582a24d803ba` | 137.0 → 135.6 | -1.02 % | 1,109,371 → 1,102,613 | -0.61 % | open | 2 of 10 | their offer meets our ask | 0.858 |
| P01 | stabilise | llm | `de8dc7a18d921a31` | 138.55 → 137.5 | -0.76 % | – | – | open | 1 of 10 | llm: hold | 0.829 |
| P01 | stabilise | playbook | `134ff5ef09203be7` | 135.1 → 134.42 | -0.50 % | 1,100,199 → 1,096,917 | -0.30 % | agreed | 5 of 10 | agreed | 0.917 |
| P01 | stabilise | tactical | `67fe83b13ef212b1` | 140.1 → 137.0 | -2.21 % | 1,113,131 → 1,101,922 | -1.01 % | open | 2 of 10 | their offer meets our ask | 0.856 |
| P01 | stabilise | tactical | `091c5e503507b0ec` | 135.8 → 133.0 | -2.06 % | 1,116,581 → 1,112,260 | -0.39 % | agreed | 4 of 10 | – | 0.728 |
| P01 | stabilise | tactical | `e391bae7cc16df04` | 133.6 → 131.3 | -1.72 % | 1,102,209 → 1,098,272 | -0.36 % | final_offer | 4 of 10 | last word: take it | 0.969 |
| P01 | stabilise | tactical | `0446cebd4fc19a70` | 133.6 → 131.3 | -1.72 % | 1,102,209 → 1,098,272 | -0.36 % | final_offer | 4 of 10 | last word: take it | 0.969 |
| P01 | stabilise | tactical | `d38f16014eab7d4f` | 133.6 → 131.8 | -1.35 % | 1,102,209 → 1,099,289 | -0.26 % | final_offer | 4 of 10 | last word: take it | 0.952 |
| P01 | stabilise | tactical | `184a8cc59cd3c6f8` | 134.5 → 133.4 | -0.82 % | 1,116,900 → 1,108,982 | -0.71 % | agreed | 3 of 10 | – | 0.785 |
| P01 | stabilise | tactical | `790be548dc591f10` | 133.0 → 132.5 | -0.38 % | 1,106,606 → 1,102,510 | -0.37 % | final_offer | 4 of 10 | last word: take it | 0.896 |
| P01 | stabilise | tactical | `b09b53b9d72e57b0` | 134.4 → 134.8 | +0.30 % | 1,119,732 → 1,111,961 | -0.69 % | agreed | 3 of 10 | – | 0.733 |
| P01 | stabilise | tactical-slow25 | `4c3a3f7c4fdf6c14` | 133.2 → 132.2 | -0.75 % | 1,102,649 → 1,094,499 | -0.74 % | final_offer | 4 of 10 | last word: take it | 0.914 |
| P02 | stabilise | playbook | `3275fa0d5a9d5df0` | 373.88 → 372.92 | -0.26 % | 2,270,369 → 2,264,542 | -0.26 % | open | 2 of 10 | close enough | 0.385 |
| P02 | stabilise | tactical | `aa2e0891149b82fb` | 373.88 → 356.17 | -4.74 % | 2,270,406 → 2,262,044 | -0.37 % | agreed | 2 of 10 | – | 0.576 |
| P02 | stabilise | tactical | `44549782e6fa9a2a` | 373.88 → 358.45 | -4.13 % | 2,270,369 → 2,194,241 | -3.35 % | agreed | 2 of 10 | – | 0.686 |
| P02 | stabilise | tactical | `2ee6ed2973fb4191` | 370.96 → 362.02 | -2.41 % | – | – | agreed | 1 of 10 | – | 0.733 |
| P02 | stabilise | tactical | `978f639248ebdfda` | 370.96 → 362.02 | -2.41 % | – | – | agreed | 1 of 10 | – | 0.733 |
| P02 | stabilise | tactical | `508aea2632ba9229` | 370.96 → 362.02 | -2.41 % | – | – | agreed | 1 of 10 | – | 0.733 |
| P02 | stabilise | tactical | `e11991f5a540845b` | 373.22 → 372.62 | -0.16 % | 2,266,621 → 2,263,354 | -0.14 % | open | 3 of 10 | their offer meets our ask | 0.421 |
| P02 | stabilise | tactical | `9d7ebcf9854a9734` | 373.22 → 372.62 | -0.16 % | 2,266,621 → 2,263,354 | -0.14 % | open | 3 of 10 | their offer meets our ask | 0.421 |
| P02 | stabilise | tactical-slow25 | `e5471e792b2e64a9` | 350.32 → 345.39 | -1.41 % | 2,144,501 → 2,135,441 | -0.42 % | final_offer | 4 of 10 | last word: take it | 0.000 |
| P03 | stabilise | tactical | `248fecdc5631bd81` | 436.66 → 430.01 | -1.52 % | 4,070,085 → 3,967,151 | -2.53 % | agreed | 2 of 10 | – | 0.828 |
| P03 | stabilise | tactical | `ae3c9e50f1e6ba89` | 438.21 → 432.94 | -1.20 % | – | – | open | 1 of 10 | no valid term sheet below their offer | 0.903 |
| P05 | leverage | tactical | `492f97766973186c` | 30.5 → 28.79 | -5.61 % | 259,037 → 244,577 | -5.58 % | agreed | 2 of 10 | – | 0.742 |
| P05 | leverage | tactical-slow25 | `91dbf752ed31c16a` | 29.5 → 29.38 | -0.41 % | 250,016 → 249,002 | -0.41 % | agreed | 3 of 10 | – | 0.689 |
| P07 | routine | llm | `488cf69a0154e619` | 5.51 → 5.49 | -0.36 % | 328,425 → 327,233 | -0.36 % | agreed | 3 of 10 | agreed | 0.695 |
| P07 | routine | llm | `7ed02a15aee21aed` | 5.58 → 5.56 | -0.36 % | 332,597 → 331,405 | -0.36 % | final_offer | 4 of 10 | final_offer | 0.650 |
| P07 | routine | tactical | `1d54a4bd137025ad` | 5.69 → 5.54 | -2.64 % | 339,153 → 330,213 | -2.64 % | final_offer | 2 of 10 | last word: take it | 0.663 |
| P07 | routine | tactical | `12616d36794684a8` | 5.48 → 5.45 | -0.55 % | 326,637 → 324,849 | -0.55 % | final_offer | 4 of 10 | last word: take it | 0.721 |
| P07 | routine | tactical-slow25 | `c982469f8cee75ef` | 5.69 → 5.66 | -0.53 % | 339,153 → 337,365 | -0.53 % | final_offer | 2 of 10 | last word: take it | 0.585 |
| P08 | leverage | playbook | `8868848caac84892` | 5.61 → 5.56 | -0.89 % | 1,090,070 → 1,080,355 | -0.89 % | agreed | 4 of 10 | agreed | 0.316 |
| P08 | leverage | tactical | `050ad7682c15cd74` | 5.52 → 5.42 | -1.81 % | 1,049,034 → 1,039,278 | -0.93 % | final_offer | 3 of 10 | last word: take it | 0.550 |
| P08 | leverage | tactical | `1279dddfbefa767c` | 5.52 → 5.43 | -1.63 % | 1,049,034 → 1,041,196 | -0.75 % | final_offer | 3 of 10 | last word: take it | 0.539 |
| P08 | leverage | tactical | `705d7cdddfe255a3` | 5.48 → 5.45 | -0.55 % | 1,041,432 → 1,035,731 | -0.55 % | final_offer | 4 of 10 | last word: take it | 0.570 |
| P10 | secure_supply | playbook | `c0d7c5ea297a4de4` | 33.8 → 33.63 | -0.50 % | 1,597,721 → 1,589,712 | -0.50 % | agreed | 2 of 10 | agreed | 0.568 |
| P10 | secure_supply | tactical | `6122063d95709e15` | 33.8 → 31.9 | -5.62 % | 1,597,721 → 1,541,808 | -3.50 % | agreed | 2 of 10 | – | 0.647 |
| P10 | secure_supply | tactical | `c975cb89eced1845` | 33.8 → 31.9 | -5.62 % | 1,597,721 → 1,541,808 | -3.50 % | agreed | 2 of 10 | – | 0.647 |
| P10 | secure_supply | tactical | `5dd7f9f888de86ad` | 33.8 → 31.9 | -5.62 % | 1,597,721 → 1,541,808 | -3.50 % | agreed | 2 of 10 | – | 0.647 |
| P10 | secure_supply | tactical-slow25 | `1e88d4350a05e9e3` | 33.8 → 31.9 | -5.62 % | 1,597,721 → 1,541,808 | -3.50 % | agreed | 2 of 10 | – | 0.647 |
| P11 | quality_first | llm | `83289ddb2e3763e6` | 49.0 → 48.5 | -1.02 % | 803,586 → 795,636 | -0.99 % | open | 2 of 10 | llm: hold | 0.231 |
| P11 | quality_first | tactical | `a0ad5de90040eabf` | 46.0 → 45.5 | -1.09 % | 758,032 → 753,660 | -0.58 % | agreed | 5 of 10 | – | 0.672 |
| P18 | leverage | tactical | `d1121ef6821dc6a4` | 5.5 → 5.4 | -1.82 % | 261,308 → 259,970 | -0.51 % | agreed | 3 of 10 | – | 0.485 |
| P18 | leverage | tactical | `8576fd4b5b32d5e6` | 5.6 → 5.5 | -1.79 % | 266,059 → 264,784 | -0.48 % | agreed | 3 of 10 | – | 0.419 |
| P18 | leverage | tactical | `1190864f00363d5c` | 5.2 → 5.2 | +0.00 % | 252,560 → 250,342 | -0.88 % | agreed | 4 of 10 | – | 0.618 |
| P18 | leverage | tactical-slow25 | `527b981af508570f` | 5.4 → 5.5 | +1.85 % | 262,316 → 261,308 | -0.38 % | final_offer | 2 of 10 | last word: take it | 0.467 |

| Strategy family | Deals | Accepted right after a price or C drop | of these: drop ≥ 0.5 % in price | of these: status `open` | `agreed` | `final_offer` |
|---|---|---|---|---|---|---|
| tactical | 50 | 36 | 29 | 4 | 19 | 13 |
| playbook | 7 | 4 | 3 | 1 | 3 | 0 |
| llm | 30 | 5 | 3 | 3 | 1 | 1 |

Notes on the list:

- In six rows the lower price is the supplier's alternative sheet, not a concession: P10 `6122063d95709e15`,
  `c975cb89eced1845`, `5dd7f9f888de86ad`, `1e88d4350a05e9e3` (33.80 → 31.90), P11 `a0ad5de90040eabf` and P18
  `1190864f00363d5c` (see section A).
- A dash under *Hold reason* is an accept decided without a hold (the strategy accepted in the same turn).
- P02 `e5471e792b2e64a9` scored 0.000 at EUR 345.39: the relationship charge (`agent/docs/runs.md`, P-15).

### What the supplier did next when the thread went on

Each row is one supplier reply k that had a previous message to compare with and was followed by a further e-mail
of ours (not by a timeout); the columns describe the supplier's reply k+1. 188 such replies.

**all strategies**

| Supplier's move in reply k | Cases followed by a further e-mail of ours | Next move: mean price change | Next move: median | Next move lowered the price | Next move: no change | Next move: rise | Next reply `final_offer` | Next reply walked away |
|---|---|---|---|---|---|---|---|---|
| drop ≥ 0.5 % | 95 | -0.77 % | -0.55 % | 57 (60 %) | 32 | 5 | 26 | 1 |
| drop < 0.5 % | 19 | -0.18 % | +0.00 % | 8 (42 %) | 10 | 1 | 7 | 0 |
| no change | 42 | -0.46 % | +0.00 % | 11 (26 %) | 29 | 0 | 17 | 2 |
| rise | 32 | -1.86 % | -1.03 % | 25 (78 %) | 7 | 0 | 2 | 0 |

**tactical**

| Supplier's move in reply k | Cases followed by a further e-mail of ours | Next move: mean price change | Next move: median | Next move lowered the price | Next move: no change | Next move: rise | Next reply `final_offer` | Next reply walked away |
|---|---|---|---|---|---|---|---|---|
| drop ≥ 0.5 % | 63 | -0.90 % | -0.60 % | 41 (65 %) | 18 | 4 | 15 | 0 |
| drop < 0.5 % | 10 | -0.28 % | -0.04 % | 5 (50 %) | 4 | 1 | 2 | 0 |
| no change | 13 | -0.75 % | -1.06 % | 7 (54 %) | 6 | 0 | 4 | 0 |
| rise | 17 | -2.95 % | -2.86 % | 16 (94 %) | 1 | 0 | 2 | 0 |

**playbook**

| Supplier's move in reply k | Cases followed by a further e-mail of ours | Next move: mean price change | Next move: median | Next move lowered the price | Next move: no change | Next move: rise | Next reply `final_offer` | Next reply walked away |
|---|---|---|---|---|---|---|---|---|
| drop ≥ 0.5 % | 13 | -0.66 % | -0.84 % | 8 (62 %) | 4 | 0 | 6 | 1 |
| drop < 0.5 % | 1 | +0.00 % | +0.00 % | 0 (0 %) | 1 | 0 | 1 | 0 |
| no change | 8 | -0.08 % | +0.00 % | 1 (12 %) | 5 | 0 | 2 | 2 |
| rise | 4 | -0.82 % | -0.77 % | 4 (100 %) | 0 | 0 | 0 | 0 |

**llm**

| Supplier's move in reply k | Cases followed by a further e-mail of ours | Next move: mean price change | Next move: median | Next move lowered the price | Next move: no change | Next move: rise | Next reply `final_offer` | Next reply walked away |
|---|---|---|---|---|---|---|---|---|
| drop ≥ 0.5 % | 19 | -0.44 % | +0.00 % | 8 (42 %) | 10 | 1 | 5 | 0 |
| drop < 0.5 % | 8 | -0.08 % | +0.00 % | 3 (38 %) | 5 | 0 | 4 | 0 |
| no change | 21 | -0.39 % | +0.00 % | 3 (14 %) | 18 | 0 | 11 | 0 |
| rise | 11 | -0.55 % | +0.00 % | 5 (45 %) | 6 | 0 | 0 | 0 |

**all strategies, leverage and routine cases**

| Supplier's move in reply k | Cases followed by a further e-mail of ours | Next move: mean price change | Next move: median | Next move lowered the price | Next move: no change | Next move: rise | Next reply `final_offer` | Next reply walked away |
|---|---|---|---|---|---|---|---|---|
| drop ≥ 0.5 % | 51 | -0.99 % | -0.38 % | 29 (57 %) | 19 | 2 | 16 | 1 |
| drop < 0.5 % | 11 | +0.00 % | +0.00 % | 2 (18 %) | 8 | 1 | 5 | 0 |
| no change | 26 | -0.61 % | +0.00 % | 7 (27 %) | 17 | 0 | 15 | 2 |
| rise | 9 | -0.87 % | -0.55 % | 5 (56 %) | 4 | 0 | 2 | 0 |

**all strategies, stabilise and secure_supply cases**

| Supplier's move in reply k | Cases followed by a further e-mail of ours | Next move: mean price change | Next move: median | Next move lowered the price | Next move: no change | Next move: rise | Next reply `final_offer` | Next reply walked away |
|---|---|---|---|---|---|---|---|---|
| drop ≥ 0.5 % | 35 | -0.54 % | -0.75 % | 24 (69 %) | 8 | 3 | 7 | 0 |
| drop < 0.5 % | 8 | -0.43 % | -0.12 % | 6 (75 %) | 2 | 0 | 2 | 0 |
| no change | 7 | -0.07 % | +0.00 % | 1 (14 %) | 6 | 0 | 0 | 0 |
| rise | 18 | -2.53 % | -2.14 % | 16 (89 %) | 2 | 0 | 0 | 0 |

**all strategies, previous reply `open` only**

| Supplier's move in reply k | Cases followed by a further e-mail of ours | Next move: mean price change | Next move: median | Next move lowered the price | Next move: no change | Next move: rise | Next reply `final_offer` | Next reply walked away |
|---|---|---|---|---|---|---|---|---|
| drop ≥ 0.5 % | 90 | -0.80 % | -0.57 % | 56 (62 %) | 29 | 5 | 25 | 0 |
| drop < 0.5 % | 19 | -0.18 % | +0.00 % | 8 (42 %) | 10 | 1 | 7 | 0 |
| no change | 30 | -0.51 % | +0.00 % | 8 (27 %) | 22 | 0 | 12 | 0 |
| rise | 26 | -1.40 % | -1.02 % | 20 (77 %) | 6 | 0 | 1 | 0 |

### After an `agreed` or `final_offer` reply, when we wrote again

| Status of reply k | Our next e-mail | Cases | Next move lowered the price | Mean price change | No change | Rise | Next status `agreed` | `final_offer` | `open` | Walked away |
|---|---|---|---|---|---|---|---|---|---|---|
| open | with a term sheet | 158 | 90 | -0.76 % | 62 | 6 | 14 | 44 | 100 | 0 |
| open | a question, no sheet | 7 | 2 | -1.03 % | 5 | 0 | 0 | 1 | 6 | 0 |
| agreed | with a term sheet | 1 | 0 | +0.00 % | 1 | 0 | 1 | 0 | 0 | 0 |
| agreed | a question, no sheet | 5 | 0 | +0.00 % | 5 | 0 | 0 | 2 | 3 | 0 |
| final_offer | with a term sheet | 15 | 9 | -2.25 % | 3 | 0 | 9 | 3 | 0 | 3 |
| final_offer | a question, no sheet | 2 | 0 | +0.00 % | 2 | 0 | 0 | 2 | 0 | 0 |

| Status of reply k | Goal group | Our next e-mail carried a term sheet: cases | Lowered | Walked away |
|---|---|---|---|---|
| agreed | leverage, routine | 1 | 0 | 0 |
| agreed | stabilise, secure_supply | 0 | 0 | 0 |
| agreed | quality_first | 0 | 0 | 0 |
| final_offer | leverage, routine | 7 | 2 | 3 |
| final_offer | stabilise, secure_supply | 6 | 6 | 0 |
| final_offer | quality_first | 2 | 1 | 0 |

Of the 15 further e-mails with a term sheet after a `final_offer`: 9 lower prices (5 of them the supplier's own
alternative sheet - P10 four times, P11 once; 4 on unchanged terms: -0.5 %, -0.5 %, -0.9 %, -1.5 %), 3 unchanged,
3 walk-aways (the three `playbook` counter-offers after a final offer in round 2). After an `agreed` reply we
wrote again with a term sheet once (no change) and with a question 5 times (no price change; 2 of the 5 next
replies were `final_offer`).

## C. Supplier movement by reply number

**Mean price change of the supplier's n-th reply against its previous message, % (number of replies) - all**

| Case type | reply 1 | reply 2 | reply 3 | reply 4 | reply 5 | reply 6 | reply 7 | reply 8 |
|---|---|---|---|---|---|---|---|---|
| price_increase | -0.62 (26) | -1.18 (22) | -0.43 (17) | -0.85 (12) | -0.25 (2) | – | – | – |
| renewal | -0.62 (19) | -0.11 (14) | +0.00 (6) | +0.00 (1) | – | – | – | – |
| rfq | -4.52 (21) | -2.90 (21) | -0.27 (17) | -0.27 (11) | -0.49 (3) | +0.00 (1) | – | – |
| raw_material | -7.21 (16) | -0.27 (16) | -1.01 (11) | -0.48 (3) | – | – | – | – |
| bundling | -2.02 (7) | -1.09 (7) | -0.32 (4) | -0.45 (2) | – | – | – | – |
| capacity | +6.13 (8) | -4.60 (5) | – | – | – | – | – | – |
| quality | +2.28 (7) | -1.18 (7) | -0.71 (6) | +0.00 (6) | -0.27 (4) | – | – | – |
| all types | -1.80 (104) | -1.43 (92) | -0.47 (61) | -0.44 (35) | -0.34 (9) | +0.00 (1) | – | – |

**Mean price change of the supplier's n-th reply against its previous message, % (number of replies) - tactical**

| Case type | reply 1 | reply 2 | reply 3 | reply 4 | reply 5 | reply 6 | reply 7 | reply 8 |
|---|---|---|---|---|---|---|---|---|
| price_increase | -0.88 (18) | -1.81 (15) | -0.33 (12) | -1.17 (8) | – | – | – | – |
| renewal | -0.93 (11) | -0.15 (10) | +0.00 (5) | +0.00 (1) | – | – | – | – |
| rfq | -7.83 (9) | -4.22 (9) | +0.34 (7) | -0.98 (3) | – | – | – | – |
| raw_material | -9.38 (8) | -0.38 (8) | -1.46 (7) | -0.27 (2) | – | – | – | – |
| bundling | -1.45 (3) | -1.47 (3) | -0.72 (1) | -0.55 (1) | – | – | – | – |
| capacity | +4.97 (4) | -5.62 (4) | – | – | – | – | – | – |
| quality | +1.06 (3) | -1.74 (3) | -1.07 (3) | +0.00 (3) | -1.09 (1) | – | – | – |
| all types | -2.73 (56) | -1.96 (52) | -0.45 (35) | -0.75 (18) | -1.09 (1) | – | – | – |

**Mean price change of the supplier's n-th reply against its previous message, % (number of replies) - playbook**

| Case type | reply 1 | reply 2 | reply 3 | reply 4 | reply 5 | reply 6 | reply 7 | reply 8 |
|---|---|---|---|---|---|---|---|---|
| price_increase | -0.20 (2) | -0.38 (2) | -0.81 (1) | +0.00 (1) | -0.50 (1) | – | – | – |
| renewal | -0.20 (2) | +0.00 (1) | – | – | – | – | – | – |
| rfq | +0.46 (3) | -0.49 (3) | -0.50 (3) | +0.00 (2) | +0.00 (1) | – | – | – |
| raw_material | -6.09 (2) | -0.44 (2) | -0.88 (1) | -0.89 (1) | – | – | – | – |
| bundling | -2.44 (1) | -1.43 (1) | – | – | – | – | – | – |
| capacity | +4.97 (1) | -0.50 (1) | – | – | – | – | – | – |
| quality | +3.19 (1) | -1.03 (1) | -1.04 (1) | +0.00 (1) | +0.00 (1) | – | – | – |
| all types | -0.49 (12) | -0.55 (11) | -0.70 (6) | -0.18 (5) | -0.17 (3) | – | – | – |

**Mean price change of the supplier's n-th reply against its previous message, % (number of replies) - llm**

| Case type | reply 1 | reply 2 | reply 3 | reply 4 | reply 5 | reply 6 | reply 7 | reply 8 |
|---|---|---|---|---|---|---|---|---|
| price_increase | +0.01 (6) | +0.40 (5) | -0.62 (4) | -0.27 (3) | +0.00 (1) | – | – | – |
| renewal | -0.20 (6) | +0.00 (3) | +0.00 (1) | – | – | – | – | – |
| rfq | -2.86 (9) | -2.38 (9) | -0.79 (7) | +0.00 (6) | -0.74 (2) | +0.00 (1) | – | – |
| raw_material | -4.69 (6) | -0.06 (6) | +0.00 (3) | – | – | – | – | – |
| bundling | -2.44 (3) | -0.60 (3) | -0.18 (3) | -0.36 (1) | – | – | – | – |
| capacity | +8.07 (3) | – | – | – | – | – | – | – |
| quality | +3.19 (3) | -0.68 (3) | +0.00 (2) | +0.00 (2) | +0.00 (2) | – | – | – |
| all types | -0.79 (36) | -0.81 (29) | -0.43 (20) | -0.10 (12) | -0.29 (5) | +0.00 (1) | – | – |

**Share of threads the supplier itself had closed by its n-th reply (first `final_offer`, `agreed` or walk-away), cumulative, % of all threads; in brackets the threads that received an n-th reply**

| Strategy family | Threads | by reply 1 | by reply 2 | by reply 3 | by reply 4 | by reply 5 | by reply 6 | by reply 7 | by reply 8 | never (we closed first) |
|---|---|---|---|---|---|---|---|---|---|---|
| all | 104 | 17 (104) | 33 (92) | 54 (64) | 74 (35) | 76 (9) | 76 (1) | 76 (0) | 76 (0) | 25 |
| tactical | 56 | 12 (56) | 27 (52) | 50 (35) | 75 (18) | 75 (1) | 75 (0) | 75 (0) | 75 (0) | 14 |
| playbook | 12 | 33 (12) | 58 (11) | 67 (9) | 92 (5) | 92 (3) | 92 (0) | 92 (0) | 92 (0) | 1 |
| llm | 36 | 19 (36) | 33 (29) | 56 (20) | 67 (12) | 72 (5) | 72 (1) | 72 (0) | 72 (0) | 10 |

**Status of the n-th reply, all strategies (replies)**

| Reply | Replies | open | agreed | final_offer | walked_away |
|---|---|---|---|---|---|
| 1 | 104 | 86 | 10 | 8 | 0 |
| 2 | 92 | 68 | 13 | 11 | 0 |
| 3 | 64 | 37 | 9 | 15 | 3 |
| 4 | 35 | 9 | 4 | 22 | 0 |
| 5 | 9 | 1 | 3 | 5 | 0 |
| 6 | 1 | 0 | 0 | 1 | 0 |
| 7 | 0 | 0 | 0 | 0 | 0 |
| 8 | 0 | 0 | 0 | 0 | 0 |

Notes: the supplier's answers to our timeouts (14, all case:P05) are counted as replies here. A positive mean in
reply 1 (capacity, quality) means the supplier's first reply was priced above its opening quote in those
cases. "Never" in the cumulative table are threads we closed, or that the case's end closed, before the
supplier sent `final_offer`, `agreed` or walked away.
