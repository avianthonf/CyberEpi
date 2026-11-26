# Family 03: data assimilation, particle methods, parameter inference, and undercoverage

Scope: KF/EnKF/EAKF variants, inflation, particle filters, IF2, pMCMC, ABC, and fixes for
model 1's undercoverage. Read against `backtest/eakf.py`, `backtest/seir_fast.py`,
`backtest/forecast.py`, `backtest/run_flusight.py`, `backtest/model_config.json`,
`backtest/METHODS.md`, and `docs/research/PROBLEM_BRIEF.md`.

Source legend: **[OPENED]** = read in this session (repo files, hub metadata, or a web
search summary of the paper; full text was not opened in most cases). **[UNVERIFIED]** =
cited from memory and not checked. There are three unverified citations in this file
(section 9), each justified there.

---

## 0. What the code actually does (read first)

1. **Config drift.** `model_config.json` (frozen, "live") says `sd_beta=0.03`,
   `r_rel=0.15`, `inflation=1.03`, `sd_beta_fwd=0.03`. `METHODS.md` describes the "EAKF-final"
   run as `sd_β = 0.05`, `r_rel = 0.15`, `sd_β,fwd = 0.05`. `EakfConfig` defaults are
   `sd_beta=0.03`, `r_rel=0.30`, `inflation=1.01`, `sd_beta_fwd=0.03`. `run_flusight.py`
   argparse defaults are `inflation=1.03`. The live config is what runs; `METHODS.md` should
   be corrected in a documentation commit. [OPENED]

2. **`EakfConfig.sd_beta_fwd` is dead inside `EAKF`.** `forecast_week()` uses only
   `sd_beta`. Forecast-time drift lives in `forecast.py::forecast_quantiles`, which reads the
   value passed from `run_flusight.py` (live: 0.03). The `forecast.py` default is 0.05, which
   is not what runs. [OPENED]

3. **Inflation is applied to the state, not to the observation ensemble (consistency error).**
   In `_ensrf_update` (eakf.py:75–94), `x` is inflated by λ (`x_mean + λ(x − x_mean)`), but the
   caller passes `ens` (the `X[:,W]` copy or the ILI ensemble) computed before inflation. So
   `cov_xy` uses inflated anomalies, while `ybar`, `pyy` and the anomaly term
   `outer(ens − ybar, k)` use uninflated values. Consistent inflation gives
   `pyy' = λ²·pyy` and `cov_xy' = λ·cov`, so the correct gain is
   `K_c = λ·cov/(λ²·pyy + R)`. The code gives `K' = λ·cov/(pyy + R)`. Ratio
   `K'/K_c = (λ²·pyy + R)/(pyy + R)`, which lies in [1, λ²]. The code gain is therefore
   always overstated: about 0% when `R ≫ pyy`, up to about 6% (λ² − 1) when `pyy ≫ R`
   for λ = 1.03. It never understates. Small, but it is a real inconsistency. Fix: inflate
   `ens` with the same λ, or recompute it from the inflated `x`.
   Any fix changes the frozen model and needs a new pre-registration. [OPENED]

4. **Clipping after each update** (`_clip`) sets negative W/E/I to zero and S to [0, N].
   In troughs the Gaussian EnSRF pushes members below zero, and clipping removes that mass
   without refitting the mean. This biases the posterior upward at low counts and contracts
   spread. [OPENED]

5. **Observation noise is Gaussian on the count scale**, with a relative term:
   `r_var = max((r_rel·y)², 4²)`. Count noise is closer to Poisson-plus-reporting (skewed),
   which the EnSRF cannot represent. The ILI stream is also Gaussian on a fraction. [OPENED]

6. **The observation model ignores reporting revisions.** The brief says first reports
   average ~96% of final nationally (range 78–142%; ~89% in 2025-26). The EAKF assimilates the
   first report as if it were the truth, with 15% noise. Systematically low first reports would
   pull the filter's level down, which could contribute to the documented low-in-declines bias.
   Testable (section 4). The mechanism is an inference, not a measured result. [OPENED: brief §2]

7. **ED stream and look-ahead risk (flag for the owner).** The brief says NSSP published
   versions exist only from Nov 2025; earlier values are final (revised). If 2023-24 and
   2024-25 backtests used final ED values in the ILI update, the reported ED contribution
   (relWIS 3.3–4.2 without it, 0.80–0.85 with it) may be inflated by look-ahead. I did not
   check which vintage `hub_data.py` loads. Check this before trusting any ED-driven claim.
   [INFERENCE; check `hub_data.py` and `run_vintage.py`.]

8. **The forecast predictive distribution is narrower than the filter's own observation
   model.** `forecast_quantiles` takes the posterior ensemble's W over each 7-day block and
   multiplies it by `exp(N(0, s_obs²))` with `s_obs = 0.10`. Missing: (a) the observation noise
   the filter itself assumes (15% relative, floor 4 counts); (b) spread on HIR or c during the
   forecast (only log β drifts). Posterior collapse therefore passes straight into the
   intervals, a likely reason 90% intervals cover ~74%. [OPENED: forecast.py:15–50; size of
   effect is INFERENCE.]

9. **Tuning is tied to WIS.** `METHODS.md` says the forward dispersion "was tuned on the
   calibration sweep, not on accuracy", but the sweep scores on relWIS and coverage over the
   same backtest used to pick the frozen config. The 2023-24 selection rule is in
   `tune_vintage.py`; later seasons are not clean holdouts for the sweep. [OPENED: METHODS.md §4.]

---

## 1. Theory: how each method produces uncertainty

**Kalman filter (KF).** Linear-Gaussian state-space. Predict covariance `P⁻ = F P Fᵀ + Q`,
update with gain `K = P⁻Hᵀ(HP⁻Hᵀ + R)⁻¹`. Uncertainty is the covariance; forecasts are Gaussian.
The SEIR is nonlinear and the counts are non-Gaussian, so a plain KF is not appropriate; it is the
starting point for the ensemble versions.

**Extended / unscented KF.** Linearize (EKF) or use sigma points (UKF). Still Gaussian. The
SEIR is stiff near peaks, so linearization error is largest exactly at turning points.

**Ensemble Adjustment KF (EAKF)** [OPENED: Anderson 2001, MWR 129, 2884]. Anderson's EAKF
updates the whole prior ensemble with a linear operator so that the posterior ensemble has the
correct mean and covariance from Kalman theory, without perturbing observations. Compared with
the perturbed-observation EnKF it avoids the extra sampling noise, and it does better with small
ensembles. The scalar sequential form in `eakf.py` (`x̄' = x̄ + K(y − ȳ)`,
`x'ᵢ = x̄' + (xᵢ − x̄) − α·K·(ŷᵢ − ȳ)`, `α = 1/(1+√(R/(P_yy+R)))`) is the square-root
(ensemble-adjustment) form of that update. Because no observations are perturbed, spread
shrinks faster than in the EnKF, which is why inflation is needed.

**Perturbed-observation EnKF.** Evensen-style EnKF [UNVERIFIED, see section 9]: each member is
updated with `y + ε`, `ε ~ N(0,R)`. Uncertainty comes from ensemble spread plus per-member
observation noise. Sampling error from small M is the main failure mode.

**Covariance inflation.** Multiplicative: `xᵢ' = x̄ + λ(xᵢ − x̄)`.
Adaptive inflation estimates λ from the innovations in a hierarchical Bayesian framework
[OPENED: Anderson 2007, Tellus A 59(2); the method produces inflation comparable to well-tuned
fixed inflation with small ensembles and large model error]. Anderson 2009 (Tellus A 61A, 72–83)
extends this to a normally distributed inflation variable for each state element, varying in
space and time, and reports better mean and variance estimates than fixed or non-adaptive
inflation in two low-order experiments [OPENED: search summaries; full text not read].

**Relaxation-to-prior-spread (RTPS).** [OPENED: Whitaker & Hamill 2012, MWR 140, 2012–2024;
abstract and secondary summaries.] Posterior spread is relaxed back toward prior spread:
`r = 1 + α(σ_a/σ_b − 1)`, where `σ_b` is the prior spread, `σ_a` the pre-inflation posterior
spread, and `α` tunable. It gives no inflation when observations have no impact. Reported in the
paper as slightly more accurate than RTPP and constant inflation, and best combined with additive
inflation when model error is significant. RTPS is purely multiplicative and per-variable; it can
unbalance cross-variable covariances in convective-scale tests (Zeng et al. 2018 [OPENED: search
summary]).

**Particle filter (PF, bootstrap / SIR).** [OPENED: Gordon, Salmond & Smith 1993, IEE Proc F
140.] Propagate particles through the stochastic model, weight by the observation likelihood, and
resample. No Gaussian assumption; a count likelihood (Poisson or negative binomial) is used
directly. Degeneracy is the risk: with an 8-dim state and two observation streams, many particles
(N in the thousands) or a better proposal are needed.

**Liu–West filter.** [UNVERIFIED, see section 9.] PF with kernel shrinkage of parameters toward
their mean. Used by NAU_PyBNF-OracleSIHRS in the hub [OPENED: `model-metadata/NAU_PyBNF-OracleSIHRS.yml`].
The shrinkage parameter (typically 0.95–0.99) biases parameter variance downward, the same
undercoverage risk we have.

**Iterated filtering (IF2).** [OPENED: Ionides, Nguyen, Atchadé, Stoev & King 2015, PNAS, via
search summary; full text not read.] IF2 runs a particle filter over an extended state that
includes parameters perturbed by a random walk whose size cools each iteration. The result is a
parameter swarm that converges toward a maximum-likelihood estimate. Its spread is not a posterior
sample; intervals from IF2 need their own calibration.

**Particle MCMC (pMCMC).** [OPENED: Andrieu, Doucet & Holenstein 2010, JRSS B 72(3), 269–342.]
SMC is used inside an MCMC step, which targets the exact parameter posterior for enough particles.
Uncertainty is the MCMC posterior. Expensive: each MH step runs a full particle filter.
Dureau et al. 2013 applied this to time-varying drivers of epidemics [UNVERIFIED, see section 9].

**ABC / ABC-SMC.** [OPENED: Toni, Welch, Strelkowa, Ipsen & Stumpf 2009, J R Soc Interface;
ABC-SMC with model selection; PubMed and DOI summaries.] Simulate, accept parameters whose
summary statistics fall within a shrinking tolerance. Uncertainty is the accepted-sample posterior.
Needs informative summaries and is expensive at 53 locations × weeks. Hub: `Xi_lab-GLEAM_AI`
uses ABC with two rounds of population Monte Carlo ABC per location [OPENED:
`model-metadata/Xi_lab-GLEAM_AI.yml:30–33`].

**Hub usage of filters** [OPENED: `model-metadata`]:
- SIR-EAKF (Columbia CU-STS family): `CU-STS_base.yml`, `CU-STS_Residual.yml`, `CU-ensemble.yml`
  use the ensemble adjustment KF on a humidity-driven SIR. Closest peer to our method. The hub
  files do not show these ranking above the ensemble on our scoring.
- Liu–West PF: NAU_PyBNF-OracleSIHRS.
- Particle filter over log expected admissions: GT_Influencers-ensemble (inside the ensemble).
- PF with time-varying β: NAU-epymorph.
- MCMC (not filter): MDPredict-SIRS, PSI-PROF, PSI-PROF_MOA, PSI-PROF_beta, BYFlu-STMGGP.
- ABC-PMC: Xi_lab-GLEAM_AI.
- Ours: CyberEpi-EAKF (SEIR + EAKF, no spatial, no strain).

**The EAKF lineage in influenza** [OPENED via search summaries].
- Shaman & Karspeck 2012, PNAS: EAKF assimilates weekly ILI (Google Flu Trends) into a
  humidity-forced SIRS model; NYC 2003–2008; 200 members; inflation 1.02. Peak timing skill
  more than 7 weeks ahead, with confidence tied to ensemble spread.
  https://www.pnas.org/doi/10.1073/pnas.1208772109 ; https://pubmed.ncbi.nlm.nih.gov/23184969/
- Pei, Kandula, Yang & Shaman 2018, PNAS: EAKF on an ensemble metapopulation model with mobility
  and humidity; onset up to 6 weeks ahead at state level.
  https://www.pnas.org/doi/abs/10.1073/pnas.1708856115
- Yang, Karspeck & Shaman 2014, PLoS Comp Biol: compares PF, MIF, pMCMC, EnKF, EAKF, RHF on a
  humidity-forced SIRS model across 115 cities. The two search summaries disagree on whether EnKF
  or EAKF fits better; the full text was not read, so that comparison is unresolved. Consistent
  across summaries: ensemble filters and basic PF reproduce multimodal outbreaks better than MIF
  and pMCMC; PF-based methods do best for peaks 1–4 weeks ahead; ensemble filters (RHF in
  particular) do best 2–6 weeks past. https://journals.plos.org/ploscompbiol/article?id=10.1371%2Fjournal.pcbi.1003583

---

## 2. How this applies to our model

Per unit the state is 8-dim: S, E, I, R, log β, log HIR, W, log c. Two streams per week
(admissions W increment, ILI fraction). 53 units, weekly assimilation, 7-day forecast, h=0..3.

- **EAKF (current):** cheap, works, and the closest hub peer (CU-STS) uses the same family.
  Its weakness is that spread is kept only by inflation and additive parameter noise, so
  undercoverage is what its design predicts.
- **Innovation-likelihood tuning:** the EAKF already returns `pyy` and `chi2` for each update
  (the `info` dict). The summed Gaussian predictive log-likelihood over a season gives a principled
  way to set `sd_beta`, `sd_hir`, `r_rel`, `r_ili_rel` and inflation, without the WIS sweep, and
  can be run leave-one-season-out. This is the most useful immediate change. [INFERENCE from
  code; the adaptive-inflation papers (Anderson 2007) use innovations the same way.]
- **Particle filter with a count likelihood:** natural for skewed counts, and avoids clipping by
  reweighting rather than truncating. Degeneracy is the issue; N≈2000–5000 per unit is likely
  needed. Weekly cost roughly N/300 times the EAKF's integration work. Must be measured.
- **IF2 / pMCMC / ABC:** offline tools to check and re-estimate the hyperparameters, not
  weekly forecasters on the runner. Use one-off to set the noise values, then freeze, per the
  pre-registration rule.

---

## 3. Undercoverage: causes ranked by expected size

Ordered by prior, not measured. Each has a test in section 5. The live forward drift is
`sd_beta_fwd=0.03` (`model_config.json`); the `forecast.py` default of 0.05 is not what runs. Use
the config, not function defaults.

1. **Predictive interval ignores observation noise and revisions** (section 0, item 8). Most
   likely large. Fix: sample predictive W from the filter's observation model (plus a revision term,
   section 4), not only the posterior ensemble.
2. **Posterior collapse of parameters** (log β, log HIR). Additive random walk plus λ = 1.03 is
   too little for two observations per week. Fix: adaptive or RTPS inflation on the parameter block,
   with a separately tuned strength (Anderson 2007/2009; Whitaker & Hamill 2012).
3. **Level bias from first-report data** (section 0, item 6). Interacts with 1: a low-biased level
   with a narrow spread gives systematic misses in declines.
4. **Clipping and Gaussian count noise** in troughs (items 4–5).
5. **Inflation mismatch** (item 3): small, but it can make the gain overconfident or underconfident
   depending on `pyy/R`.

---

## 4. Revision-aware observation model (Track A candidate)

`target-data/time-series.csv` holds every published version (`as_of`, from 2023-09-23). For each
location-date, the first report `y₁` and the final `y∞` are known. Define
`ρ(lag) = median(y_first / y_final)` by lag, estimated only from versions published before each
forecast date (as-of). The admissions observation becomes `y_obs ~ NegBin(mean = ρ(lag)·W,
dispersion = φ)`, with ρ and φ refit weekly from data available at R. Expected effect: less level bias
in declining weeks, and a predictive interval that covers reporting error.

Caveat: about 212 of 2,915 location-dates have no archived version (per the brief). ρ must be
estimated from the rest, and the code must handle missing ρ without look-ahead.

---

## 5. Ranked experiments

All experiments: develop on 2023-24 and 2024-25 leave-one-season-out (LOSO); 2022-23 only where the
data allow. The 2025-26 holdout is used up and must not inform any choice. Pre-register each
comparison (metric, pooling, thresholds, decision rule) in a file committed before the run. Use
as-of data only at each forecast date R. Report 50% and 95% coverage per horizon, relWIS vs
baseline, and per-phase (rising / near peak ±2 weeks / declining) scores, on raw and log-scale WIS.

**E0 (precondition). Confirm the vintage of ED and admissions data** loaded by `hub_data.py` and
`run_vintage.py` for every forecast date. No experiment until this is checked.

**E1 (Track A candidate). Innovation-likelihood tuning instead of the WIS sweep.** Fit `sd_beta`,
`sd_hir`, `r_rel`, `r_ili_rel`, inflation by maximizing the summed Gaussian innovation
log-likelihood (from `info["pyy"]`, `info["chi2"]`) on training seasons; freeze; score the held-out
season. Decision rule: beats the frozen config's held-out relWIS on both LOSO folds, and 95% coverage
in [0.90, 0.98] on both. Cost: one EAKF pass per candidate setting (unmeasured).

**E2 (Track A candidate). Predictive distribution from the observation model.** Add NegBin(W, φ)
draws (φ fit on LOSO training residuals) to the forecast quantiles in `forecast_quantiles`, in
place of or in addition to the ±10% lognormal jitter. Target: 50% and 95% coverage within ±5 points
on each fold. Most direct test of cause 1.

**E3 (Track A candidate). RTPS or adaptive inflation on the parameter block.** Replace the fixed
λ = 1.03 with RTPS (α ∈ {0.8, 0.9, 0.95}) on log β, log HIR, log c. Fix the inflation mismatch
(section 0, item 3) first, as a bug fix, before tuning. Decision rule as E2.

**E4 (Track A candidate, after E0). Revision-aware observation model** (section 4). Decision rule:
improves decline-phase relWIS on both LOSO folds without hurting rising-phase relWIS by more than 2%.

**E5 (Track B). Bootstrap PF with NegBin likelihood**, N ∈ {1000, 2000, 5000}, with resample-move
on parameters against degeneracy. Compare against the EAKF on the same as-of data, LOSO. Measure
runtime on the 4-CPU runner before any decision. Shadow mode unless it wins by the E1 rule.

**E6 (Track B, offline). IF2 on the frozen SEIR** per season, to check whether the EAKF's `sd_beta`
and `r_rel` fall inside the IF2 swarm.

**E7 (Track B, offline). pMCMC on one season's hyperparameters** (`sd_beta`, `r_rel`, φ), as an
oracle check on E1's values. Not per week.

**E8 (Track B, offline). ABC-SMC on summary statistics** for the national series (peak height,
peak week, rise rate, decline half-life), summaries pre-registered before running.

**E9 (Track B). Log-scale EnSRF.** Assimilate `log1p(y)` so that multiplicative noise and clipping
are handled naturally. Compare to the EAKF on LOSO. Shadow mode.

**E10 (Track B). Multi-filter combination** of EAKF, PF and RTPS-EAKF with equal weights
(shrinking any learned weights, per the combination-puzzle rule). Do not add until E1–E4 settle.
Coordinate with family 08.

---

## 6. Failure modes

- Tuning on the sweep and reporting the same seasons (current risk; section 0, item 9).
- Innovation likelihood overfits training seasons with many free parameters; keep it to five scalars.
- Revision ratios estimated from data after R (look-ahead). Use the as-of table only.
- NegBin φ fit on in-season residuals is dominated by the peak; fit on LOSO training seasons only.
- PF degeneracy: report effective sample size per week; if ESS < 0.3 N, distrust that week.
- IF2 swarm intervals are not posterior intervals; do not report them as such.
- pMCMC on one season can overfit that season; use only for hyperparameters, with a prior not tuned
  on the same season.
- Coverage can be met by widening everything; report sharpness (interval width) next to coverage
  and judge on WIS.

---

## 7. Cost on a 4-CPU, 30-minute weekly budget

Estimates, not measurements. The weekly EAKF is the baseline.

- EAKF (current, M=300): one stacked 2,400-state RK45 per unit per day, 7 days per week. Expected
  seconds to a few minutes total. Measure on the runner.
- E1, E8, E6, E7: offline; weekly use only of frozen values.
- E2, E3, E4: negligible extra weekly cost (sampling, vector ops, a small offline ρ table).
- E5 (PF, N=2000): roughly 6–7 times the EAKF integration work. Probably fits if the EAKF takes
  minutes; measure first.
- E9: same cost as the EAKF. E10: sum of its parts.

---

## 8. Recommendations (ranked)

1. **Check the ED and admissions vintages used in backtests (E0)** before any further ED-based
   claim. Possible look-ahead.
2. **E2: predictive intervals from the observation model** (most likely cause of undercoverage).
   Track A candidate; φ fit on LOSO training seasons.
3. **E1: tune noise and inflation by innovation likelihood**, not the WIS sweep; then freeze.
   Track A candidate.
4. **E3: RTPS on the parameter block, after fixing the inflation mismatch.** Track A candidate.
5. **E4: revision-aware admissions observation model**, after E0. Shadow mode first.

Shadow candidates: E5 (PF), E9 (log-scale EnSRF). Offline only: E6–E8.

---

## 9. References

**Opened (abstract, DOI or search summary; full text mostly not read):**
- Anderson JL (2001). An ensemble adjustment Kalman filter for data assimilation. Mon Weather
  Rev 129(12), 2884. https://journals.ametsoc.org/view/journals/mwre/129/12/1520-0493_2001_129_2884_aeakff_2.0.co_2.xml
- Anderson JL (2007). An adaptive covariance inflation error correction algorithm for ensemble
  filters. Tellus A 59(2). DOI 10.1111/j.1600-0870.2006.00216.x
- Anderson JL (2009). Spatially and temporally varying adaptive covariance inflation for ensemble
  filters. Tellus A 61A(1), 72–83. DOI 10.1111/j.1600-0870.2008.00361.x
- Whitaker JS, Hamill TM (2012). Evaluating methods to account for system errors in ensemble data
  assimilation. Mon Weather Rev 140(9). https://journals.ametsoc.org/view/journals/mwre/140/9/mwr-d-11-00276.1.pdf
- Zeng Y et al. (2018). Representation of model error in convective-scale data assimilation:
  additive noise, relaxation methods, and combinations. JAMES.
  https://agupubs.onlinelibrary.wiley.com/doi/10.1029/2018MS001375
- Gordon NJ, Salmond DJ, Smith AFM (1993). Novel approach to nonlinear/non-Gaussian Bayesian state
  estimation. IEE Proc F 140(2). https://digital-library.theiet.org/doi/10.1049/ip-f-2.1993.0015
- Andrieu C, Doucet A, Holenstein R (2010). Particle Markov chain Monte Carlo methods. JRSS B
  72(3), 269–342. DOI 10.1111/j.1467-9868.2009.00736.x
- Ionides EL, Nguyen D, Atchadé Y, Stoev S, King AA (2015). Inference for dynamic and latent variable
  models via iterated, perturbed Bayes maps. PNAS. https://pubmed.ncbi.nlm.nih.gov/25568084/
- Toni T, Welch D, Strelkowa N, Ipsen A, Stumpf MPH (2009). Approximate Bayesian computation scheme
  for parameter inference and model selection in dynamical systems. J R Soc Interface.
  DOI 10.1098/rsif.2008.0172
- Shaman J, Karspeck A (2012). Forecasting seasonal outbreaks of influenza. PNAS 109.
  DOI 10.1073/pnas.1208772109
- Pei S, Kandula S, Yang W, Shaman J (2018). Forecasting the spatial transmission of influenza in the
  United States. PNAS 115(11). DOI 10.1073/pnas.1708856115
- Yang W, Karspeck A, Shaman J (2014). Comparison of filtering methods for the modeling and
  retrospective forecasting of influenza epidemics. PLoS Comput Biol.
  https://journals.plos.org/ploscompbiol/article?id=10.1371%2Fjournal.pcbi.1003583
- Hub `model-metadata/` entries listed in section 1 (grep only).

**Unverified (three, kept because they are needed for named methods):**
- [UNVERIFIED] Evensen G (1994). Sequential data assimilation with a nonlinear quasi-geostrophic
  model. JGR. Kept for the perturbed-observation EnKF description only; not used for any claim.
- [UNVERIFIED] Liu J, West M (2001). Combined parameter and state estimation in simulation-based
  filtering. Used to describe the Liu–West filter, which NAU_PyBNF uses.
- [UNVERIFIED] Dureau J, Kalogeropoulos K, Baguelin M (2013). Capturing the time-varying drivers of an
  epidemic using stochastic dynamical systems. Biostatistics. Cited as the epidemic application of
  pMCMC; the claim is not used in any decision.

**Dropped this round (no longer cited):** Whitaker & Hamill 2002 EnSRF attribution (replaced by
Anderson 2001), Bishop et al. 2001 ETKF, Sakov & Oke 2008 DEnKF, Burgers et al. 1998, Pitt & Shephard
1999 APF, Doucet & Johansen 2009, Fearnhead & Künsch 2018, Ionides et al. 2006 IF1, Shaman & Karspeck
2012 "EAKF lineage" tag (now verified above).

---

## Top 5 recommendations (summary)

1. Check the ED and admissions vintages in backtests (E0) before trusting any ED-driven claim.
2. E2: build predictive intervals from the observation model (NegBin, LOSO-fitted φ). Track A candidate.
3. E1: tune noise and inflation by innovation likelihood, not the WIS sweep. Track A candidate.
4. E3: RTPS on the parameter block, after fixing the inflation mismatch. Track A candidate.
5. E4: revision-aware admissions observation model, after E0. Shadow mode first.
