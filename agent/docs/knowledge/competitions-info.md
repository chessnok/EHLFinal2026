# Competition facts beyond the brief

As of 10 October 2026. Source: the arena's FAQ page (`https://arena.tacto.ai`, "Questions from the room"), pasted
into the session that evening, read against the brief (`negotiation-arena-kit/brief/brief.md`). Only what the brief
does not say, or says differently, is listed; the brief stays the reference for everything else.

## Scoring

- **C_open is the cheapest opening quote that keeps our must-haves.** The brief says "the best opening quote".
- **A deal worse than the opening scores 0**, as does a broken must-have. No deal scores the alternative, 0 without
  one.
- **Every case weighs the same.** The score ranks, not the euros saved; "€ saved" on the board is a side number.
- **Final:** wave score = the mean of the wave's case scores × 100; points = the sum of five waves, up to 500. A
  case still open at the 8-minute cap, **or never opened**, counts as no deal. Ties: more deals, then fewer rounds.

## Practice

- **Practice does not rank.** The best score per hosted case counts, and the practice board shows the mean over the
  10 hosted cases; the FAQ calls it "for learning".
- **Quota:** the FAQ and the brief say 200 sessions a day. `negotiator me` showed a limit of 650 for our key on
  10 October (reset 2026-10-11 12:47 UTC). Read the balance, not the FAQ.
- **Old replays:** `GET /v1/sessions?set=practice`, then `/replay/<session_id>`.
- **One run gives C_open and C_best of a case;** after that `arena_kit.total_cost` scores any term sheet offline.

## Running the final

- **Nothing is deployed and Tacto does not run our code.** We submit the repo and the commit hash on ehl.gg and run
  that commit ourselves; the agent polls from before 12:00 until the last wave has closed.
- **The FAQ advises a cloud VM over a laptop on the venue Wi-Fi** (sleep, dropped connections).
- `arena-sim serve --no-clock` runs the kit's scripted supplier without the 60-second clock.

## The FAQ's worked example: P01, score 0.76

The page replays one negotiation on P01 (C_open 1,153,780, C_best 1,096,816) that ends at EUR 134.50, 30 days, valid
from 1 January 2027. What the buyer did, in order:

1. Opened with the relationship ("you held your prices for a quarter in 2022"), one falling index with its ID and
   figure (`idx:PPI-D351@2026-08`, −3.7 %), an offer to pay faster, and two sheets (129.90 at 60 days, 128.90 at 30
   days), both from January. The supplier: "We did not know that - a fair point", and moved the date to January.
2. Asked "Can you meet us at 131.50?" with two sheets. The supplier: "Which figures is that based on? Please send us
   the data."
3. Answered with the should-cost estimate and its ID (`cost:310010`, EUR 132.64 before margin) and "we want you to
   earn a fair margin on top". The supplier verified it and proposed 134.50.

**The FAQ's own comparison:** the same index sent as an ultimatum ("unacceptable … or we go elsewhere") got 136.50
from November instead of January, about EUR 13,700 a year worse.

Our scores on P01 for reference: `tactical` 0.856 and `playbook` 0.917 (`../benchmarks/`).
