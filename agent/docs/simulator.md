# The supplier simulator (`negotiator sim`)

As of 10 October 2026, fitted from 84 recorded arena sessions (54 sandbox, 30 practice).

A local arena between `arena-sim` (the kit's fixed script) and the real bots: the kit's API, the 12 cases we have
played, the arena's own `C_open` and `C_best` per case as the yardstick, and suppliers fitted from our replays. It
costs no practice session and no token; 4 strategies x 12 cases x 5 repeats take about 30 seconds.

```sh
cd agent
uv run negotiator sim calibrate                        # fit from runs/ -> data/sim/model.json (git-ignored)
uv run negotiator sim check                            # how well the fit predicts sessions it has not seen
uv run negotiator sim bench baseline tactical --reps 5 # strategies on the simulator, next to their arena scores
uv run negotiator sim bench tactical --strangers       # each supplier with the habits of another one
uv run negotiator sim serve --port 8100                # as a local arena for `negotiator --url ...`
```

Simulator runs go to `agent/runs-sim/`, apart from `runs/`: they are not benchmark records and never enter
`negotiator stats`.

## What is fitted, and from what

| Part | Source in the replays |
|---|---|
| Opening and standard terms | each supplier's quote e-mail and quote PDF |
| What a term is worth to it (payment days, lead time, effective date, contract length, index clause, ppm) | the alternatives it quotes in one e-mail ("alternatively, with 14 days net: EUR ...") - two prices for one position |
| Its floor | the price at which the best package it could accept costs exactly the `C_best` the arena published |
| How far it moves per e-mail | its recorded steps as a share of the gap to the floor, by what the buyer did: moved, stood still, a rival quote, another argument that convinced it, the second half of an approved step |
| When it calls an offer final | the reply number of its recorded final offers |

`C_open` computed by the simulator equals the arena's on all 12 cases, and the fitted floor reproduces `C_best` on 9
of them. On the other three (P01, P02, P04) the floor is a guess below the lowest offer seen; in every case no
simulated offer can be cheaper than `C_best`.

## How far to trust it

Measured, not assumed. `negotiator sim check` leaves one session out, fits on the rest, replays that session's buyer
e-mails and scores the offer standing when the buyer accepted.

| | Score points |
|---|---|
| Mean error per held-out session (84 sessions) | 0.078 |
| Mean bias | -0.007 |
| Worst cases | P01 0.29, P04 0.18, P18 0.12, P08 0.12 (three sessions each) |
| Played end to end, simulator mean against arena mean (8 strategy-case pairs, sandbox) | 0.037 |

Read it as: a change that moves the simulator's mean by less than about 0.08 is not a finding. The fit on the ten
practice cases rests on three sessions each, all played by one strategy (`llm`).

**Blind to wording.** The simulated supplier reads term sheets and cited IDs, not the e-mail. On the arena the text
decides too, with the same numbers on the table:

| Sandbox, arena | D01 | D02 | Simulator |
|---|---|---|---|
| baseline | 0.843 | 0.629 | 0.83 / 0.63 |
| budget ("a ceiling set by management") | 0.863 | 0.314 | 0.85 / 0.61 |
| shelby (tone) | 0.663 | 0.566 | 0.80 / 0.55 |

So: use it for what the numbers do (anchor, concession schedule, menus, which arguments, when to hold or accept),
never for tone, questions, unbacked claims or leaks. Those need the sandbox, which is free and, for a strategy
without an LLM, gives the same replies every time.

**Not fitted at all:** walking away (no recorded supplier did; the simulator walks after three pushes past a final
offer with probability 0.5), the price of a volume change (no recorded alternative varied it), suppliers of cases
we have not played, the relationship charge except on P01.

## The loop

1. Change a strategy; `sim bench old new --reps 5`. Worse by more than 0.08: drop it. Text-only change: skip the
   simulator, go to step 2.
2. Sandbox (free): both cases, the real bots.
3. Practice (quota): only what passed 1 and 2, then `sim calibrate` again - every practice run makes the fit better.
