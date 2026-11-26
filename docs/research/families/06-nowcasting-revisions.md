# Family 06: nowcasting, reporting triangles, backfill

Scope: how NHSN weekly flu hospital admissions are revised after first publication; what that means for nowcasting h=0..3 and for model 1 (EAKF) and model 2 (GBQR). Data: `flusight-forecast-hub/target-data/time-series.csv` (934k rows, `wk inc flu hosp`, as_of 2023-09-23 to 2026-11-25, 105 vintage dates). All numbers below come from my own pandas run (scripts were scratch, in /tmp; not committed).

## 1. Method used for the numbers

- **Final value** = the last published vintage for a (location, week end). Restricted to week ends with at least 12 weeks between the week end and that last vintage ("mature"), and to finals ≥ 20 admissions (ratios are unstable for small counts).
- **Lag** = floor((as_of − week end) / 7). Lag 0 = first published version (the Friday/Wednesday after the Saturday week end). Lag 8+ is capped; its ratio is 1 by construction (it contains the final vintage itself), so read the lag-8 row as "final".
- **Ratio r** = observation at lag k / final. Rows: 3,560 at lag 0, about 3,550 at each lag 1–7 (all locations, mature finals, ≥20).
- **Phase** (in-sample, from the mature final series, so it is an analysis label, not a forecast-time feature): per location-season, the peak is the max of the 3-week centred smoothed final. Rising = more than 2 weeks before the peak; near peak = ±2 weeks; declining = after that.
- Season = Aug–Jul year (2021 has 26 US weeks; 2026 is incomplete).

## 2. Revision by lag (all 53 locations, mature finals ≥ 20)

| lag (wks) | n | median r | p10 | p90 | mean abs rel. revision |
|---|---|---|---|---|---|
| 0 | 3,560 | 0.953 | 0.764 | 1.018 | 0.103 |
| 1 | 3,568 | 1.000 | 0.895 | 1.011 | 0.050 |
| 2 | 3,551 | 1.000 | 0.922 | 1.009 | 0.034 |
| 3 | 3,554 | 1.000 | 0.931 | 1.008 | 0.030 |
| 4 | 3,547 | 1.000 | 0.938 | 1.008 | 0.026 |
| 5 | 3,524 | 1.000 | 0.944 | 1.007 | 0.025 |
| 6 | 3,480 | 1.000 | 0.949 | 1.006 | 0.023 |
| 7 | 3,433 | 1.000 | 0.951 | 1.006 | 0.023 |

Nationally (US only, 96 weeks at each lag 0–7):

| lag | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---|---|---|---|---|---|---|---|
| median r | 0.906 | 0.963 | 0.972 | 0.974 | 0.976 | 0.977 | 0.977 | 0.979 |
| p10 | 0.851 | 0.931 | 0.945 | 0.948 | 0.955 | 0.958 | 0.961 | 0.959 |
| p90 | 0.997 | 1.004 | 1.000 | 0.998 | 0.999 | 1.000 | 1.000 | 1.000 |

Reading: the first report is about 5% low in the median at every location, and about 9–10% low nationally. Most of the gap closes by lag 1, and a residual 2–3% national gap persists to lag 7. The "chain ladder" completion factor for lag 0 is therefore about 1/0.95 = 1.05 (all locations) or 1/0.906 = 1.10 (US). The lag-0 tail is wide: p10 is 0.76 for all locations, and 0.56–0.6 for some states (05, 10, 16, 29, 40).

## 3. Revision by season (first report, lag 0)

| season | all-location median r (lag 0) | US median r (lag 0) |
|---|---|---|
| 2023-24 | 1.000 | 0.999 (all vintages, US first/final) |
| 2024-25 | 0.909 | 0.915 (all vintages, US first/final) |
| 2025-26 | 0.920 | 0.907 |

Lag 1 by season: 2023 1.000, 2024 0.973, 2025 0.988. Lag 2: 0.986 (2024), 0.999 (2025).

Interpretation: 2023-24 looks complete at first report. The shortfall appears in 2024-25 and 2025-26. This matches the NHSN reporting change: mandatory reporting was relaxed for part of 2024 (about May–October), and first reports were less complete in that period. The brief's "~89% in 2025-26" is consistent with my US lag-0 median (0.907) rather than the all-location median (0.92). The brief's "96% average, range 78–142%" is close to the all-vintage US figures I computed (min 0.775, max 1.417).

Caveat: the 2024 voluntary-period mask is by target date, not by vintage. In 2024-25, the weeks May–Oct 2024 were the ones most affected, so the season split and the regime split overlap. I have not separated them further, and the sample of mature weeks per season is small (52 US weeks each).

## 4. Revision by phase (near peak matters, rising is mixed)

Median r, lag 0 (all locations):

| phase | n | median | p10 | p90 |
|---|---|---|---|---|
| declining | 1,897 | 0.946 | 0.757 | 1.009 |
| near peak (±2 wk) | 764 | 0.945 | 0.761 | 1.015 |
| rising | 899 | 0.974 | 0.793 | 1.041 |

Median r by lag and phase (all locations):

| phase | lag 0 | lag 1 | lag 2 | lag 3 |
|---|---|---|---|---|
| declining | 0.946 | 1.000 | 1.000 | 1.000 |
| near peak | 0.945 | 0.988 | 0.996 | 1.000 |
| rising | 0.974 | 1.000 | 1.000 | 1.000 |

Reading: first reports are *more* incomplete near the peak and in decline (about 5.5% low at the median), and less so while rising (2.6% low). Near the peak, the lag-1 median is still 1.2% low, so the post-peak week is the one with the largest remaining revision. This is the phase where the models already run low (model 1 declines too steeply). Part of that may be a measurement artefact: a truth set published late under-counts exactly the weeks the forecast is judged on. Two phase points:
- The "rising" lag-0 tail is heavy (max 14.5): small early counts with large relative revisions. WIS is on the count scale, so this matters less than the median suggests.
- The phase labels use the mature final series (look-ahead). For a real forecast the phase must come from the data available at R.

## 5. Revision by location (lag 0 and lag 1, median r)

Largest lag-0 shortfall (median r, n ≥ 29): 02 Alaska 0.823 (n 29; lag 1 0.933), 41 Oregon 0.843 (n 62; lag 1 0.981), 05 Arkansas 0.891 (n 63; lag 1 0.985), 11 DC 0.891 (n 32; lag 1 1.000), 21 Kentucky 0.886 (n 76; lag 1 0.969), 40 Oklahoma 0.877 (n 64; lag 1 1.000). Weakest lag-0 median among the best-sampled: 10 Delaware 0.909, 33 New Hampshire 0.911, 48 Texas 0.907, 06 California 0.906 (US total 0.906).

Lag-0 to lag-4 medians for key locations (median r): US 0.906 / 0.963 / 0.976; CA (06) 0.907 / 0.972 / 0.987; TX (48) 0.907 / 0.945 / 0.970; FL (12) 0.900 / 0.972 / 0.984; IL (17) 0.929 / 0.983 / 0.999.

Largest mean absolute deviation at lag 0 (|r − 1|, n ≥ 30): 39 Ohio 0.284 (median 0.958, p10 0.880, so a few large early upward or downward values); 29 Missouri 0.193; 33 New Hampshire 0.192; 41 Oregon 0.181; 40 Oklahoma 0.182; 02 Alaska 0.188; 05 Arkansas 0.173. Smallest: 34 New Jersey 0.028, 09 Connecticut 0.026, 27 Minnesota 0.055, 37 North Carolina 0.044, 08 Colorado 0.045.

Location figures use 29–105 mature weeks each, so state-level medians are noisy (roughly ±0.02–0.03). Full table: `/tmp/rev06_loc.csv` (scratch; regenerate from the script if needed).

## 6. Does a simple multiplier fix lag 0? (leave-one-season-out)

For each season s, the multiplier is fitted on the other seasons and applied to lag-0 observations (`pred = obs / m`); error is |pred − final| / final. n = 3,560 (all locations, mature finals ≥ 20).

| method | median abs rel. error | mean abs rel. error |
|---|---|---|
| raw first report | 0.058 | 0.103 |
| global multiplier (1/0.9535) | 0.089 | 0.114 |
| per-location multiplier | 0.071 | 0.116 |

By season (mean abs rel. error, raw / global / per-location): 2023 0.046 / 0.103 / 0.121; 2024 0.152 / 0.138 / 0.130; 2025 0.117 / 0.102 / 0.097.

Reading: the global and per-location multipliers hurt the typical week in the pooled sample (median error 0.058 raw vs 0.071–0.089), because in 2023 (no revision regime) they push a complete report too high. In the two revision seasons they help: 2024 0.152 → 0.130 (per-location) and 0.152 → 0.138 (global); 2025 0.117 → 0.097 (per-location). So a multiplier is useful only when the revision regime is active. It must be gated by recent as-published evidence (e.g. the last 4–8 vintages' lag ratios), not applied unconditionally. The gate itself is untested here and is the thing to test (Section 8, item 3).

## 7. Implications for our models and the hub

1. **Training data.** Model 2 (GBQR) is refitted on as-published data each week, so its lag-0 inputs are already the depressed first reports. Its training targets (weekly changes in log rate) therefore inherit the revision bias in the most recent weeks. Check whether the last 1–2 weeks of training rows are dropped or nowcast. (Track A, low cost.)
2. **Model 1 (EAKF).** The ensemble assimilates the latest admission count as if it were complete. With a 9–10% national shortfall at lag 0 and about 3.7% still missing at lag 1 (US 0.963), the filter sees a too-low final point. This should push the state's incidence low in the most recent week, which is the phase where model 1 already runs low. An observation-error term for the most recent week (larger for lag 0 than for lag ≥ 1) is a direct test, and it is cheap. (Track A candidate, needs shadow confirmation.)
3. **Truth for scoring.** If `oracle-output.csv` is taken at the first publication for the last reference week, its value is biased low (lag-0 US median 0.906 of final). Expect the first weeks of each live season to show systematic "overprediction" against truth that is partly an artefact. The shadow protocol should therefore score against the value available at the next week's publication, and report a lag-1-based sensitivity too.
4. **Hub baseline caveat.** FluSight-baseline and the ensemble use the same truth vintages, so relWIS is not directly affected by revisions, but absolute WIS for the most recent week will be.
5. **Nowcast candidates (Track B):** NobBS (Bayesian reporting-delay model with time-varying delays, which the source reports as more robust than heuristic/hybrid approaches under changing delays, on dengue and ILI data); epinowcast (Stan-based, renewal-process nowcast with delay and missing-data modelling, and a stratified option for locations). Both need a reporting triangle built from as-published vintages. Our archive has 105 vintage dates over three seasons and sparse weekly coverage (lags 1–7 exist for ~3,500 of ~3,560 target dates, but the lag-0 vs lag-1 relation changes with regime), so a triangle with time-varying delays is data-hungry. A lighter option is a gated multiplier per location with a regime indicator, fitted on as-published lag ratios of the last 4–8 vintages, and it can be tested leave-one-season-out.

## 8. Ranked experiments

Track A (for submission; strong evidence needed):
1. **Lag-aware observation error in EAKF** for the most recent week. Pre-register: inflate observation SD for lag 0 by the empirical lag-0 spread (p10–p90 0.76–1.02 all locations; 0.85–1.00 US). Test LOSO on 2023-24, 2024-25; measure h=0..3 relWIS vs current EAKF. Stop if no gain at h=0 and h=1.
2. **Exclude or nowcast the newest GBQR training weeks** (drop lag-0 rows from training). Test on 2024-25 and 2023-24 by as-of replay. Expect a small gain; evaluate in rising phases.

Track B (shadow only):
3. **Regime-aware multiplier nowcast** (per-location, the last 4–8 vintages' lag ratios, with a 2024-like regime flag). LOSO test on lag-0 errors (benchmark: raw 0.058 median abs error; ungated global multiplier 0.089 is a poor baseline; per-location 0.071).
4. **NobBS** (R package) as a nowcast of the latest 1–2 weeks, used as an input or as a shadow model; test on the as-of triangle built only from the archive.
5. **epinowcast** (renewal-process nowcast, stratified by location) as a shadow model; same test. Costly to fit weekly within 30 CPU-minutes for 53 locations without pooling, so benchmark cost first.

## 9. Failure modes

- The "final" in this archive is the last vintage, which is itself a snapshot (last update 2026-11-25 for the current season). Mature-week ratios are reliable only for dates at least 12 weeks old.
- Vintage coverage is sparse: 15, 22, 33, 35 vintage dates in 2023–2026 (not weekly). Early-lag results rest on the few weeks that were re-published, so lag 1–7 medians are estimated from unequal subsets. Per-location numbers have n ≈ 30–105.
- Phase labels are in-sample (peak from the final series). They explain where revision is large, but are not usable as forecast-time features as they stand.
- Reporting regime (2024 voluntary) is confounded with season; I have not split vintages within 2024-25.
- Small counts: relative revision is unstable below 20 admissions; I dropped those.

## 10. Costs (4-CPU, 30-minute budget)

- Lag-aware EAKF observation error: negligible (one extra variance per week).
- Dropping recent GBQR rows: negligible.
- Regime multiplier: under 1 second per week (per-location arithmetic on the archive).
- NobBS per week (53 locations, MCMC, Stan-free but iterative): on the order of seconds to minutes per location; benchmark before adopting.
- epinowcast per week (53 locations, Stan): likely several minutes with pooling; must be benchmarked.

## 11. References

- McGough SF, Johansson MA, Lipsitch M, Menzies NA. "Nowcasting by Bayesian Smoothing: A flexible, generalizable model for real-time epidemic tracking." PLOS Computational Biology 16(4): e1007735 (2020). Opened as the PLOS article page (search summary), and the NobBS CRAN package DOI 10.32614/cran.package.nobbs. Author list as given by the search summaries (McGough, Menzies, Lipsitch, Johansson, Yaari, Zepeda Tello): the article page was not opened in full, so the exact author order is [unverified].
- epinowcast project: github.com/epinowcast/epinowcast and package.epinowcast.org (both opened as search summaries). Its methods paper, and a 2024 Abbott–Sherratt–Funk–Hickson paper I was asked to check, were not located: [unverified].
- Chain-ladder / reporting-triangle methods are standard in claims and infectious-disease nowcasting; no source was opened for this report: [unverified].
- Data: `flusight-forecast-hub/target-data/time-series.csv` (local copy, opened).

## 12. Top recommendations (for Main)

1. Treat the lag-0 value as a biased observation: model 1's EAKF should use a larger error for the newest week, and GBQR should not train on lag-0 rows. Cheap, testable in as-of replay.
2. Do not deploy a fixed revision multiplier. It helps in revision seasons (2024, 2025) and hurts in the complete season (2023). Only a gated version, switched on by recent as-published evidence, is worth testing.
3. Score shadow models against the next-week vintage as a sensitivity check, since lag-0 truth is biased low by 5–10% in the newest week.
4. Test NobBS or a regime-aware nowcast in shadow mode; benchmark run time before adding it to the weekly job.
5. Expect that near-peak weeks carry the largest unrevised gap (lag 1 about 1% low); phase-aware calibration should take this into account.
