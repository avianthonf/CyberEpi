# A4 — NegBin count-aware intervals on dev-season forecasts

Status: **pre-registered 2026-11-26T03:51Z**, before the driver `backtest/a4_intervals.py` was run. Results are appended below "## Results".
Source: SYNTHESIS §6 item 4 (A4); report 11 top-1 (small-count dispersion); report 07.
Dev seasons only: 2023-24 and 2024-25, leave-one-season-out (LOSO). 2025-26 is not used.
Truth: the hub oracle (final values). ED is not used here.

## Question

Forecast intervals for small weekly counts are miscalibrated under a shared Gaussian/lognormal layer (report 11). This experiment tests whether replacing each interval with a negative-binomial predictive distribution, with dispersion pooled across locations and shrunk toward the pool, improves coverage on small-count locations without costing overall WIS.

## Scope

- Post-processing only. `eakf.py`, `forecast.py`, `run_flusight.py`, `run_vintage.py` and the `dev_members` files are read, never changed.
- Models: CyberEpi-EAKF, CyberEpi-GBQR, CyberEpi-MIX_LP (dev_members, unmodified).
- Arms: `U` (unmodified quantiles) and `NB` (recalibrated quantiles). The U arm is read from the dev_members files, not re-run.

## Method (fixed before running)

1. **Centre.** For each (model, reference date, location, horizon) the centre is the unmodified median from dev_members. The NB mean is `mu = max(median, 0.5)`. The median is kept as the centre.
2. **Distribution.** NB with mean `mu` and dispersion `phi`: variance `mu + phi·mu²`. The 23 FluSight quantile levels are the NB quantiles (scipy `nbinom`), made non-decreasing.
3. **Dispersion, LOSO.** For each fold, `phi` is estimated only on the other dev season, by grid-search maximum likelihood on the log grid `phi ∈ [1e-3, 10]` (201 points). Rows: all training-season origins, horizons 0–3, with the observed final value as the outcome.
   - Pooled `phi_pool`: fit on all locations.
   - Per-location `phi_i`: MLE on that location's training rows.
   - Shrunk: `phi_i* = (n_i·phi_i + k·phi_pool)/(n_i + k)` with **k = 50** (training rows).
   - Fitted separately for each of the three models.
4. **Strata.** Small-count locations are those whose median observed value in the test season is < 10 per week. The median is computed from the final truth, for evaluation only.

## Metrics

- cov50 and cov90 (the 25–75 and 5–95 quantile intervals), overall and by stratum, per model and fold.
- relWIS of NB vs U, and of each arm vs FluSight-baseline, per horizon (h=0..3) and overall. WIS via `run_flusight.summarize`.

## Pass criterion (fixed before running)

An arm passes **for a model** only if, on **both folds**:
1. Small-count locations: `|cov50_NB − 0.50| < |cov50_U − 0.50|` **and** `|cov90_NB − 0.90| < |cov90_U − 0.90|`.
2. Overall relWIS vs U ≤ 1.00 (all horizons pooled).

Per-horizon relWIS and large-count coverage are reported, not part of the decision.

## Risks and controls

- phi is estimated on the training season only; the test season is never used to fit it (LOSO).
- Small `mu` (near 0) makes the NB close to a point mass; the 0.5 floor is applied to all arms identically.
- Non-integer hub values are compared with continuous NB quantiles; this is noted in the results if it matters.

## Results

Run 2026-11-26T03:52Z–03:53Z, after pre-registration. Driver `backtest/a4_intervals.py`; output `backtest/results/a4/summary.json`. The first run was discarded before any decision was made, for two reasons. First, NaN oracle values were cast to int inside the φ fit. Second, the small-count window was taken per model, and EAKF's horizon −1 rows widened it, so the models got different small-location sets. The fixed run drops NaN rows before fitting and uses one shared small-location set per fold. The method and pass rule did not change.

**U arm** = the dev_members files themselves. They are read only and were not changed (mtimes predate the run). Scoring tests pass (4/4). `ruff check backtest` passes. Runtime: 44 s for everything.

**Small-count stratum (pre-registered: median observed < 10/wk over the fold's scored window):** 2023-24 has one location (02, 120 rows). 2024-25 has **none**, because the lowest median is 9.0 under the EAKF window and 10.0 under the union window. The coverage clause therefore cannot be met on 2024-25. As a non-decisional extra, the table also reports coverage on rows with observed < 10 (`obs<10`).

### Pass decision

| Model | Fold | φ_pool (train) | relWIS NB/U | ≤ 1.00? | small cov50 U→NB | small cov90 U→NB | Coverage toward nominal? | Fold |
|---|---|---|---|---|---|---|---|---|
| EAKF | 2023-24 | 3.16 | 1.322 | no | 0.442→0.667 | 0.800→0.942 | no (cov50 overshoots) | FAIL |
| EAKF | 2024-25 | 0.437 | 1.047 | no | n/a (no small locs) | n/a | not evaluable | FAIL |
| GBQR | 2023-24 | 0.724 | 1.154 | no | 0.358→0.675 | 0.667→0.933 | no (cov50 overshoots) | FAIL |
| GBQR | 2024-25 | 0.331 | 1.052 | no | n/a | n/a | not evaluable | FAIL |
| MIX_LP | 2023-24 | 0.832 | 1.168 | no | 0.542→0.742 | 0.875→0.917 | no | FAIL |
| MIX_LP | 2024-25 | 0.263 | 1.091 | no | n/a | n/a | not evaluable | FAIL |

**Verdict: FAIL for all three models on both folds.** Overall WIS is worse than unmodified in every model-fold (+5% to +32%). That fails the WIS clause alone, whatever the stratum definition. No change is adopted.

### relWIS per horizon (h0, h1, h2, h3)

| Model | Fold | NB vs U | U vs baseline | NB vs baseline |
|---|---|---|---|---|
| EAKF | 2023-24 | 2.222, 1.529, 1.180, 1.045 | 0.738, 0.720, 0.809, 0.863 | 1.640, 1.101, 0.954, 0.902 |
| EAKF | 2024-25 | 1.255, 1.042, 1.003, 1.012 | 0.680, 0.660, 0.666, 0.622 | 0.854, 0.688, 0.668, 0.629 |
| GBQR | 2023-24 | 1.893, 1.255, 1.075, 0.988 | 0.561, 0.642, 0.761, 0.850 | 1.062, 0.806, 0.818, 0.840 |
| GBQR | 2024-25 | 1.252, 1.014, 1.000, 1.044 | 0.659, 0.656, 0.625, 0.590 | 0.825, 0.665, 0.625, 0.617 |
| MIX_LP | 2023-24 | 1.831, 1.281, 1.064, 0.991 | 0.601, 0.615, 0.683, 0.724 | 1.101, 0.788, 0.726, 0.717 |
| MIX_LP | 2024-25 | 1.236, 1.079, 1.048, 1.075 | 0.610, 0.565, 0.541, 0.509 | 0.754, 0.609, 0.568, 0.547 |

Overall relWIS vs baseline, U → NB: EAKF 0.799→1.056 and 0.650→0.681; GBQR 0.741→0.855 and 0.622→0.655; MIX_LP 0.672→0.785 and 0.543→0.592 (2023-24 first, then 2024-25).

### Coverage (cov50 / cov90), U → NB

| Model | Fold | all | obs<10 rows (extra) |
|---|---|---|---|
| EAKF | 2023-24 | .466/.856 → .634/.977 | .440/.779 → .809/.982 (n=843) |
| EAKF | 2024-25 | .349/.734 → .402/.761 | .470/.809 → .577/.876 (n=581) |
| GBQR | 2023-24 | .410/.779 → .652/.930 | .335/.702 → .574/.913 |
| GBQR | 2024-25 | .375/.726 → .502/.821 | .546/.859 → .609/.904 |
| MIX_LP | 2023-24 | .540/.911 → .685/.955 | .504/.852 → .662/.944 |
| MIX_LP | 2024-25 | .444/.827 → .431/.770 | .582/.916 → .561/.857 |

### Reading (not part of the decision)

- **One φ per location cannot fit both seasons.** The LOSO φ is unstable. Trained on 2024-25 and applied to 2023-24, φ_pool = 0.72 (GBQR), 0.83 (MIX_LP) and 3.16 (EAKF). Trained on 2023-24, φ_pool = 0.26–0.44. The NB variance `mu + φ·mu²` is relative-scale, so φ mostly encodes the median's error in the training season, not count noise. Applied to the other season, it over-widens 2023-24 and under-widens 2024-25 (MIX_LP 2024-25 cov90 drops 0.827 → 0.770).
- **The cost is at h0–h1.** h3 is roughly neutral (0.99–1.05). h0 roughly doubles WIS in 2023-24, because a horizon-independent φ discards the models' horizon-growing spread.
- **Small counts are not the coverage problem in dev.** In 2024-25 no location has a median below 10/wk. On rows with observed < 10, unmodified coverage is closer to nominal than overall coverage is (e.g. MIX_LP 2024-25 .582/.916 vs .444/.827). The undercoverage is at large counts, in line with A5/B4 (calibration by horizon), not with a count-noise layer.
- **Phase bias:** NB keeps the unmodified median (the 0.5 quantile is the U value; the cummax monotonisation can only raise it when NB lower quantiles exceed it, which is rare). Phase bias therefore equals U's to within that effect and was not recomputed.
