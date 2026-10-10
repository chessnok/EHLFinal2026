# Report: the baseline buyer algorithm (v1)

Date: 10 October 2026 · Package: `agent/` (`negotiator`) · Strategy: `BaselineStrategy`
(`agent/src/negotiator/strategy/baseline.py`)

> This report describes **baseline v1**. It has since been replaced by baseline v2 (equal-C menus, reciprocal
> concessions) and the default tactical strategy; see [`strategies.md`](strategies.md) for the current comparison.

## 1. Summary

The strategy is a deterministic baseline without a language model. Code computes every number:
- **Costs:** every offer is costed with the published cost function C from the arena's starter kit
  (`arena_kit.cost.total_cost`).
- **Arguments:** taken from the data package, with IDs the arena can check.

It is a reference to beat and a test of the whole infrastructure (client, runner, telemetry, reports), not the final
solution.

| Where | Cases | Deals | Mean score |
|---|---|---|---|
| Arena sandbox (real supplier bots) | D01, D02 | 2 of 2 | 0.346 |

The e2e check on the local simulator passed (3 of 3 cases closed with a deal); its score is not used as a metric.

No practice quota (200 sessions per day) was spent on development.

## 2. How the algorithm works

### 2.1. Preparation (once per case, per supplier)

**Target price.** Take the lower of the supplier's opening price and our current price, and subtract an anchor that
depends on the case's category goal:

| Category goal | Anchor |
|---|---|
| `leverage` | 10 % |
| `routine` | 7 % |
| `stabilise` | 4 % |
| `quality_first` | 4 % |
| `secure_supply` | 3 % |

**Floor.** The target never goes below the part's should-cost (`should_cost.csv`). In `stabilise` and
`secure_supply` cases the floor is `full_cost / (1 − sustainable_margin)`. In those cases C charges a deal that leaves
the supplier below a sustainable margin, so our estimate of its cost is passed into C.

**Arguments.** Collected from the data and ranked by strength. Each argument is one sentence with the figure next to
the IDs it rests on, so the arena can check it:

| Argument | Source | When it is used |
|---|---|---|
| Short notice | letter `doc:` + contract `ctr:` | the price letter gave fewer days than the framework contract requires |
| Index moves | `idx:` pairs over 12 months, weights from `cost_drivers` | the part's cost indices rose less than the asked increase, or fell |
| Scorecard | `sc:` | on-time delivery below 95 % or quality worse than 500 ppm |
| Should-cost | `cost:` | the offered price is more than 12 % above our cost estimate |
| Alternative quote | `quote:` | our fallback is cheaper than the opening price |
| Rival offer | `offer:` | RFQ only: another bidder's standing offer is cheaper |

### 2.2. Each round, per thread

**Price.** Our price moves from the target towards the supplier's current price by a growing share of the gap:

| Round | 1 | 2 | 3 | 4 | 5 | 6 | 7+ |
|---|---|---|---|---|---|---|---|
| Share of the gap | 0 % | 30 % | 50 % | 65 % | 78 % | 88 % | 95 % |

The price never drops below our previous offer and never rises above the supplier's price.

**Up to three term sheets per round.** A sheet is dropped if it costs us more than the supplier's standing offer or
breaks a must-have of the case.

| Sheet | Content |
|---|---|
| A – C-optimal | our price; every other negotiable field (payment days, contract length, effective date, index clause, ppm, chargeback and so on) set to the value that minimises C (coordinate search, two passes) |
| B – price only | our price + 1 % on the supplier's own terms |
| C – "cash sooner" | shorter payment at the price where C equals sheet A's: worth something to a cash-short supplier, costs us nothing |

**E-mail.** Templated text:
- In the first round: up to three arguments and a request for a cost breakdown.
- In later rounds: at most one new argument.
- Each ID is cited once per case; otherwise the arena marks it `duplicate`.
- The exception is a rival's offer, which can be shown once to each other bidder.

**When a thread is held** (we stop pushing):

- the supplier answered `agreed` or `final_offer`;
- the supplier's price has not changed in its last three replies;
- our next price is within 0.5 % of its price;
- one round is left;
- less than 120 seconds remain before the wave deadline.

A thread is over for us when the supplier answers `walked_away` or `no_bid`.

### 2.3. Closing the case

Once every thread is held or closed, the algorithm accepts the cheapest standing term sheet (by C) that keeps the
must-haves and beats our alternative. If there is none, it walks away.

### 2.4. Runner mechanics (around the strategy)

- **One worker per thread:** each supplier has its own 60 seconds for our answer.
- **Keepalive:** while other threads still negotiate, a held thread gets a clarifying question without a term sheet
  after 42 seconds. Its timer does not run out and its offer stays valid.
- **Final:** in the Live Final a case closes 90 seconds before the wave's cap.
- **Retries:** retries are safe (`X-Move-Id`).
- **Live feed:** reading the leaderboard and the live feed is blocked in final mode, because the rules forbid it for
  the agent.

## 3. Results

### 3.1. E2e check on the local simulator `arena-sim`

The simulator is an e2e test of the mechanics, not a metric: its scripted supplier concedes a fixed 2 % per round.
Result:
- all three cases (S01, S02, S03) closed with a deal;
- all 22 arguments `verified`;
- no duplicates and no `contradicted`.

### 3.2. Arena sandbox (real supplier bots)

| Case | Type | Score | C_open | C_deal | C_best | Rounds | Time |
|---|---|---|---|---|---|---|---|
| D01 | price increase (`stabilise`) | 0.268 | 448,811 | 438,059 | 408,624 | 5 | 91 s |
| D02 | RFQ, 2 suppliers (`leverage`) | 0.425 | 214,296 | 189,822 | 156,739 | 9 | 187 s |

Saved against the best opening offer: €35,226 over the two cases.

**D01.** The supplier's price went 52.90 → 52.00 → 51.40 → 50.90 → 50.60 → 50.23, ours 46.66 → 48.26 → 49.03 →
49.42 → 49.73. We converged on the supplier's price and it answered `agreed` at 50.23, while the best reachable price
was about 47.4.

**D02.** Two suppliers negotiated in parallel. While DEMO-C1 was still moving, DEMO-J1 was kept alive with a keepalive
message. The deal was with DEMO-J1 at 15.67.

**Arena observations:**
- **Reply time:** a supplier bot replies within 13–60 seconds.
- **Serialisation:** the arena handles the calls of one session one after another. A two-supplier RFQ took about three
  minutes, against eight minutes per wave in the final.

## 4. Weaknesses

1. **The concession schedule is mechanical.** We raise the price on a schedule regardless of how the supplier reacts.
   On D01 this led directly to a deal above the reachable price.
2. **The supplier is not read.** Meeting and call notes, letters, news and quote remarks are not used, although they
   show what matters to a supplier (cash, volume, lead time, relationship).
3. **Replies are not analysed.** The text of the supplier's reply and a cost breakdown it sends do not affect our next
   steps.
4. **Trades are not sought deliberately.** The three term sheets reveal what the supplier values, but the algorithm
   draws no conclusions from its choice.
5. **Templated e-mails.** Tone and content do not adapt to the supplier, although per the brief the bots react to
   tone, questions and signals.

## 5. Next steps (at the time of this report)

1. **An LLM layer on top of the code.** The model reads the supplier's dossier (data, notes, letters) and its replies,
   and chooses arguments, trades and wording. Code still computes every figure and checks every term sheet through C.
2. **Reacting to signals.** Concede less while the supplier moves, hold position on a `final_offer`, look for trades
   (payment, volume, contract length) instead of haggling on price alone.
3. **Using the documents.** The XLSX cost breakdown, to estimate the supplier's floor.
4. **Time budget.** Timing for the eight-minute final wave: up to 10 cases in parallel, supplier replies of up to a
   minute.
5. **Learning loop.** Every change goes through sandbox and the `arena-sim` e2e tests first, then deliberate practice
   runs; compare with `negotiator stats` and the arena's replays.

## 6. How to reproduce

```sh
make sandbox                                    # the free cases D01, D02 against real bots
cd agent && uv run negotiator play case:P05     # one practice case (1 of 200 per day)
make report                                     # report of the latest run: agent/runs/<run_id>/report.md
make stats                                      # best and mean score per case across all runs
```

Each run's telemetry is in `agent/runs/<run_id>/`:

- `events.jsonl`: events;
- `http.jsonl`: HTTP requests;
- `metrics.json`: metrics;
- `sessions/`: full case transcripts with the suppliers' documents;
- `report.md`: the run's report.
