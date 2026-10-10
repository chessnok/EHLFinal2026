# Getting the best price: what the negotiation literature says

As of 10 October 2026. A reading of the human negotiation literature against the arena's rules and our own traces
([`../strategies.md`](../strategies.md), [`../rejections.md`](../rejections.md)).

**Working assumption:** the supplier bots behave like a human sales rep inside hard-coded limits. The brief says so
itself: the cost floor, the approval ladder, the ID check and "nothing without a move from you" are rules; inside
them the supplier "decides as that person would" and "reacts to tone and relationship as people do". So human
negotiation advice should carry over to everything except those four rules.

**Tested since:** section 7 lists what the sandbox confirmed and what it contradicted. Read it before acting on
the rules below; several did not survive.

**Caveat on sources:** the books and papers below are cited from memory, not looked up for this document. Titles,
authors and the main findings are well known; check a page or a figure before quoting one in the pitch.

## 1. The short version

Ten rules from the literature. Section 7 says which of them the sandbox confirmed.

1. **Negotiate the package, not the price.** The score is total cost `C`, and the supplier values terms differently
   from us. Give what is cheap for us and dear to them; take the reverse.
2. **Open first, open ambitiously, and justify the number.** The first number anchors the whole thread. An anchor
   without a reason reads as a lowball; one with a checked reason is a position.
3. **Know the other side's floor before you open.** Should-cost, past prices, rival quotes and the index path give an
   estimate of the supplier's walk-away point. The anchor belongs just beyond it, not a fixed percentage below the
   quote.
4. **Never concede without getting something, and make each concession smaller than the last.** Shrinking steps tell
   the supplier that we are near our limit; equal steps tell it to keep waiting.
5. **Send two or three packages of equal value to us.** The supplier's choice reveals what it values, and it feels
   it chose instead of being pushed.
6. **Answer the supplier's questions.** A question is a named lever. Our largest gap is the unanswered "which volume
   can you commit to?".
7. **Use one or two strong arguments, not six.** Weak arguments dilute strong ones and give the supplier something
   easy to rebut.
8. **Ask "how" and "what" questions when blocked.** "What would have to change for you to reach X?" makes the
   supplier design the solution and names the next lever.
9. **Never take a first offer or an early `agreed`.** An early yes means the anchor was too shallow.
10. **Stay warm and consistent.** Appreciation is free and buys concessions; a threat or a price that moves the wrong
    way costs trust and can trigger `final_offer`.

## 2. Books

| Book | Core idea | What we take from it |
|---|---|---|
| Fisher, Ury, Patton, *Getting to Yes* (1981) | Interests behind positions; BATNA (the best alternative to a deal); objective criteria. | The alternative in the case file is our BATNA and sets when to walk. Indices, should-cost and rival quotes are the "objective criteria": argue from them, not from wishes. |
| Malhotra, Bazerman, *Negotiation Genius* (2007) | Reservation value and the zone of possible agreement; anchoring; "investigative negotiation"; logrolling; contingent contracts. | Estimate the supplier's floor before opening. Trade across issues. An index clause is a contingent contract: it settles a disagreement about future costs without either side conceding. |
| Lax, Sebenius, *The Manager as Negotiator* (1986) and *3-D Negotiation* (2006) | Creating value and claiming it happen at once; differences between the parties are the source of value. | Differences in the cost of capital, in volume certainty and in risk tolerance are exactly the levers in `C`. |
| Raiffa, *The Art and Science of Negotiation* (1982) | Decision analysis of bargaining; scoring multi-issue packages; the midpoint of the two opening offers predicts the outcome. | We already score packages in `C`. The midpoint rule is the argument for a deep anchor: the deal tends to land halfway between the two openings. |
| Voss, *Never Split the Difference* (2016) | Calibrated questions, labelling the other side's concern, the "accusation audit", the Ackerman plan, precise numbers. | The e-mail's wording: name their problem before asking, ask "how" questions, use non-round figures. See section 4 for the Ackerman plan. |
| Cialdini, *Influence* (1984) | Reciprocity, commitment and consistency, social proof, authority, liking, scarcity. | Reciprocity is a hard rule in the arena. Consistency: get a small yes on a principle ("price should follow the index") before using it. |
| Shell, *Bargaining for Advantage* (1999) | Leverage is who loses more from no deal; people defer to standards they have already accepted. | Cite the supplier's own letter, contract clause or scorecard back to it. Its own standard is harder to dismiss than ours. |
| Dawson, *Secrets of Power Negotiating* (1995) | A catalogue of gambits: bracketing, the flinch, higher authority, the vise, the nibble, tapering concessions. | A description of what the bots do to us (higher authority is their approval ladder) and the counters. |
| Karrass, *The Negotiating Game* (1970) and *Give and Take* (1974) | Experiments with buyers: high aspiration wins; losers make the larger concessions and make them first. | Set the target high and concede slowly and late. |
| Camp, *Start with No* (2002) | Neediness loses; be ready to hear no. | Do not leak urgency or a missing alternative, as the brief's tips also say. |
| Diamond, *Getting More* (2010) | Trading items of unequal value; use the other side's standards. | The same trade logic, with wording examples. |
| Thompson, *The Mind and Heart of the Negotiator* (textbook) | The research summarised: the fixed-pie bias, anchoring, package offers. | A reference for the papers below. |

Procurement-specific sources:

- **Kraljic, "Purchasing Must Become Supply Management" (HBR, 1983).** Sort purchases by profit impact and supply
  risk into leverage, strategic, bottleneck and routine items, each with its own stance. The arena's category goals
  are this matrix: `leverage` is leverage, `secure_supply` is bottleneck, `stabilise` and `quality_first` are
  strategic, `routine` is routine. Exploit power on leverage items; protect supply on bottleneck items.
- **Schuh et al., *The Purchasing Chessboard* (A.T. Kearney, 2008).** 64 methods placed by supply power against
  demand power. Useful as a checklist of levers when price is stuck.
- **Should-cost / clean-sheet costing** and **total cost of ownership** (Ellram, 1990s). Build the price from
  material, labour, energy, overhead and margin; compare the total, not the unit price. This is our `C`.

## 3. Research findings worth knowing

| Finding | Source | Consequence |
|---|---|---|
| The first offer anchors the outcome. Thinking about the other side's alternatives and floor weakens an anchor set against you. | Galinsky, Mussweiler (2001) | Round 0 is the supplier's anchor on us. Compute targets from should-cost and the floor estimate, never as a discount on the quote. |
| A precise offer anchors harder than a round one: it looks calculated. Against experts, precision without a reason backfires. | Mason et al. (2013); Loschelder et al. (2016) | Offer 41.37, not 41.00, and show the calculation. |
| An extreme first offer raises the risk of an impasse, more so against a weaker counterpart, who feels offended. | Schweinsberg et al. (2012) | Deep anchors need a reason and a warm tone, most of all with small family suppliers. |
| Several equivalent offers at once get better outcomes and a more satisfied counterpart than one offer. | Medvec, Galinsky et al. (2005) | Our equal-C menu. Keep it, and read the supplier's choice. |
| Skilled negotiators ask twice as many questions, give fewer reasons, summarise more and avoid "irritators" such as calling their own offer fair or generous. | Rackham, Carlisle (Huthwaite study, 1978) | Fewer arguments per e-mail. Strip self-praise from the model's text. |
| Weak arguments added to strong ones lower persuasion. | "Argument dilution" research | Matches row 6 of `rejections.md`: true but unconvincing data. |
| A concession made after a delay and in steps satisfies the other side more than the same total given at once. | Kwon, Weingart (2004) | Hold the first move; do not jump to the target. |
| A firm concession curve ("Boulware") beats an early-conceding one when the deadline is not binding. | Faratin, Sierra, Jennings (1998); the ANAC agent competitions | Tactical already does this. The round limit is our only deadline: do not spend rounds on stalls. |
| In a bargaining game the more patient side gets the larger share. | Rubinstein (1982) | Signs of supplier impatience (short quote validity, cash need, idle capacity) justify a harder line. |
| A large request that is refused makes a following smaller one more likely to be accepted. | Cialdini et al. (1975), "door in the face" | The refused deep anchor still does work for the second offer. |

Two findings on LLM negotiators, relevant if the bots are language models playing a human:

- **Bianchi et al., *NegotiationArena* (2024):** LLM counterparts were measurably moved by the other agent's tone and
  persona; behavioural tactics changed payoffs by a wide margin.
- **Vaccaro et al., MIT AI negotiation competition (2025):** warm agents closed more deals, dominant agents claimed
  more of each deal; the best agents combined both.

Both point the same way as rule 10: firm on numbers, warm in wording. Test before trusting; these were other bots.

## 4. Tactics, mapped to the arena

### 4.1 Anchoring and the opening

- **Anchor on the floor estimate.** Baseline v2 anchors 18 % below the quote on `leverage`, tactical at most 15 %,
  and the D02 floor was about 24 % below the opening. A fixed percentage is the wrong unit. Estimate the floor from
  should-cost, the last paid price moved by the index, and the lowest rival quote; open below that estimate.
- **Bracket.** The deal tends to land midway between the openings. To end at target `T` against a quote `Q`, open
  near `2T − Q`, bounded by what we can justify.
- **Give the reason in the same sentence** as the number, with the ID. Row 7 of `rejections.md` is the cost of
  skipping this.
- **Reanchor after their quote.** Do not write "your price less X %": that accepts their number as the start.

### 4.2 Concessions

- **The Ackerman plan** (Voss), for a buyer: open at 65 % of the target, then 85 %, 95 %, 100 %, with a precise final
  figure and a non-monetary extra at the end. The percentages suit haggling, not industrial contracts with a cost
  floor; the shape is what matters. Each step is about half the previous one.
- **Label every concession and name its price.** "We can move to X if the term is 24 months." A concession that is
  not labelled is not counted as a move by a human; test whether the bots count it.
- **The last step should be small and odd-sized**, with a statement that it is the limit. It makes `final_offer` on
  their side more likely to land near us.
- **Never split the difference when they propose it.** Their offer to split concedes half; hold and ask for the rest
  in terms.

### 4.3 Trading terms (logrolling)

The fields with different value to each side, and the signal that the supplier wants the trade:

| Lever | Worth to us | Signal from the supplier |
|---|---|---|
| Payment days | Our interest rate, per case | "Faster payment is welcome" (row 5), "Faster payment would help us more than anything" (row 12), credit notes in the dossier |
| Contract length | Covers the horizon; an uncovered year costs the fallback price plus risk | "Planning security", an expiring framework contract |
| Volume commitment | Free where the forecast already covers it | "Which volume can you commit to?" (row 1, 57 times) |
| Index clause | Removes their risk premium; costs us the goal's index risk | "We can offer a Preisgleitklausel" (P08, P18), a letter blaming energy or material |
| Price effective date | Units before the date are bought at the old price | A price increase letter with a date |
| Lead time, Incoterm | € per day and freight in `C` | "With overtime we can deliver in N days", idle capacity |
| Quality terms (PPM, chargebacks) | Expected defect cost | A red scorecard, an open 8D report |

- **When price is frozen** (row 11), stop asking for price. Everything else is still open, and the score counts it.
- **Volume:** where `volume_per_year` is a field, put the forecast volume in as a commitment and ask for the price
  it earns. Where it is not, state what the forecast covers and cite it. Either beats silence.
- **Index clause:** when the supplier defends with its own index (row 2), offer the clause both ways. If the index
  justifies the rise, it must also bring the price down when it falls. The supplier has already accepted the
  standard (Shell).

### 4.4 Arguments

- **Pick by the supplier's situation, not by what we can verify.** Row 6: a verified scorecard argument rarely moves
  price. Row 2: an index we cite can support their side. Check the direction of every index before citing it.
- **Rival quotes are the strongest argument we have** (8 "took it into account", D02 and P05). This is BATNA made
  visible. Only cite real ones with IDs: an invented rival is `contradicted` and costs trust.
- **"We did not know that"** (4 times) comes from facts about the supplier's own performance or contract that the
  sales rep had not seen. Notice periods, past price paths and should-cost belong here.
- **At most two arguments per e-mail,** the strongest first.

### 4.5 Questions and tone

- **Calibrated questions** when the supplier stalls or refuses: "What would make 24 months workable for you?", "How
  can we close the gap on payment terms?". Never a question alone: row 8 shows that a message with no move counts as
  no move.
- **Label their problem first.** "We understand energy costs have hit the foundry hard this year" before the ask. It
  costs nothing and the brief says tone is read.
- **No irritators:** "fair", "generous", "reasonable" about our own offer. No threats we cannot carry out.
- **Counter the approval ladder** (rows 9 and 10): it is the "higher authority" gambit. Ask what the boss needs to
  see, give that, and ask again. Our trace shows the second ask gets the next step.
- **Counter the call stall** (row 10): restate the offer in writing with one new trade, so the round is not wasted.

### 4.6 Closing and walking

- **Compare every standing offer with the alternative in `C`.** "Some cases are best left without a deal."
- **Probe a `final_offer` once** with a trade, not with a lower price: a term that costs them nothing may still be
  open. Tactical does this when a walk-away is cheap.
- **The nibble:** before accepting, ask for one small non-price term. Check that unstated fields are not closing on
  the supplier's standard terms.
- **In RFQ cases, run the threads against each other** to the last round, and tell each supplier truthfully where it
  stands. Accept only when the leader has stopped moving.

## 5. Other options

Ways to improve beyond tuning price tactics.

1. **Model the supplier's type first, then pick the playbook.** The brief names four: the family foundry (relationship
   and memory), the group with an approval ladder (persistence, material for the boss), the job shop short of cash
   and work (payment days, volume), the near-monopolist (take terms, protect supply, consider no deal). A third of the
   final cases mix types and case types, so the mapping must come from traits in the dossier, not from supplier IDs.
2. **Estimate the floor per case** from should-cost and history, and set the anchor from it (section 4.1).
3. **Build our own supplier simulator** from the replays, as the brief suggests, to test concession curves without
   spending the 200 daily sessions.
4. **Mine the replays for what moved each supplier,** per trait, and feed that into argument selection. The trace
   gives the supplier's reasons in words.
5. **Use the LLM where judgment is needed and nowhere else:** reading the dossier, choosing the lever and the tone,
   writing the e-mail. Numbers stay in code. This is the planned `judged` strategy.
6. **Decide the no-deal cases on purpose.** Where the alternative beats the best reachable deal, spend few rounds
   and walk.

## 6. What to test

Hypotheses for benchmark runs, each recorded under `agent/docs/benchmarks/`. Section 7 has the results of those
the sandbox could test.

| # | Change | Basis |
|---|---|---|
| 1 | Answer the volume question: commit the forecast volume where it is a field, cite the forecast where it is not | Row 1; logrolling |
| 2 | Anchor from the floor estimate instead of a fixed percentage | D02 floor; Galinsky, Mussweiler |
| 3 | Offer a two-way index clause when the supplier cites its own index | Row 2; contingent contracts |
| 4 | Lead with payment days for suppliers flagged cash-short | Rows 5 and 12 |
| 5 | Cap arguments at two per e-mail, chosen by supplier trait | Row 6; Rackham |
| 6 | Shrinking, labelled concessions with a precise last step | Ackerman; Kwon, Weingart |
| 7 | One line of appreciation and a label of their problem in each e-mail | Brief; Vaccaro et al. |
| 8 | A calibrated question added to every message that also contains a move | Voss; row 8 |

## 7. What the sandbox said

Tested on 10 October 2026 as the `playbook` strategy, on D01 and D02 only, without an LLM. Runs, parameters and
figures: [`../benchmarks/2026-10-10-playbook-none.md`](../benchmarks/2026-10-10-playbook-none.md). Two demo cases and
three suppliers; one run per variant, and a change below about 0.05 on one case is noise.

| Rule | Result |
|---|---|
| 9, 4.6: do not take the final offer as final; make one closing offer | **Confirmed on the sandbox, contradicted on practice.** On D01 and D02 it moved the leading supplier five times out of five and none walked away. On the 10 practice cases three suppliers walked away, three gave a further step and two held: mean 0.376 with it, 0.539 at the final offers. |
| 2, 4.1: a deeper anchor | Confirmed as harmless and slightly positive (the earlier `lowball` runs). An opening 10 % deeper again changed nothing: the foundry ended at the same final offer. |
| 5: a menu of equal-cost sheets | Confirmed. One sheet instead of the menu lowered D01 from 0.803 to 0.777. |
| 4.3: lead with payment days for a supplier that wants cash | Not confirmed. The job shop took 14 days and kept the price it gave for 30. |
| 1, 4.3: pick the terms that are cheapest at the supplier's price | Contradicted on D01. The foundry prices each term at about what it is worth to us, so a later effective date bought nothing. |
| 8, 4.5: an open question next to every move | Contradicted on D01 (0.863 → 0.803): the foundry explains its costs instead of moving. One question in the first e-mail did no harm. |
| 6, hypothesis 1: answer the volume question | Contradicted as written. Stating the need without a data ID is an unbacked claim: "please provide the corresponding data", for three rounds. An ID without a figure is not counted either. It needs the forecast ID with its figure; the sandbox cases have none in the data package, so this is untested where it can work. |
| 4.2: shrinking concessions | No effect seen. The suppliers call a final offer in reply 3 or 4 whatever our steps are. |
| 3: index clause, hypotheses 3 to 5 | Not testable on the sandbox: no index clause, no supplier dossier, no data arguments. |

The pattern on the sandbox: the suppliers concede on their own schedule and stop after three or four replies. What
we send changes the outcome in two places only - a verified rival quote early, and a closing offer at the end.

**Practice run, the same evening** (10 hosted cases, one run each): `playbook` 0.376 with 7 of 10 deals, `tactical`
0.695 with 10 of 10. A final offer is final for some practice suppliers, and the sandbox did not show which. Push
past one only with a fallback, as `tactical` does.
