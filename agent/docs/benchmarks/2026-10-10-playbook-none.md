# 2026-10-10 · playbook · no LLM

## Result and cost

| Run | Variant | D01 score | D01 C_deal (EUR) | D02 score | D02 C_deal (EUR) | Mean | Rounds D01 / D02 |
|---|---|---|---|---|---|---|---|
| `20261010-195610-sandbox-playbook` | `playbook` | 0.943 | 410,933 | 0.660 | 176,307 | **0.801** | 4 / 10 |
| `20261010-195651-sandbox-playbook-noprobe` | `playbook-noprobe` | 0.869 | 413,877 | 0.639 | 177,519 | 0.754 | 3 / 7 |

Sandbox: D01 (price increase, stabilise; C_open 448,811, C_best 408,624) and D02 (RFQ with two suppliers, leverage;
C_open 214,296, C_best 156,739). Reference: baseline 0.736, lowball 0.756 ([overview](README.md)).

Run cost: 0 practice sessions (sandbox), 0 LLM tokens, about 1 minute wall time per run. Development took about 20
further sandbox runs (the variants under Notes); the arena answers a repeated e-mail sequence from its cache.

## Strategy

`strategy/playbook.py`, strategy names `playbook` and `playbook-noprobe`, commit `14d3791` plus uncommitted changes to
`playbook.py` and `tests/test_sim.py`. The baseline plus the rules of
[`docs/knowledge/get-best-price-guide.md`](../knowledge/get-best-price-guide.md) that held up on the sandbox.

| Parameter | Value |
|---|---|
| `anchor_scale` | 1.5 (as `lowball`: leverage 27 %, stabilise 12 % below the lower of opening and current price) |
| `probe` | `always`: one closing offer after a final offer, on the supplier's terms, its last step lower (at least 0.5 %); `playbook-noprobe`: `off` |
| `cash_below` | on: the shorter-payment sheet pays sooner than the supplier's own term where an option allows |
| `question` | on: one open question in the first e-mail |
| `first_claims` | 2 arguments in the first e-mail, one a round after that |
| `min_sheet_share` | 0.75: sheets priced below 75 % of the supplier's price are dropped |
| ties in the term optimiser | go to the supplier's own terms (lead time 28 instead of 21 days when 35 is needed) |
| everything else | baseline v2: concession schedule, reciprocity 1.0, minimum step 0.4 %, equal-C menu |

## Notes

- **The closing offer is the gain.** After `final_offer` we accept the supplier's terms and offer to sign today at its
  last step lower. D01: the foundry went from 50.20 to 49.80 ("While our previous offer was final, we want to honor
  our long-standing relationship and your significant movement"). D02: the job shop agreed to 14.50 instead of 14.60.
  Five of five closing offers to the leading supplier lowered the price; the second bidder in D02 held twice.
- **The risk of the closing offer is not measured.** The brief says a supplier pushed past its final offer may walk
  away. None did in about ten closing offers today; in the earlier runs one of 16 pushed threads ended in a walk-away,
  after a timeout. The kit's scripted `arena-sim` supplier always walks away from an offer below its final one, so
  `playbook` closes no deal there (the test asserts it). A walk-away without an alternative scores 0 for the case; the
  gain per case was 0.02 to 0.07. `probe="safe"` sends the closing offer only when another outcome within 2 % exists.
- **Asking for twice the last step changed nothing:** the foundry gave the same 49.80 for an ask of 49.00 as for 49.60.
- **Single runs of small changes are noise.** Any change to the e-mail text changes the bots' replies: the same
  parameters scored 0.789 on D01 without the first-e-mail question and 0.869 with it. Differences below about 0.05 on
  one case say nothing; only the closing offer was reproduced in several configurations.

Variants tried and left out (one sandbox run each, the others unchanged; D01 unless noted):

| Variant | Score | Against | Reading |
|---|---|---|---|
| open question in every e-mail and a warmer opener | 0.803 | 0.863 | The foundry explains its costs instead of moving. |
| terms optimised at the supplier's price (price valid from April instead of December) | 0.789 | 0.803 | The supplier prices each term at about what it is worth to us; no gain. |
| one sheet instead of the menu (cash sheet only on a cash signal) | 0.777 | 0.803 | With a menu the supplier picks a shorter payment and gives more for it. |
| opening 10 % below the target, halving steps up to it | 0.773 | 0.773 | The foundry opened higher and ended at the same final offer. |
| need stated in words ("4,000 units a year over 2 years") | 0.797 | – | "Please provide the corresponding data": an unbacked claim, asked for three rounds. |
| case IDs cited without a figure (forecast, orders, should-cost) | 0.773 | – | Not counted as arguments (no claim result); the supplier asks for "the exact data". |
| cash sheet at 14 days for the job shop, D02 | 0.639 | 0.650 | It takes 14 days at the same price as 30. With a question in every e-mail it gave 14.40 (0.681) once. |

What the runs showed about the bots: the foundry's price path closes about half of the gap to its floor per round
(52.90 → 51.60 → 50.90 → 50.50, floor near 50.1) and it calls the offer final in round 3, whatever we send. Most
suppliers in our recorded sessions call a final offer in reply 3 or 4. The rounds before it are few; what moves the
price in them is a verified rival quote, and after it a closing offer.

## Practice: the 10 hosted cases

| Run | Variant | Mean | Deals | Rounds |
|---|---|---|---|---|
| `20261010-212101-practice-playbook` | `playbook` | **0.376** | 7 of 10 | 38 |

Run cost: 10 practice sessions, 0 LLM tokens, about 2 minutes wall time. Same parameters as above, on commit
`96f7545`. Reference of the same hour: `tactical` 0.695, 10 of 10 deals ([record](2026-10-10-tactical-none.md)).

| Case | Type, goal | Score | C_deal (EUR) | C_open | C_best | Deal | Score at the supplier's final offer, before the closing offer |
|---|---|---|---|---|---|---|---|
| P01 | price_increase, stabilise | 0.917 | 1,101,536 | 1,153,780 | 1,096,816 | yes | 0.941 |
| P02 | price_increase, stabilise | 0.385 | 2,264,634 | 2,282,867 | 2,235,514 | yes | 0.387 |
| P03 | renewal, stabilise | 0.762 | 3,989,244 | 4,246,314 | 3,909,043 | yes | 0.762 |
| P04 | renewal, routine | 0.000 | – | 198,846 | 196,529 | no | 0.860 |
| P05 | rfq, leverage | 0.295 | 281,351 | 305,545 | 223,424 | yes | 0.295 |
| P07 | bundling, routine | 0.121 | – | 391,027 | 299,241 | no | 0.676 |
| P08 | raw_material, leverage | 0.316 | 1,080,355 | 1,135,887 | 960,309 | yes | 0.261 |
| P10 | capacity, secure_supply | 0.568 | 1,589,712 | 1,932,492 | 1,328,927 | yes | 0.555 |
| P11 | quality, quality_first | 0.398 | 779,736 | 817,578 | 722,500 | yes | 0.398 |
| P18 | raw_material, leverage | 0.000 | – | 295,173 | 222,651 | no | 0.252 |
| **Mean** | | **0.376** | | | | 7 of 10 | 0.539 |

The last column is computed from the same run: the C of the cheapest standing offer when the first supplier called
its offer final (the `c` of that `reply` event), or the alternative where it is cheaper, scored with the case's
C_open and C_best. It was not played as a separate run.

- **The closing offer loses on practice.** Three suppliers walked away from it: P04 (4.94 final), P07 (5.52 final)
  and P18 (5.70 final). Three others gave a further step (P01 135.10 → 134.42, P08 5.61 → 5.56, P10 33.80 → 33.63);
  in P05 and P11 the final offer stood. The mean is 0.376 with the closing offer and 0.539 at the final offers.
- **This contradicts the sandbox,** where no supplier walked away in about ten closing offers. Three demo
  suppliers did not show the behaviour.
- **In P01 the lower price did not lower C:** the score at the final offer is 0.941, after the closing offer 0.917.
  It is a `stabilise` case, where a price that leaves the supplier below a sustainable margin costs C.
- **Without the closing offer playbook is still behind tactical** (0.539 against 0.695): P02, P05, P08, P11 and P18
  are all 0.15 or more lower. It has no supplier profile, no guards and no search over the term menu.
