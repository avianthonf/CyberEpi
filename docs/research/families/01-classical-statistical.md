# Family 01: classical and statistical methods

Scope: baselines, analogues, ARIMA/ETS, state space, count models, GAM/GP, Delphi-style judgement.
Problem context: `docs/research/PROBLEM_BRIEF.md`. Data facts below are from the brief unless marked.

Evidence status legend: **[OPENED]** = I read the source in this session (hub YAML files in `model-metadata/`). **[SEARCH]** = checked only through a search-result summary, not the full text. **[STANDARD REF]** = bibliographic details checked by search (publisher or catalog listing); content not read. **[UNVERIFIED]** = from memory, not checked. **[INFERENCE]** = my reasoning, not observed.

Summary of the main point: the classical toolkit is cheap and interpretable, and every component below fits in the weekly budget. The leverage is not in a fancier single model. It is in (a) proper handling of the reporting triangle, (b) honest log-scale predictive distributions whose width is learned on as-of data, and (c) a few components with different error phases to feed the combiner (family 08). Several classical teams are already in the hub, so the archive can test them directly once `archive_scores.py` has run.

---

## 0. Hub evidence on classical methods

**[OPENED]** `model-metadata/*.yml` in the hub (159 files). Classical or near-classical designs I opened:

| Team-model | Designated | Method (from YAML) |
|---|---|---|
| CMU-TimeSeries | yes | Pooled quantile autoregression on lagged counts per 100k, data whitened so FluSurv-NET and ILI can augment training; one quantile regression per level (23), fit over 7-week window, all past years. |
| CMU-TimeSeries_Cal | no | Same ensemble plus MultiQT online quantile offsets (sqrt scale, lr 0.018, cold start each season). |
| CMU-climate_baseline | no | Empirical quantiles from 7-week windows around target week, 2022 onward; averaged with geo-aggregated quantiles. |
| ChinaCDC-seasAR | yes | `auto.arima` with weekly seasonal frequency 52 per location; quantiles from normal approximation using the 95% interval for the standard error; horizon −1 from the latest count. |
| FluCast-SeasonalRidge | yes | Ridge regression per horizon on four lagged counts, latest weekly change, annual seasonal features, and horizon-specific empirical calibration. |
| DMAPRIME-DLM | yes | Dynamic linear model (level, trend, seasonality) with EHR covariates and holiday indicators; recursive 1-step model iterated to h=3. |
| HallAI-FluTrend | yes | Damped log(1+x) trend (damping 0.8/week, slope capped ±0.5). Uncertainty from resampled own past forecast-error paths matched on growth, level and season time, using only data before each forecast date. |
| NU_Baselines-naive | no | Negative binomial by method of moments to all weeks since 2022-08 (excluding 2024-05-04 to 2024-11-02 reporting weeks); same quantiles every horizon. |
| FluSight-base_seasonal | no | Kernel density over historical peak week and intensity (for peak targets). |
| CU-STS_base / CU-STS_Residual | no / yes | Equal-weight quantile ensemble of SIR-EAKF, a seasonal-drift analogue model, SARIMAX with epiweek climatology and Fourier terms, pooled LightGBM, and zero-shot Chronos-2 and TimesFM. The Residual version adds a learned residual shift. |
| OHTJHU-BM | no | Median of zero-shot foundation models (Chronos-2, TimesFM 2.5, Moirai 2.0, Timestral). |

Observations **[OPENED]**:
- Almost every classical entry is on a log, root or per-capita scale, and most use as-of hub snapshots. HallAI and CU-STS are the only ones that describe learning uncertainty from their own past errors. This matters for family 07.
- Only CMU-TimeSeries and CU-STS pool across locations. Single-location ARIMA (ChinaCDC) is the typical classical design.
- Designated status is not evidence of skill. I did not read scores for these models; **[INFERENCE]** the archive run (`backtest/archive_scores.py`) is the first place to check whether classical designs beat the ensemble by phase. Its output is not yet available.

- **[OPENED]** Grep of all `methods:` fields for classical terms (ARIMA, ETS/Holt, GAM, GP, negative binomial, baseline, kalman, judgement):
  - ARIMA/Holt/damped-Holt ensembles: CADPH-FluCAT_Ensemble, Gatech-ensemble_point and _stat (ARIMA, ARGO, LightGBM), UVAFluX-OptimWISE, UGA_CEID-auto_AVG_LB (automatic ARIMAX on 104 weeks of log hospitalisations, one-week-lag national exogenous term).
  - Log random walk and baselines: NU_Baselines-logrw (random walk on log(x+1), symmetrised differences), BFrimpong-baseline (flat forecast, symmetrised 3-year log changes widened by sqrt(h)), FluSight-baseline, UMass-trends_ensemble (equal-weight simple baselines).
  - Gaussian process: BYFlu-STMGGP (temporal, spatial and season correlation components).
  - Negative binomial output: CU-ARNB_Net (residual network with NB output), NU_Baselines-naive.
  - Compartmental plus AR: fjordhest-ensemble (inverse-WIS weights on a compartmental model, quantile AR and random walk with drift).
  - Delphi-style: no `methods:` entry describes expert elicitation. FluSight-HJudge_ensemble and CADPH-FluCAT_HJudge_* are median ensembles of submissions, i.e. aggregation of human-judgement submissions, not elicitation.
  - GAM: no `methods:` entry mentions a GAM.
  - The hub therefore has GP and NB-output entries; GAM and formal Delphi elicitation are absent.

---

## 1. Baselines, persistence, climatology

### 1.1 Theory
- Persistence (random walk): ŷ_{t+h} = y_t. Predictive distribution from empirical h-step log-changes, Q_h(p) = y_t · exp(quantile_p(Δ_h log y)).
- Climatology: empirical distribution of y at the same epiweek over prior seasons. Uncertainty is the spread across seasons, which is wide because seasons differ in timing and size.
- Ratio-to-last or "relative" baseline: forecast = y_t × seasonal ratio. Uncertainty from residuals on the ratio scale. This is the standard for multiplicative noise.

The FluSight-baseline reference (brief §3) is persistence with empirical quantiles. Beating it is the usual minimum bar; the 2025-26 holdout gives the best 45 real teams 0.86 vs the ensemble on our rows, so the baseline is itself a strong opponent [brief].

### 1.2 Application
- Use the baseline as our own honest floor: relWIS vs baseline must be reported for every candidate.
- A "log-persistence with as-of error quantiles" baseline is cheap (under 1 s for 53 locations). It gives a reference for calibration tests in family 07.
- Use climatology only as a horizon-0/-1 seasonal anchor, not as a forecast.

### 1.3 Evidence
- Bracher et al. (WIS): the interval score and its decomposition used by the hub **[OPENED]** arXiv:2005.12881 (abstract checked; hub use is [INFERENCE]; journal page numbers dropped as unverified).
- Reich et al. 2019, real-time FluSight multi-model ensemble. PLOS Comput Biol e1007486 **[OPENED]** (abstract only): 2017/18 season; the ensemble beat every component model on average and the CDC used it publicly.
- Reich et al., "A collaborative multiyear, multimodel assessment of seasonal influenza forecasting in the United States," PNAS 116(8):3146–3154 (2019) **[SEARCH]**: 22 models, 7 seasons; search summaries report that over half beat the historical baseline at 1–3 weeks ahead. Not opened.

### 1.4 Failure modes
- Persistence cannot anticipate turning points; it is worst exactly where our score gaps occur (rises and peaks). Its relWIS is dominated by peaks [INFERENCE].
- Climatology ignores the current season's size and timing; it fails in early or atypical seasons (2025-26 national 55.5k peak in Feb-2025 is an example of the spread).
- Empirical quantiles from few seasons are unstable in tails.

### 1.5 Cost
Negligible (<1 s total).

---

## 2. Analogues and nonparametric trajectory methods

### 2.1 Theory
Analogue forecasting: find past windows similar to the recent trajectory (after level/phase alignment), and average their continuations. Kernel conditional density estimation (KCDE) gives the predictive distribution as a weighted kernel mixture:
p(y_{t+h} | x_t) = Σ_i w_i(x_t) K_σ(y − y_{i+h}) / Σ_i w_i(x_t), with w_i(x_t) = K_ℓ(x_t − x_i).
Uncertainty is the mixture spread plus kernel bandwidth σ. Bandwidth and window choice are the tuning parameters.

Ray & Reich (2018) use KDE/KCDE components in weighted density ensembles for influenza timing and intensity **[OPENED]** (PLOS Comput Biol 14(2) e1005910). FluSight-base_seasonal uses a kernel density over peak week and intensity **[OPENED]**.

### 2.2 Application
- Analogue on log1p rate, matching the last 4–8 weeks and the calendar position, with continuations rescaled to the current level. Output quantiles directly (no parametric form).
- Use with a shrinkage weight toward climatology: few seasons means few analogues.
- Peak targets: KDE over (peak week, peak height) from past seasons, rescaled by current incidence. This is a cheap alternative to model-based peak targets (family 10).

### 2.3 Evidence
- Ray & Reich 2018 **[OPENED]** (PLOS Comput Biol e1005910): components KDE, KCDE, SARIMA; ensembles matched the best component on average and were more consistent across five test seasons. (Earlier claim that KDE is weakest is dropped.)
- Analogue-method work by Shaman and colleagues: cited in general terms only **[UNVERIFIED]**. Justification: no source opened or search-checked; drop before any Track A design uses it.

### 2.4 Failure modes
- Analogues require enough seasons with similar shapes. With ~4 seasons and the 2026-27 early start (13.7k rising on 2026-11-21), the match set may be tiny or wrong-shaped.
- Level alignment on counts is unstable across reporting regimes (voluntary NHSN period, 2024). Use rates or log-differences.
- Analogues never extrapolate: they cannot predict a record season (2025 peak 55.5k is above past national analogues in the hub's 2022–2024 seasons).

### 2.5 Cost
Negligible for KCDE with a few thousand kernel evaluations per forecast.

---

## 3. ARIMA, ETS and seasonal autoregression

### 3.1 Theory
- ARIMA(p,d,q)(P,D,Q)_s on log1p: φ(B)Φ(B^s)(1−B)^d(1−B^s)^D y_t = θ(B)Θ(B^s)ε_t. The h-step variance is σ² Σ_{j<h} ψ_j², which grows with h and is exact for Gaussian errors.
- ETS(A,Ad,N) or ETS(M,Ad,M) in state-space form: ℓ_t = ℓ_{t−1} + φb_{t−1} + α ε_t, with damped trend φ<1. Prediction intervals from the state-space model; with multiplicative errors they are asymmetric on the level scale.
- Fourier-regression ARIMA: seasonal terms via K pairs of sin/cos at period 52.18, avoids seasonal differencing of length 52.
- Seasonal period 52 with weekly data gives a long-memory seasonal structure; `auto.arima` with `m=52` is slow and often picks unstable orders with 4 seasons of data.

### 3.2 Application
- Use log1p or log(rate) and a damped trend for h=0..3, with Fourier terms (K=2–3) plus an ED-fraction regressor (exogenous, as-of).
- For h=−1 use the same model, but the nowcast gap is explicit: fit to the latest as-published counts and inflate the variance by the revision scale (family 06).
- Do not run `auto.arima` weekly on 53 locations within 30 minutes unless restricted; a fixed order (e.g., AR(2) on differences plus Fourier) is cheaper and more stable.

### 3.3 Evidence
- ChinaCDC-seasAR: auto.arima with m=52 and normal-approximated quantiles **[OPENED]**. Normal approximation from the 95% interval ignores skew, which matters near peaks.
- CU-STS SARIMAX with epiweek climatology and Fourier terms **[OPENED]** as a component of an equal-weight ensemble.
- Hyndman & Athanasopoulos, *Forecasting: Principles and Practice*, ch. 8 (exponential smoothing; ETS state-space in 8.5–8.7) **[OPENED]** otexts.com/fpp3. Damped-trend phi restricted to 0.8–0.98 in the text; Gardner & McKenzie (1985) cited as origin. Use for ETS state-space formulae.

### 3.4 Failure modes
- Normal intervals on counts miscover at peaks; this is the classical source of the undercoverage our model 1 shows (family 07).
- ARIMA trained on a whole history with reporting regime changes (2024 voluntary) absorbs the break into the AR roots.
- Damped trends keep the level; they still fall too slowly after peaks or too fast, depending on φ. Our model 1 falls too fast, so a damped-trend ETS on a post-peak window is a direct comparator.

### 3.5 Cost
Fixed-order ARIMA or ETS per location: about 0.02 s per fit, under 10 s for 53 locations. `auto.arima` with m=52: minutes; do not use weekly.

---

## 4. State-space models (Kalman, structural time series)

### 4.1 Theory
Linear Gaussian state space:
- y_t = Z α_t + ε_t, ε_t ~ N(0, σ²_ε)
- α_{t+1} = T α_t + η_t, η_t ~ N(0, Q)

Structural time series (STS): level, slope and seasonal components, with variances estimated by MLE or Bayes. Kalman filter gives the predictive mean and covariance at each t; the h-step predictive variance is Z P_{t+h|t} Z' + σ²_ε, where P grows with the state variance. This is exact under Gaussianity. Local level: P_{t+h|t} = P_{t|t} + h·σ²_η.

DLM with covariates: y_t = F_t θ_t + ε_t, with F_t including lagged ED fraction, EHR and holiday indicators (DMAPRIME-DLM uses this) [OPENED].

Non-Gaussian and nonlinear versions (particle filters, EAKF) belong to family 03; this family covers only the linear-Gaussian models.

### 4.2 Application
- Local linear trend on log1p rate with a seasonal Fourier block and as-of ED-fraction covariate. Output log-scale Gaussian predictive intervals, back-transformed. Quantiles on the count scale are exact transformations.
- Use the Kalman innovation variance as a time-varying calibrator (in family 07 language, a scale-adaptive interval).
- Horizon −1 nowcast: treat the latest count as a noisy observation with variance from the revision distribution (`time-series.csv`), so the filter is partly nowcasting (family 06).

### 4.3 Evidence
- DMAPRIME-DLM is designated and uses this family **[OPENED]**. I did not read its scores.
- Harvey, *Forecasting, Structural Time Series Models and the Kalman Filter* (Cambridge University Press, 1989) **[STANDARD REF]**: checked via ECU library catalog record (xvi+554 pp.); a Google Books listing shows a 1990 reprint. Equations and content not read.
- Reich's group and the FluSight-era statistical entries use state-space-style covariate models **[INFERENCE]**.

### 4.4 Failure modes
- Gaussian state noise on a growth process gives symmetric-in-level errors; peaks and falls are asymmetric. Use log-scale.
- A random-walk level with large Q adapts too quickly to a single noisy week (reporting drops). Put Q on the robust scale or use a t-distributed observation (not linear-Gaussian any more, but a cheap extension).
- MLE variance parameters fitted on a full history use future data unless re-estimated as-of each week. Estimate parameters on data up to R only.

### 4.5 Cost
Kalman filter on 53 locations with n≈250 weeks: under 1 s. MLE per location: about 1–5 s with a few parameters; cheap enough weekly.

---

## 5. Count models (Poisson, negative binomial, INGARCH)

### 5.1 Theory
- Poisson: Var = μ. Real counts are overdispersed.
- Negative binomial NB(μ, θ): Var = μ + μ²/θ. Method of moments gives θ from sample mean and variance (NU_Baselines-naive **[OPENED]**).
- INGARCH(1,1) for count time series: λ_t = ω + α y_{t−1} + β λ_{t−1}, y_t | past ~ NB(λ_t, θ). h-step mean is a geometric mixture; variance grows with persistence α+β.
- Negative binomial GLM or GAMLSS with log link on a seasonal and lag design gives counts directly. Quantiles are exact.
- Zero-inflation is irrelevant for national and large states; it matters for small states and for Puerto Rico and Virgin Islands in summer.

### 5.2 Application
- NB-INGARCH on the count scale, or NB-GLM on log μ with lags and Fourier terms, for the 53 locations. Use the national series as a pooled reference. Count models differ from log-scale Gaussian intervals chiefly for small locations.
- Practical: the largest series (US, CA, TX, NY) dominate raw WIS, so count-model advantages at small scale do not show in pooled raw WIS. Report relWIS per location tier.

### 5.3 Evidence
- NU_Baselines-naive **[OPENED]**: one NB fit for all weeks with no trend. A useful floor for count-scale calibration.
- INGARCH model class: Ferland, Latour & Oraichi (2006), "Integer-Valued GARCH Process," J Time Series Anal 27(6):923–942, doi:10.1111/j.1467-9892.2006.00496.x **[STANDARD REF]**: checked via Wiley DOI page and HAL record; content not read.

### 5.4 Failure modes
- NB variance is quadratic in μ; at the US national scale (13.7k) it is far too narrow relative to real forecast errors dominated by reporting revisions. Count-scale NB is not a calibration cure.
- INGARCH persistence estimates are near 1 during epidemics; forecasts then carry the last level rather than turning.
- Overdispersion parameters estimated from a few seasons are unstable.

### 5.5 Cost
NB-GLM or NB-INGARCH on 53 locations: under 5 s.

---

## 6. GAM, splines and Gaussian processes

### 6.1 Theory
- GAM: y_t = f_0(season time) + f_1(lagged ED fraction) + f_2(lagged log rate) + ε. Penalized regression splines (P-splines) with smoothing penalty λ; REML picks λ. Posterior covariance (Wood 2006) gives approximate Bayesian intervals.
- GP regression: y(x) ~ GP(m, k), with kernel k = periodic (season) × squared-exponential (trend) + noise. Predictive mean and variance are closed form: μ* = K*ᵀ(K+σ²I)⁻¹y, σ*² = k** − K*ᵀ(K+σ²I)⁻¹K*. Cost O(n³); n≈250 per location is trivial.
- Spatial GP (across locations via hierarchical kernels) is family 11.

### 6.2 Application
- GAM with a cyclic season spline and lag terms on log1p, fit once per horizon. Predictive intervals from the posterior covariance, then mapped to quantiles. Useful as a smoother that captures a season-shape that Fourier terms miss.
- GP with a periodic kernel on log rate gives a smooth season and honest variance growth when data are sparse, which is the case for small locations.
- Both are candidates for Track B and for the combiner (family 08) as a differently-phased component.

### 6.3 Evidence
- Wood, *Generalized Additive Models: An Introduction with R* (2nd ed., CRC Press, 2017) **[STANDARD REF]**: checked via Routledge/CRC publisher listing; content not read.
- Rasmussen & Williams, *Gaussian Processes for Machine Learning* (MIT Press, 2006) **[OPENED]**: bibliographic entry verified from the title page and contents only; no content claims rest on it.
- Hub: no GAM entry in any `methods:` field (grep above). GP appears once (BYFlu-STMGGP), so GP is rare but not unique.

### 6.4 Failure modes
- GAM smoothers chase the last season's peak height; with 4 seasons, the spline basis over season time is underdetermined at the tails.
- GP posteriors are overconfident if the kernel hyperparameters are fitted to the same data they forecast (use LOSO hyperparameters).
- GAM intervals from the Bayesian posterior ignore smoothing-parameter uncertainty; use the corrected covariance or a bootstrap.

### 6.5 Cost
GAM: under 2 s per fit with mgcv-like code; in numpy/scipy, a penalized least squares solve is milliseconds. GP with n≈250 Cholesky: under 0.05 s per location, about 2–3 s for all 53 with optimisation of hyperparameters.

---

## 7. Delphi and judgement-based methods

Two meanings need separating (the repo's "Delphi" mention is ambiguous):
1. **Delphi (expert elicitation):** structured iterated rounds of expert judgement. Aggregation by median, linear pool or the Cooke classical model.
2. **Delphi Epidata:** the CMU data API (ILINet, FluSurv-NET, NSSP, etc.). Its as-of archive is family 09's responsibility; I do not treat it as a method here.

### 7.1 Theory
- Expert aggregation: linear pool (equal-weight average of CDFs), quantile averaging, or the Cooke classical model (weights from calibration on seed questions). The linear pool widens intervals; quantile averaging narrows them. Which is better depends on whether experts' errors are correlated (family 08).
- Human judgement, when recorded at fixed times, is a forecast with an as-of record and so is testable.
- Crowd aggregation is the same idea in a different setting. The hub has no crowd-forecast entry.

### 7.2 Application
- A cheap, pre-registered "judgement proxy" is possible: fixed rules that mimic an expert's adjustment (e.g., trust the last two weeks' trend more when ED fraction rises). That is a rule, not a human, and it is testable.
- Live human elicitation is not feasible in a 30-minute weekly pipeline and needs a named human, which the owner has not set up. Treat any human panel as out of scope unless the owner asks.
- Hub entry FluSight-judge_ensemble **[OPENED]** (YAML): median of selected quantile submissions, i.e. aggregation of human-judgement submissions, not elicitation. The local hub has no Metaculus entry; that comparator is removed.

### 7.3 Evidence
- Cooke, *Experts in Uncertainty* (1991) **[UNVERIFIED]**. Justification: book not opened; used only as a pointer for expert weighting, not as evidence.
- Reich et al. 2019 **[OPENED]** (abstract) covers model ensembles; the abstract states no human-judgement component. Check the hub's FluSight-HJudge metadata before relying on it.

### 7.4 Failure modes
- Expert forecasts anchor on the last value and the press; with pooled experts they are often overconfident in the median and underconfident in tails.
- Seed-question weights (Cooke) are fitted on past seasons: the look-ahead rule applies.
- Human forecasts cannot be re-run as-of; audit trails are needed.

### 7.5 Cost
Human: not in budget. Rule-based proxy: negligible.

---

## 8. Ranked experiments

Pre-registration template for all: forecast date R; as-of data only; dev seasons 2023-24 and 2024-25 (and 2022-23 where available), leave-one-season-out; metric WIS on log1p scale and count scale; relWIS vs the FluSight-baseline and vs our EAKF; report by phase (rising, near peak ±2 weeks, declining) and horizon; no winner declared without a block bootstrap over weeks (family 13). Shadow mode means live weekly runs committed to git, not submitted.

**1. [Track B] Archive classification of classical entries.** Using `backtest/archive_scores.py` output (not yet run here): compare the classical team-models (CMU-TimeSeries, ChinaCDC-seasAR, DMAPRIME-DLM, FluCast-SeasonalRidge, HallAI-FluTrend, NU_Baselines-naive, CMU-climate_baseline, FluSight-base_seasonal) by phase and horizon. Rule written before results: a method family is "useful" only if relWIS vs ensemble is below 1.0 in at least 2 of 3 seasons and in the declining phase. Cost: zero new compute.

**2. [Track B, shadow] Damped log-trend ETS with as-of error quantiles.** Fit an ETS(A,Ad,N) on log1p with a 3–5-week slope, and build quantiles from its own as-of errors (HallAI-style). Purpose: a clean declining-phase comparator for model 1, which falls too steeply. Pre-registered test: declining-phase relWIS vs EAKF on dev seasons; graduation only if it wins in shadow.

**3. [Track B, shadow] Pooled quantile AR with Fourier and ED covariate.** CMU-TimeSeries-style, but with our as-of ED fraction and a log1p scale. Per-horizon, per-level quantile regression with sorting. Test: LOSO relWIS vs GBQR (family 04) and vs baseline, by phase.

**4. [Track B, shadow] Local linear trend Kalman filter with revision-aware observation noise.** Observation variance on the latest count from the `time-series.csv` revision distribution. Test: h=−1 and h=0 relWIS vs EAKF; also coverage of the 90% interval (family 07 sets the target).

**5. [Track B] Analogue KCDE on log rate.** Pre-registered bandwidths from dev seasons. Test: whether it is a useful combiner component (family 08) rather than standalone skill. Its strongest use is as a differently-phased component.

**6. [Track B] NB-INGARCH for small locations only.** Test: relWIS on locations below median population vs the pooled Gaussian model. Not a national model.

**7. [Track B] GP with periodic kernel for sparse locations.** Test: relWIS on small locations; hyperparameters LOSO.

**8. [Track A candidate, only if 1–4 pass] Add a classical component to the pool.** The Track A test is a combiner comparison, not a new model: equal-weight pool of EAKF, GBQR and one classical component vs the current pool, on LOSO dev seasons, with a pre-registered threshold (relWIS improvement with block-bootstrap interval excluding 1). Submission requires the shadow result as well.

**9. [Not recommended] Human Delphi panel.** Out of scope for the weekly pipeline and needs a named human. Revisit only with owner approval.

---

## 9. Cost summary (4 CPU, 30 min weekly)

| Method | Weekly cost (53 locations) |
|---|---|
| Persistence / climatology / empirical quantiles | <1 s |
| KCDE analogue | <5 s |
| Fixed-order ARIMA or damped ETS | <10 s |
| `auto.arima` with m=52 | minutes: avoid |
| Kalman local linear trend | ~1 s |
| NB-GLM / NB-INGARCH | <5 s |
| GAM | <2 s per fit |
| GP with periodic kernel, all locations | ~3 s |
| Delphi / human panel | not feasible |

Total for all classical components: well under 1 minute, leaving the budget for family 03 and family 05.

---

## 10. References

Opened (hub YAML, this session): `model-metadata/` entries named in §0.

Search-summary checked (full text not opened) **[SEARCH]**:
- Bracher J, Ray EL, Gneiting T, Reich NG. Evaluating epidemic forecasts in an interval format. arXiv:2005.12881 (2020) [OPENED abstract]. Journal version not verified. https://arxiv.org/abs/2005.12881
- Reich NG et al. Accuracy of real-time multi-model ensemble forecasts for seasonal influenza in the U.S. PLOS Comput Biol 2019; 15(11): e1007486. https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1007486
- Ray EL, Reich NG. Prediction of infectious disease epidemics via weighted density ensembles. PLOS Comput Biol 2018; 14(2): e1005910. https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1005910 ; arXiv:1703.10936.

Unverified (no source opened): Cooke (1991) *Experts in Uncertainty*; Shaman analogue papers (§2.3). Standard references (bibliographic confirmed by search, content not read): Harvey (1989); Ferland, Latour & Oraichi (2006); Wood (2017). Opened: Hyndman & Athanasopoulos ch. 8; Rasmussen & Williams (title page and TOC only).

Hub teams checked for the table in §0 are listed by their `model-metadata` file names; the archive results they would generate are not yet in the repository.
