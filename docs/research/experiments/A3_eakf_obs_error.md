# A3 — Lag-aware observation error in model 1 (EAKF), dev seasons

Status: **pre-registered 2026-11-26T01:01:21Z** (written before any variant code or run). Results appended below "## Results".
Source: SYNTHESIS §6 item 3; SYNTHESIS §2 A3; report 06 §8.1 and Track A #1.

## Question

The newest admissions value a live forecaster sees is a first report. Nationally it is about 9% low
at lag 0 (volume-weighted lag-0 to lag-1 factor 1.06). Model 1 assimilates it with the same noise as
a settled value. Does a larger lag-0 observation SD, scaled by each location's lag-0 share, improve
forecasts at h=0..3?

## Variant (pre-registered)

- Unmodified model 1 config (`backtest/model_config.json`); only the lag-0 admissions update changes.
- Lag-0 observation = the last week of the as-of series for the origin (week R−7). Its admissions
  noise SD is multiplied by m_loc = max(1, 1/s_loc).
- s_loc = volume-weighted lag-0 share of location loc: Σ_w lag0(w) / Σ_w final(w), over weeks w of the
  estimation season. lag0(w) is the value the filter sees at origin R = w+7 (`pick_vintage`, `series_at`).
  final(w) is the hub oracle value. Weeks with missing values on either side are dropped.
- Leave-one-season-out: fold 2023-24 uses s_loc from 2024-25 weeks; fold 2024-25 uses s_loc from 2023-24
  weeks.
  Caveat (stated now): for fold 2023-24 the share comes from a later season. This is the pre-registered
  LOSO design; the caveat is reported with the result.
- Only the admissions noise variance of that one update changes. Inflation, ensemble size, ED stream,
  seeds and emission rules are unchanged.
- Opt-in: `lag0` multiplier defaults to 1.0. With it off, outputs must be byte-identical to the existing
  `backtest/results/dev_members/` model 1 files for 2 reference dates (checked before the variant run).

## Setup (all dev, no 2025-26)

- Origins: all dev reference dates from `run_flusight.season_origins` for 2023-24 and 2024-25, filtered
  by the A0 rules. Origins with no usable vintage (`pick_vintage` returns None or fewer than 10 non-NaN
  weeks) are dropped in both arms, so the comparison is paired.
  A0 stale picks (R = 2024-11-30, 2024-12-14, 2025-01-11; vintage one week older than expected) are kept
  in both arms and counted in the result.
- ED visits: final values, for both arms. As-published ED vintages start 2025-11, so no ED vintage exists
  for dev seasons. This is a leakage label that applies to every dev result.
- Scoring: `run_flusight.summarize` against FluSight-baseline, horizons 0..3. The unmodified model is the
  second reference.

## Pass criterion (fixed before running)

For each fold (2023-24, 2024-25) separately:
- relWIS(variant vs unmodified model) < 1 at h=0 AND at h=1. Computed as mean WIS over fold rows at that
  horizon.
- **Stop rule:** if either horizon fails on either fold, A3 stops. The unmodified model is kept, and A2 is
  read without any observation-layer correction.

Secondary, reported but not part of the pass decision: relWIS vs FluSight-baseline; coverage (50/90);
median log error by phase (rising, peak, declining; as-of 3-week growth rule from `dev_members`) at
h=0..3, for both arms; runtime.

Bias question (decides how A2 is read): does the variant shrink the rising-phase and declining-phase
median log error of model 1, relative to the unmodified model, at h=0..3? "Shrink" = |median log error|
smaller on both folds.

## Results

Run 2026-11-26T01:06Z (after the pre-registration above). Driver `backtest/a3_obs_error.py`; outputs
`backtest/results/a3/` (summary.json, lag0_share_for_<season>.csv, phase_bias_<season>.csv).
ED = final values in both arms (no dev-season ED vintages exist).

**Bit-identity:** with the multiplier at 1.0, all 57 dev reference dates are byte-identical to
`results/dev_members` (the pre-registration required 2). Scoring tests pass.

**Shares (LOSO):** estimated on 2024-25 and applied to 2023-24: US share 0.888, median multiplier 1.133,
max 1.552. Estimated on 2023-24 and applied to 2024-25: US 0.969, median 1.003, max 1.148.
The as-of store shows the larger lag-0 shortfall in 2024-25, in line with report 06 (2023-24 near complete).

**Origins:** every dev origin had a vintage (A0 gap months are not dev origins). Stale picks: 159 of
3,021 location-origins are one week stale (A0's 3 dates in 2024-25); they are kept in both arms.

| Fold | h | variant / unmodified | relWIS vs baseline, unmodified → variant | cov50 | cov90 |
|---|---|---|---|---|---|
| 2023-24 | 0 | 1.021 | 0.738 → 0.754 | 0.42 → 0.43 | 0.82 → 0.81 |
| 2023-24 | 1 | 1.005 | 0.720 → 0.724 | 0.46 → 0.46 | 0.85 → 0.85 |
| 2023-24 | 2 | 1.002 | 0.809 → 0.810 | 0.48 | 0.88 |
| 2023-24 | 3 | 1.001 | 0.863 → 0.863 | 0.50 → 0.51 | 0.88 → 0.89 |
| 2024-25 | 0 | 1.002 | 0.680 → 0.681 | 0.33 | 0.70 |
| 2024-25 | 1 | 1.002 | 0.660 → 0.661 | 0.35 | 0.73 |
| 2024-25 | 2 | 1.003 | 0.666 → 0.667 | 0.35 | 0.75 |
| 2024-25 | 3 | 1.002 | 0.622 → 0.623 | 0.36 | 0.76 |

**Verdict: FAIL on both folds at h=0 and h=1. The stop rule applies.** A3 stops, and model 1 is unchanged.

**Phase bias (median log error, unmodified → variant):** neither bias shrinks.
- Declining: 2023-24 h3 −0.368 → −0.350; 2024-25 h3 −0.616 → −0.613. Changes are ≤ 0.02 and occur only
  in the fold with large multipliers.
- Rising: 2023-24 h0..3 −0.02..−0.09, unchanged within ±0.01. 2024-25 h0..3 −0.20..−0.46, unchanged.
- Peak in 2023-24 gets slightly worse (h3 −0.218 → −0.251).

**Reading for A2:** a larger lag-0 observation SD only down-weights the first report; it does not remove
its bias. Model 1's rise and decline biases are therefore not explained by observation weighting of the
newest week. A2 should be read against the unmodified observation layer. A debiasing (nowcast-multiplier)
variant is a different hypothesis that this experiment did not test.

**Runtime:** 210 s for both arms on 8 CPUs (all 53 locations, 57 origins). The variant itself adds
negligible cost (one multiply per lag-0 update).
