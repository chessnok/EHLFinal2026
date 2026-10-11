# Argument audit: what the arena can check and what we cite

As of 11 October 2026. A reading of files, no arena session and no strategy change.

Sources: `negotiation-arena-kit/brief/api.md` ("What counts"), `negotiation-arena-kit/data/facts.json` (10,356 IDs),
and the sessions stored under `agent/runs/` on one machine: 102 practice sessions (P01-P18, 8 to 14 per case) and 98
sandbox sessions, 10 and 11 October, all strategies. The 293 replays behind [`bot-mechanics.md`](bot-mechanics.md) are
not on this machine; where a figure comes from that file it says so. The scripts were one-off and are not in the
repository. Strategy versions are mixed, so the counts are correlations.

## 1. What the arena checks

`api.md` lists six rows of checkable data; the trace (`interpreted.claims`) names the type it read from our e-mail.

| Arena type | We cite | Rule in `api.md` | Our kind in the code |
|---|---|---|---|
| `index_change` | 2 × `idx`, one series | at most 12 months apart, ending within the last 12 months of the data | `index`, `recent_drop` |
| `rival_quote` | the case's `quote` (its refs or our alternative), or another supplier's `offer` in this session | once per supplier in an RFQ | `rival_offer`, `quote` |
| `delivery_record` | `sc` rows | mean on-time delivery | `scorecard` |
| `quality_record` | `sc` rows, also `qn` | mean ppm | `quality`, `complaint` |
| `price_history` | 2-8 × `po`, same part | each part is its own argument | `orders` |
| `volume_change` | `fc` | the recorded change | `forecast` |
| `should_cost` | `cost` | the estimate | `should_cost` |
| `notice_period` | a letter `doc` + the contract `ctr` | the letter's notice against the contract's | `notice` |
| (not seen in a trace) | `news` | "that it is about this supplier" | none |

At most three arguments are read per message. Each ID counts once per case; measured on P08 (`runs.md` P-33), one
index series counts once per case whatever the IDs. Meeting notes, suppliers and parts are context, not checks.

The order of the sentences in an e-mail: `ledger.arguments_read` reproduces the arena's reading of 1031 of 1033
replayed messages by ordering the arguments by kind, not by their place in the text (comment in `ledger.py`). The
local sessions hold no two first e-mails with the same arguments in a different order, so an effect of the order on
the price is not measured.

## 2. Coverage per case

Facts of each type that exist for the case's parts and suppliers, and how many of them any of our local sessions
cited. "Case quote" is the `quote` in the case's refs with its price against the supplier's opening.

| Case | `po` | `fc` | `cost` | `sc` | `qn` | `news` (topic) | Case quote | Drivers never cited |
|---|---|---|---|---|---|---|---|---|
| P01 | 3 of 72 | 1 of 9 | 1 of 1 | 1 of 9 | 0 of 15 | none | 143.22, opening 138.55 | none |
| P02 | 3 of 72 | 1 of 9 | 0 of 1 (374.95, above the quote) | 1 of 9 | 0 of 2 | none | 421.06, opening 370.96 | CU-NOTATION, PPI-C241 |
| P03 | 3 of 72 | 1 of 9 | 1 of 1 | 1 of 9 | 0 of 2 | 0 of 1 (noise) | 466.99, opening 438.21 | CU-NOTATION, PPI-C2611 |
| P04 | 3 of 72 | 1 of 9 | none | 1 of 9 | 0 of 10 | 0 of 1 (refocus) | 5.04, opening 4.96 | none |
| P05 | none | none | 0 of 1 (36.87) | 3 of 27 | none | 0 of 3 (renamed, free capacity, full order book) | none | none |
| P07 | 0 of 216 | 4 of 36 | none | 1 of 9 | 0 of 71 | none | none | PPI-C2594, LCI-C |
| P08 | 3 of 72 | 1 of 9 | none | 1 of 9 | 0 of 23 | 0 of 1 (noise) | 6.06, opening 6.05 | none |
| P10 | 3 of 72 | 1 of 9 | 1 of 1 | 1 of 9 | 0 of 22 | 0 of 1 (allocation) | none | PPI-C2219 |
| P11 | 3 of 72 | 1 of 9 | none | 1 of 9 | 1 of 16 | 0 of 1 (restructuring) | 53.56, opening 47.00 | PPI-C241 |
| P18 | 3 of 72 | 1 of 9 | none | 1 of 9 | 0 of 8 | 0 of 1 (noise) | 6.31, opening 6.10 | none |

Sandbox D01 and D02 keep their facts in the case, not in `facts.json`; D02's refs hold `quote:D02-ALT` (19.90, both
openings are lower: 16.00 and 17.10) and `news:N-0412`, neither cited in 48 sessions.

What the table shows:

- **`news` is the one checkable type we have never cited** - in no case and no session.
- **The case quote is never cited** because it is above the supplier's opening in all seven cases that have one;
  the code cites it only when it is lower (`baseline.py`).
- **The drivers never cited rose over twelve months.** Their only falls are over old or short windows (PPI-C241
  −4.0 % from 2024-11 to 2025-11, CU-NOTATION −2.2 % from 2026-01 to 2026-03, PPI-C2611 −1.1 %, PPI-C2594 −1.4 %;
  PPI-C2219 has none). `tactical+all_windows` cites those and was measured (`runs.md` P-36).
- `qn` complaints were measured on P11 and reverted (`TRYED.md`); `po` and `sc` are cited by their latest rows.

## 3. What a verified argument did

The supplier's sentence about each kind of data, counted over the local sessions (practice and sandbox):

| Data | "took it into account" | "a fair point" | "does not change our calculation" | Other |
|---|---|---|---|---|
| rival quote | 115 | 1 | 23 | - |
| should-cost | 11 | 1 | 0 | - |
| notice period | 13 | 2 | 0 | - |
| index change | 26 | 3 | 4 | 5 "cannot give up margin" (P11), 1 "not our reality" (P08), 3 "adjusted our price" (P11) |
| volume change | 32 | 5 | 10 (P04, P10) | 2 "cannot give up margin" (P11), 6 "price reductions frozen" (P03) |
| quality record | 24 | 10 | 1 | - |
| delivery record | 5 | 0 | 23 | - |
| price history | 0 | 0 | 52 | 6 "price reductions frozen" (P03) |

Claim results in the same sessions: 442 verified, 13 duplicate (12 of them forecasts, 1 a quality record), none
contradicted or irrelevant.

Price history was answered "does not change our calculation" in every one of 52 practice sessions, in eight cases.
`bot-mechanics.md` section 4 has the first reply's drop +2.14 pp where price history was cited (6 of 8 suppliers),
from the 293 replays; the two readings are not reconciled here.

The supplier's first reply by the arguments of our first e-mail, P08 (local sessions):

| First e-mail read as | First ask under the quote | First reply | Sessions |
|---|---|---|---|
| AS-14404, PPI-C2431, price history | 26-27 % | 5.41, 5.58 | 3 |
| price history, forecast | 19 % | 5.46 | 1 |
| AS-14404, LCI-C | 27 % | 5.57 | 1 |
| AS-14404 | 27 % | 5.57 | 1 |
| AS-14404, PPI-C2431 | 27 % | 5.59 | 1 |
| delivery record, forecast | 34 % | 5.71 | 1 |
| delivery record | 29 % | 6.10 | 1 |

## 4. P08: what is left to cite

Facts of a checkable type for `part:370010` and `sup:70710` that no local session cited:

| Fact | Content | State |
|---|---|---|
| `news:20260822-24` | "at the trade fair" (topic: noise) | never cited |
| `quote:7200008` | the other supplier's 6.06 of 2026-09-09 | above the opening of 6.05 |
| `quote:7100065`, `quote:7100064`, `quote:7300008` | 5.41 (the other supplier, 2025-05-18), 5.34 and 5.45 (this supplier) | not in the case's refs; `api.md` checks the case's quote only |
| 23 × `qn`, 8 older `sc` rows | complaints, scorecards | a delivery record raised the first reply to 5.71 and 6.10 (section 3) |
| older windows of AS-14404 and PPI-C2431 | −8.1 % from 2024-11 to 2025-11 | one argument per series (`runs.md` P-33, P-36) |
| `ctr:4600070710#3.2` | the contract's own index clause | not read as an argument (`runs.md` P-24) |

Not checkable but in the data: the supplier's letter of 2026-07-06 (its alloy need is covered at fixed prices until
March 2027) and the call note of 2026-04-21 (its owner offered to walk us through the calculation). We asked for a
cost breakdown in nine local P08 sessions and received none; a breakdown file arrived on D02 only (43 of 86 asks).

The price the best team's score stands for, from `arena_kit.cost.total_cost` on the deal of
`20261011-010356-practice-tactical` (C_open 1,135,887, C_best 960,309; 90 days, 24 months):

| Score | C | Price, clause deadband 5 % | Price, no clause |
|---|---|---|---|
| 0.550 (ours, deadband 3 %) | 1,039,278 | 5.42 at deadband 3 % | - |
| 0.91 (best team, live page of 10 October) | 976,111 | 5.136 | 5.183 |
| 1.00 | 960,309 | 5.053 | 5.099 |

Our nine local P08 sessions: first replies 5.41 to 6.10, lowest supplier offer 5.38 (with a deadband of 0 %).
`bot-mechanics.md` (31 sessions): the final offer sat 0.04 to 0.18 under the first reply.

## 5. Where `news` exists

| Case | Supplier | News | Our argument without an ID today |
|---|---|---|---|
| P05 | sup:70250 | `news:20260309-03` advertises free machine capacity | `their_capacity`, after it writes "we have free capacity" (24 replies in 8 sessions) |
| P05 | sup:70240 | `news:20260710-18` fully booked into next year | - |
| P10 | sup:70410 | `news:20260822-23` allocates volumes | - |
| P11 | sup:70140 | `news:20260911-28` restructures with its banks | - |
| P04 | sup:70620 | `news:20260619-15` concentrates on larger accounts | - |
| D02 | - | `news:N-0412` (in the case's refs) | - |

Only P05's free-capacity item argues for a lower price; it is the one case in the hosted set where the type could
be cited to our advantage, and D02 is where it can be tried without quota.

## 6. Measured after the audit

`tactical+news` on sandbox D02 (`runs.md` S-37 to S-40, [record](benchmarks/2026-10-11-tactical-news-none.md)): the
arena reads the type `news`; cited to the bidder it is about it is `verified` and "taken into account" (D02 0.587 →
0.713, four of four runs), cited to the other bidder it is `irrelevant`. Not played on practice.
