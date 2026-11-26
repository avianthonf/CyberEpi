# Family 06: nowcasting, reporting triangles, backfill

Scope: how NHSN weekly flu hospital admissions are revised after first publication, and what that means for nowcasting h=0..3 for model 1 (EAKF) and model 2 (GBQR). Data: `flusight-forecast-hub/target-data/time-series.csv`, opened locally (934k rows; 105 as-of dates: 15 in 2023, 22 in 2024, 33 in 2025, 35 in 2026). Two targets are present: `wk inc flu hosp` (analysed here) and `wk inc flu prop ed visits` (not analysed; its vintages are published only from Nov 2025 per the brief, so it cannot be checked the same way).

## 1. Data handling

- **Target:** `wk inc flu hosp` only.
- **Backfill:** the 2023-09-23 snapshot holds history back to 2022-02, with first-vintage lags up to 250 weeks. It is excluded (`as_of > 2023-09-23`). Lags above 11 weeks are dropped rather than pooled (the earlier lag-8+ bucket was mostly the snapshot and is not used).
- **Lag:** floor((as_of − target_end_date) / 7). Lag 0 = first publication.
- **Final:** last vintage of each (location, week); a week counts as final only if its last vintage is at least 12 weeks after the week end. This removes right-censoring for 2025-26 weeks.
- **Cells:** first vintage at each lag 0–11; ratio analyses use finals ≥ 20 admissions.
- **Season:** Aug–Jul year label (2023 = 2023-24).

## 2. US equals the sum of locations (checked)

For each vintage and week end, the US count minus the sum of the 52 other hub locations (50 states, DC, Puerto Rico) has median 1, is exactly zero in 43% of cases, and has mean relative difference 0.14%. The US national series is therefore the sum of the locations (rounding only). The earlier suspicion that US runs ahead of the states is not supported once Puerto Rico (location 72) is included; without it the median difference would be 52, roughly Puerto Rico's median weekly count (50).

## 3. Chain ladder: volume-weighted factors (US and all locations)

Development factor f_k = Σ obs(lag k+1) / Σ obs(lag k), over cells observed at both lags. Cumulative share of final, volume-weighted = Σ obs(lag k) / Σ final, over cells observed at lag k. Chain-implied share = Π_{j≥k} 1/f_j.

| lag k | US vw share of final | US f_k (k→k+1) | US chain-implied share | all-location vw share | all-location f_k |
|---|---|---|---|---|---|
| 0 | 0.907 | 1.060 | 0.921 | 0.907 | 1.060 |
| 1 | 0.960 | 1.009 | 0.976 | 0.960 | 1.008 |
| 2 | 0.967 | 1.004 | 0.984 | 0.967 | 1.004 |
| 3 | 0.968 | 1.004 | 0.987 | 0.968 | 1.004 |
| 4 | 0.971 | 1.004 | 0.992 | 0.970 | 1.004 |
| 5 | 0.973 | 1.002 | 0.995 | 0.973 | 1.002 |
| 6 | 0.975 | 1.002 | 0.998 | 0.974 | 1.002 |
| 7 | 0.975 | 1.001 | 0.999 | 0.975 | 1.001 |

Reading: the chain ladder (completion factor 1/0.921 ≈ 1.086 at lag 0 for the US) is more consistent across methods than the median-ratio factor. The median-of-ratios figure (1/0.906 = 1.10) is a per-cell median and sits close to it. The volume-weighted factors are the right ones for WIS, which is volume-weighted in the count scale.

Per-location tables (lags 0–2, volume-weighted and chain-implied) are in §7.

## 4. Where the persistent gap sits

US at lag 7 remains at 0.975 (volume-weighted) while the median state reaches 1.0 by lag 1–2. Medians hide the gap; it is concentrated in a few large states. Share of the total lag-k shortfall (final − observed, summed over states):

| lag | total gap (admissions, all cells) | Texas (48) | Michigan (26) | California (06) | Florida (12) | Pennsylvania (42) | top-5 total |
|---|---|---|---|---|---|---|---|
| 1 | 39,321 | 17.5% | 10.5% | 9.2% | 9.0% | 6.9% | 53% |
| 5 | 26,963 | 24.0% | 14.8% | 11.5% | 7.1% | 9.6% | 67% |
| 7 | 24,743 | 25.0% | 15.4% | 12.5% | 7.2% | 10.5% | 71% |

So the national residual is slow reporting in a handful of large jurisdictions (Texas and Michigan together give about 40% of it), not a broad slow tail. This matters for nowcasting: a national multiplier learned from the US total would over-correct small states and under-correct TX and MI.

## 5. Revision by lag, season and phase (clean cells)

Median ratio first report / final (finals ≥ 20):

| lag | all locations, median | US median | states-only vw share |
|---|---|---|---|
| 0 | 0.953 (n 3,560) | 0.906 | 0.909 |
| 1 | 1.000 | 0.963 | 0.961 |
| 2 | 1.000 | 0.972 | 0.968 |
| 3 | 1.000 | 0.974 | 0.969 |
| 4 | 1.000 | 0.976 | 0.972 |
| 5 | 1.000 | 0.977 | 0.974 |
| 6 | 1.000 | 0.977 | 0.976 |
| 7 | 1.000 | 0.979 | 0.976 |

Lag-0 medians by season (all locations; US in brackets): 2023-24: 1.000 (0.981); 2024-25: 0.909 (0.890); 2025-26: 0.920 (0.887). Lag 1 by season: 2023-24 1.000 (US 0.977); 2024-25 0.973 (0.950); 2025-26 0.988 (0.958). Lag 2: 1.000, 0.986 (0.961), 0.999 (0.979).

Caveat on 2023-24: a median of exactly 1.000 over 1,233 cells is unusually clean and may partly reflect how that season was recorded in the archive (publication timing). It is not verified against the NHSN source. Treat it as a regime I cannot fully explain, and do not use it as evidence that reporting was complete in 2023.

Lag-0 phase (phases from the mature final series, in-sample; median first/final): declining 0.946 (n 1,897), near peak ±2 weeks 0.945 (n 764), rising 0.974 (n 899). Lag 1: declining 1.000, near peak 0.988, rising 1.000. First reports are most incomplete near the peak and in decline. Phase is a label of the final series and is not available at forecast time.

## 6. Multiplier test: does a revision correction help? (log-error and relative error)

Method: lag-0 cells; for test season s, the multiplier (per-location median ratio, or global median) is fitted on the other seasons; prediction = obs / m. Errors are |log(pred+1) − log(final+1)| and |pred − final| / final.

| test season | method | n | median abs log err | mean abs log err | mean rel err |
|---|---|---|---|---|---|
| 2023-24 | raw | 1,233 | 0.020 | 0.047 | 0.045 |
| 2023-24 | global | 1,233 | 0.088 | 0.097 | 0.103 |
| 2023-24 | per-location | 1,233 | 0.086 | 0.110 | 0.120 |
| 2024-25 | raw | 1,139 | 0.096 | 0.166 | 0.152 |
| 2024-25 | global | 1,139 | 0.073 | 0.149 | 0.138 |
| 2024-25 | per-location | 1,139 | 0.060 | 0.139 | 0.130 |
| 2025-26 | raw | 1,177 | 0.084 | 0.137 | 0.117 |
| 2025-26 | global | 1,177 | 0.059 | 0.119 | 0.102 |
| 2025-26 | per-location | 1,177 | 0.053 | 0.113 | 0.097 |

Separate train-2024-25 → test-2025-26 (the strict forward test): raw median 0.084 / mean 0.137; per-location 0.053 / 0.104; global 0.072 / 0.109.

Reading:
- The correction is harmful in 2023-24, where lag-0 reports are already complete; it helps clearly in 2024-25 and 2025-26, the two seasons with the revision regime.
- The pooled LOSO result is therefore not a verdict on the correction; it is the mixture of a no-revision season and two revision seasons. The useful question is whether the regime can be detected in time.
- The per-location multiplier is better than global in both revision seasons, with a larger gain in the forward test (median log error 0.084 → 0.053).
- Mean log errors are larger than median log errors everywhere: the tail (small counts, large relative revisions) dominates, and it is what WIS penalises.
- Gating: the correction should be switched on only when recent as-published vintages show lag-0 shortfalls. That rule is untested here and is the pre-registration target (§8).

## 7. Per-location chain ladder and shortfall

Columns: n = cells with final ≥ 20; vw = volume-weighted share of final at lag k; cl = chain-implied share; med0 = median lag-0 ratio. Names from `location_name`. Puerto Rico (72) and the US are shown for reference.

| loc | name | n | vw lag0 | vw lag1 | vw lag2 | cl lag0 | cl lag1 | cl lag2 | med lag0 |
|---|---|---|---|---|---|---|---|---|---|
| 01 | Alabama | 96 | 0.920 | 1.003 | 1.003 | 0.908 | 0.997 | 0.997 | 0.969 |
| 02 | Alaska | 27 | 0.810 | 0.907 | 0.917 | 0.852 | 0.933 | 0.963 | 0.823 |
| 04 | Arizona | 100 | 0.915 | 0.981 | 0.973 | 0.734 | 0.813 | 0.831 | 0.985 |
| 05 | Arkansas | 67 | 0.837 | 0.931 | 0.958 | 0.858 | 0.950 | 0.978 | 0.891 |
| 06 | California | 145 | 0.890 | 0.953 | 0.956 | 0.920 | 0.987 | 0.990 | 0.907 |
| 08 | Colorado | 81 | 0.955 | 0.995 | 0.996 | 0.955 | 0.998 | 0.999 | 0.982 |
| 09 | Connecticut | 67 | 0.983 | 0.988 | 1.001 | 0.992 | 0.996 | 1.006 | 1.000 |
| 10 | Delaware | 43 | 0.797 | 0.858 | 0.854 | 0.927 | 0.990 | 0.997 | 0.909 |
| 11 | District of Columbia | 34 | 0.874 | 0.969 | 0.965 | 0.893 | 0.982 | 0.981 | 0.891 |
| 12 | Florida | 146 | 0.884 | 0.957 | 0.970 | 0.899 | 0.979 | 0.989 | 0.899 |
| 13 | Georgia | 105 | 0.861 | 0.963 | 0.980 | 0.860 | 0.967 | 0.984 | 0.900 |
| 15 | Hawaii | 51 | 0.909 | 0.964 | 0.991 | 0.928 | 0.990 | 0.996 | 0.947 |
| 16 | Idaho | 61 | 0.914 | 1.001 | 1.008 | 0.908 | 0.998 | 1.001 | 0.971 |
| 17 | Illinois | 102 | 0.922 | 0.966 | 0.974 | 0.924 | 0.969 | 0.977 | 0.929 |
| 18 | Indiana | 84 | 0.907 | 0.939 | 0.943 | 0.956 | 0.991 | 0.995 | 0.936 |
| 19 | Iowa | 59 | 0.914 | 0.972 | 0.980 | 0.914 | 0.976 | 0.982 | 0.929 |
| 20 | Kansas | 60 | 0.912 | 0.993 | 1.005 | 0.897 | 0.979 | 0.991 | 0.933 |
| 21 | Kentucky | 82 | 0.884 | 0.959 | 0.965 | 0.888 | 0.964 | 0.972 | 0.886 |
| 22 | Louisiana | 115 | 0.912 | 0.993 | 1.000 | 0.898 | 0.994 | 0.991 | 0.970 |
| 23 | Maine | 49 | 0.944 | 0.976 | 0.982 | 0.942 | 0.973 | 0.980 | 0.965 |
| 24 | Maryland | 72 | 0.899 | 0.958 | 0.976 | 0.912 | 0.971 | 0.986 | 0.933 |
| 25 | Massachusetts | 83 | 0.914 | 0.965 | 0.967 | 0.952 | 1.006 | 1.006 | 0.945 |
| 26 | Michigan | 100 | 0.870 | 0.880 | 0.877 | 0.980 | 0.987 | 0.988 | 0.927 |
| 27 | Minnesota | 71 | 1.014 | 1.013 | 0.997 | 0.972 | 0.991 | 0.993 | 1.000 |
| 28 | Mississippi | 82 | 0.912 | 0.961 | 0.967 | 0.932 | 0.989 | 0.994 | 0.943 |
| 29 | Missouri | 92 | 0.788 | 0.902 | 0.948 | 0.796 | 0.914 | 0.962 | 0.916 |
| 30 | Montana | 50 | 0.882 | 0.958 | 0.971 | 0.901 | 0.979 | 0.991 | 0.913 |
| 31 | Nebraska | 48 | 0.928 | 0.978 | 0.992 | 0.926 | 0.984 | 0.992 | 0.954 |
| 32 | Nevada | 79 | 0.914 | 0.982 | 0.988 | 0.920 | 0.990 | 0.994 | 0.956 |
| 33 | New Hampshire | 49 | 0.855 | 1.017 | 0.972 | 0.847 | 0.936 | 0.964 | 0.911 |
| 34 | New Jersey | 105 | 0.984 | 0.992 | 0.992 | 0.986 | 0.994 | 0.995 | 1.000 |
| 35 | New Mexico | 64 | 0.884 | 0.970 | 0.981 | 0.890 | 0.979 | 0.987 | 0.917 |
| 36 | New York | 116 | 0.898 | 0.968 | 0.985 | 0.895 | 0.968 | 0.984 | 0.922 |
| 37 | North Carolina | 89 | 0.942 | 0.988 | 0.990 | 0.949 | 0.992 | 0.994 | 0.983 |
| 38 | North Dakota | 43 | 0.980 | 1.007 | 1.003 | 0.974 | 1.001 | 0.996 | 0.973 |
| 39 | Ohio | 90 | 0.944 | 0.988 | 0.981 | 0.944 | 0.989 | 0.993 | 0.958 |
| 40 | Oklahoma | 69 | 0.809 | 0.928 | 0.962 | 0.816 | 0.931 | 0.966 | 0.877 |
| 41 | Oregon | 68 | 0.818 | 0.942 | 0.964 | 0.819 | 0.953 | 0.973 | 0.843 |
| 42 | Pennsylvania | 146 | 0.936 | 0.963 | 0.967 | 0.964 | 0.988 | 0.993 | 0.986 |
| 44 | Rhode Island | 42 | 0.878 | 0.913 | 0.934 | 0.903 | 0.929 | 0.953 | 0.912 |
| 45 | South Carolina | 77 | 0.953 | 0.981 | 0.990 | 0.954 | 0.984 | 0.992 | 0.977 |
| 46 | South Dakota | 41 | 0.886 | 0.954 | 0.972 | 0.886 | 0.956 | 0.975 | 0.952 |
| 47 | Tennessee | 129 | 0.957 | 0.993 | 0.998 | 0.956 | 0.994 | 0.997 | 0.981 |
| 48 | Texas | 141 | 0.885 | 0.915 | 0.918 | 0.965 | 0.994 | 0.997 | 0.906 |
| 49 | Utah | 45 | 0.950 | 0.989 | 0.989 | 0.956 | 0.993 | 0.995 | 0.984 |
| 50 | Vermont | 32 | 0.877 | 0.952 | 0.967 | 0.890 | 0.966 | 0.981 | 0.898 |
| 51 | Virginia | 99 | 0.927 | 0.970 | 0.979 | 0.928 | 0.972 | 0.980 | 0.959 |
| 53 | Washington | 86 | 0.995 | 1.011 | 1.024 | 1.024 | 1.043 | 1.040 | 0.996 |
| 54 | West Virginia | 56 | 0.952 | 0.986 | 0.994 | 0.954 | 0.988 | 0.997 | 0.998 |
| 55 | Wisconsin | 69 | 0.947 | 0.979 | 0.983 | 0.948 | 0.983 | 0.986 | 0.973 |
| 56 | Wyoming | 37 | 0.957 | 0.997 | 1.002 | 0.952 | 0.995 | 1.000 | 1.000 |
| 72 | Puerto Rico | 135 | 0.809 | 0.859 | 0.857 | 0.848 | 0.890 | 0.905 | 0.986 |
| US | US | 147 | 0.907 | 0.960 | 0.967 | 0.921 | 0.976 | 0.984 | 0.905 |

Notes on the table:
- Chain-implied factors are unstable where development factors are estimated on few cells (e.g. Arizona 04 lag 0 0.734 vs vw 0.915; Michigan 26 lag 0 0.980 vs vw 0.870). Use the volume-weighted column for corrections, and treat the chain column as a cross-check only.
- Several small states have vw shares above 1 at lag 1–2 (Minnesota 27, Idaho 16, Washington 53): the first report was higher than the final in some weeks. Both directions occur.
- Texas 48 and Michigan 26 have the largest volume-weighted gaps at lag 1–2 (0.915, 0.880) and are the main drivers of the national residual (§4).
- Puerto Rico's lag-0 median (0.986) is not representative of its volume-weighted share (0.809): a few large weeks dominate. PR is not part of the US total's revision.

## 8. Implications and ranked experiments

Implications for our models:
1. **Model 1 (EAKF).** The filter assimilates the first report as if it were complete. Nationally the newest week is about 9% low; the volume-weighted development factor from lag 0 to 1 is 1.06. An observation error for lag 0 larger than for lag ≥ 1 is the direct test. The effect should be largest in the most-revised states (TX, MI, CA, FL, PA carry about 70% of the residual).
2. **Model 2 (GBQR).** Its training rows at lag 0 are first reports. Dropping or nowcasting the most recent 1–2 training weeks is a cheap test.
3. **Scoring.** If scoring truth is taken at first publication of the latest week, it is biased low by about 9% nationally; shadow scoring should also report against the next-week vintage.
4. **Corrections should be per location and gated.** Global multipliers over-correct small states; the national residual is concentrated in TX and MI.

Track A (for submission):
1. **Lag-aware observation error in EAKF** for the most recent week. Pre-register: observation SD for lag 0 scaled by the per-location volume-weighted lag-0 share (§7). Test: as-of replay, leave-one-season-out, 2023-24 and 2024-25 development, h=0..3 relWIS vs current EAKF. Stop if no gain at h=0 and h=1.
2. **Drop lag-0 GBQR training rows** (or nowcast them). Same test design.

Track B (shadow only):
3. **Gated per-location multiplier.** Apply the volume-weighted lag-0 factor only when the last 4–8 as-published vintages show a shortfall above a threshold chosen on 2023-24 alone; evaluate on 2024-25 then 2025-26 (forward test). Benchmark: raw (median abs log error 0.020 in 2023-24, 0.096 in 2024-25, 0.084 in 2025-26). The gate is the untested part.
4. **NobBS** as a nowcast of the latest 1–2 weeks, built only from the as-published archive (lags 0–7). NobBS was described in its PLOS paper as more robust than heuristic approaches under time-varying delays (dengue and ILI).
5. **epinowcast** (renewal-process nowcast, partial pooling across locations) as a shadow model. Benchmark run time first.

## 9. Failure modes and limits

- The 2023-24 season shows no lag-0 shortfall (median 1.000). I did not verify this against NHSN; it may reflect the archive's publication timing for that season. It drives the pooled LOSO result (§6), which is why the forward test is reported separately.
- Vintage cadence is sparse (15, 22, 33, 35 as-of dates per year). Lag-1 to lag-11 cells come from re-published weeks only, so the number of cells differs by lag; counts are shown in §3 and §6.
- Finals are the last vintage (12+ weeks old). A real but slow revision after 12 weeks would be invisible here.
- Phase labels use the final series (look-ahead); they describe where revision is large, not a forecast-time feature.
- The ED-visit target (`wk inc flu prop ed visits`) was not analysed; its archive differs and needs its own check.
- Small counts: ratios are noisy below 20 admissions, and the mean relative error is dominated by a few small-count cells.

## 10. Costs (4-CPU, 30-minute budget)

- Lag-aware EAKF observation error and dropping recent GBQR training rows: negligible.
- Gated per-location multiplier: well under 1 second per week (table arithmetic on the archive).
- NobBS per week (53 locations, MCMC): seconds to minutes per location; benchmark before adopting.
- epinowcast per week (53 locations, Stan): likely several minutes with pooling; benchmark.

## 11. References and verification status

- McGough SF, Johansson MA, Lipsitch M, Menzies NA. "Nowcasting by Bayesian Smoothing: A flexible, generalizable model for real-time epidemic tracking." PLOS Computational Biology 16(4): e1007735 (2020). Opened as the PLOS article page summary and the NobBS CRAN package DOI (10.32614/cran.package.nobbs). Author order from search summaries: [unverified].
- epinowcast: github.com/epinowcast/epinowcast and package.epinowcast.org (opened as search summaries). The Abbott–Sherratt–Funk–Hickson 2024 paper I was asked to check was not located: [unverified].
- Chain-ladder and reporting-triangle methods: standard in claims and infectious-disease nowcasting; no source was opened for this report: [unverified].
- Data: `flusight-forecast-hub/target-data/time-series.csv` (local copy, opened and analysed).

## 12. Top recommendations (for Main)

1. Treat the newest admission as a biased observation: about 9% low nationally at first report and about 2.5% still missing at lag 7, concentrated in Texas, Michigan and California. Test a larger lag-0 observation error in EAKF and a drop of lag-0 GBQR training rows, as-of replay only.
2. Correct per location, not nationally, and gate the correction on recent evidence. A global multiplier over-corrects small states; a per-location one cuts the median log error by about 37% in the forward test (2025-26: 0.084 → 0.053), but it is harmful in the no-revision season (2023-24).
3. Score shadow models against the next-week vintage as a sensitivity check.
4. Benchmark NobBS or epinowcast run time before adding either to the weekly job.
5. Expect near-peak weeks to carry the largest unrevised gap; phase-aware calibration should use the lag-0 shortfall as an input, not as a constant.
