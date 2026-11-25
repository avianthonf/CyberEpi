# CyberEpi-EAKF: Methods

Mechanistic influenza forecaster backtested against CDC FluSight targets.
Implements the model described by `backtest/eakf.py` + `backtest/seir_fast.py`;
evaluation by `backtest/run_flusight.py` against `backtest/out/flu/`.

## 1. Process model

Age-homogeneous SEIR with an admission accumulator and evolving
parameters, one independent unit per jurisdiction. State (8 dims):

    x = (S, E, I, R, log β(t), log HIR(t), W(t), log c(t))

- Latent period 1/σ = 1.2 d; infectious period 1/γ = 3.8 d; population
  N = 10⁶ per unit (prevalence fractions are what enter the likelihood,
  so absolute N does not affect scores).
- dW/dt = HIR · σE — weekly incident hospital admissions; W resets at
  week rollover, after observation assimilation.
- β (transmission), HIR (hospitalization-to-infection ratio) and c
  (ILI observation multiplier) follow geometric random walks:
  daily innovations N(0, sd_β ²) on log β etc. This makes the model an
  SEIR with time-varying transmission rather than a fixed-parameter ODE.

Integration: one vectorized `solve_ivp` over the stacked ensemble
((M·8,) RHS), adaptive RK45.

## 2. Observation model

Two weekly streams, assimilated sequentially:

1. **Hospital admissions** (NHSN, target data): observed weekly increment
   of W. Noise R_adm = max(rel·ŷ, floor)², rel = 0.30, floor = 4 counts.
2. **ED ILI fraction** (NSSP): ili_frac = c · I/N. Nonlinear in the
   state; enters via ensemble cross-covariances (no linearization).
   c itself is jointly estimated in log space (LC state).

EAKF-final run configuration (`backtest/run_flusight.py` CLI defaults):
M = 300 members; sd_β = 0.05, sd_HIR = 0.005, sd_lc = 0.01 daily random-walk
sds; admissions observation noise rel = 0.15 (floor 4 counts); ILI noise
rel = 0.10 (floor 5e-4); inflation 1.03; s_obs = 0.10;
sd_β,fwd = 0.05.

## 3. Inference

Ensemble square-root filter (EnSRF, Whitaker & Hamill 2002),
M = 300 members, deterministic square-root update per scalar
observation; multiplicative anomaly inflation (1.03) pre-update. Initial
ensemble covers wide priors on log β, log HIR, log c (see
`EAKF._init_ensemble`). Forecasts roll the posterior ensemble forward with
per-day log-β drift (sd_beta_fwd = 0.05) and s_obs quantile jitter —
the forward dispersion was tuned on the calibration sweep, not on
accuracy.

## 4. Calibration protocol

Grid over (s_obs, sd_beta, sd_beta_fwd, sd_hir) plus ILI on/off,
scored per season and pooled on relWIS and per-horizon coverage
(`backtest/TUNE` artifacts: `backtest/out/flu/sweep.csv`). EAKF-final
(sd_β = 0.05, sd_HIR = 0.005, s_obs = 0.10, sd_β,fwd = 0.05,
inflation 1.03) trades small raw-WIS differences for near-nominal
coverage (cov50 0.44–0.53 vs 0.5, cov90 0.85–0.91 vs 0.9).

## 5. Evaluation

- Origins: every Saturday of each FluSight season (2023-24, 2024-25,
  2025-26), 53 locations (US national + states/territories).
- Data: weekly incident admissions and NSSP ED ILI fraction, snapped to
  week R−7 at origin R (no look-ahead: the filter state at origin never
  sees data past R−7).
- Scoring: per-horizon relWIS vs the hub's persistence baseline
  (`wis_baseline_mean` in the scoring tables); horizons h = 0..3
  (FluSight convention — h=-1 nowcast rows are emitted for hub submissions
  but excluded from evaluation). **Scientific reporting**: relWIS and all
  summary statistics computed over finite paired (wis, wis_base) comparison
  rows only; non-finite scores excluded before ratio computation. Excluded
  counts reported in summary JSON (`n_comparison_rows`, `n_finite_paired`,
  `n_excluded_nonfinite`).
- Determinism: cross-run seeds derive from sha256 of (run seed, location);
  per-origin emission RNGs are derived from the run seed, so reruns are
  bitwise stable.

Sections 4–5 describe the original August 2026 evaluation (final data,
tuning on the reported seasons; pooled relWIS 0.714, archived in
`docs/archive/BACKTEST_RESULTS-2026-08.md`).

The current evaluation (`run_vintage.py`, `tune_vintage.py`) differs in three
ways: each origin sees only the admissions version published by then (hub
`time-series.csv` `as_of`); settings are tuned on 2023-24 only by a rule
committed before scoring; and scores are reported against FluSight-ensemble
as well as the baseline. Results: `BACKTEST_RESULTS.md` (pooled relWIS 0.697
vs baseline, 1.046 vs ensemble, out of sample on 2024-25 and 2025-26).

## 6. Limitations

- Single serotype-agnostic season dynamics; no age structure, spatial
  coupling, or variant effects.
- HIR absorbs reporting artifacts (testing policy, bed capacity) — jumps
  at reporting-rule changes are absorbed as state, not modeled.
- Scores are retrospective, computed by the in-repo harness. Submission
  artifacts for hub verification: `backtest/package_submission.py` /
  `validate_submission.py` (hub file format, metadata, output-type-ids).
