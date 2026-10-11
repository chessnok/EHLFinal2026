# 2026-10-11 · tactical with `ppm_ladder`, `anchor18`, `owner_offer` · no LLM

## Result and cost

| Strategy | Case | Score | C_deal (EUR) | Deal | Control (`tactical`) |
|---|---|---|---|---|---|
| `tactical+ppm_ladder` | P11 | 0.710 | 750,082.50 | 45.50, 300 ppm, chargeback 0, round 4 | 0.710 (`../runs.md` P-54) |
| `tactical+anchor18` | P08 | **0.670** | 1,018,176.02 | 5.24, 90 days, 24 months, deadband 0 %, round 5 | 0.659 (P-57) |
| `tactical+owner_offer` | P08 | 0.416 | 1,062,866.95 | 5.47, 90 days, 24 months, deadband 0 %, round 3 | 0.659 (P-57) |
| `tactical+anchor18` | P18 | 0.532 | 256,557.24 | 5.40, final offer in round 4 | 0.685 (P-57) |
| `tactical+anchor18` | P05 | 0.522 | 262,700.48 | sup:70250 at 31.00, 9 rounds, 8 arena timeouts | 0.865 (P-57) |

5 of 5 deals. Run cost: 5 practice sessions, 0 LLM tokens, about 1.5 to 2 minutes wall time per session and
5.5 minutes for P05. No LLM, so one run per flag and case.

What the arena answered:

- **P11, `ppm_ladder`.** The 300 ppm sheet took the control's path (46.50 → 46.00 → 45.50 → final 45.50). The first
  reply offered 46.00 at 1500 ppm beside 46.50 at 300 ppm, the final offer 45.00 at 1500 ppm beside 45.50 at 300 ppm.
  45.00 at 1500 ppm costs us 750,718 (`arena_kit.total_cost`), 636 more than the deal. Last reply: "thanks for the
  small step, but we are still quite far apart."
- **P08, `anchor18`.** First ask 4.96 (control 4.54). Replies 5.41 → 5.44 with a 5 % deadband (alternative 5.39 at
  3 %) → 5.29 → 5.26 → final 5.24, the last three at deadband 0.
- **P18, `anchor18`** (code `19a72f4`). Replies 5.50 → 5.30 → 5.40 → final 5.40.
- **P05, `anchor18`** (code `19a72f4`). The arena counted 8 timeouts over the three threads; sup:70210 walked away
  from a final offer of 28.00 on one of them, sup:70240 walked away in round 4, the deal is sup:70250's 31.00. The
  score says little about the flag.
- **P08, `owner_offer`.** The same sheets and the same three verified arguments as the control; the first reply came
  at 5.52 (control 5.40), then 5.49 and final 5.47.

## Strategy

`strategy/tactical.py` at `2e40de5` (branch `feat/p08-p11-p02`), `tactical` with one flag each, all off by default:

- `ppm_ladder`: where the ppm commitment is negotiable, every message carries one sheet per commitment the must-haves
  allow, tightest first, at the lowest chargeback and at option A's C.
- `anchor18`: with a `leverage` goal the first ask is at most 18 % under the quote (`MAX_ANCHOR_LEVERAGE`).
- `owner_offer`: a supplier with the trait `open_book` is asked for its calculation with the date of the note in
  which it offered it, in place of "Could you send us a cost breakdown for this part?".

## Runs

Set practice, the Sunday release loaded (`../runs.md` P-58 to P-60): `20261011-112529-practice-tactical+ppm_ladder`
(P11), `20261011-112618-practice-tactical+anchor18` (P08), `20261011-112625-practice-tactical+owner_offer` (P08);
P-61 and P-62: `20261011-113020-practice-tactical+anchor18` (P18), `20261011-113241-practice-tactical+anchor18` (P05).
