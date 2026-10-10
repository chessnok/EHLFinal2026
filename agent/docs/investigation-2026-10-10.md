# Investigation, 10 October 2026: scoring, payment terms, relationship charge, term menu

No arena session was played for this. Everything is read from local files or computed offline.

**Data read** (other agents were adding runs while this was written; the snapshot is fixed by the newest run named):

- 64 practice sessions in 8 run directories under `agent/runs/*practice*` (61 deals, 3 no-deals), up to
  `20261010-234407-practice-tactical` with its first 2 sessions (P01, P02);
- 89 sandbox sessions under `agent/runs/*sandbox*` (46 on D01, 43 on D02), all deals;
- `negotiation-arena-kit/brief/brief.md`, `brief/api.md`, `starter-kit/arena_kit/cost.py`, `data/world.sqlite`.

**Source labels used below:**

| Label | Meaning |
|---|---|
| [docs] | `brief.md` or `api.md` |
| [code] | `arena_kit/cost.py`, the published cost function |
| [practice] | a recorded practice session; cited as `run/session`, run names without the `20261010-` prefix |
| [sandbox] | a recorded sandbox session |
| [computed] | the published cost function applied to a stated term sheet, with the supplier fitted in section 3 |
| [inference] | our reading; not established |

"Score points" always means EUR divided by `c_open − c_best` of that case.

## 1. Scoring

### 1.1 How C is built

[docs] `api.md`, "Cost and score"; [code] `cost_breakdown`. Both say the same:

```
years     = min(contract_months / 12, horizon_years)        a single order counts as 1 year
committed = volume_per_year · years
covered   = min(volume_per_year, need_per_year) · years
pre       = units between the horizon start and effective_date, at current_unit_price
spend     = pre · current_unit_price + (committed − pre) · unit_price
uncovered = (need_per_year · horizon_years − covered) · fallback_unit_price

C = spend
  + uncovered · (1 + fallback_risk_pct / 100)
  + spend · interest_rate · (reference_payment_days − payment_days) / 360
  + committed · freight_eur_per_unit[incoterm]
  + late_cost_per_day · max(0, lead_time_days − need_lead_time_days)
  + committed · ppm / 1e6 · (cost_per_defect − min(chargeback, cost_per_defect))
  + tooling_eur
  + new_spend · material_share · max(0, |index_path| − deadband/100) · sign(index_path)     index clause only
  + new_spend · material_share · index_risk_pct / 100                                       index clause only
  + relationship_eur_per_point · soft(sustainable_margin_pct − supplier_margin_pct) · years  stabilise, secure_supply
```

Answers to the questions asked:

| Question | Answer | Source |
|---|---|---|
| Plain sum or discounted? | Plain sum. A unit bought in year 2 counts the same as one bought in year 1. There is no discount factor anywhere in the function. | [code] |
| Is an interest rate modelled? | Only in the payment term: `spend × interest_rate × (reference_payment_days − payment_days) / 360`. Simple interest, 360-day year, linear in days. Paying later than the reference earns the same rate (the term turns negative). | [code], [docs] |
| Which rate and reference? | `interest_rate` 0.08 and `reference_payment_days` 60 in all 10 practice cases and both sandbox cases. | [practice], [sandbox] case files |
| Is inflation modelled? | No. A fixed price stays fixed for the whole horizon at no cost. The only price path is `index_paths`, and it counts only if the deal carries an index clause (P02 copper +5 %, P08 and P18 alloy surcharge +6 %). | [code], case files |
| Does a contract longer than the horizon count? | No. 36 months gives the same C as 24 months when the horizon is 2 years. | [code] `_years`; [computed] section 4 |
| Does volume above the need count? | Yes, in full: committed units are bought "needed or not". | [code] |

### 1.2 From C to the score

[docs], [code] `score`:

```
score = clip((C_open − C_deal) / (C_open − C_best), 0, 1)
```

| Outcome | Score | Source |
|---|---|---|
| `C_deal ≥ C_open` | 0 | [code]; [practice] P02 `221425-practice-tactical-slow25/e5471e792b2e64a9` |
| `C_deal ≤ C_best` | 1 | [code] |
| a broken must-have | 0 | [docs] |
| no deal, case has an alternative | the alternative's score | [docs]; [practice] P07 `212101-practice-playbook/6bcba80947d374a4`: 0.121 with `c_alt` 379,916 |
| no deal, alternative dearer than C_open, or none | 0 | [practice] P04 `212101-practice-playbook/3bf0807b2eebd8b1` (`c_alt` 203,169 > `c_open` 198,846) |

What the two yardsticks are, as far as the records show:

- **C_open** is the opening sheet filled with the supplier's standard terms. Recomputed with the kit it matches the
  arena's `c_open` to the cent in all 10 practice cases. [practice]
  - In the RFQ P05 it is Dralveck's EUR 36.00, not Hrvelec's cheaper EUR 31.50: Hrvelec's opening has a 52-day lead
    time and breaks the must-have (≤ 42). This agrees with [docs] "among those that keep the must-haves".
  - In P10 and P11 the only opening breaks a must-have (volume 19,890 < 22,230; ppm 6,400 > 1,500) and is still used
    as C_open. [practice] The docs do not say this.
- **C_best** includes the relationship charge. On P01 and on D01 it equals, to EUR 0.01, the lowest C the published
  function can reach over all term options and prices once the supplier of section 3 is plugged in. [computed]
  On P02 and P03 the function can go lower than `c_best` (by EUR 5,134 and EUR 32,586 at 90 days), so there
  `c_best` is limited by something else - by the docs' definition, what the supplier would accept. What that limit
  is cannot be established from the records.

### 1.3 Numerical check

For every recorded deal C was recomputed with `arena_kit.cost.cost_breakdown` from the closed terms, without a supplier
estimate, and compared with the arena's result.

| Set | Deals | Max difference per term (EUR) | Max of `c_deal − (kit sum + arena relationship)` (EUR) | Max score difference |
|---|---:|---:|---:|---:|
| practice | 61 | 0.005 (`price`, `payment_terms`, `quality`, `index_clause`, `index_risk`); 0 for the others | 0.0073 | 0 |
| sandbox | 89 | 0.003 (`payment_terms`); 0.001 (`price`); 0 for the others | 0.0033 | 0 |

The differences are rounding. The only part of C the kit cannot reproduce without an estimate is `relationship`:
it is above 0 in 15 practice deals and 6 sandbox deals (section 3). No other deal differs.

## 2. Payment terms

### 2.1 What the term sheet allows

- [docs] `payment_days` is one integer per term sheet ("days net", 0-120).
- [docs] "Every negotiable field except `unit_price` takes a value from `term_options` (or the supplier's standard
  value)"; a value outside the options is a `422`.
- So the choice is one of the listed options, nothing else. **Instalments, staged payments, a payment later than the
  longest option or any other deferral cannot be expressed.** The term sheet has 11 fields ([docs] "Terms"); none of
  them is a payment schedule.
- The only up-front cash field is `tooling_eur`. It is fixed at 0 in all 10 practice cases.
- Text in the e-mail does not bind ([docs] "term sheets bind - nothing else").

### 2.2 Options and value per case

Value of each step at the opening price, on a contract that covers the whole horizon. [computed] with the kit, no
relationship charge. A step of 30 days is always 0.667 % of the spend (0.08 × 30 / 360).

| Case | Negotiable? | Options | 30 → 14 | 30 → 45 | 30 → 60 | 30 → 90 |
|---|---|---|---|---|---|---|
| P01 | yes | 14, 30, 45, 60, 90 | +4,015 (−0.070) | −3,764 (+0.066) | −7,528 (+0.132) | −15,056 (+0.264) |
| P02 | yes | 14, 30, 45, 60, 90 | +8,059 (−0.170) | −7,555 (+0.160) | −15,110 (+0.319) | −30,221 (+0.638) |
| P03 | yes | 14, 30, 45, 60, 90 | +14,272 (−0.042) | −13,380 (+0.040) | −26,760 (+0.079) | −53,520 (+0.159) |
| P04 | yes | 14, 30, 45, 60, 90 | +705 (−0.304) | −661 (+0.285) | −1,323 (+0.571) | −2,645 (+1.142) |
| P05 | yes | 14, 30, 45, 60, 90 | +1,075 (−0.013) | −1,008 (+0.012) | −2,016 (+0.025) | −4,032 (+0.049) |
| P07 | yes | 14, 30, 45, 60, 90 | +1,225 (−0.013) | −1,148 (+0.013) | −2,296 (+0.025) | −4,592 (+0.050) |
| P08 | yes | 14, 30, 45, 60, 90 | +4,079 (−0.023) | −3,824 (+0.022) | −7,647 (+0.044) | −15,294 (+0.087) |
| P10 | no, fixed at 30 | – | – | – | – | – |
| P11 | no, fixed at 60 | – | – | – | – | – |
| P18 | yes | 14, 30, 45, 60, 90 | +1,028 (−0.014) | −964 (+0.013) | −1,928 (+0.027) | −3,855 (+0.053) |

Cells: EUR change of C (score points gained). Sandbox: D01 offers 30, 45, 60; D02 offers 14, 30, 45, 60.

Notes:

- **P04** is the case where payment decides the score: the whole range `c_open − c_best` is EUR 2,317, and one cent of
  price on 40,000 units is EUR 397 (0.17 score points).
- **P10** carries a fixed EUR 9,953 of `payment_terms` in every deal (30 days against a 60-day reference).
- **P11**: the supplier asks for faster payment in its replies, but the case fixes it at 60 days, which is also its
  standard term in the `suppliers` table. It cannot be given.
- In the two `stabilise` cases with a narrow range (P01, P02) the table overstates the gain: the supplier re-prices the
  payment term (section 2.3) and the relationship charge reacts to it (section 3).

### 2.3 What the supplier charges for payment days

When a supplier's reply carries an alternative sheet that differs from its standing sheet only in `payment_days`, the
two prices give its own exchange rate: `(1 − P_alt / P_standing) × 360 / days`. [practice] The interval is what the
supplier's price rounding allows.

| Case, supplier | Alternative sheets | Rate per year | Against our 0.08 | Example |
|---|---:|---|---|---|
| P02 Nordmark | 16 | 0.0660 – 0.0663 | below: 90 days is the cheaper sheet for us | 374.72 at 90 d, 370.60 at 30 d (`173324-practice-llm/6b2cf6e71cc80435` r1) |
| P03 Selvbrunn | 4 | 0.0405 – 0.0408 | below: 90 days | 432.87 at 90 d, 429.94 at 30 d (`211824-practice-tactical/81a280e40e69302e` r2) |
| P04 Wälzlager-Zentrum | 5 | 0.065 – 0.081 | about equal | 4.94 at 90 d, 4.88 at 30 d (`211824-practice-tactical/cb0949b8477a0af8` r1) |
| P07 Leitner | 13 | 0.072 – 0.084 | about equal | 5.59 at 90 d, 5.52 at 30 d (`211824-practice-tactical/12616d36794684a8` r1) |
| P08 Donautal | 5 | 0.059 – 0.070 | below: 90 days | 6.10 at 90 d, 6.03 at 30 d (`173324-practice-llm/a0a3f562a163279d` r1) |
| P18 Werdenfels | 3 | 0.107 – 0.140 as quoted; rounding to EUR 0.10 allows 0 – 0.21 | above in all 3 sheets: the shorter term was the cheaper sheet for us by EUR 1,275 – 2,203 | 5.60 at 90 d, 5.50 at 30 d (`211824-practice-tactical/8576fd4b5b32d5e6` r2) |
| P05 Hrvelec | 4 | 0.118 – 0.139 as quoted (one sheet 0.35); rounding to EUR 0.50 allows 0.07 – 0.20 | above in all 4 sheets, by EUR 1,358 – 3,662 | 34.00 at 90 d, 33.00 at 14 d (`173324-practice-llm/146b65f28b6e91ed` r4) |
| P01 Brandlhuber | 1 | 0.063 – 0.084 (blended with the units sold at the old price) | one sheet only | 137.00 at 45 d, 137.70 at 60 d (`211824-practice-tactical/67fe83b13ef212b1` r2) |

So a longer payment term is not free: every supplier prices it. Whether 90 days or 14 days is the cheaper sheet for us
depends on which side of 0.08 the supplier's rate lies.

## 3. Relationship charge

### 3.1 Every recorded charge

[practice], [sandbox]. All 21 deals with `cost_breakdown.relationship > 0`. No deal had an arena C that differed from
the kit's C for any other reason (section 1.3).

| Case | Run / session | Price | Days | Effective | Clause | Charge (EUR) | Margin points below sustainable | Score |
|---|---|---:|---:|---|---|---:|---:|---:|
| P01 | `212101-practice-playbook/134ff5ef09203be7` | 134.42 | 14 | 2027-04-01 | – | 4,618.93 | 1.728 | 0.917 |
| P01 | `173324-practice-llm/ce54582a24d803ba` | 135.60 | 14 | 2027-04-01 | – | 2,264.51 | 1.210 | 0.858 |
| P01 | `211824-practice-tactical/67fe83b13ef212b1` | 137.00 | 45 | 2027-04-01 | – | 3,085.81 | 1.412 | 0.856 |
| P01 | `180637-practice-llm/23998ca12bf8eec0` | 137.10 | 45 | 2027-04-01 | – | 2,898.77 | 1.369 | 0.851 |
| P01 | `175025-practice-llm/de8dc7a18d921a31` | 137.50 | 45 | 2027-04-01 | – | 2,210.50 | 1.195 | 0.829 |
| P01 | `221425-practice-tactical-slow25/4c3a3f7c4fdf6c14` | 132.20 | 60 | 2026-11-01 | – | 7,213.59 | 2.159 | 0.914 |
| P01 | `234407-practice-tactical/184a8cc59cd3c6f8` | 133.40 | 45 | 2026-11-01 | – | 1,178.34 | 0.873 | 0.785 |
| P02 | `221425-practice-tactical-slow25/e5471e792b2e64a9` | 345.39 | 90 | 2027-01-01 | deadband 0 | 179,204.24 | 8.114 | 0.000 |
| P02 | `211824-practice-tactical/44549782e6fa9a2a` | 358.45 | 90 | 2027-01-01 | deadband 5 | 56,126.93 | 4.193 | 0.686 |
| P02 | `233708-practice-tactical/e11991f5a540845b` | 372.62 | 90 | 2027-01-01 | none | 199.55 | 0.250 | 0.421 |
| P02 | `234407-practice-tactical/9d7ebcf9854a9734` | 372.62 | 90 | 2027-01-01 | none | 199.55 | 0.250 | 0.421 |
| P02 | `212101-practice-playbook/3275fa0d5a9d5df0` | 372.92 | 90 | 2027-01-01 | none | 92.02 | 0.170 | 0.385 |
| P03 | `211824-practice-tactical/81a280e40e69302e` | 432.87 | 90 | 2027-01-01 | – | 379.55 | 0.259 | 0.905 |
| P03 | `221425-practice-tactical-slow25/fac1082c4cc761d9` | 432.94 | 90 | 2027-01-01 | – | 337.04 | 0.244 | 0.903 |
| P03 | `233708-practice-tactical/ae3c9e50f1e6ba89` | 432.94 | 90 | 2027-01-01 | – | 337.04 | 0.244 | 0.903 |
| D01 | `214434-sandbox-tactical/0fb4a423c6151c16` | 49.60 | 30 | 2026-12-01 | – | 837.82 | 0.915 | 0.969 |
| D01 | `214628-sandbox-tactical-slow25/a6d257ba9bfd04f5` | 49.70 | 30 | 2026-12-01 | – | 518.86 | 0.720 | 0.957 |
| D01 | 4 sessions, e.g. `194543-sandbox-playbook-probe/2c8446008ce4db8a` | 49.80 | 30 | 2026-12-01 | – | 276.79 | 0.526 | 0.943 |

"Margin points below sustainable" is the charge inverted through the published `soft`: `s = charge / (EUR per point ×
years)`, gap `= √(10 s)` for `s ≤ 2.5`, else `s + 2.5`.

Deals on the same cases **without** a charge: P02 at 373.95, 373.97 and 374.72 (90 days); P03 at 438.21 (90 days, four
sessions); D01 at 50.20 and above (30 days), 50.40 and above (45 days), 50.90 and above (60 days); P10 all six deals
(31.90 to 34.90).

### 3.2 When it applies and how it scales

The published function reproduces every charge once a supplier is supplied: [code] `relationship_cost`,
`supplier_value`.

```
value  = (price · share at the new price + current price · share before effective_date)
         · (1 − supplier_rate · (payment_days − supplier_standard_days) / 360)        + freight, tooling, chargeback items
margin = (value − full_cost) / value · 100
charge = relationship_eur_per_point · soft(sustainable_margin_pct − margin) · years
soft(g) = 0 for g ≤ 0;  g² / 10 for g ≤ 5;  g − 2.5 above
```

What the records confirm:

| Property | Evidence |
|---|---|
| Starts exactly at the sustainable margin, quadratic first | D01: three prices 49.60 / 49.70 / 49.80 give one and the same full cost (48.070). P01: seven deals fit one supplier with a maximum error of EUR 0.004. The seventh (`234407-practice-tactical/184a8cc59cd3c6f8`) was played after the fit was made and matched it without a change. |
| Linear beyond 5 points | P02 at 345.39 (gap 8.11) and at 358.45 (gap 4.19) and at 372.62 / 372.92 (gap 0.25 / 0.17) give the same constant 371.6886. |
| An index clause does not change the supplier's margin | P02: the constant is the same for deals with deadband 0, deadband 5 and no clause. [docs] say the same ("security, not cash"). |
| Units sold at the old price before `effective_date` count | P01: deals effective 2026-11-01 and 2027-04-01 fit one supplier. |
| Payment days count at the supplier's own rate | P01: deals at 14, 45 and 60 days identify the rate (below). |
| Multiplied by the years covered | D01 and P03 (2 years) fit with `years = 2`. |

### 3.3 The fitted suppliers

Standard payment term: 30 days for all four practice suppliers, from the `suppliers` table of `world.sqlite`; for P01
the arena's own thread data also lists `payment_days: 30` as the standard term. D01's supplier is not in the data
package; its opening sheet states 30 days and we take that as the standard. [inference] for D01 only.

| Case | What the charges fix | Own-plant should-cost (`should_cost.unit_cost`) | Full cost / should-cost | Supplier rate | Deals, max error |
|---|---|---:|---|---|---|
| P01 | full cost **130.040**, rate **0.0960** | 132.64 | **0.9804** | 0.0960; at 0.0955 or 0.0965 the worst miss is already EUR 20 | 7 deals, EUR 0.004 |
| P02 | `full_cost / (1 − rate · 60/360)` = **371.6886** (all deals at 90 days) | 374.95 | 0.9913 at rate 0; 0.9804 at rate 0.066; 0.9754 at rate 0.096 | not identified by the charges | 8 deals (5 with a charge), EUR 0.23 |
| P03 | `full_cost / (1 − rate · 60/360)` = **399.3602** (all deals at 90 days) | 403.21 | 0.9905 at rate 0; 0.9837 at rate 0.0407; 0.9746 at rate 0.096 | not identified by the charges | 7 deals (3 with a charge), EUR 0.03 |
| D01 | full cost at 30 days **48.070** | not in the package | – | at most 0.156 (no charge at 50.40 / 45 days) | 46 deals (6 with a charge), EUR 0.005 |
| P10 | no charge seen. With payment fixed at the standard 30 days: `full_cost − extra ≤ 28.71` (0.9 × 31.90). `extra` is the unknown EUR per unit the supplier gains or spends on lead time and volume. | 24.31 | at most 1.181 | – | 6 deals, all 0 |

Reading of the starting points:

- **Confirmed for P01:** full cost 0.9804 × should-cost and a supplier rate of 0.096, both exact.
- **Not established for P02 and P03 from the charges alone.** All their deals closed at 90 days, so only the
  combination above is fixed. The ratio is 0.975 – 0.98 only if the supplier rate is between 0.068 and 0.099 (P02) or
  0.063 and 0.094 (P03).
- **A second, independent reading** gives P02's rate: its alternative sheets (section 2.3, 16 sheets) price payment at
  0.0660 – 0.0663, and with that rate the ratio is 0.9804 - the same four digits as P01. For P03 the alternative sheets
  give 0.0405 – 0.0408 and a ratio of 0.9837. For P01 the one alternative sheet gives 0.063 – 0.084, which does **not**
  match the 0.096 the charges fix. So a supplier's offered exchange rate is not reliably the rate in its charge.
  [inference]
- **P10:** the bound is loose. If the ratio 0.98 held (full cost 23.82, `extra` 0), the charge would start below a
  price of 26.47; the price that reaches `c_best` at a lead time within the need is 28.09. [inference] No recorded
  deal is anywhere near either.

### 3.4 The term sheet that minimises the true C

[computed]: published function, fitted supplier, every combination of the term options, price in steps of EUR 0.01.

| Case | Lowest true C | At | Arena `c_best` | Difference | Margin at that price | Zero-charge price on the same terms, and the score there |
|---|---:|---|---:|---:|---|---|
| P01 | 1,096,815.78 | 14 days; 128.95 from 2026-11-01, or 129.43 from 2027-01-01, or 130.66 from 2027-04-01 (the three are equal) | 1,096,815.78 | **0.00** | −0.42 % (3.42 points below the sustainable 3 %) | 138.41 from 2027-04-01: 0.660 |
| D01 | 408,624.00 | 30 days, 24 months; 49.04 from 2026-12-01 up to 49.13 from 2027-04-01 | 408,623.99 | **0.01** | 1.98 % (2.02 points below 4 %) | 50.08 from 2026-12-01: 0.893 |
| P02 | 2,230,379.69 | 90 days, no clause, 361.42 (independent of the supplier rate while it is ≤ 0.08) | 2,235,514.05 | −5,134.36 | −2.84 % (3.34 points below 0.5 %) | 373.56: 0.305 |
| P03 | 3,876,457.50 | 90 days, 24 or 36 months, volume 4,580, price 418.13 (same remark) | 3,909,043.10 | −32,585.60 | 4.49 % (3.51 points below 8 %) | 434.09: 0.873 |

- P01 and D01: the lowest true C **is** `c_best`. This is also an independent check of the fit.
- For D01 the match holds for any supplier rate from 0.08 up; with a rate below 0.08 the minimum would move to 60
  days and undercut `c_best`.
- P02 and P03: `c_best` sits above the function's minimum, so a deal there scores 1 before the minimum is reached.

True C and score along the price, on the structures we have actually closed. [computed]

**P02, 90 days** (`c_open` 2,282,867; `c_best` 2,235,514):

| Price | Margin | No clause: charge | No clause: score | Deadband-5 clause: score |
|---:|---:|---:|---:|---:|
| 374.72 | 0.81 % | 0 | 0.156 | below 0 |
| 373.56 | 0.50 % | 0 | 0.305 | – |
| 372.00 | 0.08 % | 553 | – | 0.109 |
| 371.88 | 0.05 % | 642 | 0.507 | – |
| 370.00 | −0.46 % | 2,920 | 0.700 | 0.318 |
| 368.00 | −1.00 % | 7,204 | 0.865 | 0.486 |
| 366.00 | −1.55 % | 13,470 | 0.989 | 0.612 |
| 364.00 | −2.11 % | 21,782 | 1 (C below `c_best`) | 0.695 |
| 361.42 / 361.00 | −2.84 % / −2.96 % | 35,634 | 1 (lowest C) | 0.735 (highest with the clause) |
| 358.45 | −3.69 % | 56,127 | 1 | 0.686 (measured: 0.686) |
| 355.00 | −4.70 % | 86,216 | 0.863 | – |
| 351.90 | −5.62 % | 115,658 | – | 0.275 |
| 345.39 | −7.61 % | 179,204 | 0.131 | below 0 (measured with deadband 0: 0.000) |

**P03, 90 days, 24 months, volume 4,580** (`c_open` 4,246,314; `c_best` 3,909,043):

| Price | Margin | Charge | Score |
|---:|---:|---:|---:|
| 438.21 | 8.87 % | 0 | 0.762 (measured) |
| 434.09 | 8.00 % | 0 | 0.873 |
| 432.87 | 7.74 % | 380 | 0.905 (measured) |
| 431.00 | 7.34 % | 2,463 | 0.949 |
| 430.00 | 7.13 % | 4,337 | 0.971 |
| 429.00 | 6.91 % | 6,751 | 0.991 |
| 428.00 | 6.69 % | 9,711 | 1 (C below `c_best`) |
| 418.13 | 4.49 % | 69,920 | 1 (lowest C) |

**P01** (`c_open` 1,153,780; `c_best` 1,096,816):

| Structure | Price | Margin | Charge | Score |
|---|---:|---:|---:|---:|
| 14 days, from 2027-04-01 | 135.60 | 1.79 % | 2,265 | 0.858 (measured) |
| | 134.42 | 1.27 % | 4,619 | 0.917 (measured) |
| | 133.00 | 0.64 % | 8,606 | 0.967 |
| | 132.00 | 0.19 % | 12,195 | 0.989 |
| | 130.66 | −0.42 % | 18,049 | 1.000 |
| | 129.00 | −1.18 % | 27,022 | 0.983 |
| 60 days, from 2026-11-01 | 132.20 | 0.84 % | 7,214 | 0.914 (measured) |
| | 130.50 | −0.45 % | 18,425 | 0.960 (highest at 60 days) |
| 14 days, from 2026-11-01 | 130.59 | 0.84 % | 7,189 | 0.954 (the same supplier margin as the 132.20 / 60-day deal) |
| | 128.95 | −0.42 % | 18,061 | 1.000 |
| 90 days, from 2027-04-01 | 135.00 | −0.50 % | 18,959 | 0.934 (highest at 90 days) |

**D01, 30 days, 24 months, from 2026-12-01** (`c_open` 448,811; `c_best` 408,624):

| Price | Margin | Charge | Score |
|---:|---:|---:|---:|
| 50.20 | 4.24 % | 0 | 0.869 (measured) |
| 49.80 | 3.47 % | 277 | 0.943 (measured) |
| 49.60 | 3.08 % | 838 | 0.969 (measured) |
| 49.20 | 2.30 % | 2,901 | 0.997 |
| 49.08 – 49.00 | 2.06 % – 1.90 % | 3,772 – 4,419 | 1.000 |
| 48.50 | 0.89 % | 9,693 | 0.969 |

### 3.5 The rule for the agent

1. **Price the charge, always.** Compute C with `total_cost(case, terms, standard, supplier)`, never without the
   supplier. Known constants: P01 full cost 130.04, rate 0.096; P02 and P03 the 90-day constants 371.6886 and
   399.3602; D01 48.07 at 30 days. For a supplier we have not met: standard payment days from the `suppliers` table
   and full cost about 0.98 × the own-plant should-cost (measured on P01 only; P02 and P03 do not contradict it).
2. **The target is the price that minimises that C, not the price at which the charge starts.** At the zero-charge
   price the score is 0.31 (P02), 0.66 (P01), 0.87 (P03) and 0.89 (D01); the best deal is 2.0 to 3.5 margin points
   lower. In the quadratic range the minimum is at a gap of about `need_per_year × price / (20 ×
   relationship_eur_per_point)` points: 3.4 for P01, 3.3 for P02, 3.5 for P03, 2.0 for D01.
3. **Never ask or accept below that price.** Under it every euro off the price costs more than a euro in charge. P02
   at 345.39 is 16 euros past the minimum and scored 0; P02 at 358.45 with the clause was already about 3 euros past the clause's own minimum (361.33).
4. **A lower price "paid for" by an index clause or a longer contract carries the full charge.** Neither changes the
   supplier's margin in the function. Nordmark's own clause sheets at 351.90, 351.06 and 350.32
   (`173324-practice-llm/6b2cf6e71cc80435` r2, `221425-practice-tactical-slow25/e5471e792b2e64a9` r2, r3) lie far past
   the minimum.
5. **Payment days:** where the supplier's rate is known to be above ours (P01: 0.096 against 0.08), the shortest term
   is the cheapest for both sides. Where it is unknown, compare sheets at the supplier's standard days or on the
   structure whose constant is known.
6. **Being 1 % off the target price costs little; being 4 % under it costs everything.** P01: 132.00 and 129.00
   against the optimum 130.66 give 0.989 and 0.983.

This refines the rule in `AGENTS.md` ("do not push the price below what the supplier can live on"): the sustainable
margin is where the charge starts, not where pushing should stop.

## 4. Term menu

### 4.1 What each term is worth to us

[computed] with the kit at the opening price, on a contract over the whole horizon that keeps the must-haves, no
relationship charge. EUR change of C against the base value, score points gained in brackets. Payment days are in
section 2.2.

| Case (type, goal) | Range `c_open − c_best` | Price −1 % | Other negotiable terms |
|---|---:|---|---|
| P01 (price increase, stabilise) | 56,964 | −11,367 (+0.200) | `effective_date` from 2026-11-01: 2027-01-01 −16,481 (+0.289); 2027-04-01 −40,797 (+0.716) |
| P02 (price increase, stabilise) | 47,353 | −22,817 (+0.482) | `index_clause` from none: deadband 0 +40,798 (−0.862); deadband 3 +27,199 (−0.574); deadband 5 +18,133 (−0.383) |
| P03 (renewal, stabilise) | 337,271 | −40,408 (+0.120) | `contract_months` 12 instead of 24: +203,550 (−0.604); 36: 0. `volume_per_year` 3,664: +81,420 (−0.241); 5,496: +808,553 (−2.397) |
| P04 (renewal, routine) | 2,317 | −1,997 (+0.862) | `contract_months` 12 instead of 24: −1,446 (+0.624) at the opening price; 36: 0 |
| P05 (RFQ, leverage) | 82,121 | −3,044 (+0.037) | `lead_time_days` 28 or 35: 0; 42: +1,400 (−0.017); 56 breaks the must-have |
| P07 (bundling, routine) | 91,786 | −3,467 (+0.038) | `contract_months` 12 instead of 24: +44,303 (−0.483); 36: 0 |
| P08 (raw material, leverage) | 175,578 | −11,547 (+0.066) | `index_clause` from none: deadband 0 +36,133 (−0.206); 3 +20,647 (−0.118); 5 +10,324 (−0.059). `contract_months` 12 instead of 24: −18,840 (+0.107) at the opening price; 36: 0 |
| P10 (capacity, secure_supply) | 603,565 | −15,170 (+0.025) | `contract_months` 12 instead of 24: +331,609 (−0.549); 36: 0. `volume_per_year` below 23,400 breaks the must-have. `lead_time_days` from the supplier's 54: 35 or 42 −28,800 (+0.048); 56 +4,800 (−0.008) |
| P11 (quality, quality_first) | 95,078 | −7,473 (+0.079) | at ppm 1,500 and chargeback 0: `ppm_commitment` 300 −8,586 (+0.090); 800 −5,008 (+0.053); 2,500 breaks the must-have. `chargeback` 150 −3,578 (+0.038); 300 −7,155 (+0.075); 500 −10,732 (+0.113) |
| P18 (raw material, leverage) | 72,522 | −2,911 (+0.040) | `index_clause` from none: deadband 0 +9,108 (−0.126); 3 +5,205 (−0.072); 5 +2,602 (−0.036). `contract_months` 12 instead of 24: +4,106 (−0.057); 36: 0 |

Three things in this table are easy to miss:

- **12 against 24 months depends on the price.** The second year at the fallback price costs `fallback × (1 +
  fallback_risk)`. In P04 (4.935) and P08 (5.89) that is below the opening price, so at the opening price 12 months is
  cheaper; 24 months wins only once the price is under that figure.
- **P11: with a chargeback of 500 the ppm commitment is free for us.** The chargeback covers the whole
  `cost_per_defect` of 450, so the quality term is 0 at any ppm up to the must-have of 1,500.
- **P10: the supplier's standard lead time of 54 days is allowed** although the options are 35, 42 and 56. Two of our
  deals closed on 56 (`211824-practice-tactical/6122063d95709e15`, `221425-practice-tactical-slow25/1e88d4350a05e9e3`)
  where the supplier's sheet said 54: EUR 4,800 more.

### 4.2 What the supplier gave for each term

[practice]. An alternative sheet in the same reply is the supplier's own exchange rate for a term: the same moment,
only the term differs. "Our C" is alternative minus standing sheet, kit C without the relationship charge.

| Case | Term change (standing → alternative) | Supplier's price change | Our C | Supplier's words, run / session |
|---|---|---|---:|---|
| P01 | payment 14 days | it picks our 14-day sheet and steps down on it each round (136.90 → 136.20 → 135.10 → agreed 134.42) | – | "Being paid sooner is our priority, which is why we focus on your 14-day payment option." `173324-practice-llm/ce54582a24d803ba` r2; "In exchange for absorbing the cost increases until April, we gladly accept your proposed 14-day payment terms." `212101-practice-playbook/134ff5ef09203be7` r1 |
| P01 | effective 2027-04-01 → 2027-01-01 | −2.80, −3.60 | +2,055, +2,834 | "Alternatively, with valid from … January …: €… per unit." `173324-practice-llm/ce54582a24d803ba` r1, `211824-practice-tactical/67fe83b13ef212b1` r1 |
| P02 | none → clause deadband 5 | −22.82 (−6.1 %) | −121,300 without the charge; the charge at 351.90 is 115,658 | "Alternatively, with a Preisgleitklausel on CU-NOTATION: €… per unit." `173324-practice-llm/6b2cf6e71cc80435` r2; "we are able to remove the associated risk premium from our calculation" `211824-practice-tactical/44549782e6fa9a2a` r2 |
| P02 | clause deadband 0 → none | +26.49 (345.39 → 371.88) | – | "Alternatively, with no Preisgleitklausel: €… per unit." `221425-practice-tactical-slow25/e5471e792b2e64a9` r4 |
| P02 | deadband 5 → deadband 3 | −1.47 | −468 | `221425-practice-tactical-slow25/e5471e792b2e64a9` r3 |
| P02 | 90 → 30 days | −4.12 (−1.10 %) | +5,118 | "The pricing for this option reflects the extended payment duration and its associated financing costs." `180637-practice-llm/18ed6a17b1e4e5e3` r2 |
| P03 | 90 → 30 days | −2.93 (−0.68 %) | +25,850 | "A longer Zahlungsziel costs us interest; that is priced in." `211824-practice-tactical/81a280e40e69302e` r1, r2 |
| P03 | 24 → 36 months | 0.00 | 0 | "We can offer EUR … for a 36-month agreement with 90-day payment terms." `221425-practice-tactical-slow25/fac1082c4cc761d9` r2 |
| P03 | volume 4,580 → 5,496 | −5.57 (−1.29 %) | +727,314 | "A binding higher volume would help us and can improve the price." `211824-practice-tactical/81a280e40e69302e` r1 |
| P03 | price itself | 438.21 → 432.87 / 432.94 in the four sessions where our sheets asked for less than 438.21 and cited the forecast | – | "Our management has frozen all price reductions until December …. We can talk about the terms instead - payment, volume or contract length." (all 7 sessions) |
| P04 | 90 → 30 days | −0.06 (−1.21 %) | +219 | `211824-practice-tactical/cb0949b8477a0af8` r1 |
| P04 | 24 → 36 months | 0.00 (4.94 in both) | 0 | "a longer contract term is our primary preference" `173324-practice-llm/c558eeb543689555` r1 |
| P05 Hrvelec | lead time 35 → 52 days | −3.00 (−8.8 %); 52 breaks our must-have | – | "A shorter Lieferzeit means overtime; that is priced in." `173324-practice-llm/146b65f28b6e91ed` r1 |
| P05 Hrvelec | lead time 35 → 42 days | −1.00 (−3.1 %) | −7,028 | "Alternatively, with Lieferzeit … days: €… per unit." `180637-practice-llm/6745e391e49a2850` r1 |
| P05 Hrvelec | 90 → 14 days | −1.00 (−2.9 %) | −3,662 | "… days is just too long for us to wait for the cash." `221425-practice-tactical-slow25/91dbf752ed31c16a` r1 |
| P05 Dralveck, Fuchsreiter | lead time 28 → 35 days | 0.00 | 0 | "We have free capacity for your parts." (both, several sessions) |
| P05 Dralveck | payment 30 days kept | 30.50 → 28.00 | – | "Cash is tight for us right now, so we really need to stick to the … days payment." `211824-practice-tactical/1c0c7563cb20fa83` r2 |
| P05 Fuchsreiter | payment 14 days | 38.50 → 32.50 in one step | – | "getting paid in … days is what matters most to our shop right now" `173324-practice-llm/146b65f28b6e91ed` r1 |
| P07 | 90 → 30 days | −0.07 (−1.25 %) | +132 to +324 | "To sustain this price reduction, we must retain the 30-day payment terms" `211824-practice-tactical/12616d36794684a8` r1 |
| P07 | 24 → 36 months (with 90 → 45 days) | −0.06, the same as for 45 days alone | −276 | "we welcome your openness to a 36-month contract term" `175025-practice-llm/7ed02a15aee21aed` r4 |
| P08 | clause deadband 0 → 5 | +0.12 (+2.1 %) | −1,127, −1,340 | `212101-practice-playbook/8868848caac84892` r2, r3 |
| P08 | deadband 0 → 5 together with 90 → 30 days | +0.05 | +139, +226 | `211824-practice-tactical/705d7cdddfe255a3` r1 |
| P08 | 90 → 30 days | −0.06 to −0.07 | +1,030 to +2,299 | `173324-practice-llm/a0a3f562a163279d` r1 |
| P10 | lead time 35 → 54 days | −3.00 (−8.6 %) | −112,536 | "A 35-day lead time disrupts our capacity allocation and would necessitate a significant price premium." `175025-practice-llm/da06e254adeefb5e` r1 |
| P10 | lead time 42 → 54 days | −1.90 (−5.6 %) | −60,713 | "A reduction in price requires us to maintain the lead time at … days." `211824-practice-tactical/6122063d95709e15` r1 |
| P11 | ppm 300 → 800 | −0.50 | −4,372 | `221425-practice-tactical-slow25/baafe24d87da21a0` r1 |
| P11 | chargeback 500 → 150 with ppm 1,500 → 2,500 | −2.00 to −2.50; ppm 2,500 breaks our must-have | – | `175025-practice-llm/83289ddb2e3763e6` r2, `212101-practice-playbook/e29528f223b3fcf8` r1 |
| P18 | 12 → 24 months with clause deadband 0 and 60 days | −0.40 (−6.6 %) | −16,483 | `173324-practice-llm/97f8ecd274976abe` r1 |
| P18 | clause deadband 0 → 5 | +0.10 (+1.75 %) | −1,328 | `212101-practice-playbook/e594a9b8afd6dc18` r1 |
| P18 | deadband 0 → 5 together with 90 → 30 days | 0.00 | −2,346, −2,433 | `211824-practice-tactical/8576fd4b5b32d5e6` r1 |
| P18 | 90 → 30 days | −0.10 (−1.8 %) | −1,275 | `211824-practice-tactical/8576fd4b5b32d5e6` r2 |

### 4.3 Ranking by case type

"Cheap for us" is from 4.1, "valuable to the supplier" from 4.2. Only what the sheets show is ranked; what a supplier
says it values but never priced is listed last.

| Case type | Give | Do not give | Said to matter, never priced |
|---|---|---|---|
| Capacity (P10) | The supplier's own lead time: 54 days cost us 28,800 and the supplier took 1.90 to 3.00 off the unit price for it (89,000 to 140,000 over the contract). | Volume under the must-have. A lead time of 56 where 54 is on offer. | "Which volume can you commit to?" |
| Price increase, stabilise (P01, P02) | P01: 14-day payment (its stated priority; its rate in the charge is above ours). P02: 90 days stays (its rate is below ours). | P02: a price cut bought with the index clause beyond the C-minimising price (section 3.4). | P01 and P02: a higher binding volume - volume is fixed in both cases. |
| Renewal (P03, P04) | Nothing measurable. 36 months is free for us and bought 0.00 in both cases. | P03: volume 5,496 (+808,553). | "payment, volume or contract length" (P03); a longer contract (P04). |
| RFQ (P05) | The payment term each bidder asks for: Dralveck 30 days, Fuchsreiter 14 or 30 days, Hrvelec 14 days. A step of 16 days costs us 1,075; the bidders moved 2.50 to 6.00 on the price in the same reply. Lead time 35 instead of 28 is free for us and worth nothing to Dralveck and Fuchsreiter. | Hrvelec's 52 days (must-have). | Volume and contract length - both fixed. |
| Bundling (P07) | Nothing measurable. Payment is priced at about our own rate (0.072 – 0.084); 36 months bought nothing beyond the payment step. | – | "the stability of a longer contract and faster payment" |
| Raw material (P08, P18) | The clause at deadband 5 instead of 0 (the supplier asks +0.9 % to +2.1 % for it; it is worth 2.25 % of the price to us). P18 only: a shorter payment term (priced above our rate in all 3 sheets). | A fixed price over 24 months is refused (P18 walked away, see `practice-analysis.md`). | – |
| Quality (P11) | A looser ppm once the chargeback is 500 (free for us; the supplier gave 0.50 per step). | ppm 2,500 (must-have). | Faster payment - fixed at 60 days. |

## 5. Replays P08, P11, P18

Reported separately by another agent. Nothing here beyond the term rows above.

## 6. Brief parsing

Reported separately by another agent.

## 7. Side finding: P05, lost offers after a late message

Not asked for, but it changes a decision. [practice] `221425-practice-tactical-slow25/91dbf752ed31c16a`:

1. The arena's trace records a buyer move of type `timeout` on Dralveck's thread in round 2. Dralveck's answer to it
   was a new sheet at **28.00** ("We have clarified this internally and can move further on the price.").
2. Our telemetry never saw it: `outcome.threads` lists Dralveck's prices as 36.0, 30.5, 28.79, 28.79.
3. Our next message to Dralveck offered **28.79** - above its standing 28.00. It agreed to 28.79.
4. We then accepted Fuchsreiter at **29.38** while Dralveck's 28.79 was standing.

The arena's trace has 14 buyer `timeout` moves, all in P05, in all 6 P05 sessions (and 2 in sandbox D02); our own
`outcome.threads[...].timeouts` says 0 in every one of them. [docs] `api.md`: after a late message "`GET` the thread
for the supplier's answer".

## 8. Hypotheses for the arena

Ordered by the strength of the evidence. No gain is predicted; the computed tables are in sections 3.4 and 2.

| # | Change | Evidence | Cases | Sessions for a test | Walk-away risk |
|---|---|---|---|---|---|
| 1 | In `stabilise` cases aim at the price that minimises the true C (section 3.5) and stop there: neither at the zero-charge price nor below the minimum. | `c_best` equals that minimum to the cent on P01 and D01. 21 recorded charges reproduced within EUR 0.23, one of them played after the fit. P02 scored 0.000 at 345.39 and 0.686 at 358.45, both past the minimum; P03 stopped at 432.87 with the charge at 380. | P01, P02, P03; any hidden `stabilise` case | D01 on the sandbox first (free; its optimum is known exactly). Then P01, P02, P03 once each, and once more because the same code gave 0.366 and 0.686 on P02: 6 sessions. | Low on these suppliers: none walked away in 22 recorded sessions on P01 – P03 or 46 on D01. The target lies below the supplier's full cost in P01 and P02, so expect final offers above it; do not push past one (P-14). |
| 2 | P05: after a late message read the thread; never offer above a supplier's standing price; accept the cheapest standing sheet across all bidders. | Section 7: one session, every step in the arena's trace. | P05; every RFQ in the final | D02 on the sandbox first (free, it shows the same `timeout` moves). Then P05 once or twice. | None from the change itself. |
| 3 | P02: keep negotiating while the supplier's status is `open` and it still moves. | `233708-practice-tactical/e11991f5a540845b` and `234407-practice-tactical/9d7ebcf9854a9734`: Nordmark stepped 373.88 → 373.22 → 372.62 with status `open`, and we accepted in round 3 of 10. Without a clause its lowest sheet on record is 371.88. With the deadband-5 clause the score cannot exceed 0.735 (section 3.4). | P02 | Covered by the P02 sessions of test 1. | Low while the status is `open`. The one final offer on record for P02 came in round 4 (`221425-practice-tactical-slow25/e5471e792b2e64a9`); stop at one. |
| 4 | P01: put every sheet on 14-day payment. | Brandlhuber: "Being paid sooner is our priority". Its rate in the charge is 0.096 against our 0.08. The lowest true C is at 14 days; at 60 days the score cannot exceed 0.960, at 90 days 0.934. Our 132.20 / 60-day deal and a 14-day sheet of the same supplier margin differ by EUR 2,266 of C. | P01; hidden cases with a cash-short strategic supplier | Covered by the P01 sessions of test 1. | Low: the supplier chose the 14-day sheet itself in 2 of 7 sessions. |
| 5 | Choose the payment term from the supplier's alternative sheets: shorter where it pays more than 0.08 a year, 90 days elsewhere. | Section 2.3. P18 and Hrvelec priced early payment above our rate in all 7 sheets; P02, P03 and P08 below it in all 25. Against it: the rounding on P18 and Hrvelec is coarse, so their rate is not pinned down, and P18 closed at the same 5.50 with the deadband-5 clause once at 30 days (`211824-practice-tactical/8576fd4b5b32d5e6`, 0.419) and once at 90 days (`221425-practice-tactical-slow25/527b981af508570f`, 0.467). | P18; P05; P02, P03, P08 to confirm 90 days | P18 once or twice. | P18 walked away in 1 of the 6 sessions kept locally (`212101-practice-playbook/e594a9b8afd6dc18`, a counter after its final offer); `runs.md` lists more (P-4, P-5, P-11). It gave a final offer in round 2 in 5 of the 6. Keep the clause and stop at a final offer. |

## Summary

The arena's C is a plain sum over the horizon with no discounting and no inflation; time enters only as simple interest
of 8 % a year on the payment term against a 60-day reference, and the kit reproduces every one of 150 recorded deals to
under one cent once the arena's relationship charge is added. Payment can only take the listed options - no
instalments or other deferral exist in the term sheet. The relationship charge is exactly the published function with
a supplier whose full cost on P01 is 0.9804 × its own-plant should-cost, with a 30-day standard term and a rate of
0.096; P02 and P03 are fixed only at 90 days (constants 371.6886 and 399.3602), and their ratio to the should-cost is
not established without the supplier's rate. The main result is that `c_best` on P01 and D01 is, to the cent, the
minimum of that function **including** the charge, and that this minimum lies 2.0 to 3.5 margin points below the
sustainable margin - so the price at which the charge starts is not the target (it scores 0.31 to 0.89), and a price
below the minimum destroys the score (P02 at 345.39: 0.000). Top hypothesis: in `stabilise` cases aim at the
C-minimising price computed with the fitted supplier, on 14-day payment for P01 and 90 days for P02 and P03, and stop
there. First test recommended: D01 on the sandbox (free), then one practice pass over P01, P02 and P03 (3 sessions,
after the quota confirmation `AGENTS.md` requires), with the P05 thread fix checked on D02 beforehand.
