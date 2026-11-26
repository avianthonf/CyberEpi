# A2c — Admission delay in the filter observation operator (consistent model 1), dev seasons

Status: **pre-registered 2026-11-26T03:58Z** (written before any A2c code or run). Results are appended below "## Results".
Source: A2b result (`A2b_delay_depletion.md`): the forward-only Erlang-2 delay (mean 6 d) passed the decline-bias rule on both folds, but the filter's admissions observation was still undelayed and pre-origin incidence was back-filled as a constant. A2c puts the same kernel into the filter so that filter and forecast share one observation model.
Dev seasons only: 2023-24 and 2024-25, leave-one-season-out. 2025-26 is not used.
**ED caveat:** dev-season ED values are final-only. The arms do not change the ED observation (`ili="final"` in every arm). Any ED-dependent claim is labelled ED final-only.

## Model change under test

- **Consistent observation operator.** The filter carries a per-member buffer `H` of the last 37 daily incidences `inc_t = hir·σ·E_t` (the same flow as the W accumulator). Weekly admissions are predicted as `Σ_{t in week} Σ_{l=0..30} k(l)·inc_{t−l}` with the same normalized Erlang-2 kernel `k` (mean 6 d). The EnSRF admissions update (and the ILI update) is applied to the augmented state `[X, H]`, so the observation and its cross-covariances use filtered incidence history. Initial `H` = 0 (the filter has no pre-start history; warm-up covers the buffer).
- **Consistent forward emission.** The forward emission uses the filter's actual last 30 days of incidence (`H`) as the pre-origin pipeline, instead of the constant back-fill of A2b.
- Opt-in option `delay_consistent` (default False) with `delay_mean_days`. Default byte-identical to U.

## Arms

- **U (unmodified):** `backtest/model_config.json`, `ili="final"`. Must be byte-identical to `backtest/results/dev_members/` EAKF files on all 57 dev reference dates.
- **DELAY:** A2b arm as-is (forward-only delay, constant back-fill, undelayed filter observation). Reference.
- **CONSISTENT-6 (primary):** consistent observation operator and forward emission, Erlang-2 mean 6 d (the A2b setting, pre-specified; no tuning).
- **CONSISTENT-4, CONSISTENT-8 (sensitivity):** same, mean 4 d and 8 d. Reported; not used to choose or to change the verdict.

## Pass criterion for CONSISTENT-6 (fixed before running)

Phase = as-of 3-week growth rule (`dev_members._phase`, threshold 0.05 log/week). Bias = median of `log((median_forecast+1)/(observed+1))` per phase and horizon. Declining headline horizon h=3.

On **each fold separately** all four must hold:
1. **Declining cut by ≥ one third:** `|bias(declining, h=3)| ≤ (2/3)·|bias_U(declining, h=3)|`, and the sign does not flip.
2. **Peak cost ≤ 0.02:** `|bias(peak, h)| ≤ |bias_U(peak, h)| + 0.02` for every h = 0..3.
3. **relWIS vs U ≤ 1.00 at every horizon:** mean WIS ratio vs U ≤ 1.00 for each h = 0..3.
4. **cov90 not lower than U by more than 0.03:** mean cov90 over h = 0..3 satisfies `cov90_arm ≥ cov90_U − 0.03`. (Per-horizon cov90 is also reported.)

**Verdict:** CONSISTENT-6 passes only if all four hold on both folds. A pass makes it a **diagnostic candidate, not a change** to model 1. Any failure means no change. DELAY, CONSISTENT-4 and CONSISTENT-8 are reported with the same checks, but they do not affect the verdict.

Secondary, reported but not part of the decision: relWIS vs U and vs FluSight-baseline per horizon; cov50/cov90 per horizon; declining and rising bias at h=0..3; runtime. Stop rule: none beyond the pass criterion.

## Results

Run: `backtest/a2c_delay.py --ncpus 8`, 5 arms in 316 s (348 s wall). Outputs `backtest/results/a2c/` (`summary.json`, `phase_bias_<season>.csv`). Dev seasons only, ED final-only.

Identity: U reproduces `dev_members` EAKF rows on 57/57 reference dates. Default byte-identity holds. Ruff clean on `backtest`; `test_scoring_accounting.py` 4 passed.

**Verdict: CONSISTENT-6 FAIL** (the pre-registered rule is not met on either fold).

Per-fold checks for CONS6 (decl h3 cut / peak ≤ U+0.02 / relWIS ≤ 1 each h / cov90 mean ≥ U−0.03):
- 2023-24: cut 0.41 (ok, sign kept) / peak fails (h0 +0.072 vs U −0.021; h3 −0.039 ok) / relWIS fails (h1 1.14, h2 1.22, h3 1.33) / cov90 mean 0.81 vs U 0.86 (fails). Fold fails.
- 2024-25: cut 0.74 (fails; needs ≤ 0.41) / peak ok / relWIS ok (0.83–0.92) / cov90 mean 0.72 vs U 0.735 (diff −0.015, ok). Fold fails on the cut.

relWIS vs U per h (CONS6): 2023-24 0.998, 1.144, 1.218, 1.325; 2024-25 0.829, 0.897, 0.916, 0.912.
relWIS vs FluSight-baseline (CONS6): 2023-24 0.737, 0.824, 0.985, 1.143; 2024-25 0.564, 0.592, 0.610, 0.568. U vs base: 0.738/0.720/0.809/0.863 and 0.680/0.660/0.666/0.622.
cov90 per h (CONS6): 2023-24 0.75/0.79/0.83/0.87 (U 0.82/0.85/0.88/0.88); 2024-25 0.67/0.71/0.74/0.76 (U 0.70/0.73/0.75/0.76).

Phase bias h3 (U → CONS6): declining 2023-24 −0.368 → −0.217; 2024-25 −0.616 → −0.457. Peak 2023-24 −0.218 → −0.039; 2024-25 −0.669 → −0.416. Rising 2023-24 −0.092 → +0.086; 2024-25 −0.463 → −0.260. The consistent operator cuts the declining and peak under-forecast on both folds but overshoots the rising phase in 2023-24.

Sensitivity (reported, no effect on verdict): CONS4 fails both folds (2023-24 declining cut fails; 2024-25 cut 0.84 fails). CONS8 fails both folds (2023-24 peak/relWIS fail; 2024-25 relWIS ok but cov90 fails). DELAY (A2b as-is) still passes the decline rules on both folds but fails the cov90 check on both.

Conclusion: no change to model 1. The consistent observation operator is not a diagnostic candidate under the pre-registered rules. A2b's DELAY remains a finding, with the cov90 and rising-bias caveats.

Runtime: 316 s for 5 arms (8 CPUs). The results are dev seasons only; 2025-26 not used.
