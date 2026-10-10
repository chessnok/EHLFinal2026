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
