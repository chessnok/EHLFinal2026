# Practice runs: where the score is lost and how to fix it

As of 10 October 2026. Russian version: [`practice-analysis.ru.md`](practice-analysis.ru.md).

**Source.** All 42 practice sessions the team has played on the arena (`GET /v1/sessions?set=practice`). For each
session: the result with the cost breakdown, C_best, the deal's terms, and the arena's trace with the supplier's
reasons per move. These are read-only calls; no quota was spent on this analysis. The raw files are in
`agent/runs/prod-traces/` (git-ignored).

**Caveats:**
- The sessions were played by different strategies (mostly `tactical` and `llm`); the API does not record which.
- The bots answer non-deterministically, so a single session is anecdotal; patterns across sessions are what count.

## Scores per case

"Price at C_best" is the unit price that would give C_best on the deal's own terms. It shows how much room was left,
in price terms.

| Case | Type, goal | Sessions | Best | Mean | Best deal price | Price at C_best | Opening price(s) | Main loss |
|---|---|---:|---:|---:|---:|---:|---|---|
| P02 | price increase, stabilise | 7 | 0.268 | 0.200 | 373.85 (90 d) | 368.14 | 370.96 | price oscillation; unbacked volume claims |
| P18 | raw material, leverage | 6 | 0.319 | 0.137 | 5.60 (+ clause) | 4.58 | 6.10 | 2 no-deals: refused the index clause, supplier walked |
| P11 | quality, quality_first | 3 | 0.398 | 0.287 | 47.50 | 43.90 | 47.00 | ignored the cash signal; steps of €0.02 |
| P10 | capacity, secure_supply | 3 | 0.484 | 0.477 | 34.70 | 28.10 | 32.20 | accepted a final offer in round 1 |
| P05 | RFQ, 3 suppliers, leverage | 3 | 0.524 | 0.387 | 30.80 | 26.20 | 36.0 / 31.5 / 38.5 | closed near the cheapest opening |
| P08 | raw material, leverage | 7 | 0.538 | 0.178 | 5.48 (+ clause) | 5.05 | 6.05 | 3 deals on 12 months (50 % uncovered need); 1 no-deal |
| P07 | bundling, routine | 3 | 0.695 | 0.656 | 5.49 | 5.02 | 5.74 | about 9 % price room left (trace not analysed in detail) |
| P03 | renewal, stabilise | 3 | 0.762 | 0.762 | 438.21 | – | – | identical deal three times |
| P01 | price increase, stabilise | 4 | 0.858 | 0.780 | 135.60 | 134.40 | 138.55 | close to optimal |
| P04 | renewal, routine | 3 | 0.860 | 0.860 | 4.94 | – | – | close to optimal |

**Team practice total** (mean of the best score per case × 100): **57.1 points**. The six weakest cases (P02, P18,
P11, P10, P05, P08) hold almost all of the remaining points.

## What went wrong, case by case

### P18 and P08: raw material with an index clause (leverage)

**What happened:**
- **The supplier requires an index clause on long contracts.** P18 supplier: "As material costs remain volatile, we
  cannot accept a fixed price for extended contract durations"; "we must include an AS-14404 index clause".
- **We kept offering fixed prices.** Our C-optimal sheet always picks `index_clause: null`, because the expected index
  path (+6 %) makes a clause cost us money. After the supplier's final offer we sent fixed prices again, and it walked
  away (P18, two sessions).
- **Some deals closed on 12 months.** Three P08 deals were on the supplier's 12-month structure. With a 24-month
  horizon that leaves half the need uncovered: €542k of €1.13M C was `uncovered_need`, score 0.017.
- **The best P08 deal took the clause with a 5 % deadband (score 0.538).** With deadband 5 % against a 6 % path, the
  clause costs only 1 % of the material share, not 6 %. Clauses with deadband 0 cost about four times as much
  (P08 0.305 and 0.327).

**Fixes:**
1. **Offer the clause on our terms when the supplier asks for one.** Add a menu variant with the index clause at the
   largest deadband in `term_options`, priced iso-C. It meets the supplier's demand and costs us little.
2. **Never accept a contract shorter than the horizon while a longer one is negotiable.** Uncovered need at the
   fallback price dominates C. Add a guard: if `contract_months < horizon` and longer options exist, do not accept
   before offering the longer structure at least once.
3. **After a final offer, do not resend a sheet the supplier has already refused.** It reads as "no move" and ends
   the thread.

### P10: capacity squeeze (secure_supply, no alternative)

**What happened:**
- We opened at 29.29, close to the C_best price (28.10).
- The supplier answered `final_offer` at 34.70 in round 1. We accepted immediately: tactical holds on a final offer,
  and with no alternative it never probes.
- In the same reply the supplier offered other structures ("We can accommodate the 24-month contract …, provided the
  lead time remains at … days. Alternatively, …"). We left them unexplored.

**Fixes:**
1. **A round-1 final offer is a position, not a limit.** Probe it once with an iso-C menu built on the supplier's
   stated conditions (its lead time, its contract length) before accepting. Two rounds were played out of ten.
2. **Read the "Alternatively …" terms in the reply as a menu** and price each of them with C.

### P11: quality case (quality_first)

**What happened:**
- **The supplier said what it wants, again and again:** "We cannot give up margin right now. Faster payment would help
  us more than anything", "If you really want a lower price, we need to talk about much faster payment terms",
  "Without faster payment, our price stays at …".
- **Payment terms are fixed in this case**, so that lever was not available. We moved €0.02 per round
  (42.44 → 42.52) and accepted the final offer at 47.50, above the opening price of 47.00.
- **The `llm` text leaked a budget.** The supplier replied: "You mentioned your budget; please share the exact
  figures".
- **Free levers were wasted.** With a chargeback of €500 ≥ the €450 cost per defect, `ppm_commitment` does not change
  our C at all. A looser ppm is free for us and worth money to the supplier.

**Fixes:**
1. **Give away free levers.** When several values of a field give the same C (a tie), pick the one the supplier
   prefers: the loosest ppm when the chargeback covers our defect cost, a later effective date when it costs us
   nothing, and so on. Our optimiser now picks one of the tied values arbitrarily.
2. **Step size has a floor in money,** not only in percent. Steps of €0.02 on a €47 part read as no move. The
   tactical stall logic should not shrink our steps to crumbs when the supplier itself is still moving.
3. **Never mention a budget**, in prompts or templates. Add "budget" to the stripped words in the llm strategy.

### P02: copper price increase (stabilise)

**What happened:**
- **There was little room.** C_best is only about 2 % below C_open; our best deal captured 27 % of it.
- **Our prices oscillated.** One option went 372.44 → 370.96 → 372.44, and the supplier said "We note that your
  proposed prices have decreased compared to your previous offer, which prevents us from making further concessions."
  Different strategies or option orderings produce this. The monotone-structure rule (baseline v2) prevents it and
  should be in every strategy.
- **We made volume claims without data.** The supplier asked "Which volume can you commit to?" in every round and
  "Which figures is that based on?" three times.

**Fixes:**
1. **Monotone prices per structure in every strategy,** including tactical and llm.
2. **Answer the volume question with data.** Cite the forecast (`fc:<part>@<month>`, a checkable fact) when volume is
   not negotiable, instead of asserting a figure.

### P05: RFQ with three suppliers (leverage)

**What happened:**
- The best deal was 30.80 against a C_best price of about 26.2, which is roughly 15 % room left.
- Mean score 0.387 with large swings between sessions (0.267 to 0.524).
- **What moved suppliers:** the rival-offer argument ("we took it into account") and the approval step ("We need to
  clarify this internally" → "we can move further").

**Fixes:**
1. **Keep re-citing the cheapest rival offer.** Each round's offer is a new `offer:` ID and can be cited again to the
   other bidders.
2. **After "clarify internally", ask again**, as `rejections.md` already notes. The next step comes on the next
   message.
3. **In an RFQ, do not close while two suppliers are still moving.** Close when the leader stops.

### P07: bundling (routine)

**What happened:** the best deal was 5.49 against a C_best price of 5.02, so about 9 % price room was left. The trace
was not analysed in detail.

**Fix (likely):** the same as P11, a money floor on steps plus free levers.

## Cross-cutting issues, by expected gain

| # | Issue | Cases | Fix | Rough gain |
|---|---|---|---|---|
| 1 | Short contract accepted against a longer horizon (uncovered need) | P08, P18 | guard plus a longer-structure offer before any accept | up to +0.3 per affected session |
| 2 | Supplier's index-clause demand refused → walk-away | P18, P08 | clause at maximum deadband, iso-C, in the menu | no-deal 0 → about 0.3–0.5 |
| 3 | Final offer accepted in round 1 without a probe | P10 | one probe on the supplier's stated conditions | about +0.2 |
| 4 | Crumb steps and ignored cash signals | P11, P07 | money floor on steps; give away free (tied) levers | about +0.1–0.2 |
| 5 | Price oscillation per option | P02 | monotone structure prices in all strategies | small, avoids final offers |
| 6 | Unbacked claims and a leaked budget (llm text) | P02, P11, P05 | strip "budget"; cite forecasts for volume questions | trust |
| 7 | Variance between sessions | all | rerun winners several times before relying on a score | measurement |

## Next steps

Each fix above should first be implemented and checked on the sandbox and the `arena-sim` e2e tests. Then the
affected practice cases are replayed: P08, P18, P10, P11, P05, P02. Replaying them spends practice quota, so under the
hard rule in `AGENTS.md` this needs an explicit confirmation with the current balance. At the time of writing: 158 of
200 left, resetting 2026-10-11 12:47 UTC.
