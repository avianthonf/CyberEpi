# Backtest results (honest retest, 2026-11-25)

The forecaster in `backtest/` (SEIHDR model + ensemble Kalman filter, see
[backtest/METHODS.md](backtest/METHODS.md)) scored against CDC FluSight
targets (weekly flu hospital admissions, 53 locations, horizons 0–3).

These numbers replace the August 2026 headline (pooled relWIS 0.714), which is
kept in [docs/archive/BACKTEST_RESULTS-2026-08.md](docs/archive/BACKTEST_RESULTS-2026-08.md).
That result used fully revised data, was tuned on the seasons it reported, and
was compared only with the persistence baseline. This retest removes all three
problems.

**relWIS** = our mean weighted interval score ÷ the reference model's, on the
same (location, date, horizon) rows. Below 1 means better than the reference.

## Headline

Settings frozen after tuning on 2023-24 only; scored once on the two later
seasons, using only data as it was published at each forecast date.

| Season | vs FluSight-baseline | vs FluSight-ensemble | 50% interval coverage | 90% interval coverage | n |
|---|---|---|---|---|---|
| 2024-25 | **0.650** | 0.966 | 0.35 | 0.73 | 5,724 |
| 2025-26 | **0.766** | 1.163 | 0.39 | 0.74 | 5,936 |
| pooled | **0.697** | 1.046 | 0.37 | 0.74 | 11,660 |

In plain terms:

- **About 30% better than the CDC persistence baseline**, out of sample.
- **About level with the CDC ensemble** (the combination of all submitted
  models): 3% better in 2024-25, 16% worse in 2025-26, 5% worse pooled.
- **Intervals are too narrow.** The 90% intervals contain the truth about 74%
  of the time (target 90%). This is the main weakness to fix.

relWIS vs the ensemble by horizon (pooled): h0 0.88, h1 1.00, h2 1.11, h3 1.08.
The model is strongest for the current week and loses ground further out.

## What "honest" means here

1. **As-published data.** At each forecast date R the model only sees the
   admissions version the CDC published by R (hub `target-data/time-series.csv`,
   `as_of`), re-running the filter from the season start on that version.
   First reports average ~96% of final values (range 78–142% nationally).
2. **Out-of-sample settings.** Selection rule committed before any test result
   (`backtest/tune_vintage.py`, commit `f25fb31`): 16 settings on 2023-24, lowest
   relWIS vs baseline with 90% coverage ≥ 0.85. Chosen: `sd_beta=0.03,
   s_obs=0.10, sd_beta_fwd=0.03`, ED input on (2023-24: relWIS 0.799, cov90 0.86).
3. **Strong comparison.** Scored against both FluSight-baseline and
   FluSight-ensemble on identical rows.

### Remaining limitations

- **ED input before Nov 2025 uses final values.** The second data stream
  (share of ED visits for flu) has no published versions in the hub before
  Nov 2025. For 2025-26, a fully as-published run (both streams) gives
  relWIS **0.759** vs baseline and **1.156** vs ensemble (n = 5,712; origins
  before the first archived ED version skipped), essentially the same as the
  headline, so ED revisions do not appear to inflate the result.
- **Missing archived versions.** On 212 of 2,915 location-dates the hub has no
  version for the expected week, so the model ran one week stale. This can only
  make the scores worse.
- **Retrospective.** Still a backtest. The real test is live submission during
  the 2026-27 season (see [ROADMAP.md](ROADMAP.md)).

## Supporting findings

| Run | 2023-24 | 2024-25 | 2025-26 | pooled vs baseline | pooled vs ensemble |
|---|---|---|---|---|---|
| Original settings, final data (re-run on today's data) | 0.834 | 0.654 | 0.711 | — | — |
| Original settings, as-published data | 0.852 | 0.709 | 0.714 | 0.736 | 1.085 |
| Frozen tuned settings, as-published data (headline) | (tuning) | 0.650 | 0.766 | 0.697 | 1.046 |

- **As-published data costs little**: 0–8% worse relWIS than final data, depending on season.
- **The ED input carries most of the skill.** Every admissions-only setting
  scored relWIS 3.3–4.2 vs baseline on 2023-24; every setting with ED input
  scored 0.80–0.85.
- **Tuning trades calibration for sharpness.** The original settings have
  better 90% coverage (0.77–0.83) but slightly worse relWIS.

## Reproduce

Data: clone the hub (`https://github.com/cdcepi/FluSight-forecast-hub`, sparse:
`target-data`, `auxiliary-data`, `model-output/FluSight-baseline`,
`model-output/FluSight-ensemble`) and link into `data/flusight/`:
`locations.csv` (from `auxiliary-data/`), `target-hospital-admissions.csv`,
`target-ed-visits-prop.csv`, `oracle-output.csv`, `time-series.csv`,
`model-output/`, and `target-data-archive/` (from `auxiliary-data/`).

```sh
LOCS=US,01,02,04,05,06,08,09,10,11,12,13,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40,41,42,44,45,46,47,48,49,50,51,53,54,55,56,72

# 1. tuning on 2023-24 (pre-registered rule)
python3 backtest/tune_vintage.py --ncpus 4 --locations $LOCS
# 2. frozen settings on the test seasons
python3 backtest/run_vintage.py --seasons 2024-25,2025-26 --locations $LOCS \
  --ncpus 4 --label test-chosen --sd-beta 0.03 --s-obs 0.10 --sd-beta-fwd 0.03 --ili final
# 3. fully as-published 2025-26
python3 backtest/run_vintage.py --seasons 2025-26 --locations $LOCS \
  --ncpus 4 --label test-chosen-edvintage --sd-beta 0.03 --s-obs 0.10 --sd-beta-fwd 0.03 --ili vintage
```

About 45 minutes on 4 CPUs in total. Summaries of every run above are committed in
[backtest/results/honest/](backtest/results/honest/); row-level outputs go to
`backtest/out/honest/` (not committed, ~100 MB).
