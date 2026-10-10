# Deal terms and the cost formula C

Source: `negotiation-arena-kit/brief/api.md` and `brief/brief.md`. The published function is `arena_kit.cost.total_cost`;
our agent computes through it.

**The formula is the same for every case, practice and final.** What changes are its inputs: which fields a case
negotiates and the buyer's rates.

## Deal terms (term sheet)

| Field | Meaning |
|---|---|
| `unit_price` | price per unit in €, 2 decimals (per the part's `price_unit`: piece, 100 pieces, kg) |
| `payment_days` | payment term, days net (0–120) |
| `lead_time_days` | lead time from order to delivery, days |
| `volume_per_year` | binding annual volume |
| `contract_months` | contract length (0–36; 0 = a single order, counted as one year's lot) |
| `effective_date` | date from which the new price applies |
| `index_clause` | the price follows an index (series, material share, deadband, base month) |
| `incoterm` | `EXW` / `FCA` / `DAP`: who pays for freight |
| `tooling_eur` | one-off tooling payment |
| `ppm_commitment` | committed defect rate, ppm |
| `chargeback_eur_per_complaint` | what the supplier pays us per complaint |

**Not every field is negotiated in every case:**

- **`negotiable`**: the fields every term sheet must carry. In D02, for example: price, payment, lead time and Incoterm.
- **`fixed_terms`**: fields the case fixes.
- **The supplier's standard terms** from its quote PDF: everything the term sheet leaves out and the case does not fix
  closes on these.
- **`term_options`**: the allowed values for fields other than the price.

## Buyer parameters (per case, the `buyer` block)

| Parameter | Meaning |
|---|---|
| `need_per_year`, `horizon_years` | how much is needed per year, and for how many years (at most 3) |
| `current_unit_price` | the price until a new price takes effect |
| `fallback_unit_price` | what uncovered need costs: re-tender or spot |
| `interest_rate`, `reference_payment_days` | cost of money and our standard payment term |
| `need_lead_time_days`, `late_cost_per_day` | the lead time we need and the cost per day beyond it |
| `cost_per_defect` | cost of one defective part |
| `category_goal` | `stabilise`, `secure_supply`, `quality_first`, `leverage` or `routine`; sets the rates below |
| `fallback_risk_pct`, `index_risk_pct` | risk on uncovered need and risk of an index clause, in % |
| `sustainable_margin_pct`, `relationship_eur_per_point` | `stabilise` and `secure_supply` only: the supplier's sustainable margin and the charge per point below it |
| `freight_eur_per_unit` | freight per unit for each Incoterm |
| `index_paths` | expected index moves over the horizon |
| `must_haves` | mandatory conditions; break one and the score is 0 |
| `alternative` | what we get without a deal |

## The total cost formula C

Notation: `N` = `need_per_year`, `H` = `horizon_years`, `V` = `volume_per_year`, `M` = `contract_months`,
`P` = `unit_price`, `r` = `interest_rate`, `d_ref` = `reference_payment_days`.

```
years     = min(M / 12, H); a single order (M = 0) counts as 1 year
committed = V · years                         bought, needed or not
covered   = min(V, N) · years
pre       = units bought before effective_date (at current_unit_price)
new       = (committed − pre) · P
spend     = pre · current_unit_price + new
uncovered = (N · H − covered) · fallback_unit_price

C = spend
  + uncovered · (1 + fallback_risk_pct / 100)                      uncovered need and its risk
  + spend · r · (d_ref − payment_days) / 360                       paying early costs interest
  + committed · freight_eur_per_unit[incoterm]                     freight
  + late_cost_per_day · max(0, lead_time_days − need_lead_time_days)
  + committed · ppm_commitment / 1e6 · (cost_per_defect − min(chargeback, cost_per_defect))
  + tooling_eur
  + new · material_share · max(0, |index_path| − deadband/100) · sign(index_path)   with an index clause
  + new · material_share · index_risk_pct / 100                                     with an index clause
  + relationship_eur_per_point · soft(sustainable_margin − supplier margin) · years   stabilise / secure_supply only

soft(g) = 0 for g ≤ 0;  g² / 10 for 0 < g ≤ 5;  g − 2.5 for g > 5
```

The horizon starts at the fixed or earliest allowed `effective_date`; `index_path` is the expected move of the clause's
series over the horizon.

**Supplier margin** = `(value − full_cost) / value × 100`. Here `value` is what the deal is worth to the supplier in
cash per unit, including payment timing, freight and tooling. We do not know its `full_cost`; we have to estimate it,
for example from the should-cost data.

## Score

```
score = clip((C_open − C_deal) / (C_open − C_best), 0, 1)
```

- **`C_open`**: the cheapest opening offer that keeps the must-haves.
- **`C_best`**: the cheaper of our alternative and the best package any supplier in the case would accept with every
  valid lever applied. It is fixed in advance, so good arguments raise the score instead of moving the yardstick.
- **No deal**: the alternative's score (0 if there is none).
- **A broken must-have**: 0.
- **Final**: each wave scores the mean of its case scores × 100; points add up over 5 waves, at most 500.

## What stays the same and what changes

**The same:** the formula C and the score. The brief states that the calculation rules are the same for practice and
the hidden final cases.

**Changes from case to case:**

- **Negotiated fields and allowed values** (`negotiable`, `term_options`, `fixed_terms`).
- **All buyer rates.** `category_goal` sets them: for example, the supplier-margin charge exists only in `stabilise`
  and `secure_supply`, and `leverage` has a higher risk on uncovered need.
- **The supplier's standard terms** from its quote PDF: everything not in the term sheet closes on these.

So the same price can produce very different C. In D01 a 12-month versus a 24-month contract made a difference of about
€30k at almost the same unit price: with the shorter contract the second year of the horizon is bought at the fallback
price.

**The buyer's goal is the lowest C, not the lowest price.** A slightly higher price with a better structure can win.
The exception: in `stabilise` and `secure_supply` cases C charges for a supplier margin below the sustainable one, so
squeezing the price too hard does not pay either.
