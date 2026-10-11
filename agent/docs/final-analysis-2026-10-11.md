# Live Final, 11 October 2026: where the score was lost

Source: our own run dirs `agent/runs/20261011-120734-final-tactical` and `-121536-final-tactical` (commit `10c8036`,
`runs.md` F-1), the session files there, and `arena_kit.total_cost` offline. The arena's board was not read. Mean
0.584, 27 of 30 deals.

## Per case

| Case | Score | Class | What happened |
|---|---|---|---|
| H15, H01 | 0 | infrastructure | A network restart left requests on sockets of an old address; they hung until the 180 s read timeout and the arena played the suppliers' timeouts. Fixed after the final: TCP keepalive (PR #18) |
| H30 | 0.258 | fitted constant | Renewal under a `leverage` goal, one supplier: `floor_factor` gives the price-only floor 0.99 and the first ask 10 % under the quote (`groundtruth.py:189-192`, `tactical.py:604-605`), fitted on practice price-increase and renewal cases, all `stabilise` or `routine`. It agreed in round 1 at 4.56; C_best sat at about 3.29 |
| H38, H06, H34, H24 | 0.48-0.68 | the same | All 5 hidden leverage price-only cases closed at or under our 10 % ask in 1-3 rounds, while C_best sat 14-35 % under the quote |
| H10 | 0.012 | bug + missed mechanism | RFQ, 3 bidders. (1) Where a bidder's opening named no lead time, option A asked 21 days against a need of 28 at the same C (the menu lists the shortest first, `menu.py:52-62`, `tactical.py:1600`); the winner answered "rushing it means we need EUR 97.50" and its price rose. Same over-specification in H15, H09, practice P05 and P10. (2) Arguments count once per case, so the first thread to decide (the dearest bidder) took the index fall; the eventual winner got only its quality record. (3) The keepalive "confirm the validity of your offer" went to final-offer threads 4 times, 2 walked |
| H13 | 0.313 | mostly ceiling | First reply already a final offer with an index clause at deadband 0 (approval-ladder supplier). About 0.077 was the clause: no clause option in round 1 (`clause_rel_only`), and a clause imposed in a final offer cannot be renegotiated |
| H19 | 0.165 | no measured lever | quality_first, no should-cost, no cheaper alternative; the supplier moved 0.3-1.1 % per verified argument and called final in round 4 |

Strong cases for contrast: H29 0.969 (own-plant should-cost, 3-4 % a round), H32 0.933 and H37 0.810 (deep first
ask, real competition), H35 and H02 (routine, small room).

## Candidate general fixes (not played; offline checks only)

1. **First-ask depth and floor follow the goal, not the case type:** price-only floor and 10 % depth only outside
   `leverage`. Offline replay: only the first asks of H06, H24, H30, H34, H38 change; 0 of 255 practice decisions change
   (practice has no leverage price-only case).
2. **Multi-bidder cases:** on a C and price tie prefer the supplier's own value, and for a field it omitted the value
   nearest our need (never a stricter lead time at no gain); reserve once-per-case arguments for the bidder with the
   lowest opening C. Offline: changes H10, H15, H09 and practice P05 (37 decisions), P10 (4) - re-measure P05.
3. **Keepalive:** only the delivery-capacity question; never "confirm the validity" to a held final-offer thread.

Not proposed again (failed before, `TRYED.md`): larger steps, arguments held back, pushing a final offer, hedge
turning, pushing past an approval band.
