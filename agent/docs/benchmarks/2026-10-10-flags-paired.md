# Tactical flags: paired simulator test (2026-10-10, written before the run)

Setup: `data/analysis/scripts/paired_bench.py`, 12 cases × 20 seeds, `normal` and `hard` (`--strangers --jitter`, fitted
opponents). Seed i is the same supplier draw for every strategy (seed fix `sim.opened.clear()` in `sim/arena.py`;
earlier bench comparisons without it are not fair). Base: `tactical` (practice 0.675, run 20261010-220320).

Decision rule (fixed beforehand): ADOPT is recommended only if, in `hard`, the lower bound of the 95 % bootstrap interval
of the paired mean difference is above −0.01 and the mean is above 0, and the flag has no more total failures (score
< 0.2) than the base. p-values: Wilcoxon signed-rank (normal approximation), Holm-corrected over the 8 variants.
Otherwise REJECT (mean < 0 with interval below 0) or UNCLEAR. The final decision is David's.

| flag | hypothesis |
|---|---|
| strict_final | no change in most cases; small gain where a final offer comes with a lower text price |
| belief_cap | fewer early accepts after two equal steps (P01 type); small gain |
| probe_leader | fewer pointless probes in RFQs; tiny gain in RFQ cases, none elsewhere |
| anchor_cap25 | shallower first ask in high-lever cases; risk of a small loss |
| dedupe_series | no measurable effect (the simulator does not grade duplicates like the arena) |
| big_steps | faster closing, more deals under hard opponents; may lose price with fitted ones |
| equal_c | no effect in the simulator (P02's floor case does not occur there); the arena test is P02 |
| all | the sum of the above, interactions unknown |

## Results (20 seeds; `patient` added later with 10 seeds)

Paired mean difference against `tactical`, 95 % bootstrap interval, Holm-corrected Wilcoxon p, failures (< 0.2):

| flag | normal | hard | fails hard (base 15) | rule |
|---|---|---|---|---|
| strict_final | −0.001 [−0.006, +0.005] | −0.002 [−0.006, +0.002] | 15 | UNCLEAR |
| belief_cap | +0.002 [−0.002, +0.006] | +0.000 [−0.001, +0.003] | 15 | ADOPT (≈ 0) |
| probe_leader | −0.001 [−0.005, +0.002] | −0.001 [−0.004, +0.002] | 15 | UNCLEAR |
| anchor_cap25 | −0.001 [−0.005, +0.004] | −0.000 [−0.003, +0.002] | 15 | UNCLEAR |
| dedupe_series | −0.003 [−0.006, +0.001] | −0.003 [−0.008, +0.001] | 15 | UNCLEAR |
| big_steps | −0.004 [−0.012, +0.003] | −0.001 [−0.006, +0.003] | 16 | UNCLEAR |
| equal_c | −0.001 [−0.005, +0.004] | −0.001 [−0.005, +0.002] | 15 | UNCLEAR |
| all | −0.007 [−0.015, +0.000] | −0.004 [−0.011, +0.002] | 16 | UNCLEAR |
| patient (10 seeds) | +0.006 [+0.001, +0.015] | +0.006 [+0.001, +0.012], p 0.005 | 7 (base 7) | ADOPT |

No flag moves the simulator by more than 0.01 on average.

**The simulator is not credible for these decisions.** Practice (deterministic, one session per case) against the
simulator for `tactical+all` - `tactical` on the same 9 cases: Spearman −0.55 (normal), −0.22 (hard). P01: simulator
−0.03/−0.05, practice +0.076; P18: simulator 0.00, practice −0.066; `equal_c` on P02: simulator 0.00, practice +0.564.
The simulator's suppliers do not react to duplicate arguments (P01) and never meet P02's price-floor case.

Practice (each variant once, against `tactical` run 20261010-220320): `equal_c` P02 0.167 → 0.731 (adopted by David,
760194c); `tactical+all` P01 +0.076 (first reply differs after other arguments: likely `dedupe_series`), P18 −0.066 and
P07 −0.007 (round-2 ask capped at 4 % of C_open: `big_steps`), P05 −0.057 (timing), the other five unchanged.

## Practice decisions (10 Oct, evening; each variant once per case, deterministic bots)

| Variant | Change against `tactical` | Decision |
|---|---|---|
| `equal_c` | P02 0.167 → 0.731 | adopted (760194c) |
| `patient` | P01 0.831 → 0.946, P18 0.618 → 0.685, P10 0.663 → 0.601, rest equal | adopted: our floor estimate no longer ends an open thread |
| `floor_ask` (+patient) | P07 +0.03, P02 −0.14, P11 −0.05 | dropped |
| `wide_band` (+patient) | P08 0.626 → 0.592 (the supplier prices the deadband itself) | dropped |
| `dedupe_series` (+patient) | P01 0.946 → 0.911 | dropped |
| `all_claims` (+patient) | P01 −0.078, P08 −0.044, P05 −0.021: the arena reads at most 3 arguments per message (api.md), later rounds ran dry | dropped |
| `anchor_rel` (+patient) | P10 0.601 → 0.647, but its deeper anchor triggered the final in round 1 at a higher price; the gain came from taking the alternative | dropped (unclear) |
| `tactical+all` | P01 +0.076, P18 −0.066, P05 −0.057, P07 −0.007 | dropped |

Next candidates (agent/data/analysis/konzept-analyse.md, zuarbeit-t1t2-t3t4.md, antwort-fehler.md): three fresh
verified arguments every round and new sources, the supplier's alternative as structure information (P10), an answer
to "Which figures …?", the volume answer from the case's need.
