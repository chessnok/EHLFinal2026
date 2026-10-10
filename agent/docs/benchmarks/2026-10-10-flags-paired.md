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

Results: below, after the run.
