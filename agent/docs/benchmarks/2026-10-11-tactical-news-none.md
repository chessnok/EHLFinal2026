# 2026-10-11 · tactical and the `news` flag · no LLM

## Result and cost

| Strategy | D01 | D02 | Mean |
|---|---|---|---|
| `tactical` (control) | 0.669 (`../runs.md` S-29) | 0.587 | 0.628 |
| `tactical+news` | 0.669 | **0.713** | **0.691** |

C_deal in EUR:

| Strategy | D01 | D02 | D02 deal |
|---|---|---|---|
| `tactical` | 421,931 (`tactical+news` run; no news item in D01) | 180,488 | DEMO-J1 at 14.50 |
| `tactical+news` | 421,931 | 173,240 | DEMO-J1 at 13.90 |

D02 repeated: the control twice (0.587 both), the flag four times with each bidder asked (0.713 all four). 8 of 8
deals. Run cost: 0 practice sessions (sandbox), 0 LLM tokens, about 15 minutes wall time for the seven runs.

What the arena answered (run `20261011-102124-sandbox-tactical+news`, round 2): the claim was read as type `news`,
`verified` for DEMO-J1 - "We checked the news data you cited; it holds and we took it into account", "the news about
Kurzarbeit is true, so we have machines ready for you right now" - and its price went 15.80 → 14.30 → 13.90 (control:
15.80 → 14.90 → 14.50). For DEMO-C1 the same ID was `irrelevant` ("concerns a different company") when it was asked
first and `duplicate` when asked second; DEMO-J1's check was `verified` in both orders.

Not measured on practice. Of the ten hosted practice cases only P05 has a qualifying item (`news:20260309-03`,
sup:70250).

## Strategy

`strategy/tactical.py`, the commit that adds this record (branch `docs/argument-audit`): `tactical` with the flag
`news`, off by default. From round 2 one press report is cited by ID beside the round's other arguments (up to the
three the arena reads): a `news` fact about this supplier whose topic or headline shows idle capacity (the package's
and a hidden case's own facts), or a `news` ID in the case's refs that no package holds (the sandbox), offered to each
bidder once. `guards.known_id` lets an ID named in the case's refs pass; `profile.NEWS_TOPICS` maps `free_capacity`.

## Runs

Set sandbox (`../runs.md` S-35 to S-38): `20261011-101750-sandbox-tactical`, `20261011-102604-sandbox-tactical`,
`20261011-101914-sandbox-tactical+news` (the item cited once per case, to DEMO-C1 only: 0.587),
`20261011-102124-sandbox-tactical+news`, `20261011-102435-sandbox-tactical+news`,
`20261011-102636-sandbox-tactical+news`, `20261011-103025-sandbox-tactical+news` (D01 and D02, the code as
committed).
