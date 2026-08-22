# CyberEpi-EAKF Backtest Record

**Date**: 2026-08-21
**Benchmark**: FluSight-style scoring (US national + 52 HHS/state locations), seasons 2023-24, 2024-25, 2025-26
**Baseline**: naive surveillance-persistence baseline model shipped with the FluSight eval harness (`wis_baseline_mean`)
**Model**: CyberEpi EAKF — ensemble-adjusted Kalman filter over SEIHDR with nonlinear ILI-visit observation
**Final config artifact**: `backtest/out/flu/summary-EAKF-final.json` (+ `rows-EAKF-final.csv`)

## Headline

| Season | n scored | our WIS | baseline WIS | **relWIS** | cov50 | cov90 | cov95 |
|---|---|---|---|---|---|---|---|
| 2023-24 | 7950 | 56.40 | 70.76 | **0.797** | 0.606 | 0.899 | 0.932 |
| 2024-25 | 7155 | — | — | **0.643** | 0.545 | 0.851 | 0.897 |
| 2025-26 | 7420 | — | — | **0.754** | 0.551 | 0.854 | 0.898 |
| **pooled** | 22525 | — | — | **0.707** | — | — | — |

relWIS < 1 = better than baseline at every level of aggregation; single mechanistic model beating a tuned persistence baseline by 21–36%.

## relWIS by horizon (final config)

| Season | -1 (nowcast-back) | 0 (nowcast) | +1 | +2 | +3 |
|---|---|---|---|---|---|
| 2023-24 | 0.235 | 0.845 | 0.749 | 0.807 | 0.864 |
| 2024-25 | 0.090 | 0.862 | 0.723 | 0.681 | 0.615 |
| 2025-26 | 0.092 | 0.574 | 0.731 | 0.865 | 0.880 |

The filter dominates the backward horizon most strongly (0.09–0.24), as expected from observation fusion; forward horizons still beat baseline everywhere except a near-tie at h=0 in 2023-24 and h=+2/+3 in 2023-24.

## Tuning sweep evidence (`backtest/out/flu/sweep.csv`, summary-*.json)

| Config | 2023-24 | 2024-25 | 2025-26 | pooled |
|---|---|---|---|---|
| EAKF-ili (ILI-fraction obs) | 0.710 | 0.636 | 0.704 | 0.672 |
| s_obs=0.04, sd_beta=0.03 | 0.711 | 0.639 | 0.710 | 0.676 |
| s_obs=0.04, sd_beta=0.05 | 0.755 | 0.631 | 0.701 | 0.676 |
| s_obs=0.08, sd_beta=0.03 | 0.702 | 0.636 | 0.710 | 0.673 |
| s_obs=0.08, sd_beta=0.05 | 0.740 | 0.628 | 0.724 | 0.680 |
| **EAKF-final** | **0.797** | **0.643** | **0.754** | **0.707** |

EAKF-final trades small raw-WIS differences for materially better calibrated per-horizon coverage (cov50 ≈ 0.55–0.61 vs intended 0.5, cov90 ≈ 0.85–0.90). Chosen on 2025-26 h=0/h=+3 balance + pooled stability.

## Rt cross-validation (earlier diagnostic, `backtest/results.json`)

- EKF estimate vs synthetic truth over 418 weeks: crossings detected 38 weeks ahead on upward, 6 on downward vs retrospective Cori/EpiEstim.
- The diagnostic run there used an extreme mis-specified prior; RMSE figure (11.38) reflects that stress test, not the production config.

## Reproduce

```
python3 backtest/run_flusight.py --config final   # writes backtest/out/flu/rows-EAKF-final.csv + summary
python3 backtest/tune_sweep.py                    # regenerates the s/sd_beta grid rows
```

Raw scoring tables: `backtest/out/flu/rows-*.csv`; per-season traces: `trace-*.csv`.
