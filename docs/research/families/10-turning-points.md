# Family 10: Turning points, predictability limits, early warnings, changepoints, regimes, peak and rate-change targets

Scope: how far ahead the turning points of a flu season (onset, peak timing, peak size, end of rise) are predictable; early-warning signals (EWS); changepoint and regime methods; the hub's peak and rate-change targets; and a phase analysis of the FluSight ensemble's bias. Written against `PROBLEM_BRIEF.md` (2026-11-25). No look-ahead was used in any experiment reported as a result of the forecasting type; the phase analysis in section 6 is diagnostic and uses hindsight (see caveats).

## 0. Why this family matters here

The brief's lever 1 says peaks and declines decide most of the score. Our own tables agree: model 1 runs low in declines (its post-peak fall is too steep), model 2 runs low in rises, and the ensemble's relWIS in peak-adjacent weeks is the worst of the three phases (section 6). Any turning-point method must therefore beat a phase-blind reference, and the test is not "does it find the peak" but "does it reduce WIS in the phases where the current models fail, without hurting the others".

## 1. Predictability limits

### 1.1 Theory
For a stochastic SIR-type process, the forecast distribution of any future quantity is a function of the current state estimate and the process noise. Two limits matter:

- **Intrinsic (stochastic) limit.** Early in an outbreak, demographic noise dominates. Drake (2006) shows that for directly transmitted diseases the coefficient of variation (CV) of final outbreak size is above 1 for subcritical outbreaks unless the removal rate exceeds about 2.41 times the effective contact rate, and remains large for delayed-onset interventions. Final size is therefore intrinsically noisy; timing and early growth are less noisy than size [Drake 2006].
- **Dynamical (chaos / sensitivity) limit.** Realistic (non-exponential) infectious-period distributions and seasonal forcing destabilise SIR dynamics and make incidence more irregular and chaotic, shrinking the horizon over which the trajectory is predictable [Lloyd 2001]. Scarpino and Petri (2019) use permutation entropy as a model-independent measure and report an entropy barrier to time-series predictability of outbreaks [Scarpino & Petri 2019, verified via search summary].

Uncertainty: a forecast distribution for the peak is the push-forward of the posterior over state and parameters through the model, plus observation noise. Its spread should contract as the season progresses (less time to amplify errors) and expand with horizon.

### 1.2 Application here
- Our observed data: national NHSN admissions, weekly, with the latest 1–2 weeks revised (first reports ~96% of final nationally, ~89% in 2025-26; `PROBLEM_BRIEF.md` §2). Data noise at the turning point is therefore comparable to the signal in the week that matters most.
- The 2026-27 season is early: 13.7k on 2026-11-21 and rising. The horizon to a peak is unknown; the forecast horizon (0–3 weeks) is short relative to the uncertainty of peak timing, so the predictability limit binds on peak week, not on the next 2–3 weeks.
- Practical consequence: peak-week (`peak week inc flu hosp`) predictions should be probabilistic over several weeks, not a point; the rate-change target (`wk flu hosp rate change`) is the natural short-horizon version of the same question.

### 1.3 Evidence
- Reich et al. 2019, PLoS Comput Biol 15(11):e1007486: real-time multi-model ensemble forecasts for the FSNetwork 2017/18 season. Reich et al. 2019, PNAS 116(8):3146–3154 (DOI 10.1073/pnas.1812594116): 22 models over 7 seasons. These are separate papers; findings are cited per paper [verified via search summaries].
- Shaman & Karspeck (2012): an EAKF-driven SIRS model predicted NYC peak timing up to ~7 weeks ahead retrospectively, with ensemble spread as a confidence signal [PNAS 2012, DOI 10.1073/pnas.1208772109]. Peak timing skill is nonzero far ahead; peak size skill is much lower. Retrospective, single-city, pre-hub.
- Brooks et al. (2018): nonmechanistic one-week-ahead delta densities, chained into trajectories, with adaptive weights, placed top in the 2015/16 FluSight comparison [PLOS CB 2018, DOI in PMC6034894; verified via search summary].

### 1.4 Failure modes
- Peak timing is a flat-topped target near the maximum; WIS for peak week is dominated by the discrete week choice and by data revisions around the peak (Reich et al. note a revision-driven failure in one region).
- A horizon-based skill curve computed on the 3 seasons we have will be dominated by 2 large seasons (2024-25 peak 55.5k; 2025-26 peak 42.5k) and one small one (2023-24, 21.7k). Peak-size skill cannot be established on 3 seasons.

### 1.5 Cost
Negligible. A bootstrap of peak week from the ensemble of trajectories is O(M·T) per location.

## 2. Early-warning signals (EWS)

### 2.1 Theory
Scheffer et al. (2009) argue that systems approaching a fold bifurcation show critical slowing down: recovery from perturbations slows, which appears as rising lag-1 autocorrelation and variance in the detrended series [Scheffer et al. 2009, Nature 461:53, verified via search summary]. Dakos et al. (2012) benchmark metric EWS (variance, lag-1 AR, skewness, kurtosis, spectral reddening) and model-based EWS on simulated data; no single indicator wins, detrending and window choice dominate results, and false alarms are common [Dakos et al. 2012, PLoS ONE 7:e41010, verified via search summary]. Scheffer et al. (2012) extend this to spatial and network indicators [Science 338:344, verified via search summary].

Uncertainty: EWS are not probabilities; the usable output is a rank of rising risk. Calibrate it with a hit/false-alarm curve on past seasons, never on a single season.

### 2.2 Application
Flu epidemic peaks are not a fold bifurcation of a slow variable. They are driven by forcing (season, immunity, strain) and by the depletion of susceptibles, so classical CSD does not clearly apply. The plausible use is narrower: a rising autocorrelation/variance of the growth rate of admissions as a warning that a peak is near, which is what the phase analysis (section 6) needs.

### 2.3 Evidence
No hub team reports a CSD method (keyword search of `model-metadata/*.yml` for "early warning" and "critical slowing" found none; the regime/peak keyword hits are listed in section 5.4). Ecological EWS evidence is simulated; no peer-reviewed real-data flu CSD validation was found in the searches run.

### 2.4 Failure modes
Detrending removes the signal it is meant to find; window length trades lag against noise; a seasonal rise is a non-stationarity that triggers variance and autocorrelation rises by construction. Revisions raise recent variance artificially.

### 2.5 Cost
Negligible.

## 3. Changepoints

### 3.1 Theory
- **Offline, penalised (PELT).** Minimise the sum of segment costs plus a penalty per changepoint over all partitions. Killick, Fearnhead and Eckley (2012) give an exact solution with (under conditions) linear expected cost [JASA 107:1590, verified via search summary; arXiv:1101.1438].
- **Online, Bayesian (BOCD).** Maintain the posterior over the run length r_t (time since the last changepoint), with a hazard H(τ) for resets and a predictive density for the segment. Adams and MacKay (2007) give the exact recursion and predictive density under a conjugate model [arXiv:0710.3742, verified via search summary]. The predictive density gives a forecast mixed over the run-length posterior, which is the right object for forecasting after a turn.

### 3.2 Application
- BOCD is the only one of these usable in real time. Apply it to the log-growth of admissions (or to log rate per 100k of the ED fraction, from the NSSP input). A changepoint means "growth sign changed"; the predictive density then mixes "continues rising" and "turned" with posterior weights, which is exactly a phase-aware forecast.
- PELT is for retrospective phase labelling in backtests (no look-ahead only if run on data available as-of, i.e., use the as-of vintages in `time-series.csv`).

### 3.3 Evidence
Not hub-tested; FluSight-type evidence on changepoint forecasts is absent in the hub metadata. The method is standard in finance and biomedicine.

### 3.4 Failure modes
Penalty choice (the number of changes is set by it); the most recent changepoint is unstable (BOCD posterior on r_t is poorly identified for the last 2–3 weeks, exactly when it matters); revisions create spurious changepoints in the last 2 weeks unless the model uses as-of data.

### 3.5 Cost
O(n) per location per week. Trivial.

## 4. HMM regimes

### 4.1 Theory
A discrete-state HMM with states s_t ∈ {1..K} (e.g. non-epidemic, rising, peak, declining), transition matrix A, and state-dependent emissions. Rabiner (1989) gives the forward, Viterbi and Baum-Welch algorithms [Proc. IEEE 77:257, verified via search summary]. Uncertainty over the regime is the forward posterior P(s_t | y_1..t) (filtering) or the smoothed posterior (retrospective only).

### 4.2 Application
- Use a 3-state Gaussian (or negative-binomial) HMM on the weekly growth of log admissions, pooled across locations with location-specific emission means, to produce the phase probabilities used as a mixture weight over our two models' predictions. Filtering uses only as-of data.
- Two-stage use: (a) phase posterior as a gating variable for ensemble weights (Family 08 combiners); (b) phase posterior as an input to the rate-change pmf.

### 4.3 Evidence
- Rath, Carreras and Sebastiani (2003) fit an HMM with an exponential-Gaussian mixture emission to classify influenza epidemic and non-epidemic weeks [IDA 2003, DOI 10.1007/978-3-540-45231-7_48, verified via search summary].
- A comparison on Iran SARI data (Transbound Emerg Dis, DOI 10.1111/tbed.13912) found an autoregressive HMM detected epidemic weeks with higher sensitivity (92.9%) than HMM alone (66.7%), and matched well-tuned Serfling thresholds [verified via search summary]. Neither is a forecasting test.
- No FluSight hub model in the metadata grep describes an HMM regime model (see 5.4).

### 4.4 Failure modes
Number of states is not identified from short data (we have ~4 seasons, each with one peak); state labels drift between seasons; the emission means differ strongly by location (rates range widely), so pooled emissions must be on standardised growth.

### 4.5 Cost
K=3-4 states, forward filter: negligible; Baum-Welch on 53 locations × ~10 seasons of weekly growth: seconds.

## 5. Peak and rate-change targets

### 5.1 What the hub asks
- `peak week inc flu hosp`: pmf over season weeks; 27 teams in the hub archive have submitted this target (counted from `model-output/*/*.csv`).
- `peak inc flu hosp`: quantiles of the season's peak weekly count; 28 teams.
- `wk flu hosp rate change`: pmf over large_decrease, decrease, stable, increase, large_increase, for horizons 0–3 relative to the last observed week; 61 teams. Thresholds (hub `model-output/README.md` lines ~388–390): "stable" if the rate change is below 0.3 per 100k OR the count change is below 10; "increase" if positive, not stable, and below 1.7 per 100k; the remaining thresholds are in the same appendix and were not re-read here.
- We submit none of these. The brief calls them unclaimed. The hub count is the realistic competition: 27–28 teams on peak targets, so a ranking exists.

### 5.2 Theory for the pmf targets
The rate-change pmf is a discretisation of the predictive distribution of the change in rate. Given a quantile forecast of the level (ours), the pmf is the induced mass over the threshold bins, and the proper score is the log or Brier score. Peak week is a discrete distribution; the natural construction is the first-passage time of the trajectory's maximum over the ensemble of sample paths. Peak size is the maximum over the same paths.

### 5.3 Application
- Derive rate-change and peak-week pmfs from our existing sample paths (EAKF members, GBQR quantiles via a Gaussian copula or from a quantile-to-sample conversion), so there is no separate model to fit. Cost: a few seconds per week.
- Peak size is the best-supported of these given the ensemble phase bias (section 6): the ensemble under-predicts peak-week counts by a median of about 43% (log ratio −0.56), so any peak-size quantile from the ensemble is biased low.

### 5.4 Hub evidence on methods
Keyword search of `model-metadata/*.yml` for regime, peak and changepoint terms returned 27 files. Peak-specific teams include UMass-peakGB ("Gradient-boosted forecasts of peak week and peak size"; trained on NHSN, ILINet, FluSurv-NET) and influcast-peak_gbm; PSI-PROF (SIR-H² with time-varying transmission, MCMC). Other hits are ensembles mentioning "peak" in passing. No hub team describes EWS, BOCD or HMM regimes in the metadata scanned.

### 5.5 Failure modes
Peak targets are scored on very few effective observations (one peak per season per location, 3 seasons); pmfs on rate change are sensitive to the threshold and the 1.7/100k cutoff at low rates (where count threshold dominates). Local peaks are noisy and the national peak is the only one that matters much in WIS.

### 5.6 Cost
Negligible given existing sample paths.

## 6. Phase analysis of the FluSight ensemble (diagnostic)

### 6.1 Method
- Data: hub `model-output/FluSight-ensemble/` (92 weekly files), target `wk inc flu hosp`, location US, quantile 0.05/0.25/0.5/0.75/0.95, horizons h=−1..3 (aligned on `target_end_date`); truth from `target-data/target-hospital-admissions.csv` (latest vintage).
- Seasons: 2023-24, 2024-25, 2025-26 (reference dates Sep–May). 2026-27 is excluded (truth incomplete).
- Phase of target week t, defined relative to the national truth peak P of each season: rising if t < P − 2 weeks; peak if |t − P| ≤ 2 weeks; declining if t > P + 2 weeks. Peaks: 2023-12-30 (21.7k), 2025-02-08 (55.5k), 2026-01-03 (42.5k).
- Bias: log ratio of ensemble median to truth, log((q50+1)/(y+1)). Coverage: share of truths inside the 50% and 90% intervals.
- Script: throwaway, `/tmp/r10/phase.py`, output `/tmp/r10/us_phase_rows.csv`. Analysis uses h=0..3 only (h=−1 excluded). Each target week appears under up to ~5 reference dates, so tables report rows and distinct target weeks; CIs are a season-block bootstrap over three seasons.

### 6.2 Results

Median log-ratio (ensemble ÷ truth), horizons 0–3 only. Rows = target × reference date. Weeks = distinct target weeks. CI = 95% season-block bootstrap (resample the three seasons, 2000 draws); with three seasons this is a rough interval only.

| Phase | Rows | Weeks | Median log-ratio | 95% CI | Cov50 |
|---|---|---|---|---|---|
| rising | 70 | 22 | −0.35 | [−0.50, −0.27] | 0.23 |
| peak ±2 | 56 | 15 | −0.36 | [−0.41, −0.33] | 0.18 |
| declining | 214 | 58 | −0.02 | [−0.09, 0.05] | 0.67 |

Per season (rows / weeks / median log-ratio):

| Season | Rising | Peak ±2 | Declining |
|---|---|---|---|
| 2023-24 | 30 / 9 / −0.27 | 20 / 5 / −0.33 | 70 / 19 / +0.05 |
| 2024-25 | 30 / 9 / −0.50 | 16 / 5 / −0.41 | 62 / 17 / −0.09 |
| 2025-26 | 10 / 4 / −0.38 | 20 / 5 / −0.35 | 82 / 22 / −0.05 |

Phase × horizon (median log-ratio):

| Phase | h=0 | h=1 | h=2 | h=3 |
|---|---|---|---|---|
| rising | −0.22 | −0.32 | −0.54 | −0.74 |
| peak ±2 | −0.13 | −0.31 | −0.47 | −0.68 |
| declining | −0.06 | −0.06 | +0.01 | +0.10 |

### 6.3 Reading
1. The ensemble is **low in rising and peak weeks in all three seasons**: median −0.35 in both phases over horizons 0–3 (season-block 95% CI about −0.50 to −0.27 for rising, −0.41 to −0.33 for peak±2). Its 50% intervals cover the truth in under a quarter of rows. This is the same direction as model 2's known failure (low in rises).
2. In declines the ensemble is roughly unbiased at h=0–1 (−0.06) and slightly high at h=2–3 (+0.01, +0.10). Model 1's documented failure is the opposite (declines too steep). Combining models with opposite phase errors (brief lever 4) is the simplest test of this.
3. Horizon compounds the rising bias: the rising-phase median goes from −0.22 at h=0 to −0.74 at h=3. The h=0 peak bias (−0.13) is small; the nowcast looks reasonable and the forecast drifts.
4. Signs are consistent across seasons in rising and peak phases (rising −0.27, −0.50, −0.38; peak −0.33, −0.41, −0.35), but each season contributes only 4–9 distinct weeks per phase.

### 6.4 Caveats (honest)
- Hindsight phase: the phase uses the realised peak. A real-time rule would use only as-of data (e.g. sign of 3-week log growth). The bias by real-time phase is what matters for a correction; the table above is the upper bound on what a perfect phase detector could recover.
- Three seasons; 9–22 distinct target weeks per phase pooled. The 2025-26 rising phase has 4 distinct weeks (10 rows).
- Truth is the latest vintage, not as-of. Recent rises are likely under-reported in as-of data, which would make the true rising-phase bias look different in real time. Revision analysis belongs to Family 06.
- Ensemble membership varies across weeks (the ensemble file is the hub's computed median over designated submissions); the bias is for that object, not for any one team.
- The ensemble is a benchmark; some of this bias is common to all models and may be the data, not the methods. Model 1's declining-phase failure does not appear in the ensemble, so the two are not the same bias.

## 7. Ranked experiments

Pre-registration: write the criteria in `docs/research/SHADOW_PROTOCOL.md` before any run. Dev seasons are 2023-24 and 2024-25, leave-one-season-out. 2025-26 is the holdout and is used up for both models (brief §6.2); it may be used once more only for descriptive checks. Every real-time test uses as-of vintages (`time-series.csv`) and the truth available at the scoring date.

1. **[Track A, strong evidence needed] Real-time phase gating of the ensemble.** Define the phase at forecast date R as sign and size of the 3-week log growth of as-of admissions (rising if > +0.05/week, declining if < −0.05/week, else peak). Apply a phase-specific additive log shift to the ensemble quantiles, estimated leave-one-season-out on the other dev season only. Compare WIS (per location-horizon, national and pooled) with the unshifted ensemble, using block bootstrap over reference dates and Diebold-Mariano with HAC variance. Pass only if the shift improves pooled relWIS on both held-out seasons and the sign of the shift matches the other season. Test is a complete, offline backtest; no shadow needed for the decision to test.
2. **[Track B, shadow] BOCD on log-growth of admissions**, used as a mixture weight between "continues" and "turned" predictive densities from our EAKF and GBQR. Shadow-run weekly; score relWIS vs EAKF and vs ensemble, with a pre-registered minimum of 8 weeks in the rising and peak phases combined.
3. **[Track B, shadow] 3-state HMM filter on weekly growth (pooled, standardised emissions)** giving phase probabilities; use as a gating variable for the two-model mixture (brief lever 4). Pre-register: the gated mixture must beat the equal linear pool in the rising and peak phases on dev seasons (leave-one-out) before it enters shadow.
4. **[Track A, if 1 passes] Peak-size quantiles from the ensemble-bias correction.** Because the ensemble is biased low by ~43% at the peak, test whether a peak-size correction (multiply the ensemble's peak-size quantiles by a leave-one-season-out factor) improves `peak inc flu hosp` WIS on the dev seasons. Only submit if the factor is stable across the two dev seasons.
5. **[Track B, offline] Predictability curve.** For each dev season, compute the WIS of peak week and peak size as a function of weeks before the realised peak, for our two models and the ensemble, as-of data only. Output: the horizon at which peak-week skill appears. Purpose: decide how far ahead the peak pmf is worth publishing. No pass/fail; descriptive, pre-registered output.
6. **[Track B, offline] Rate-change pmf from sample paths.** Build the 5-category pmf from existing EAKF sample paths and from GBQR quantiles; score by log and Brier against the hub's category rule (README thresholds). Compare with the 61-team hub distribution on the same weeks if as-of team files exist.

Not recommended now: CSD/EWS indicators (no mechanism match for a forced seasonal epidemic; expected false alarms dominate on 3 seasons).

## 8. Cost on the weekly budget (4 CPUs, 30 minutes)
- Phase classification (3-week growth rule, BOCD, 3-state HMM filter): under 5 seconds for 53 locations.
- Peak and rate-change pmfs from existing sample paths: under 10 seconds.
- Ensemble-phase shift (experiment 1): a lookup table; under 1 second.
- Backtests (offline): PELT and EM fits on 4 seasons × 53 locations: minutes on one CPU.

## 9. References

All checked by web search (page summaries); full texts were not read. None are marked unverified. Where a summary disagreed with the citation (Reich 2019 was returned once as PNAS and once as PLOS CB), both were checked and listed separately.

- Adams, R.P. & MacKay, D.J.C. (2007). Bayesian Online Changepoint Detection. arXiv:0710.3742. https://arxiv.org/abs/0710.3742 (verified via search summary)
- Brooks, L.C., Farrow, D.C., Hyun, S., Tibshirani, R.J., Rosenfeld, R. (2018). Nonmechanistic forecasts of seasonal influenza with iterative one-week-ahead distributions. PLoS Comput Biol 14(6):e1006134. PMC6034894. (verified via search summary)
- Dakos, V. et al. (2012). Methods for detecting early warnings of critical transitions in time series illustrated using simulated ecological data. PLoS ONE 7(7):e41010. (verified via search summary)
- Drake, J.M. (2006). Limits to forecasting precision for outbreaks of directly transmitted diseases. PLoS Med 3(1):e3. (verified via search summary)
- Killick, R., Fearnhead, P., Eckley, I.A. (2012). Optimal detection of changepoints with a linear computational cost. JASA 107(500):1590–1598. DOI 10.1080/01621459.2012.737745; arXiv:1101.1438. (verified via search summary)
- Lloyd, A.L. (2001). Destabilization of epidemic models with the inclusion of realistic distributions of infectious periods. Proc R Soc B 268:985. DOI 10.1098/rspb.2001.1599. (verified via search summary)
- Rabiner, L.R. (1989). A tutorial on hidden Markov models and selected applications in speech recognition. Proc IEEE 77(2):257–286. (verified via search summary)
- Rath, T.M., Carreras, M., Sebastiani, P. (2003). Automated detection of influenza epidemics with hidden Markov models. IDA 2003, LNCS. DOI 10.1007/978-3-540-45231-7_48. (verified via search summary)
- Reich, N.G. et al. (2019). Accuracy of real-time multi-model ensemble forecasts for seasonal influenza in the U.S. PLoS Comput Biol 15(11):e1007486. (verified via search summary)
- Reich, N.G. et al. (2019). A collaborative multiyear, multimodel assessment of seasonal influenza forecasting in the United States. PNAS 116(8):3146–3154. DOI 10.1073/pnas.1812594116. (verified via search summary)
- Scarpino, S.V. & Petri, G. (2019). On the predictability of infectious disease outbreaks. Nat Commun 10:898. DOI 10.1038/s41467-019-08616-0. (verified via search summary; title and DOI only)
- Scheffer, M. et al. (2009). Early-warning signals for critical transitions. Nature 461:53–59. DOI 10.1038/nature08227. (verified via search summary)
- Scheffer, M. et al. (2012). Anticipating critical transitions. Science 338:344–348. DOI 10.1126/science.1225244. (verified via search summary)
- Shaman, J. & Karspeck, A. (2012). Forecasting seasonal outbreaks of influenza. PNAS 109(50):20425–20430. DOI 10.1073/pnas.1208772109. (verified via search summary)
- Transbound Emerg Dis: "Detection of influenza epidemics using hidden Markov and Serfling approaches". DOI 10.1111/tbed.13912. (verified via search summary; year not confirmed)

Hub files cited: `model-output/FluSight-ensemble/*.csv`, `target-data/target-hospital-admissions.csv`, `model-output/README.md` (rate-change appendix, lines ~388–390), `model-metadata/UMass-peakGB.yml`, `model-metadata/influcast-peak_gbm.yml`, `model-metadata/PSI-PROF.yml`.
