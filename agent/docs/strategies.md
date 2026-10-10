# Agent strategies: logic and results

As of 10 October 2026, commit `8670be2`.

**Case score:** a number from 0 to 1, `(C_open − C_deal) / (C_open − C_best)`. It is the share of the possible saving
we got, measured from the best opening offer.

**Where we played:** every run was on the arena's sandbox, cases D01 and D02, against real supplier bots. No practice
quota (200 sessions per day) was spent.

**The simulator is e2e testing, not a metric:**
- Runs on the local `arena-sim` check only the mechanics: client, runner, message format, closing a case.
- The result there is pass/fail. Its scripted supplier concedes a fixed 2 % per round, so its score is not used to
  compare strategies.
- Every strategy passes e2e: 3 of 3 deals, arguments `verified`.

## Strategies

| Strategy | Code | Author | LLM | Logic |
|---|---|---|---|---|
| **baseline v1** (replaced) | `strategy/baseline.py` before `8670be2` | Mikhail Fadin | no | Target = opening price minus an anchor (leverage −10 %, routine −7 %, stabilise −4 %, secure_supply −3 %). Concessions on a fixed schedule: 0 → 30 → 50 → 65 → 78 → 88 → 95 % of the gap. Three term sheets: C-optimal for us, the supplier's price +1 %, shorter payment at equal C. Checkable arguments from the data. A thread is held on `agreed` or `final_offer`, on a stall or in the last round. Close: the cheapest standing offer, if it beats the alternative. |
| **baseline v2** (current) | `strategy/baseline.py` (`8670be2`) | Mikhail Fadin | no | Everything from v1 plus three fixes from the sandbox analysis. **(1) Equal-C menu:** every sheet in a message costs us the same; the sheet on the supplier's own structure is cheaper by exactly how much worse that structure is for us. **(2) Deeper anchors** (leverage −18 %, routine −12 %, stabilise −8 %) **and reciprocal concessions:** our step is at most the supplier's last step (at least 0.4 %), on a slower schedule. **(3) Consistency:** a structure's price never drops between rounds; a thread is held only when the supplier's offer is no worse than ours **in C**. |
| **llm** | `strategy/llm_strategy.py` | Mikhail Fadin | yes (currently `ollama:qwen3.6`) | Runs on top of baseline v2. Before the session opens, the model reads the supplier's dossier (letters, notes, news, history, credit index) and builds a profile. Each round it picks the stance, concession share, trade lever and arguments, and writes the e-mail text. Code builds the term sheets, inserts the checked arguments and strips figures and IDs from the model's text. If the model has not answered within 30 s, baseline makes the move. |
| **tactical** (default) | `strategy/tactical.py`, `profile.py`, `guards.py`, `lessons.py` | DavidtheRavinger | no | **Policy per category goal:** anchor, concession speed, reciprocity. About 12 supplier traits found in the data by regular expressions adjust it: cash-short, approval ladder, idle capacity, hedged and so on. **Concessions in C:** Boulware curve; no move from the supplier, no move from us; three stalls end the thread. **Menu** of three sheets at equal C, including a trade on a lever the supplier values. **Learns within the case:** drops arguments that came back `contradicted` or `irrelevant`, parses the cost breakdown. Probes a `final_offer` once, when the supplier walking away would cost us little. **Guards** before accept and before sending; `lessons.md` after the run. |
| **judged / jev** (planned) | – | – | yes | Tactical at three aggressiveness levels (soft, normal, hard); a judge model picks the move. Waiting for the model. |

## Results: arena sandbox (real bots)

| Strategy | D01: price increase, stabilise | D02: RFQ, 2 suppliers, leverage | Mean | Rounds D01 / D02 | Time D01 / D02 |
|---|---|---|---|---|---|
| baseline v1 | 0.268 | 0.425 | 0.346 | 5 / 9 | 91 / 187 s |
| llm (before fixes) | 0.100 | 0.455 | 0.277 | 4 / 7 | 130 / 167 s |
| llm (after fixes, before the equal-C menu) | 0.210 | 0.448 | 0.329 | 6 / 11 | 173 / 274 s |
| **baseline v2** | **0.843** | **0.629** | **0.736** | 3 / 8 | 76 / 162 s |
| llm on v2 | 0.663 | 0.545 | 0.604 | 3 / 8 | 90 / 175 s |
| tactical | 0.773 | 0.505 | 0.639 | 4 / 7 | – |

## Conclusions

1. **The mechanics drove the gain, not the LLM.** The equal-C menu and reciprocal concessions lifted baseline on the
   arena from 0.346 to 0.736. Tactical is built on the same ideas and is also far above the old baseline.
2. **The results are noisy.** One run per case, and the bots answer non-deterministically, so the gap between
   baseline v2 (0.736) and tactical (0.639) is not reliable. It needs repeated runs.
3. **Tactical probably trails on D02 because of its shallow anchor.** Its anchor is at most −15 % below the quote,
   while the supplier's floor there is about −24 % below the opening.
4. **The LLM layer does not pay off yet.** On v2 it is worse than plain baseline: the model concedes more cautiously
   than these bots require. The natural place for a model is choosing the aggressiveness (jev), not replacing the logic.
5. **The test base is narrow.** Everything was measured on two demo cases. The real practice cases with supplier data
   (P01–P19) are untested.

## What we learned about the supplier bots (trace and back office)

- **Term structure can matter more than price.** In D01 the best deal is a 24-month contract, 60 days' payment and a
  price valid from April, at about €50.13 per unit. With a 12-month contract the second year of the horizon is bought at
  the fallback price: roughly €30k more at almost the same unit price.
- **A supplier's floor can be far below its opening.** In D02 the best deal is about €13.0 per unit against openings of
  16.0 and 17.1 (−19 to −24 %). An early `agreed` to our offer means we overpaid.
- **The bots name their levers.** Examples: "Faster payment is welcome; we can reflect it in the price", "A binding
  higher volume would help".
- **Citing a cheaper rival works.** Example: "I give half the step now and check the rest".
- **Persistence breaks the approval ladder.** "wants more than my band allows" → the owner approves the next step.
- **Unbacked claims hurt.** Benchmarks, volumes or competitors without an ID trigger "Which figures is that based on?
  Please send us the data.", and trust drops.
- **Inconsistency is punished.** When the price of the same option dropped against the previous e-mail, the supplier
  answered with a `final_offer`.

## How to reproduce

```sh
cd agent
uv run negotiator run --set sandbox --strategy tactical    # or baseline / llm (--llm provider:model)
uv run negotiator stats                                    # best and mean score per case across all runs
uv run negotiator lessons latest                           # what the last run taught
```
