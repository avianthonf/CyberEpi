# Family 11: partial pooling, hhh4, mobility, lead-lag, reconciliation, small counts

Scope: 53 hub locations (US, 50 states, DC, PR). "States" below means all 52 non-US units unless stated. Data: `data/flusight/target-hospital-admissions.csv` (NHSN weekly counts, latest version). Development window 2022-10-01 to 2025-06-30 (2022-23, 2023-24, 2024-25). The 2025-26 holdout is not used anywhere below.

## 1. Partial pooling (hierarchical shrinkage)

**Theory.** Unit-level parameters θ_i (growth rate, peak size, dispersion) are drawn from a population distribution θ_i ~ N(μ, τ²). The posterior mean is a precision-weighted average: θ̂_i = (n_i/σ_i² · θ̂_i^MLE + 1/τ² · μ)/(n_i/σ_i² + 1/τ²). Uncertainty comes from the posterior of (μ, τ) plus within-unit noise. A plug-in τ underestimates it, which is the usual reason hierarchical forecasts are too narrow. Empirical Bayes (τ from marginal likelihood) is cheap; full Bayes (MCMC) is not affordable on the 30-minute runner for 53 units with a weekly refit.

**Application.** Model 2 (CyberEpi-GBQR) already pools implicitly: one LightGBM across locations on per-capita log-growth. Model 1 (CyberEpi-EAKF) is unpooled: each location has its own random-walk β, HIR, c. Partial pooling matters most where the per-location signal is weak: small states, PR, and the first 2–3 weeks of a season, when state-level growth is dominated by Poisson noise.

**Small counts (data check).** In 2022-23..2024-25, all weeks including off-season (not restricted to Oct–May), 34.6% of state-weeks are below 10 admissions and 63.8% below 50; 9.2% are exactly zero (7,488 state-weeks). For the smallest units, Poisson noise is of order 1/√count, so a 10-count week carries about ±30% noise before any dynamics. A log1p transform is a common remedy; it biases means and should be paired with back-transformed quantiles, not with a Gaussian on the log scale.

**Evidence and hub use.** Across-season hierarchical models are used by Cornell_JHU: `hierarchSIR` (not designated) and `SCARCHhierarSIR` (designated), both wrapping a SIR model in an across-season Bayesian hierarchy. BYFlu-STMGGP (designated) is a Gaussian process with a spatial covariance over states, i.e. pooling in the covariance rather than the means. [INFERENCE] Much of the gain from pooling in these teams comes from shrinking unstable season-level parameters; not tested here.

**Failure modes.** Pooling to the national mean removes real regional timing differences (see §3). Over-pooling makes every state look like the national curve and hides the fast-decline problem of model 1. τ estimated from 3 seasons is itself very noisy.

**Cost.** Empirical Bayes shrinkage of 53 growth rates: milliseconds. Full MCMC: exceeds the budget; do not run weekly.

## 2. hhh4 (endemic–epidemic count model)

**Theory.** Conditional on the past, counts Y_it (region i, week t) are negative binomial with mean

μ_it = e_it·ν_it + λ_i·Y_{i,t−1} + φ·Σ_{j≠i} w_ji·Y_{j,t−1},

with log-linear predictors for the endemic term ν_it (seasonality, trend, population offset e_it), the autoregressive coefficient λ_i, and the neighbourhood term φ with transmission weights w_ji (power-law in adjacency order, or mobility-derived). Overdispersion ψ can be shared or unit-specific. Estimation: penalised likelihood with quasi-Newton (`nlminb`); random effects via marginal likelihood. Uncertainty: Fisher information plus parametric bootstrap by simulation from the fitted model. Sources: Meyer, Held and Höhle (2017), J. Stat. Softw. 77(11), doi:10.18637/jss.v077.i11 (opened). Held, Höhle and Hofmann (2005) and Paul and Held (2011) are cited in the hhh4 vignette and are not opened here (see §8).

**Application.** hhh4 is a natural lab baseline for the spatial question: it gives a count likelihood that respects the small-count regime (§1), a seasonal endemic term, and a directed between-state term. It does not handle the 2024 reporting regime (voluntary reporting May–Oct 2024; 18.1% of our state-weeks fall in May–Oct 2024) unless an indicator is added to e_it. Its weakness for us is the one shared by AR-type models: a power-law transmission weight does not represent the phase error we observe in declines (PROBLEM_BRIEF §5).

**Cost.** Fitting hhh4 for 53 units on ~8 seasons of weekly data takes seconds to minutes in R. Python has no maintained equivalent; a Python port (about 150 lines: NB likelihood, seasonal endemic term, weight matrix) or an offline R call is needed. A weekly refit inside the 30-minute runner is feasible only if warm-started. [INFERENCE]

**Failure modes.** Overdispersion drifting by unit; the between-unit term φ absorbs national seasonal drift when there is no unit-specific seasonal term; very small counts push λ_i to the boundary.

## 3. Lead-lag between states (measured on the data)

**Method.** Weekly NHSN counts, 52 non-US units, 2022-10 to 2025-06. Growth g_it = Δ log(3-week centred mean of count + 5). Cross-correlation corr(g_a,t, g_b,t+k) for k ∈ {−3..3}. Sign convention: k > 0 means a leads b; k < 0 means b leads a. Two tests:
1. Each unit against the rest of the US (its own counts removed, to avoid mechanical coupling).
2. All 1,326 unordered pairs, best k per pair. Pair order is alphabetical by location code, so the sign of the pairwise distribution is not informative (see below).

Scripts were run from /tmp and are not committed.

**Results: unit vs rest of US (leave-self-out).**
- Best-lag distribution: k = −1 for 13 units, k = 0 for 36, k = +1 for 3. Median best correlation 0.79; median lag-0 correlation 0.785. Lag 0 is almost as good for nearly every unit, so the directed signal is weak.
- Units that follow the rest of the US by one week (k = −1): Michigan (26), New Hampshire (33), New Jersey (34), New York (36), North Dakota (38), Iowa (19), Nebraska (31), Pennsylvania (42), Montana (30), Vermont (50), Rhode Island (44), Maine (23), Puerto Rico (72; r = 0.41, unreliable).
- Units that lead the rest by one week (k = +1): Texas (48), North Carolina (37), Minnesota (27). Correlations 0.69–0.73.
- Caveat: the "rest of US" series is dominated by large states, so this test is biased toward large-state leads. The k = −1 group is mostly Northeast and upper Midwest. This is consistent with the Viboud et al. (2006) pattern of large, connected states seeding others, but that pattern was not tested directly.

**Results: pairwise (1,326 pairs).** Best-lag counts: k = −3: 31, −2: 43, −1: 190, 0: 721, +1: 269, +2: 49, +3: 23. Median best correlation 0.66; lag-0 median 0.65. Mass sits at k = 0. Per-season pairwise best-lag distributions (restricted to |k| ≤ 2) are roughly symmetric. For 2023-24: k = −2: 77, −1: 215, 0: 623, +1: 277, +2: 134. The directed signal is small relative to synchrony.

**Peak timing (state peak week minus national peak week, 3-week smoothed).**
- 2022-23 (national peak 2022-12-10 on this smoothing): mean +0.15 wk, median 0, SD 1.7, range −5 to +3.
- 2023-24 (national peak 2024-01-06): mean +1.46 wk, median 0, SD 4.2, range −9 to +10. The SD is inflated by small units with noisy peaks; use the median or a weighted measure before drawing conclusions.
- 2024-25 (national peak 2025-02-08): mean −0.73 wk, median 0, SD 2.1, range −6 to +3.

**Interpretation.** Synchrony is high (median pairwise correlation about 0.65), and lag structure is at most one week for most units. A week-level directed lead is therefore not a usable forecasting signal for most states; it is plausible only for a handful of large or northern units. Any lead-lag feature needs a permutation test over seasons (shuffle state labels within season) before use. That test has not been run.

**Relevance.** Track B only. A one-week national-to-state lead would matter for h=0..3 forecasts only if it were stable across seasons, and our data do not show that clearly.

## 4. Mobility-informed coupling

**Evidence.** Viboud et al. (2006), Science 312(5772):447–451, doi:10.1126/science.1125237 (opened via abstract summaries): spread of US interpandemic influenza follows commuting and workflow flows better than geographic distance, with gravity-type decay (steep within ~100 km, long tail). Charu et al. (2017), PLOS Computational Biology, doi:10.1371/journal.pcbi.1005382 (opened via abstract summary; author list not confirmed): transmission probability decays with distance (power law, exponent ≈ 2.2), and commute-based connectivity outperforms air travel.

Hub teams: MOBS-GLEAM_FLUH (designated; GLEAM metapopulation, age-structured SLIR, mobility network with short- and long-range layers, from its metadata). NU_UCSD-GLEAM_AI_FLUH and Xi_lab-GLEAM_AI / Xi_lab-GLEAM_AI_hybrid are GLEAM-named models whose metadata were matched by keyword search but not read. ACCIDDA-insightcast (designated) matched the same keyword search (mobility or spatial); its metadata was not read.

**Application.** A mobility matrix would replace w_ji in hhh4 or the coupling in a metapopulation SEIR (see Family 02). No state-to-state commuting matrix is in the repo. ACS commuting flows are a candidate; they must be pulled and frozen per year, which is look-ahead-safe because commuting changes slowly.

**Failure modes.** Mobility adds parameters that three seasons cannot identify. The 2006 and 2017 findings concern earlier seasons, before the current NHSN reporting regime.

**Cost.** Static matrix: negligible. A gravity-coupled SEIR refit weekly for 53 units fits the budget only with a fixed matrix and a fast filter.

## 5. Forecast reconciliation (coherence of national and state forecasts)

**Theory.** For a hierarchy, the aggregation matrix S maps bottom-level forecasts to totals. Base forecasts ŷ are reconciled to ỹ = S·G·ŷ, where G minimises the trace of the reconciled forecast-error covariance. MinT (Hyndman et al., 2011; not opened) estimates the base-error covariance W. Wickramasuriya, Athanasopoulos and Hyndman, JASA 114(526), doi:10.1080/01621459.2018.1448825 (opened via search summaries, which give 2018 and 2019 for the same paper), gives a trace-minimisation closed form that avoids estimating the coherency-error covariance, which they argue is not identifiable in practice. Uncertainty: reconciled intervals come from the reconciled covariance, or by reconciling joint sample paths. Quantiles cannot be reconciled directly; reconciling each quantile separately is invalid in general.

**Data check.** Coherence is almost exact in the NHSN truth: median sum-of-states / US ratio is 1.000 in each season, IQR 0.998–1.000. The hierarchy US = Σ states therefore holds in the data and reconciliation can be applied without a measurement-error term.

**Application.** Our models forecast each location separately (Model 1) or pooled (Model 2); neither is guaranteed to be coherent. Two options: (a) forecast states and derive US as the sum of draws; (b) forecast US and disaggregate by state shares. The US target carries large weight in pooled WIS (PROBLEM_BRIEF §3). The hub scores each location separately and does not require coherence, so reconciliation is a Track B idea unless it improves WIS on the US row.

**Failure modes.** Summing state quantiles overstates spread unless states are perfectly correlated; sample-based reconciliation with joint draws is required. With 3 seasons, W cannot be estimated well; use a shrinkage estimator (diagonal or equal-correlation), pre-registered before testing.

**Cost.** Closed form on 53 series is trivial. Sample-based (1,000 draws): seconds.

## 6. Small counts

**Theory.** Poisson or negative binomial with log link; the NB dispersion ψ absorbs reporting noise. For small means (<10), Poisson PIT is discrete, so calibration checks need randomised PIT. A log1p or Anscombe transform stabilises variance but breaks the count likelihood; quantiles must be back-transformed to the count scale.

**Data.** All-year shares (2022-23..2024-25, off-season included): 34.6% of state-weeks are below 10 counts; 9.2% are zero. WIS on the count scale is dominated by large units (US, CA, TX, NY), so small-unit calibration is invisible in pooled raw WIS. Report small-unit WIS separately.

**Application.** Use NB with a unit-specific ψ_i, shrunk to a common value (partial pooling, §1). For PR and small states, apply the pooled dispersion. Evaluate relWIS within size class (mean <50 vs ≥50) so small units are not averaged away.

**Failure modes.** Zero-inflation (9% zeros) is not NB; a zero-inflated or hurdle model may be needed for the smallest units. Reporting artefacts (the 2024 voluntary period) produce zeros that are not epidemiological.

## 7. Ranked experiments

Pre-registration: all tests use 2023-24 and 2024-25 as development seasons with leave-one-season-out (train on the other season, test on the held-out one), using as-of data only (`time-series.csv` versions). The 2025-26 holdout is not used. Metric: relWIS vs the FluSight-ensemble and vs EAKF, on the count scale, split by size class (mean <50 vs ≥50). A candidate must beat EAKF on both held-out seasons to advance to Track A.

1. **[Track A] Small-count dispersion pooling (NB with shrunk ψ_i) in model 1's observation layer.** Test: replace the observation likelihood in the EAKF with unit-specific ψ_i shrunk to the pooled value, or recalibrate intervals offline with an NB layer. Criterion: small-unit WIS down ≥5% on both held-out seasons, large-unit WIS not worse by more than 2%. Cost: negligible.
2. **[Track A] Hierarchical shrinkage of model 2's per-location intercept.** Test: add a location random intercept, shrunk by empirical Bayes, to the pooled LightGBM target. Criterion: relWIS improvement on both seasons, including h=3. Cost: trivial.
3. **[Track B, shadow] hhh4 (negative binomial, seasonal endemic, power-law neighbourhood weights) on the 52 units**, run offline first with a Python port of the NB likelihood. Test: leave-one-season-out vs EAKF and GBQR. Criterion: beats both on 2 of 2 development seasons, pre-registered. Cost: measure offline; run weekly only if under 5 minutes.
4. **[Track B] Reconciliation of the US total with the sum of state forecasts (sample-based).** Test: forecast states, sum joint draws (pooled-correlation draws), compare US-row WIS with the direct US forecast. Criterion: US WIS improvement ≥3% on both seasons. Cost: seconds.
5. **[Track B] Permutation test for lead-lag.** Test: keep the §3 cross-correlation; shuffle state labels within season 1,000 times; retain a directed lag feature only if the sign agrees across seasons and the null is rejected at 5%. Cost: minutes offline. Expected to be null, which is itself a useful negative.
6. **[Track B] Mobility-weighted coupling** (ACS commuting flows, frozen per year) in the hhh4 neighbourhood term. Test: compare with power-law weights on the same seasons. Criterion: as for item 3. Cost: one data pull.
7. **[Track B] Zero-inflated NB for the smallest units (mean <20).** Only if item 1 shows small-unit gains. Cost: negligible.

## 8. References (opened or flagged)

- Meyer S., Held L., Höhle M. (2017). Spatio-temporal analysis of epidemic phenomena using the R package surveillance. J. Stat. Softw. 77(11). doi:10.18637/jss.v077.i11. Opened (search summary).
- Viboud C., Bjørnstad O.N., Smith D.L., Simonsen L., Miller M.A., Grenfell B.T. (2006). Synchrony, waves, and spatial hierarchies in the spread of influenza. Science 312(5772):447–451. doi:10.1126/science.1125237. Opened (abstract summaries).
- Charu V., et al. (2017). Human mobility and the spatial transmission of influenza in the United States. PLOS Comput. Biol. doi:10.1371/journal.pcbi.1005382. Opened (abstract summary; authors not confirmed).
- Wickramasuriya S.L., Athanasopoulos G., Hyndman R.J. (2019). Optimal forecast reconciliation for hierarchical and grouped time series through trace minimization. JASA 114(526). doi:10.1080/01621459.2018.1448825. Opened (search summaries; the year differs between sources).
- Hyndman R.J., Ahmed R.A., Athanasopoulos G., Shang H.L. (2011). Optimal combination forecasts for hierarchical time series. Comput. Stat. Data Anal. [unverified: cited, not opened].
- Paul M., Held L. (2011). Predictive assessment of a non-linear random effects model for multivariate time series of infectious disease counts. Stat. Med. [unverified: cited in the hhh4 vignette, not opened].
- Held L., Höhle M., Hofmann M. (2005). A statistical framework for the analysis of multivariate infectious disease surveillance counts. Stat. Model. [unverified: cited in the hhh4 vignette, not opened].
- Hub metadata opened: `model-metadata/MOBS-GLEAM_FLUH.yml`, `Cornell_JHU-SCARCHhierarSIR.yml`, `Cornell_JHU-hierarchSIR.yml`, `BYFlu-STMGGP.yml`.

Three references are unverified, as required: Hyndman et al. (2011), Paul and Held (2011), Held et al. (2005).

## 9. Top-5 (for the synthesis)

1. Small-count NB dispersion with pooled shrinkage (Track A, item 1). Cheap; 34.6% of state-weeks are under 10 counts.
2. Shrink model 2's location intercepts by empirical Bayes (Track A, item 2).
3. Sample-based reconciliation of US = Σ states (Track B, item 4). Coherence holds in the truth (ratio 1.000).
4. hhh4 offline baseline with power-law weights (Track B, item 3).
5. Permutation-tested lead-lag, expected to be null (Track B, item 5). Measured lags are mostly 0 or ±1 week; median pairwise r is 0.66.
