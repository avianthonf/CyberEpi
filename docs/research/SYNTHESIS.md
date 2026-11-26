# Synthesis: ranked experiments across the 13 family reports

Date: 2026-11-26. Inputs: `docs/research/families/01`–`13` (ranked sections cited as `[NN §x]`), `ARCHIVE_ANALYSIS.md`, `HANDOFF.md`, `SHADOW_PROTOCOL.md`, `backtest/shadow.py`. Next submission: 2026-12-02 (reference date 2026-12-05).


Scope note: report 13 §8 says its Track A tests have "no 2025-26 holdout" but then runs LOSO over 2023-24, 2024-25 and 2025-26. That conflicts with the spent-holdout rule used everywhere else. For any decision in this document, use 2023-24 and 2024-25 only; 2025-26 may appear only as "already seen" in descriptive output. Power figures follow report 13 §6 (21–24% at T = 20).

## 0. Rules this ranking applies

- **Track A (submission changes)** rests only on pre-registered leave-one-season-out (LOSO) tests on 2023-24 and 2024-25, using as-of data at each reference date. The 2025-26 holdout is spent and informs no choice. A candidate must win on both dev folds separately.
- **Track B (lab)** runs in shadow mode on 2026-27 data. Power limit [13 §6]: with the protocol's T = 20 live weeks, the minimal detectable relWIS gap is about 21–24% (pooled σ, optimistic). Equal-weight-style comparisons with 5–10% effects cannot be resolved live. So Track B picks should be large-effect, cheap, or structurally distinct (different phase behaviour), and the shadow gate must not be read as a test of small gains.
- **Shrink to equal weights.** Any learned combiner weight is shrunk to equal weights [08 §6–8; ARCHIVE_ANALYSIS]. No method type beats the ensemble on the archive: pooled medians are 1.08–1.35 times the FluSight-ensemble WIS, and only 8–30% of covered models beat it in pooled rows (ARCHIVE_ANALYSIS, season table).
- **Dedupe.** `CyberEpi-MIX_QA` and `CyberEpi-MIX_LP` are already in `backtest/shadow.py` [08 §8.1; 12 E1]. They are not re-listed as new work; they are the reference for the combiner items below.
- **Frozen spending.** Any experiment that used 2025-26 for selection (e.g. the per-location gate in [06 §8.3]) is reported as "already seen" only.

## 1. Cross-cutting findings and how they are reconciled

| Finding | Source | Reconciliation |
|---|---|---|
| The FluSight ensemble is low in rising and near-peak weeks: median log ratio ≈ −0.35 over h=0–3, same sign in all three seasons; 50% intervals cover under a quarter of rows. Declines are roughly unbiased (−0.06 at h=0–1; +0.10 at h=3). | [10 §6.3] | Phase is hindsight-defined; real-time phase must come from as-of growth [10 §6.4]. |
| Model 2 (GBQR) is low in rises. | [04 §6 E1; 04 §9] | Same direction as the ensemble. Partly a data artefact: its lag-0 training rows are first reports. |
| Model 1 (EAKF) is too steep in declines (the opposite phase error). | [02 §6; 02 §8] | Diagnosis is a median bias, not width. Candidate causes, untested: forward Rt random walk with no reversion (D-3), ED observation intercept (D-2), infection-to-admission delay kernel (§3.3), S depletion. D-0 removed forward β noise only and did not settle it [02 §8.1–3]. |
| The first report of the newest week is ~9% low nationally (volume-weighted lag-0→1 factor 1.06); about 2.5% still missing at lag 7; concentrated in TX, MI, CA. Revisions ≈ 0.91 of final in the US first report. | [06 §8, §12] | This plausibly explains part of the rise bias in models 1 and 2 and the ensemble. Lag-aware observation error must be tested before any structural change is credited. |
| Opposite phase errors: model 1 low-decline, ensemble and model 2 low-rise. | [10 §6.3 item 2; 12 E1] | Motivates the equal-weight pool of models 1 and 2 (already MIX_QA/MIX_LP in shadow) and a phase-gated shift. Neither is a learned weight. |
| No method type beats the ensemble. | [ARCHIVE_ANALYSIS] | Any combiner with learned weights is shadow-only; equal weights are the default. |
| Delphi v5 as-of archives are available (snapshot and report_time_query). V4 is frozen for 2026-27 and ~7 epiweeks behind. | [09 §5, §6, Top-5 item 1] | All as-of pulls must use V5. Prerequisite for every ILI/NSSP/NHSN experiment. |
| 20-week live gate cannot resolve 5–10% gaps. | [13 §6–8] | Track A evidence = dev LOSO with block bootstrap [12 Part 3]. Track B gate is a flag, not a pass/fail on small effects. |

Unresolved disagreement: [10 §6.3 item 4] suggests the rise bias is common to all models, so it may be the data rather than the methods. Test [06 Track A #1] before concluding that any model's structure causes it.

## 2. Track A: submission changes (ranked, deduped)

Each is a candidate only. None is adopted on the current evidence. Cost is the weekly CPU added, per reports; "[unmeasured]" means the report gave only an estimate.

| # | Item | Source(s) | Hypothesis | Exact test (dev, LOSO, as-of) | Weekly CPU | Expected effect / pass rule |
|---|---|---|---|---|---|---|
| A0 | Vintage audit of ED (NSSP) and admissions (NHSN) inputs for every forecast date | [03 E0; 09 §6 item 1; 02 §0.4 D-5 precondition; 04 §E7] | Backtests may use final-vintage ED/admissions (look-ahead). Gate for every ED-based claim. | Pull V5 `archive/` for dev seasons; re-run model 1 and 2 scores with first-published values. | Seconds | Gate: no ED-based claim until passed. If scores worsen materially, all ED-based dev results are restated. |
| A1 | Maturity-matched GBQR training labels and backfill-corrected edge (drop or nowcast lag-0/1 training rows) | [04 §6 E1; 06 §8.2 and Track A #2] | Model 2's rise bias comes from lag-0 first-report training rows. | Variants: drop labels within m=2,3,4 weeks of R−7; backfill ratios from older snapshots applied to training and serving rows. Compare to current model 2 on both dev seasons. | Negligible (ratio table) | Pass: rising below_median moves toward 0.5 on both folds and mean relWIS does not worsen. |
| A2 | Model 1 forward mean reversion (D-3) and ED intercept (D-2), as a diagnostic-then-candidate pair | [02 §8.1–2; 02 §5 items 1–2] | The too-steep decline comes from forward Rt random walk with no reversion, and an ED observation with no baseline. | D-1 innovation signs; D-3 half-lives 2, 4, 8 weeks; D-2 ED intercept from off-season data only. Pre-register declining-phase bias target. | Negligible (one extra EAKF pass per setting) [unmeasured] | Pass: cuts declining-phase bias by ≥ one third on both folds with no peak-phase cost. Report 02 gives this bar. |
| A3 | Lag-aware observation error in EAKF for the newest week (SD for lag 0 scaled by per-location volume-weighted lag-0 share) | [06 Track A #1; 06 §8.1] | Latest admission is ~9% low; observation error should be larger at lag 0. | As-of replay, h=0..3, LOSO. Stop if no gain at h=0 and h=1. | Negligible | Pass: relWIS < 1 at h=0 and h=1 on both folds. Effect expected largest in TX, MI, CA, FL, PA [06 §8.1]. |
| A4 | Predictive interval from observation model (NegBin φ fit on LOSO training residuals) | [03 E2; 03 §8.2] | Undercoverage is a predictive-distribution problem, not a median one. | Add NegBin draws to `forecast_quantiles`; target 50% and 95% coverage within ±5 points per fold. | Negligible | Pass: coverage target met on each fold; report sharpness with coverage. |
| A5 | Split CQR on model 2's outermost quantile pairs (per horizon, exchangeable calibration window of prior seasons) | [07 §5 item 3; 07 §7 item 3] | Model 2's outer tails are under-dispersed. | Null: uncorrected GBQR quantiles. Win: cov90 closer to 0.90 on both folds, 50% band ≤ 0.55 width change. | Negligible | Pass: as stated. Cheap, low risk. |
| A6 | Phase-gated additive log shift on ensemble quantiles (real-time phase from 3-week as-of log growth) | [10 §7 item 1; 10 §7 item 4] | Ensemble bias is phase-dependent; a phase shift corrects rises. | Phase rule: rising if > +0.05/week, declining if < −0.05, else peak. Shift estimated on the other dev season only. Block bootstrap over reference dates; DM with HAC. | Under 1 s (lookup) | Pass: pooled relWIS improves on both held-out seasons and shift sign matches the other season. Peak-size factor (10 §7 item 4) only if this passes. |
| A7 | Scale-free phase-specific shift and width for model 1 quantiles (count vs log1p) | [07 §5 item 2] | The global (b, k) on count scale is wrong for the phase structure. | Null: current global (b, k). Win: lower pinball on log1p counts on both folds; no coverage violation. Refit without 2025-26. | Negligible | Pass: as stated. |
| A8 | Small-count dispersion pooling (NB with shrunk ψ_i) in model 1's observation layer | [11 §7 item 1; 11 §9 item 1] | Small units (34.6% of state-weeks under 10 counts) are miscalibrated under a shared Gaussian/lognormal layer. | Replace observation likelihood with shrunk ψ_i, or recalibrate intervals offline. Report small-unit WIS (mean <50) separately. | Negligible | Pass: small-unit WIS down ≥ 5% on both folds; large-unit WIS not worse by > 2%. |
| A9 | Empirical-Bayes location intercept shrinkage in model 2 | [11 §7 item 2] | Per-location intercepts overfit; shrinkage helps h=3. | Location random intercept, LOSO. | Trivial | Pass: relWIS improvement on both seasons including h=3. |
| A10 | Equal-weight linear pool of models 1 and 2 (vs quantile average), optionally beta-transformed | [12 E1; 07 §5 item 8; 08 §8.1] | Two under-dispersed models with opposite-phase errors. | Compare MIX_LP to MIX_QA on dev, LOSO. | Trivial | Pass: beats the better single member on both dev folds. Already running in shadow; decision by shadow + dev archive. |
| A11 | Tree regularisation and monotone constraints for model 2 | [04 §6 E3] | Trees damp rises; constraints help. | min_data_in_leaf ∈ {10, 20, 50}; n_estimators ∈ {150, 300, 600}; num_leaves ∈ {7, 15}; monotone d1..d4. Choose on dev rising bias jointly with relWIS. | 92 fits per origin [unmeasured]; measure before committing | Pass: per 04 §6 rule. Run only after A1. |
| A12 | Archive-only comparison: equal-weight vs learned combiners (C1, C4 weight part, C5) | [08 §8.2] | Learned weights lose to equal weights; expected. | LOSO on 2023-24 and 2024-25 with the §6 luck gate. | Hub archive only | Proceed to Track A only if λ > 0 on both folds. Expected to fail. |

Excluded from Track A: any shift of 2025-26 use; any interval widening as a fix for a median bias [02 §6, §8.5]; any calendar or ED feature in submission before A0 passes [04 §9 item 5].

Dropped from Track A: the current `calibrate.py` params [07 §7 item 5]. Do not extend.

## 3. Track B: shadow lab (ranked, deduped)

Shadow rule: pre-registered, never tuned after the first scored week [SHADOW_PROTOCOL]. Graduation per SHADOW_PROTOCOL §Graduation. Items marked [offline] run as archive or backtest first.

| # | Item | Source(s) | Hypothesis | Test | Weekly CPU | Effect / gate |
|---|---|---|---|---|---|---|
| B1 | Real-time phase-gated ensemble shift (shadow version of A6) | [10 §7 item 1] | Forward test of the phase shift on 2026-27. | Same rule as A6, frozen before first scored week. | < 1 s | Large-effect only: needs ≥ 8 weeks in rising and peak phases combined. |
| B2 | BOCD mixture of model 1 and model 2 on log-growth | [10 §7 item 2] | Changepoint "continues vs turned" gating picks the right member per phase. | Mixture weight from BOCD predictive densities. Score vs EAKF and ensemble, minimum 8 rising+peak weeks. | Under 5 s (53 locations) | Stays in shadow. |
| B3 | Damped log-trend ETS, as-of error quantiles | [01 §8 item 2] | A clean declining-phase comparator for model 1, which is too steep. | ETS(A,Ad,N) on log1p, 3–5-week slope; quantiles from own as-of errors. Declining-phase relWIS vs EAKF. | Negligible | Graduate only if it wins in declining phase on dev and in shadow. |
| B4 | ACI wrapper (γ = 0.01) on the best of models 1, 2 quantiles | [07 §5 item 4] | Online coverage correction. | γ fixed at 0.01 in advance; success if running cov90 within 0.03 of 0.90 after 20 weeks. | Negligible | Pass as stated. |
| B5 | Lagged members: lag-1 ensemble and lag-1 own forecasts in an equal-weight pool | [12 E3] | Free independent information. | Confirm file timestamps first. Equal weights only. | Zero | Pass: beats MIX_QA on rising and peak phases. |
| B6 | Revision-aware LLT Kalman filter, obs variance from `time-series.csv` revision distribution | [01 §8 item 4] | Lag-0 observation noise matters. | h=−1, 0 relWIS vs EAKF; 90% coverage. | Negligible | Shadow only. |
| B7 | NobBS nowcast of latest 1–2 weeks, from as-published archive | [06 §8.4] | A heuristic lag-correction is worse than a delay model under time-varying delay. | Build from lags 0–7; benchmark run time first. | Seconds to minutes per location [unmeasured] | Benchmark gate before adoption. |
| B8 | Extremizing/anti-extremizing of categorical pmfs (rate change, peak week) | [12 E10] | Unclaimed targets; one parameter. | Log and Brier vs hub categories. | Trivial | Shadow. |
| B9 | DAP combiner (C3) with d_0 = 1, no fit | [08 §8.3] | Prior-tilted equal weights. | vs MIX_QA and MIX_LP. | Trivial | Shadow. |
| B10 | Log-scale EnSRF assimilating log1p(y) | [03 E9] | Multiplicative noise and clipping handled naturally. | LOSO vs EAKF; same cost as EAKF. | Same as EAKF [unmeasured] | Shadow. |
| B11 | Bootstrap PF with NegBin likelihood (N ∈ {1000, 2000, 5000}) | [03 E5] | Nonlinear observation model. | Runtime on 4-CPU runner first; ESS < 0.3N distrusted. | ~6–7× EAKF [INFERENCE] | Shadow; only if measured runtime fits. |
| B12 | Richards curve as declining-phase baseline | [02 §5 item 5; 01 §8] | Richards fit to cumulative counts. | Declining-phase relWIS. | Negligible | Shadow. |
| B13 | Pooled quantile AR with Fourier and ED covariate | [01 §8 item 3] | Classical comparator. | LOSO relWIS vs GBQR, by phase. | Low | Shadow. |
| B14 | Sample-based reconciliation of US = Σ states | [11 §7 item 4] | Coherence improves US row. | US WIS improvement ≥ 3% on both seasons. | Seconds | Shadow. |
| B15 | TSFM zero-shot (Chronos-2, TimesFM 2.5) member | [05 §6 B1] | Off-the-shelf member, no fit. | relWIS < 1.0 both seasons, cov90 0.85–0.95. | Seconds | Shadow; licence review first. |
| B16 | Event-stream gate with shrinkage α ≥ 0.5 over NSSP, ILINet, NREVSS, wastewater | [09 §6 item 5; 12 E9] | Multi-source gate adds info. | Permutation test p < 0.1 across seasons; start at equal weights. | Under 5 min added [I] | Shadow; likely drops gate. |
| B17 | ILINet and NREVSS intensity features in GBQR | [09 §6 item 2] | Intensity signal leads admissions. | LOSO relWIS vs model 2. | Low | Shadow one season before promotion. |
| B18 | Wastewater per-site lead | [09 §6 item 3] | Wastewater leads by ≥ 1 week. | 95% interval excludes zero; improves h=2–3. | Low | Shadow. |
| B19 | Hierarchical discrepancy for model 1 vs analog recalibration | [12 E6] | Principled alternative to AnEn. | Head-to-head offline. | Low–med | Shadow. |
| B20 | Analog-ensemble recalibration of model 1 (phase-conditional) | [12 E2; 12 C2] | Phase-conditional correction. | As in [12 Part 3]. | Low | Track A candidate if it wins. |
| B21 | 3-state HMM phase filter on weekly growth | [10 §7 item 3] | Phase probabilities for gating the mixture. | Gated mixture beats equal pool in rising and peak. | < 5 s | Shadow. |
| B22 | Predictability curve (peak week and size vs weeks before peak) | [10 §7 item 5] | Decide peak pmf horizon. | Descriptive. | Offline | Offline only. |
| B23 | Permutation-tested lead-lag (expected null) | [11 §7 item 5] | Lead-lag features are spurious. | Shuffle labels 1,000 times. | Minutes offline | Negative result is useful. |
| B24 | hhh4 (NB, power-law neighbourhood) on 52 units | [11 §7 item 3] | Spatial model. | Beats EAKF and GBQR on both seasons. | Measure offline | Shadow if under 5 min. |
| B25 | Zero-inflated NB for smallest units (mean < 20) | [11 §7 item 7] | Zeros are not NB. | Only if A8 shows small-unit gains. | Negligible | Conditional. |
| B26 | Taylor-law width with ACI on the final submission | [12 E4] | Targets narrow intervals. | Trivial. | Trivial | Track A candidate after shadow. |
| B27 | Farr curvature member and FET | [12 E7; 12 C5] | Constant-rate decline test vs SEIR. | Trivial. | Trivial | Shadow. |
| B28 | EDM / S-map member | [12 E8] | Non-parametric state dependence. | Low cost. | Low | Shadow. |
| B29 | Event-gated weights (C4) and CGL pool (C1) | [12 E5, E9; 08 §8.4–5] | Luck-aware combiner. | Likely to reduce to equal weights. | Low | Shadow; log λ weekly. |
| B30 | Hub-level top-5 equal-weight TST (trailing 8 weeks) | [08 §8.6] | Top-5 selection by trailing WIS. | Archive run; no new forecasts. | Hub archive only | Shadow after archive run exists. |
| B31 | Simulation-pretrained TSFM, pooled TCN, neural emulator of model 1 | [05 §6 B2–B5] | Learned members. | Pass rules in 05 §6. | Training cost, outside weekly budget | Offline only until B1 passes. |
| B32 | Classical archive classification (CMU-TimeSeries, ChinaCDC-seasAR, etc.) | [01 §8 item 1] | Archive is useful only if relWIS < 1 in ≥ 2 of 3 seasons and declining phase. | Zero new compute. | Zero | Done offline. |
| B33 | Analogue KCDE on log rate; NB-INGARCH and GP for small locations | [01 §8 items 5–7] | Component diversity. | As pre-registered. | Low | Shadow. |
| B34 | Multi-filter equal-weight combination (EAKF + PF + RTPS) | [03 E10] | Combination. | Not until E1–E4 settle. | Sum of parts | Deferred. |

Not recommended now: CSD and early-warning indicators [10 §7]; human Delphi panel [01 §8 item 9]; Google Health Trends (unavailable) [09 §6].

## 4. Track A items that are evaluation infrastructure (prerequisites)

These do not change the submission. They gate every graduation and are required before any Track B pass is read.

- **E-1.** Log-scale WIS as co-primary or sensitivity analysis [13 §8 item 1].
- **E-2.** Per-location pooled log-relWIS as sensitivity check on the US-weighted d_r (US is 45.6% of ensemble WIS from 1.9% of rows) [13 §8 item 2].
- **E-3.** Implement DM/HAC, block bootstrap, Holm, horizon check and truth-vintage recording in `score_live.py` [13 §7, §8 items 3, 5]. Currently it emits ratio-of-means relWIS only.
- **E-4.** Power curve and minimum T for the protocol [13 §8 item 4]: 20 weeks gives ≈ 21–24% MDE.
- **E-5.** Size check of DM with L=3 against stationary bootstrap or Andrews HAC on archived d_r [13 §8 item 5].

## 5. First five lab models to add to `backtest/shadow.py` before 2026-12-02

Each is a function `(ref, ctx) -> DataFrame` in hub format and is added to `MODELS`. A failing model is skipped by the existing wrapper. None uses 2025-26 for any choice. Parameters are frozen before the first scored week.

**1. `CyberEpi-PHASE_SHIFT` (B1; source [10 §7 item 1]).** Read as-of admissions for the reference date `ctx.ref` from the target data (V5 `archive/` pull or the as-of time-series snapshot, never the final series). Compute the 3-week log growth g = log(y_R) − log(y_{R−3}) divided by 3. Classify phase: rising if g > +0.05, declining if g < −0.05, else peak. Take the quantiles of our own pool `CyberEpi-MIX_LP` for `ctx.ref` (the FluSight ensemble is published after the deadline, so a model built on it could never be submitted), and add the frozen phase-specific log shift for each phase-horizon. The shift table is a constant committed in the file header, estimated on 2023-24 and 2024-25 (LOSO on those two to check the sign is stable), with the sign rule from A6. Sort quantiles and clip at zero. Log the phase label and shift per row to `forecasts/shadow/diagnostics/` so the forward test can be checked against the offline table. Fail safe: if the pool or as-of data is missing, raise, so the wrapper skips the model.

**2. `CyberEpi-BOCD_MIX` (B2; source [10 §7 item 2]).** Compute the log-growth series of as-of admissions per location over the season so far. Run Adams–MacKay BOCD with a constant hazard and a Student-t or Gaussian predictive. Use the run-length posterior to form two predictive densities: "continues" (the EAKF/GBQR forecast as submitted) and "turned" (the same forecast with the sign of the 3-week slope reversed, via a fixed shift). The mixture weight is the posterior probability of the changepoint in the last 2 weeks. Write the mixture quantiles by inverting the mixed CDF on a grid, the same way `mix_linear_pool` does. Hazard and prior are frozen in the file header. Track the weight per location in diagnostics. This is a mixture of two members, not a learned combiner.

**3. `CyberEpi-ETS_DECL` (B3; source [01 §8 item 2]).** For each location, take the as-of admissions series through `ctx.ref`, transform to log1p, and fit an ETS(A, Ad, N) with a 3–5-week trend estimate and damping φ = 0.9 fixed. Generate point forecasts for horizons 0–3 as the hub defines them (target end dates). Build quantiles from the empirical distribution of this model's own one-step as-of errors over the previous two seasons, computed only with as-of data at each past reference date. Back-transform by expm1 and sort. It is a declining-phase comparator, so it is written to be scored by phase, not as a general model. Fail safe on under 30 prior weeks of data.

**4. `CyberEpi-EAKF_ACI` (B4; source [07 §5 item 4]).** Read the submitted `CyberEpi-EAKF` quantiles for `ctx.ref`. Maintain a per-location, per-horizon, per-level miscoverage state α_t, initialised at the nominal level and updated after each truth is available, using α_{t+1} = α_t + γ(α − 1{y_t ∉ I_t}) with γ = 0.01 fixed in advance. The state is persisted to `forecasts/shadow/diagnostics/aci_state.json` so the update is reproducible. For the current week, widen or narrow the 50% and 90% quantile pairs by the state's implied level. Do not use truth from the reference week itself. Report running cov90 and state per week. This model is the calibration-only comparator for B4, so its raw quantiles are kept as a reference model (as 07 §5 requires).

**5. `CyberEpi-MIX_LAG` (B5; source [12 E3]).** Confirm first that the lag-1 files exist and that their commit timestamps are earlier than the reference date. Build the equal-weight linear pool (reuse `mix_linear_pool`) of three members: `CyberEpi-EAKF` and `CyberEpi-GBQR` at the reference date, and the same two models' forecasts at reference date minus 7 days, read from `forecasts/model-output`. Use `read_submitted` for each lagged file, and align on the shared key. If any lagged member is missing, fall back to the two-member pool for that week and write a flag in diagnostics. No weights are learned; equal weights are fixed in the code.

Why these five: (1) and (2) test the cross-cutting rise bias that the ensemble, model 2, and the archive all share, directly and with a real-time phase rule. (3) gives the declining-phase comparator that model 1 lacks. (4) is cheap calibration with a pre-registered γ. (5) is zero-cost information and extends the existing pool. Each needs a pre-registered decision row in `SHADOW_PROTOCOL.md` before its first scored week.

Deferred (sixth and later): B6 (LLT Kalman), B7 (NobBS), B9 (DAP), B30 (TST).

## 6. First three Track A dev-season experiments

1. **A0 then A2 (model 1, diagnostic-first).** Run the NSSP/NHSN as-of vintage audit (A0, 09 §6 item 1; 03 E0). Once it passes, run the D-1 innovation-sign diagnostic and D-3 forward mean reversion (half-lives 2, 4, 8) together with the D-2 ED intercept on 2023-24 and 2024-25 LOSO, using the as-of archive only (02 §8.1–2). Pass: declining-phase bias cut by at least one third on both folds, no peak-phase cost. Report A2 as a diagnostic first even if it passes; it is a candidate, not a change.

2. **A1 (model 2 maturity-matched labels and backfill-corrected edge).** Negligible cost. Pre-register the rising below_median target (0.35–0.65) and relWIS on both dev seasons (04 §6 E1; 06 §8.2). Run the m = 2, 3, 4 label-drop variants and the backfill-ratio variant on as-of snapshots only, with backfill ratios estimated from older snapshots. Pass: rising below_median moves toward 0.5 on both folds and mean relWIS does not worsen.

3. **A3 (lag-aware observation error in EAKF).** Run as-of replay, h=0..3, LOSO, with the lag-0 observation SD scaled by per-location volume-weighted lag-0 share (06 §8.1, Track A #1). Stop if there is no gain at h=0 and h=1. This test also settles the reconciliation in §1: if it closes most of the rise bias, model 1's structure and the ensemble's rise bias are partly a data artefact, and A2 must be re-read against it.

Order and dependency: A0 gates A1–A3 and any ED-based claim. A1 and A3 are independent and can run in parallel. A2 uses A3's corrected observation layer if A3 passes. A4 (NegBin intervals) and A5 (CQR) are queued after these three. Measure runtime on the 4-CPU runner before any Track A candidate is adopted.

## 7. Open items and conflicts

- 06 §8.3 proposes a per-location gated multiplier. Its 2025-26 forward test (0.084 → 0.053) used the spent holdout and is "already seen". It can only be re-tested as a forward shadow item (B-series, not Track A).
- 12 E1 ranks the equal linear pool of models 1 and 2 first; 08 favours equal quantile averaging. Both are already in shadow as MIX_QA and MIX_LP. The decision uses the dev archive plus shadow, not an extra variant.
- 10 §7 and 07 §5 both propose a phase or calibration correction to the ensemble. They are merged as A6/B1 (phase shift) and B4 (ACI). Do not run both as independent Track A changes; they share the same rise-phase target.
- Several reports rely on unverified or unopened references (e.g. [03 §9], [07 §6], [11 §8], [06 §11]). No decision here rests on them; the logic depends only on the dev-season tests listed.
- Costs marked [unmeasured] in the source reports (e.g. 04 §7 GBQR fits, 05 §5 refits, 03 §7 PF) must be measured on the 4-CPU runner before adoption.
