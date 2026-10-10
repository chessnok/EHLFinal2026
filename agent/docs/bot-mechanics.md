# What moves the arena's suppliers: our 293 practice sessions

As of 11 October 2026, about 01:30. Source: every ended practice session of our team key (293; P01-P18, all
strategies and commits since 10 October). They come from `negotiator session <sid>` (trace, claim checks, scores) and
`negotiator backoffice <sid>` (the supplier's internal notes after the case). Both are read-only calls that spend no
quota. The raw files sit in `agent/data/replays/` and `agent/data/backoffice/` (git-ignored). The analysis scripts
were one-off and are not in the repository.

These are correlations across our own sessions, so strategy versions are mixed. Where the back office states the
supplier's rule outright, that rule is direct evidence; everything else is a lead to test with one practice session
per case.

## 1. The supplier's rules, from its back office

| Note in the back office | Count | Cases |
|---|---|---|
| "The buyer shows a much lower rival quote. I give half the step now and check the rest." | 50 | P05 |
| "Checked: give the rest of the step." (the next round) | 47 | P05 |
| "The buyer wants more than my band allows (band ends at …, buyer at …). Approve a further step?" | 10 | P02, P03, P10 |
| "Approved: you may go further, within our rules." | 7 | P02, P03 |
| "My call: hold." | 135 | all but P10 |
| "My call: walk_away." | 7 | P01, P04, P05, P18 |

- **RFQ (P05).** A much lower rival quote buys a step in two halves: half now, the rest after the check, in the next
  reply, whatever we send.
  - Best P05 session (0.839, `2d73b8dc2cadc8c6`): we cited the rival's 31.5. Dralveck went 36 → 29.5, we asked 27.85
    and it agreed at 27.85 (the rest of the step).
  - A 0.742 session (`0a55ee9e09cf56d9`): same opening, Dralveck went 36 → 30.5. We then offered 28.79 on our own and
    it agreed at once, before it would have given the rest anyway.
- **Approval ladder (P02, P03, P10).** An ask beyond the manager's band goes to a committee, which approved a further
  step in 7 of the 10 cases we saw. We reached the band only 10 times in 293 sessions.

## 2. What the supplier says about our data

The most common sentences (numbers masked):

| Sentence | Count |
|---|---|
| "We checked the price history data you cited; it holds, but it does not change our calculation." | 184 |
| "We checked the volume change data you cited; it holds and we took it into account." | 104 |
| "Which figures is that based on? Please send us the data." | 90 |
| "We checked the index change data you cited; it holds and we took it into account." | 80 |
| "We checked the rival quote data you cited; it holds and we took it into account." | 79 |
| "We see your figures, but we cannot give up margin right now. Faster payment would help us more than anything." | 54 |
| "We checked the quality record data you cited; it holds and we took it into account." | 48 |
| "We checked the volume change data you cited; it holds, but it does not change our calculation." | 40 |

Claim results: 905 verified, 35 duplicate, 4 contradicted.

## 3. Our step against the supplier's next reply

Rounds 2 and later; "our step" is the change of our lowest ask against our previous ask to the same supplier.

| Our step | Replies | Supplier's mean drop | It held its price | Final offer | Agreed |
|---|---|---|---|---|---|
| no move | 65 | 0.60 % | 32 % | 25 % | 18 % |
| under 1 % | 245 | 0.59 % | 34 % | 31 % | 4 % |
| 1-3 % | 126 | 1.75 % | 12 % | 34 % | 13 % |
| over 3 % | 209 | 1.86 % | 12 % | 16 % | 34 % |

Steps under 1 % get a held price a third of the time; steps over 3 % get "agreed" a third of the time, which is the
supplier taking our concession.

## 4. The first message

The supplier's price drop in its first reply, compared within the same case and supplier (paired; the number of
suppliers where the difference is positive in brackets):

| First message | Difference in the first reply's drop |
|---|---|
| 2 or more cited arguments | +1.71 pp (8 of 12) |
| no cited argument | −2.52 pp (1 of 5) |
| first ask 15 % or more under the quote | +3.60 pp (5 of 9) |
| first ask under 8 % below the quote | −3.72 pp (4 of 9) |
| 2 or more questions | −2.39 pp (3 of 12) |
| a single term sheet | −2.24 pp (1 of 8) |
| a quality record cited | −2.18 pp (0 of 4) |
| a delivery record cited | −1.65 pp (4 of 12) |
| price history cited | +2.14 pp (6 of 8) |

Within each case, the session's score ranks with the first reply's drop at Spearman +0.63 (positive in 10 of 10
cases). It also ranks with the number of cited arguments (+0.55, 10 of 10), with "took it into account" replies (+0.47,
10 of 10) and with questions asked (−0.10; top third 0.6 questions per session, bottom third 2.2).

## 5. P08: the index clause

Offline with `arena_kit.total_cost` on the deal of `20261011-004458-practice-tactical` (P08, price 5.42, payment 90
days, 24 months):

| Index clause | C |
|---|---|
| none | 1,020,781 |
| deadband 5 % | 1,030,030 |
| deadband 3 % (the deal) | 1,039,278 |
| deadband 0 % | 1,053,152 |

The case expects AS-14404 to rise 6 % a year, so the clause we gave cost 18,497 against none: 0.105 of the score. The
supplier's final offer also held a 5 % deadband sheet at 5.46 (C 1,037,614), cheaper for us than the one we accepted.

## 6. Leads to test (one practice session per case each)

1. Steps of 1-3 % of C instead of 0.4 % crumbs, under 3 % so the supplier does not simply agree.
2. RFQ: cite a much lower rival offer to each bidder, then do not raise our ask in the next round - the rest of its
   step comes after its check. Cite a rival's new lower offer as soon as it appears (each offer has its own ID).
3. Raw material with a rising index: price the index clause in C and do not give it where it costs more than its
   price difference; offer payment or contract length instead.
4. First message: two or three verified arguments, no quality or delivery complaint outside quality cases, at most one
   question, a menu of options, a first ask at least 15 % under the quote outside strategic cases.
5. Approval-ladder cases: one ask beyond the supplier's band, so the committee is asked for a further step.
