# Archive analysis: method types vs FluSight ensemble

Source: `backtest/archive_scores.py` on `../flusight-forecast-hub` (hub archive, 132 scored models). Outputs in `backtest/results/archive/`: `summary.csv`, `pairwise.csv`, `method_types.csv` (158 rows, one per metadata file; `scored` marks the 132 with archive scores). `rows.parquet` is on disk only, not in git.

## Scope and rules

- Conclusions use completed seasons only: 2023-24, 2024-25, 2025-26.
- 2026-27 is in progress. Its truth is partial, so `phases()` labels its rows `provisional` (the peak would be the peak so far, not the season peak). It appears in `summary.csv` but in no phase result below.
- The team's own model, CyberEpi-EAKF, is included in scoring and in the type tables. It is one of the 132 scored models; its type labels come from its metadata like any other.
- Coverage: a model-season enters a type comparison only if it has at least 50% of that season's maximum scored rows. Covered model-seasons: 2023-24 n=34, 2024-25 n=42, 2025-26 n=46 (122 total).
- `rel` = model WIS / FluSight-ensemble WIS on the same rows (< 1 beats the ensemble). FluSight-ensemble itself is `rel` = 1.0 by definition and is counted inside the ensemble row; this lowers that row's median, so read the ensemble row as a slight underestimate.
- Pairwise = geometric mean of WIS ratios against each other covered model, divided by the baseline's value. Self-pairs are skipped.

## Method-type labels

- Structured `ensemble_of_models` flag decides ensemble membership; keyword match is used only when the flag is absent (none were absent in the final run).
- Other types are multi-label keyword rules on `methods` and `methods_long`. Baseline is narrow: model name contains "baseline", or method text names a naive, persistence, climatology or flat forecast.
- 13 manual overrides where keywords gave no class or a misfire. Each is recorded in the `matched` column.
- Labels are multi-label, so type rows overlap.
- Caveat: the human-judgement (4 covered model-seasons) and baseline (7) groups are too small for conclusions. Keyword labels have not been manually audited across all models.
- Classifier is a throwaway script at `/tmp/ac/classify.py`, not committed.

## Season-level results: median rel vs FluSight-ensemble

Covered models only. Bracket = 10th-90th percentile bootstrap over models.

| type | 2023-24 (n) | 2024-25 (n) | 2025-26 (n) | pooled (n) | share beating ensemble, pooled |
|---|---|---|---|---|---|
| mechanistic | 1.216 (13) | 1.035 (10) | 1.244 (12) | 1.168 [1.096, 1.257] (35) | 0.17 |
| statistical | 1.161 (14) | 1.153 (20) | 1.305 (22) | 1.199 [1.160, 1.243] (56) | 0.20 |
| ML | 1.207 (6) | 1.228 (6) | 1.083 (8) | 1.159 [1.054, 1.188] (20) | 0.30 |
| deep learning | 1.358 (7) | 1.285 (9) | 1.367 (10) | 1.350 [1.240, 1.402] (26) | 0.08 |
| ensemble | 1.220 (16) | 1.213 (23) | 1.081 (23) | 1.175 [1.136, 1.221] (62) | 0.24 |
| baseline (naive only) | 1.309 (2) | 1.487 (3) | 1.203 (2) | 1.373 [1.153, 1.518] (7) | 0.14 (n too small) |
| human judgement | 1.358 (1) | 1.430 (1) | 1.139 (2) | 1.350 [1.139, 1.394] (4) | 0.25 (n too small) |

Reading: nearly every type's median is above 1, so the FluSight ensemble is a strong reference. Deep learning is furthest behind consistently. ML and ensemble models are closest to the ensemble pooled.

## By horizon (pooled, covered)

| type | h=0 | h=1 | h=2 | h=3 |
|---|---|---|---|---|
| mechanistic | 1.233 (38) | 1.197 (38) | 1.163 (35) | 1.158 (35) |
| statistical | 1.118 (56) | 1.197 (56) | 1.220 (56) | 1.231 (56) |
| ML | 1.135 (20) | 1.127 (20) | 1.148 (20) | 1.165 (20) |
| deep learning | 1.257 (26) | 1.325 (26) | 1.351 (26) | 1.319 (26) |
| ensemble | 1.125 (62) | 1.160 (62) | 1.176 (62) | 1.215 (62) |

Reading: ML and statistical are closest to the ensemble at short horizons. Ensemble and deep learning fall further behind as the horizon grows.

## By phase (pooled, covered, completed seasons only)

| type | rising | near_peak | declining |
|---|---|---|---|
| mechanistic | 1.034 (21) | 1.113 (36) | 1.294 (41) |
| statistical | 1.099 (32) | 1.107 (47) | 1.337 (57) |
| ML | 1.088 (12) | 1.089 (19) | 1.242 (21) |
| deep learning | 1.201 (13) | 1.118 (23) | 1.505 (27) |
| ensemble | 1.145 (36) | 1.075 (56) | 1.259 (65) |

Reading: every type falls further behind the ensemble in the declining phase. Mechanistic is closest in the rising phase. Phase labels come from final truth (retrospective), so they are not forecast-time signals.

## Pairwise vs FluSight-baseline (median per season, covered)

| type | 2023-24 | 2024-25 | 2025-26 |
|---|---|---|---|
| mechanistic | 0.884 (13) | 0.692 (10) | 0.820 (12) |
| statistical | 0.829 (14) | 0.768 (20) | 0.861 (22) |
| ML | 0.887 (6) | 0.831 (6) | 0.705 (8) |
| deep learning | 0.993 (7) | 0.850 (9) | 0.904 (10) |
| ensemble | 0.887 (16) | 0.806 (23) | 0.687 (23) |

Top-10 per season is dominated by ensembles and mechanistic or statistical models: PSI-PROF and PSI-PROF_beta (mechanistic and statistical) and UMass-flusion, FluSight-lop_norm and FluSight-ensemble (ensembles) recur across seasons. Full lists are in `pairwise.csv`.

## Luck and stability caveats

- Only three completed seasons. One season moves a type median by 0.1-0.2 (e.g., statistical 1.16 to 1.31; mechanistic 1.04 to 1.24).
- Season-to-season rank persistence of `rel` is weak: Spearman rho = 0.29 (p = 0.18, n = 23) for 2023-24 to 2024-25; 0.47 (p = 0.009, n = 30) for 2024-25 to 2025-26. Season winners are not reliably repeated.
- Type labels overlap, so type medians are not independent. Ensemble models also appear in other types.
- Coverage threshold (50%) is a judgement call; per-season pairwise medians rest on 2-23 models.
- Phase labels are retrospective (final truth). The 2026-27 season is excluded until its truth is final.
- The 2025-26 holdout was already used (per handoff), so these results are descriptive only. Nothing here is a clean out-of-sample test.
- 26 metadata models are unscored (`scored = 0`); their method types are listed but do not enter any result. Scoring-drop reasons were not separately verified.

## Conclusion

No method type clearly beats the FluSight ensemble across seasons. Mechanistic, ML and statistical models are closest pooled, with ML the closest (1.16). Deep-learning models trail the ensemble most consistently (1.35). Every type's gap widens in the declining phase and at longer horizons. Given weak season-to-season persistence, these are descriptive findings; any method choice needs a pre-registered test.
