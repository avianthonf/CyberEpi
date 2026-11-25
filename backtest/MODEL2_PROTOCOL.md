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
