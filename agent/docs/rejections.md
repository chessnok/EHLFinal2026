# What suppliers say when they refuse

As of 10 October 2026. Source: the arena's trace (`reasons` per supplier move) of 26 negotiations: four sandbox runs
(D01, D02) and two practice runs over the 10 hosted cases, strategies `tactical` and `llm` on `claude-code:haiku`.
649 supplier statements in total; figures and index names were masked before counting.

**Caveat:** the bots answer non-deterministically and each practice case was played twice, so the counts show what is
common, not exact frequencies.

## Rejections and deflections

| # | What they say | Count | Cases | What it means for us |
|---|---|---:|---|---|
| 1 | "Which volume can you commit to?" / "A binding higher volume would help us and can improve the price." | 57 | all but P03, P10 | The most common reply. Neither strategy answers it. |
| 2 | "\<index\> rose X % in twelve months and is Y % of our cost." / "Your figures confirm our case: that driver rose." | 49 | P01–P05, P08, P10, P18, D01 | They defend with their own cost drivers; an index we cite can back their side. |
| 3 | "Material accounts for about X % of our cost; more detail we do not share." / "Our calculation is our property; we do not share a breakdown." / "Our calculation stays internal." | 47 | most | Asking for a cost breakdown mostly fails. One sandbox supplier sent one. |
| 4 | "Our standard Zahlungsziel is N days net." / "Our general terms and conditions apply." | 54 | most | Push-back on our payment-days ask; unstated fields close on their standard terms. |
| 5 | "Faster payment is welcome; we can reflect it in the price." | 18 | D02, P05, P11 | An invitation: earlier payment for a lower price. |
| 6 | "We checked the \<delivery record / rival quote\> data you cited; it holds, but it does not change our calculation." | 16 | P02–P05, P07, P08, P10, P18, D02 | True but not convincing: the scorecard argument rarely moves price. |
| 7 | "Which figures is that based on? Please send us the data." | 9 | D01, D02, P02, P05, P07, P11, P18 | A claim in the e-mail text without a data ID. Costs trust. |
| 8 | "Without movement from your side we cannot move either." / "Your proposal remains unchanged; we must maintain our current offer." | 7 | D02, P02, P05 | No concession without a move from us; a keepalive question counts as no move. |
| 9 | "We need to clarify this internally - we will come back to you on price." then "We have clarified this internally and can move further on the price." | 11 | D02, P05 | An approval step. Asking again gets the next concession. |
| 10 | "We are happy to discuss this in a call; until then our offer stands." | 5 | D01, P01, P04, P07 | A stall. |
| 11 | "Our management has frozen all price reductions until December. We can talk about the terms instead - payment, volume or contract length." | 2 | P03 | Price is locked: trade the other terms. |
| 12 | "We cannot give up margin right now. Faster payment would help us more than anything." | 3 | P11 | Cash matters more to it than price. |

## What did move them

| What they say | Count | Cases |
|---|---:|---|
| "We checked the rival quote data you cited; it holds and we took it into account." | 8 | D02, P05 |
| "We checked the \<quality record / index change / notice period / should cost\> data you cited; it holds and we took it into account." | 13 | P01, P05, P10, P11 |
| "We did not know that - a fair point." | 4 | P01, P05 |
| "We can offer a Preisgleitklausel on \<indices\>." | 4 | P08, P18 |
| "With overtime we can deliver in N days, at a premium." / "We have free capacity for your parts." | 32 | D02, P05 |

## Open points

- Row 1 is the largest gap: suppliers ask for a volume commitment in almost every case, including cases where
  `volume_per_year` is not negotiable. Answer it where it is a field; say what the forecast covers where it is not.
- Rows 2 and 6: choose arguments by what the supplier's own drivers did, not by what is checkable.
- Row 7: the model's text still makes unbacked claims; the figure filter does not catch a claim without a number.
- P08 and P18 offer an index clause (Preisgleitklausel) and score lowest: the clause is barely used as a lever.

## How to reproduce

```sh
cd agent
uv run negotiator run --set practice --strategy llm --llm claude-code:haiku --parallel 8
uv run negotiator lessons latest      # the supplier's reasons per round, per case
```
