# What the arena's supplier reacts to, and where our simulated supplier differs

As of 11 October 2026. Two questions, answered from recorded sessions only:

1. Where is our simulated supplier (`sim --opponents llm`, `sim/llm_supplier.py`) softer or harder than the arena's?
2. What does that, and the arena's own replies, say about the prompt behind the arena's suppliers?

Sources: the recorded arena sessions under `agent/runs/` (one play of each wording on the sandbox cases D01 and D02,
`runs.md` and `benchmarks/`), `playbook` on practice (`runs.md` P-14), and the blind test of the simulated supplier
of 11 October (`../simulator.md`: `openai:gpt-6.1-sol`, `LLM_REASONING=medium`, two repeats, each strategy fitted
without its own sessions).

**Limits.** One play per wording on the arena, two demo cases, three suppliers (DEMO-F1 on D01; DEMO-J1 and DEMO-C1
on D02). Nothing here is measured on the practice suppliers except `playbook`.

## Our simulated supplier against the arena

Score of the buyer; a higher score than the arena's means our supplier gave more (softer), a lower one that it held.

| Strategy | D01: ours − arena | D02: ours − arena | What our supplier did |
|---|---|---|---|
| baseline | 0.000 | −0.021 | as the arena |
| polite | 0.000 | +0.003 | as the arena |
| questions | +0.015 | −0.014 | as the arena |
| lowball | −0.007 | 0.000 | as the arena |
| budget | 0.000 | +0.137 | softer: stopped just under the ceiling, but took less from it than the arena |
| urgent | −0.040 | −0.130 | harder: cut every concession "because of the deadline" |
| shelby | −0.120 | −0.322 | harder: called its offer final in the first reply |
| trade | +0.007 | −0.351 | harder: read "we do not pay more without something in return" as an ultimatum |

`playbook` on practice: softer. The arena's suppliers walked away from the closing offer on P04, P07 and P18 (0.000,
0.121, 0.000); ours closed P04 at 0.860 and P07 at 0.697, P18 at 0.162.

The hardness on tone comes from one rule in our prompt ("a threat, an ultimatum, a reproach or a hard tone: give up
clearly less and call your offer final a reply earlier"): the model applied it in full, where the arena's suppliers
moved a little.

## What the arena's suppliers did

The last price each supplier offered, per wording (recorded sessions; the baseline's strategy and numbers, only the
text differs - except `budget`, whose ceiling also caps our own asks, and `trade`, which holds our price when the
supplier does not move):

| Wording | D02, job shop DEMO-J1 | D01, foundry DEMO-F1 |
|---|---|---|
| baseline | 14.70 | 50.50 |
| polite | 14.80 | 50.50 |
| trade | 14.90 | 50.40 |
| shelby (hard tone, a threat to place the order elsewhere) | 15.00 | 51.40, final offer one reply earlier |
| urgent (deadline this week, no second source) | 15.50 | 51.20 |
| budget (a ceiling named) | 16.20 | 50.40 |

- **Leaks that shift the balance weigh most.** A named budget left DEMO-J1 at 16.20 instead of 14.70. Urgency with
  "you are the only qualified supplier" raised both suppliers' last price (15.50, 51.20), and DEMO-C1 raised its
  price from 16.90 to 17.40 during that thread and later walked away.
- **The reaction depends on the supplier.** The foundry did not use the budget ("We appreciate your transparency
  regarding your budget, but our pricing must sustainably reflect ...") and did react to the tone ("We value our
  12-year relationship and expect our discussions to remain professional"), closing a reply earlier. The job shop
  hardly reacted to the tone (15.00 against 14.70) and used the budget.
- **Politeness, questions and a firm sentence without a threat move little:** 0.00 to 0.20 in price.
- **Words are checked against the sheets.** DEMO-C1 on `trade`: "We note your statement regarding a concession;
  however, the options and prices provided are identical to your ..." - and it held its price. On a hint at an
  alternative it asked for the competitive data.
- **The frame of the talks is the same under every wording:** a step "in response to your movement", a pause
  ("We need to clarify this internally"), a final offer after a few replies. The text changes the size of the steps
  and the number of rounds, not the scheme.

## Conclusions

- **For the buyer agent:** never name a budget, a deadline or a missing alternative; mind the tone with a supplier
  whose record shows a long relationship; politeness and questions do not buy price.
- **For the simulated supplier:** it is right on neutral wordings and sees the leaks, too soft on a budget, too hard
  on tone and on firm sentences, and it does not walk away. It serves as an alarm for leaks, not as a judge of
  wording (`../simulator.md`, verdict of 11 October).

## Where the data is

Nothing below is committed (`runs/`, `data/` and `runs-sim/` are git-ignored).

| What | Where |
|---|---|
| Recorded arena sessions (the "cache": about 190 sessions) | `agent/runs/<run id>/sessions/<session>.json`, with a `.md` transcript next to each |
| Fitted simulator model | `agent/data/sim/model.json` (`negotiator sim calibrate`) |
| Simulator runs; the simulated supplier's answers with its `why` | `agent/runs-sim/<run id>/`; `*-sim-supplier-llm/events.jsonl` |
| The simulated supplier's prompt | `agent/src/negotiator/sim/llm_supplier.py`, `SYSTEM` |
