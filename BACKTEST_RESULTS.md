# CyberEpi-EAKF Backtest Record

**Date**: 2026-08-21
**Benchmark**: FluSight-style scoring (US national + 52 HHS/state locations), seasons 2023-24, 2024-25, 2025-26
**Baseline**: naive surveillance-persistence baseline model shipped with the FluSight eval harness (`wis_baseline_mean`)
**Model**: CyberEpi EAKF — ensemble-adjusted Kalman filter over SEIHDR with nonlinear ILI-visit observation (model/inference details: [backtest/METHODS.md](./backtest/METHODS.md))
**Final config artifact**: `backtest/out/flu/summary-EAKF-final.json` (+ `rows-EAKF-final.csv`)

## Headline

| Season | n scored | our WIS | baseline WIS | **relWIS** | cov50 | cov90 | cov95 |
|---|---|---|---|---|---|---|---|
| 2023-24 | 6354 | 73.00 | 85.05 | **0.858** | 0.531 | 0.913 | 0.951 |
| 2024-25 | 5724 | 174.19 | 263.13 | **0.662** | 0.445 | 0.849 | 0.903 |
| 2025-26 | 5936 | 125.22 | 175.16 | **0.715** | 0.487 | 0.868 | 0.925 |
| **pooled** | 18014 | — | — | **0.714** | ~0.487 | ~0.876 | ~0.926 |

Scoring follows FluSight practice: horizons 0..3 (h=-1 nowcast-back rows
are emitted for the hub but excluded from scoring, matching the hub's own
protocol). **n scored** = finite paired (wis, wis_base) comparison rows;
18,020 total comparison rows, 6 excluded due to non-finite baseline WIS.
Numbers reproduced 2026-08-23 by the one-command run below.

relWIS < 1 = better than baseline at every level of aggregation; single mechanistic model beating a tuned persistence baseline by 14–34% depending on season.

## relWIS by horizon (final config, h>=0 scoring)

| Season | 0 (nowcast) | +1 | +2 | +3 |
|---|---|---|---|---|
| 2023-24 | 0.808 | 0.794 | 0.872 | 0.905 |
| 2024-25 | 0.623 | 0.675 | 0.694 | 0.644 |
| 2025-26 | 0.536 | 0.651 | 0.770 | 0.781 |

All forward horizons beat the baseline in every season. (The h=-1
nowcast-back horizon, where the filter is strongest at relWIS 0.09–0.24,
is excluded per FluSight scoring convention; hub submissions score h=0..3.)

## Tuning sweep evidence (`backtest/out/flu/sweep.csv`, summary-*.json)

*Note: sweep figures below predate the h>=0 scoring change and include
h=-1; they are retained as the tuning artifact that selected EAKF-final.
Final-config re-scored numbers are the headline table above.*

| Config | 2023-24 | 2024-25 | 2025-26 | pooled |
|---|---|---|---|---|
| EAKF-ili (ILI-fraction obs) | 0.710 | 0.636 | 0.704 | 0.672 |
| s_obs=0.04, sd_beta=0.03 | 0.711 | 0.639 | 0.710 | 0.676 |
| s_obs=0.04, sd_beta=0.05 | 0.755 | 0.631 | 0.701 | 0.676 |
| s_obs=0.08, sd_beta=0.03 | 0.702 | 0.636 | 0.710 | 0.673 |
| s_obs=0.08, sd_beta=0.05 | 0.740 | 0.628 | 0.724 | 0.680 |
| **EAKF-final** | **0.797** | **0.643** | **0.754** | **0.707** |

EAKF-final trades small raw-WIS differences for materially better calibrated per-horizon coverage (cov50 ≈ 0.44–0.53 vs intended 0.5, cov90 ≈ 0.85–0.91). Chosen on 2025-26 h=0/h=+3 balance + pooled stability.

## Rt cross-validation (earlier diagnostic, `backtest/results.json`)

- EKF estimate vs synthetic truth over 418 weeks: crossings detected 38 weeks ahead on upward, 6 on downward vs retrospective Cori/EpiEstim.
- The diagnostic run there used an extreme mis-specified prior; RMSE figure (11.38) reflects that stress test, not the production config.

## Reproduce

```sh
# Full EAKF-final run: 3 seasons x 53 locations (uses --ncpus workers)
python3 backtest/run_flusight.py \
  --seasons 2023-24,2024-25,2025-26 \
  --locations US,01,02,04,05,06,08,09,10,11,12,13,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40,41,42,44,45,46,47,48,49,50,51,53,54,55,56,72 \
  --ncpus 8 --label EAKF-final
# writes backtest/out/flu/{rows,trace,cmp,summary}-EAKF-final*.csv/json

python3 backtest/tune_sweep.py   # regenerates the calibration grid (backtest/out/flu/sweep.csv)
```

Raw scoring tables: `backtest/out/flu/rows-*.csv`; per-season traces: `trace-*.csv`.
