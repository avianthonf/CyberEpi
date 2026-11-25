# Second model: protocol (committed before any result)

## Why a second model

Model 1 (`CyberEpi-EAKF`, mechanistic SEIHDR + ensemble Kalman filter) runs
low while epidemics decline: its post-peak fall is too steep (see
`backtest/results/calibration.json`). FluSight allows a team two models if they
differ in method, not only in parameters. Model 2 is a different method: a
statistical model that learns how admissions evolve from the data itself.

## Model (`CyberEpi-GBQR`)

Gradient-boosted quantile regression (LightGBM), pooled across all locations.

- **Target**, per horizon h = 0..3: change in log1p(admissions per 100k)
  from the last observed week (R−7) to the target week (R+7h).
- **Features** at the last observed week: log rate, its 1-, 2-, 3- and 4-week
  changes, ED flu-visit fraction (log) and its 1- and 2-week changes, week of
  season (sin/cos).
- **One model per (horizon, quantile)**: 4 × 23. Quantiles are sorted after
  prediction so they never cross.
- **Training at origin R**: every (location, week) example whose target week
  is ≤ R−7, taken from the admissions version published by R (as-of data, the
  same rule as model 1's honest backtest). ED values are final (no published
  versions before Nov 2025), the same limitation as model 1.
- Refitted at every origin.

## Evaluation

- **Development seasons:** 2023-24 and 2024-25. Features and the small
  hyperparameter grid below may be changed while looking at these only.
  Grid: num_leaves ∈ {7, 15}, n_estimators ∈ {150, 300}; learning rate 0.05,
  min_data_in_leaf 50.
- **Holdout season:** 2025-26, scored **once**, after the code and settings
  are frozen in a commit named in the result. No changes after seeing it.
- Scores: relWIS vs FluSight-baseline, FluSight-ensemble and model 1, horizons
  0–3, same rows.

## Decision rule

- Holdout relWIS vs baseline < 1 → submit as a second model from the next
  week, alongside model 1.
- Which model is designated as primary is decided by **live 2026-27 scores**,
  not by the backtest.
- Holdout relWIS vs baseline ≥ 1 → not submitted; result recorded anyway.

## Result (2026-11-25)

Frozen at commit `9de52b8`; holdout 2025-26 scored once.

| | vs FluSight-baseline | vs FluSight-ensemble | vs model 1 | 90% coverage |
|---|---|---|---|---|
| Pre-registered (ED final) | 0.385 | 0.584 | 0.502 | 0.80 |
| Robustness: ED as published | 0.410 | 0.622 | — | 0.80 |

Development seasons (as-of data): 0.741 and 0.624 vs baseline; 0.927 and 0.960
vs model 1.

**Decision (rule above):** beats the baseline on the holdout → submitted as a
second model (`CyberEpi-GBQR`) from the reference date after 2026-11-28, not
designated for the CDC ensemble until it has a live record.

**Why the holdout looks so good, and why it should not be taken at face value.**
Scored the same way, the best of 45 real 2025-26 FluSight teams reached 0.86 vs
the ensemble; 0.58 would beat all of them, so it was checked for leakage:

- As-published admissions really were incomplete (first reports ~89% of
  final in 2025-26), so the model saw realistic data.
- Using as-published ED data changes little (0.584 → 0.622).
- The gain is concentrated in Nov–Jan (relWIS vs ensemble 0.46–0.57; from
  February 0.87–1.24), mostly at the national peak: from data ending
  27 Dec 2025 (33.5k and rising 67%/week, ED share also still rising) the
  model forecast a peak near 44k and 31k two weeks later (truth 42.5k,
  29.9k); the ensemble forecast 41k and rising.
- The data available then showed no turn, so the call came from a pattern
  learned from earlier seasons: at admission rates this high, epidemics have
  peaked soon after. That is legitimate (learned only from the past) but
  fragile: a season peaking higher than any before would be called too early.

No leak was found. The honest summary: one well-timed peak call in an unusual
season drives most of the advantage. The live season decides.

Known weakness (development seasons): runs low while epidemics are rising
(truth above the median up to 71% at 3 weeks), the opposite of model 1, which
runs low while they decline.
