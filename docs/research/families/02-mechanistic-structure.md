# Family 02: mechanistic structure, renewal and curve models

Scope: SIR/SEIR variants, multi-strain, age structure, metapopulation, humidity forcing, renewal/Rt models, curve models, and a diagnosis of model 1's too-steep post-peak decline. Read first: `docs/research/PROBLEM_BRIEF.md`, `backtest/eakf.py`, `backtest/seir_fast.py`, `backtest/forecast.py`, `backtest/run_flusight.py`, `backtest/model_config.json`, `backtest/METHODS.md`, `BACKTEST_RESULTS.md`.

Labels: `[CODE]` = read in this repo; `[HUB]` = read in hub `model-metadata/`; `[INFERENCE]` = my reasoning or a calculation, not observed; `[LIT, UNVERIFIED]` = from memory, not opened in this session.

---

## 0. Diagnosis: why model 1 declines too steeply

### 0.1 What the code does [CODE]

- State per location: (S, E, I, R, log β, log HIR, W, log c). Latent 1/σ = 1.2 d, infectious 1/γ = 3.8 d (`seir_fast.py`).
- Assimilation (`eakf.py`, `forecast_week`): each day, `log β += N(0, sd_beta)`, `log HIR += N(0, sd_hir)`, `log c += N(0, sd_lc)`. Live config has sd_beta 0.03, sd_hir 0.005, sd_lc 0.01.
- Admissions update: observe weekly W increment, noise sd = max(0.15·y, 4). ED update: observe `c·I/N`, noise sd = max(0.10·y, 5e-4). No intercept in the ED observation.
- Forecast emission (`forecast.py`, `forecast_quantiles`, called once per origin from `run_flusight.py` lines ~97–106 via `run_location`, which `run_vintage.py` also uses): the 7-day blocks use `sd_beta_fwd` (0.03 live) as a zero-drift log-β random walk. HIR and c are frozen. The only other spread is a lognormal jitter `s_obs` = 0.10 on admissions.
- Inflation 1.03 is applied to ensemble anomalies once per weekly update, then the state carries over.
- Note: `METHODS.md` still lists sd_β 0.05, rel 0.30/0.15 and sd_β,fwd 0.05. The live config (`model_config.json`) is what runs. This doc drift should be fixed separately.

### 0.2 Mechanism [INFERENCE from the equations]

1. **The tail slope of a fixed-Rt SEIR is set by Rt alone.** Linearised around a constant β, the slowest eigenvalue λ solves (λ+σ)(λ+γ) = σγR (with the Erlang variant noted in §1.1). I computed the weekly decay factor exp(7λ):

   | Rt (held constant) | SEIR weekly factor | 3-stage Erlang infectious weekly factor |
   |---|---|---|
   | 0.9 | 0.87 | 0.87 |
   | 0.8 | 0.75 | 0.74 |
   | 0.7 | 0.64 | 0.62 |
   | 0.5 | 0.46 | 0.41 |

   Adding compartments does not slow the tail. The steepness is a property of the Rt the filter holds, not of the SEIR structure. Any model that holds Rt ≈ 0.7 for four weeks extrapolates a 35% weekly drop.

2. **The filter estimates Rt from the most recent slope and then extrapolates it.** The EnSRF pulls log β down in proportion to the recent observed fall (admissions, and ED share through I). The forward walk in `forecast_quantiles` is zero-drift in log β, so the median stays at the posterior Rt. Nothing pulls Rt back toward the seasonal mean or toward 1. In a declining phase the ensemble median therefore keeps falling at the current pace. This matches the reported ~40% low 3-week medians in declines (`PROBLEM_BRIEF` §5).

3. **Two streams push Rt down together.** The ED stream has no baseline, so `c·I/N` must reach zero to fit a low ED share. Non-flu ILI/ED share is not zero at the trough, so this forces I (and hence admissions) lower than the data support. The ED stream carries most of the skill (`BACKTEST_RESULTS.md`), so this bias is large where it matters. The intercept is absent from `eakf.py` `update_ili` (the ensemble observation is `exp(LC)·I/N` alone). [INFERENCE, testable in §0.4]

4. **Revisions bias the last observed week downward.** As-published first reports average ~96% of final nationally, and ~89% in 2025-26 (`PROBLEM_BRIEF` §2). The most recent week always carries the largest revision. With r_rel 0.15 the filter trusts that point, so a decline in the as-published series is partly a reporting artifact that the model reads as a real decline. The honest run (as-published) costs only 0–8% relWIS, so this is probably a second-order contributor, but it acts in the same direction. [INFERENCE]

5. **Spread collapse is not the cause of the bias, but it hides it.** Coverage is low (50% ≈ 0.37, 90% ≈ 0.74). The problem is the median, not the width. Widening the intervals (what `tune_vintage` did) fixes coverage without moving the median, so it does not solve the decline bias. This also matches the failed post-hoc widening (`PROBLEM_BRIEF` §5).

6. **HIR cannot absorb the admissions tail.** sd_hir is 0.005 per day and HIR is frozen in the forecast. Admissions per infection cannot change to explain a reporting tail or a shift in age mix, so β has to take all the blame. An explicit infection-to-admission delay kernel (§3.3) would move part of the explanation out of β.

7. **S depletion and the missing admission delay.** The eigenvalue table holds S fixed. S starts near 0.96, so depletion is small early, but over a large season the susceptible fraction falls by the attack rate, lowering effective Rt in exactly the post-peak phase. Separately, W = HIR·σE is produced at infection onset with no lag to hospitalisation, so admissions lead real admissions and both peak and decline come early. With 1/γ = 3.8 d nothing smooths the fall. A gamma delay kernel (§3.3) belongs in the diagnosis.

### 0.3 Priority of explanations (for ranking experiments)

- Most likely: (2) no mean reversion in the forward β walk, with Rt extrapolated from the latest slope. Strongest structural case.
- Likely, and cheap to test: (3) the ED observation lacks a baseline/intercept.
- Plausible: (4) revision bias on the last point, which the nowcasting family (06) should also address.
- Less likely as the main cause: (5) spread collapse. It may still matter for coverage.
- Also test first (D-0): S depletion and the missing infection-to-admission delay (§0.2 item 7). These are alternatives to (2) and are not yet ranked against it.

### 0.4 Diagnostic experiments (Track A, diagnosis only; pre-registered; no new settings chosen from them)

Data: 2023-24 and 2024-25 only (2025-26 is used up). Use the as-published admissions vintages and `--ili final` or `vintage` as in `run_vintage.py`. Define "declining phase" before running: reference dates from 2 weeks after the national peak until the first week where the observed count is below 25% of the peak. The national peak is computed from final data and is fixed before the run.

- **D-0 Ablation (run; results in the table below).** Use `run_vintage.py` on a handful of locations (US, 06, 36, 48) for 2023-24 and 2024-25. Split rows by phase (before peak / after peak) and by horizon (h0 vs h3). Three arms: (a) live settings; (b) `--sd-beta-fwd 0`, which removes forward β noise only (the walk has zero drift, so the median Rt is unchanged; it tests spread, not reversion); (c) drop the last as-of admissions week, which isolates backfill. For depletion, record mean S/N at each origin and check whether post-peak bias grows with cumulative attack rate. Predictions: if backfill is the cause, arm (c) removes most post-peak bias; if depletion, bias tracks S/N loss. Arm (b) cannot test reversion; D-3 is still untested.
  **D-0 setup (as run).** Dev seasons 2023-24 and 2024-25 only. Locations US, 06, 36, 48. Live settings passed explicitly to `run_vintage.py` (sd-beta 0.03, sd-beta-fwd 0.03 for arms a and c, sd-hir 0.005, r-rel 0.15, inflation 1.03, s-obs 0.10, sd-lc 0.01, r-ili-rel 0.10, members 300, seed 1; `--ili final`). Arm b: `--sd-beta-fwd 0`. Arm c: via a /tmp wrapper that keeps the grid to the last observed week but marks that newest admissions week as missing. Data via symlinks in `data/flusight` (staged, gitignored). Python 3.12 venv in /tmp.
  **Pre-registration disclosure.** An expectation was drafted in an attempt to write this into the file before running, but the edit failed twice and the arms ran first. So the expectation below is not a valid pre-registration. Treat the pass/fail calls as post-hoc. The stated expectation was: arm b cuts post-peak h3 median bias by at least a third; arm c changes it by less than a third; arm a matches the honest run within rounding.
  **D-0 results (median log bias = log((median+1)/(truth+1)); negative = forecast too low; WIS absolute; phases from US final-data peak per season).**

  | Phase, horizon | Arm a (live) bias / WIS | Arm b (no fwd drift) bias / WIS | Arm c (last week missing) bias / WIS |
  |---|---|---|---|
  | Post-peak, h0 | −0.131 / 1090 | −0.125 / 1100 | −0.110 / 1291 |
  | Post-peak, h3 | −0.346 / 1478 | −0.350 / 1426 | −0.309 / 1498 |
  | Pre-peak, h0 | −0.117 / 1745 | −0.104 / 1741 | −0.107 / 1932 |
  | Pre-peak, h3 | −0.452 / 9302 | −0.415 / 9439 | −0.226 / 10559 |
  | Peak to +2 wk, h3 | 0.361 / 8523 | 0.360 / 8231 | 0.337 / 8219 |

  Counts: post-peak 128 per horizon; pre-peak 72–84; peak to +2 wk 16 per horizon. Pooled arm a relWIS is 0.626 vs baseline (2024-25 alone 0.590), not directly comparable with BACKTEST_RESULTS (different location set, ED input), so the reproduction check is not met.
  **Reading.** (1) Arm b removes forward β noise only. The median is unchanged (post-peak h3 −0.346 → −0.350; pooled relWIS identical), and coverage moves (cov50 0.51 → 0.44). It therefore says nothing about mean reversion of Rt. D-3 (a reverting walk) is still untested. (2) Backfill (arm c) moves post-peak h3 bias by about 11% and makes WIS worse, so it is at most a small contributor. (3) The post-peak bias of about −0.3 log units at h3 survives both ablations, so D-2 (ED intercept), the missing admission delay (§0.2 item 7), depletion, and D-3 are the remaining candidates. (4) Pre-peak h3 bias moves from −0.45 (live) to −0.23 (arm c), so the last observed week drives the early-season under-forecast (negative bias = forecast too low) and is worth checking. Limits: four locations only, one ED input, no phase-level significance test.
- **D-1 Innovation signs.** Log, at each declining origin, the signed innovation (y − ȳ) for admissions and for the ED stream, plus `chi2` (`_ensrf_update` already returns these). Pass if the mean signed ED innovation is significantly negative in declines (this confirms item 3). Test: a one-sample t-test with block bootstrap over weeks, α = 0.05, across both seasons and all locations.
- **D-2 Intercept.** Add a fixed ED baseline b to the observation `c·I/N + b`. Set b from the lowest ED value in each location's previous off-season (no look-ahead), leave out one season at a time. Compare the declining-phase median bias (3-week median minus truth, log scale) with and without b. Hypothesis: bias falls by at least half.
- **D-3 Mean reversion.** Replace the zero-drift forward walk with log β_t = μ + φ(log β_{t−1} − μ) + ε, where μ is the season-to-date geometric mean of β (or a prior value) and φ = exp(−ln2 / half-life in weeks). Test half-lives 2, 4 and 8 weeks. Dev seasons leave-one-season-out. Pass if declining-phase bias shrinks without lowering peak-phase relWIS by more than 2%.
- **D-4 Spread check.** Compare the posterior spread of log β with the realised innovation variance (ratio near 1 means calibrated). Use it to choose between constant inflation and relaxation to prior spread (RTPS, Whitaker & Hamill 2012 [verified: MWR 140(9), title and journal confirmed by search, abstract not opened]). This belongs to family 03 but is listed here because it explains the coverage.
- **D-5 Revision bias.** For declining origins, compare relWIS and median bias using (a) final admissions, (b) as-published, and (c) as-published with the last point inflated by the historical first-report ratio (`time-series.csv`). Family 06 provides the ratio. Pass if (c) reduces declining-phase bias with no peak-phase cost.

---

## 1. Structural variants of SIR/SEIR

### 1.1 Erlang / gamma-distributed stages (fixed-rate chain)

- **Theory.** Replace a single compartment by k sub-compartments at rate kγ (or kσ). This gives a gamma-distributed infectious period with mean 1/γ and CV 1/√k. It does not change Rt, and in §0.2 it barely changes the tail slope.
- **Application.** Use k = 3 for infectious and a longer latent (k = 2) to fit the observed incubation/infectious spread. Keep mean durations fixed at 1.2 d and 3.8 d so comparisons are fair.
- **Evidence.** Standard in epidemic models (Lloyd 2001 [LIT, UNVERIFIED]). Hub: `CU-STS` and `cfa-flumech` [HUB] do not state their chain structure in the fields I read; not verified.
- **Failure modes.** More compartments add parameters without identifying them from weekly counts. Fine structure will not fix the decline bias (§0.2).
- **Cost.** Trivial CPU; adds 2–3 state dims per location.
- **Experiment.** Track B, low priority. Test k ∈ {1, 2, 3} for infectious period, leave-one-season-out, to confirm the claim in §0.2 numerically.

### 1.2 SIRS / waning immunity and reintroduction

- **Theory.** Add R → S at rate ω. This gives a slow, season-to-season replenishment of susceptibles and an endemic floor. Effective Rt is β S/(γ N). Under waning, the post-peak tail can flatten because a replenished pool carries infections forward.
- **Application.** In a 4-month season, waning of a few months is slow relative to the season. Most value would be across seasons (carry-over of the R compartment into the next season), which matters for the 2026-27 start. Reintroduction could come from neighbouring states (§4).
- **Evidence.** `Cornell_JHU-hierarchSIR` and `SCARCHhierarSIR` [HUB] use SIR with time-varying transmission across seasons via a hierarchical prior. `NAU_PyBNF-OracleSIHRS` [HUB] uses a SIHRS form (waning included). `PSI-PROF` [HUB] is SIR[H]² with time-varying β.
- **Failure modes.** Waning rates are weakly identified from one season of weekly counts. Adding ω without a prior invites the same kind of luck fitting the brief warns about.
- **Cost.** Adds one parameter per location; cheap.
- **Experiment (Track B).** SIRS with ω ~ prior from earlier seasons, versus the current SEIR. Test on 2023-24 and 2024-25 leave-one-season-out, scoring declining-phase bias (§0.4) and relWIS.

### 1.3 Time-varying β as a random walk vs an AR process with a hierarchical prior

- **Theory.** The current model is a log-random-walk (non-stationary). An AR(1) on log β with a seasonal prior mean is stationary and reverts; it is the mechanism proposed in D-3.
- **Application.** Directly addresses the diagnosis. In a hierarchical setting, μ and φ come from earlier seasons (leave-one-out), which avoids tuning on the scored season.
- **Evidence.** The `Cornell_JHU-SCARCHhierarSIR` description in `model-metadata/` [HUB] says it uses an AR, conditionally heteroskedastic, spatially correlated transmission with across-season hyperparameters. I read this description; I did not check their code or scores.
- **Failure modes.** A mean-reverting prior can pull a real late-season surge back to the average. The mean must be learned from past seasons only.
- **Cost.** Same as now plus a one-off hyperparameter estimate per season.
- **Experiment.** D-3 above (Track A diagnosis, then Track B shadow model if it wins dev).

### 1.4 Multi-strain (H1N1pdm09, H3N2, B) SIR/SEIR

- **Theory.** Two or three coupled SIR systems with cross-immunity (partial protection of one strain against another), each with its own β. Co-circulation produces double peaks and tails.
- **Application.** The data have no strain split in the hub target. Strain shares would have to come from a public surveillance feed (FluView/NREVSS, which is family 09's scope). Without strain-specific admissions, a multi-strain model is identified only by shape and is likely to overfit.
- **Evidence.** `cfa-flumech` [HUB] fits three subtypes (H1N1pdm09, H3N2, B), three age groups, and clinical positivity and public-health lab test-distribution data. Its methods field is a long description; I did not verify fits or scores.
- **Failure modes.** Heavy identifiability problems with admissions only. Strain-specific priors from a different season will be wrong when a new subtype takes over (the 2025-26 season dynamics are not comparable with earlier ones).
- **Cost.** Two to three times the state dimension; EnSRF cost scales with the ensemble size and states; at 300 members and 53 locations it stays inside budget but the filter becomes unstable without more observations.
- **Experiment (Track B).** Two-strain SIR with strain share from NREVSS (once family 09 provides an as-of archive). Shadow only. Pre-register "strain share from data available at R" as the only allowed input.

### 1.5 Age-structured SEIR

- **Theory.** Partition the population into age groups with a contact matrix C. Force of infection λ_i = β Σ_j C_ij I_j / N_j. Hospitalisation probability depends on age, so admissions weight the age mix. Age structure creates a slower tail (children and adults decline on different schedules).
- **Application.** Admissions are heavily concentrated in 65+ in flu seasons. Age mix shifts the admissions-to-infection ratio, which is exactly the job of HIR. A two-group model (0–64, 65+) with age-specific HIR would let HIR absorb age shifts, which the current model cannot do (§0.2, item 6).
- **Evidence.** `cfa-flumech` [HUB] uses three age groups (children, adults, 65+). `PSI-PROF` and `NU-PGF_FLUH` [HUB] are age-agnostic (SIR[H]² and SLIR with PGFs). I did not verify fits.
- **Failure modes.** Age-specific admissions are not in the hub target (`wk inc flu hosp` is all-age). Age-group splits must come from external data (NHSN age files or FluSurv-NET), which lack an as-of archive (`PROBLEM_BRIEF` §2), so they can be used only in shadow mode.
- **Cost.** Two groups multiply state by two; fine for 53 locations at 300 members.
- **Experiment (Track B).** Two-group SEIR with a contact matrix from prior seasons, shadow mode. Dev test is limited to whatever external data can be reconstructed as-of. If not, this stays shadow-only.

### 1.6 Metapopulation (GLEAM-style) and spatial coupling

- **Theory.** Locations are coupled by a mobility network. Epidemics seed from neighbours with a delay set by travel. The state is one SEIR per location plus a coupling matrix.
- **Application.** The 53 locations are states and territories with commuting and flight links. Mobility can predict onset timing for a state from its neighbours (family 11 covers hhh4 and lead-lag). For the current model, coupling would help the 2026-27 season start only if neighbouring states lead.
- **Evidence.** `MOBS-GLEAM_FLUH`, `MOBS-GLEAM_NCB_FLUH`, `MOBS-GLEAM_PONG`, `MOBS-GLEAM_RL_FLUH` [HUB] are GLEAM metapopulation age-structured SLIR models; `Xi_lab-GLEAM_AI_hybrid` [HUB] trains a surrogate on GLEAM simulations. I read the GLEAM description: age-structured SLIR on mobility networks. I did not verify their scores.
- **Failure modes.** Mobility data (commuting flows, flights) are not in the hub and have no as-of archive. A network is also a large parameter set. Coupling can spread a bias from one state to its neighbours.
- **Cost.** Matrix multiply per day across 53 locations is cheap; calibration of the coupling is not.
- **Experiment (Track B).** Gravity-style coupling with a fixed (published) mobility matrix and one scalar coupling strength fitted on dev seasons. Shadow only. Pre-register that the coupling is fixed at zero if dev gain is below 2%.

---

## 2. Humidity and climate forcing

- **Theory.** Influenza transmissibility rises when absolute humidity is low (Shaman et al. 2010, PLoS Biology [verified: journal corrected from PNAS by search; PMC copy exists, not opened]; Lowen et al. 2007 [LIT, UNVERIFIED]). Forcing enters as β(t) = β₀(1 + a·(AH(t) − mean)).
- **Application.** Forcing would add a seasonal term to β and so affect the Rt extrapolation (§0.2). It is a candidate for the mean-reversion target in D-3: the reverting mean is a function of climate, not a constant.
- **Evidence.** `NAU_PyBNF-OracleSIHRS` [HUB] uses an annual harmonic on transmission (a seasonal term, not humidity). I did not find humidity in the metadata fields I read. Not verified for the other teams.
- **Failure modes.** Humidity gives a seasonal timing signal, but the 2025-26 and 2026-27 early-season onset is not explained by climate alone. Spurious correlation is very likely with four seasons. Weather archives are reanalysis, not as-of forecasts; the forecasts use the weather of the day, which is fine for backtest only if the same reanalysis product is used at forecast time. Real-time weather forecasts would be required for honest use.
- **Cost.** Trivial to read; the honest test needs a published weather forecast archive (not identified in this repo).
- **Experiment (Track B, low).** Sine-in-AH term with prior from the literature, leave-one-season-out on 2023-24 and 2024-25. Only as shadow. Do not use it for Track A without a strong dev gain.

---

## 3. Renewal / Rt models

### 3.1 Renewal equation (Cori et al.) with serial interval

- **Theory.** Incidence I_t = R_t Σ_s w_s I_{t−s}, where w is the generation (serial interval) distribution. Rt is estimated with a Gamma prior on the instantaneous reproduction number (Cori, Ferguson, Fraser, Cauchemez 2013, Am J Epidemiol 178(9):1505–1512 [verified: citation by search; full text not opened]). Uncertainty comes from the posterior of R_t given the observed incidence history.
- **Application.** Directly relevant: the post-peak tail is governed by Rt through w (§0.2). The renewal model makes Rt the state with no latent compartments. Because the serial interval is short for flu (~3 d), the renewal equation is nearly identical to SEIR in this setting; the difference is the prior on R_t.
- **Evidence.** `cfaepimlight` (`cfarenewal-cfaepimlight`) [HUB]: renewal model fit with Epidemia (Stan) to daily hospital incidence, weekly random walk on R_t extrapolation, day-of-week effects. `CFA_Pyrenew-Pyrenew_H_Flu`, `_HE_Flu`, `_E_Flu` and `CFA-PyRenew_H/HE/E` [HUB]: PyRenew renewal models on hospitalisations and ED visits. Their own design is the closest comparator to our EAKF, and its R_t random walk (not AR) is the same structural choice as ours (§0.2).
- **Failure modes.** A weekly random walk on R_t has the same extrapolation problem. Gamma priors on R_t are weak; the prior shrinks toward 1, which in declines may be too gentle.
- **Cost.** A Gamma-posterior update is closed form: negligible. Full Stan/NUTS is too slow for 30 minutes; the closed-form renewal update is fine.
- **Experiment (Track A, cheap).** Run the closed-form renewal model on the same data and the same as-of vintages, leave-one-season-out, and compare declining-phase bias to the EAKF. Pre-register: if the renewal model shows the same bias, the cause is the data (§0.2 item 3–4), not the filter. This is the cleanest test of the diagnosis.

### 3.2 Rt random walk vs AR(1) with prior mean

- **Theory.** Same as §1.3 in renewal form. The AR(1) prior pulls R_t toward a mean; in a declining phase the posterior mean moves toward 1 with the given half-life.
- **Evidence.** PyRenew and Epidemia both use random walks [HUB]: the structural choice our model shares. An AR option is not in their descriptions that I read.
- **Failure modes.** As in §1.3.
- **Experiment.** D-3 (applies to both EAKF and the renewal model).

### 3.3 Semi-mechanistic renewal with day-of-week and reporting delay

- **Theory.** Observation model: observed = reporting-fraction × (delayed incidence). Day-of-week effects are multiplicative. This is how PyRenew and Epidemia separate reporting from transmission.
- **Application.** The current model has no observation lag: admissions equal HIR·σE immediately. A delay kernel (gamma with mean 4–7 d) before admissions would turn the peak forward and make the decline look less steep (since admissions track infections with a lag). This is a cheap structural fix, Track A candidate if it wins dev.
- **Evidence.** `cfa-pyrenew` and `cfaepimlight` [HUB] both include a delay/day-of-week layer as part of the observation model (from descriptions; not verified in code).
- **Failure modes.** A delay kernel without a dev gain is overfit. The weekly counts already smooth the delay, so the effect may be small.
- **Experiment (Track A, DIAG-level).** Add a gamma delay (mean 4–7 d, shape fixed) between E-driven incidence and the admissions observation. Pre-register; leave-one-season-out; test peak-timing error and declining-phase bias.

---

## 4. Curve models (no mechanism)

### 4.1 Farr's law and Richards / logistic curves

- **Theory.** Farr (1840s) proposed that epidemic incidence follows a symmetric bell in log-time. Richards (1959) gives a flexible growth family with asymmetric peaks. Fit a curve to the season's incidence so far and extrapolate. Uncertainty comes from the fit covariance.
- **Application.** Fits the post-peak tail as a parametric decline without an Rt. It is the honest alternative to §0.2: the curve's decline rate is set by a shape parameter that is estimated from all of the season, not from the last few weeks.
- **Evidence.** Historical; Farr and Baroyan-Rvachev are in family 12's scope (the 12-rare-cross-domain report). For the hub: `CU-STS_*` [HUB] are state-space time series (family 01), not curves.
- **Failure modes.** Symmetric curves can't fit a shoulder or a double peak. Richards fits are unstable with a short rising phase, exactly the early-season case in 2026-27.
- **Cost.** Trivial.
- **Experiment (Track B, cheap, and a useful baseline for D-1 to D-5).** Fit Richards to the season's cumulative as-of incidence at each origin; forecast the tail. Compare declining-phase bias with EAKF. Pre-register: a curve that wins in declines but loses at peak is a phase-aware candidate for family 10.

### 4.2 Gompertz and cumulative-count curves

- **Theory.** A cumulative count follows a Gompertz curve (double-exponential). Incidence is its derivative.
- **Application.** Cumulative hospitalisations are less sensitive to reporting noise than weekly counts. The curve gives the season's final size and a tail shape; the peak-size target (`peak inc flu hosp`) can use it.
- **Evidence.** Historical; no hub team's metadata that I read uses Gompertz as the main form.
- **Failure modes.** Final-size estimates need the full season; early origins are weak.
- **Experiment (Track B).** Use Gompertz only for the peak-size target, shadow mode, to be scored on the `peak inc flu hosp` target (family 13 for scoring).

---

## 5. Ranked experiment list

Track A = candidate to change what we submit (needs strong dev evidence). Track B = shadow mode. All pre-registered; dev seasons leave-one-season-out on 2023-24 and 2024-25; no 2025-26 use.

Run first: D-0 ablation (§0.4). It separates drift, backfill and depletion before any Track A change. Erlang stage counts (§1.1) are low priority: the filter refits β to the observed slope, so stage structure mostly relabels Rt.

1. **[Track A, diagnosis] D-1 innovation signs + D-3 mean reversion with half-lives 2, 4, 8 weeks.** This is the decisive test of §0.2 item 2. If it cuts declining-phase bias by at least a third at no peak-phase cost on both dev seasons, it is the top candidate for a change to model 1.
2. **[Track A, diagnosis] D-2 ED intercept b.** Cheap; fixes a likely observation error (§0.2 item 3). If it helps, adopt with the baseline set from off-season data only.
3. **[Track A, cheap comparator] §3.1 closed-form renewal model on the same as-of data.** If it shows the same bias, the cause is the data (revision and ED baseline), so fix §0.4 D-5 first. If it does not, the filter is at fault.
4. **[Track A] §3.3 reporting delay kernel.** Test only if item 1 or 3 fails to explain the bias.
5. **[Track B] §4.1 Richards curve as a declining-phase baseline**, plus §1.2 SIRS across seasons and §1.5 two-group age SEIR, all in shadow mode.
6. **[Track B, low] §1.4 multi-strain and §1.6 metapopulation** only once family 09 supplies as-of strain or mobility data. §2 humidity only with a published, as-of forecast archive.

## 6. What to tell the orchestrator about model 1 (summary)

- The too-steep decline is most likely the forward Rt random walk with no reversion (D-3), with an ED observation that has no baseline (D-2) as the second cause. Both are testable on 2023-24 and 2024-25 without 2025-26.
- Widening intervals cannot fix this: it is a median bias.
- Do not change `model_config.json` on the strength of this report. Both experiments are diagnostic until pre-registered and run.
- Doc drift: `METHODS.md` values differ from `model_config.json` (sd_β, rel noise, sd_β,fwd, inflation). Fix in a separate commit.

## 7. References (status)

- Opened in this repo: `backtest/eakf.py`, `seir_fast.py`, `forecast.py`, `run_flusight.py`, `run_vintage.py`, `model_config.json`, `METHODS.md`, `BACKTEST_RESULTS.md`, `docs/research/HANDOFF.md`, `docs/research/PROBLEM_BRIEF.md`.
- Opened in hub `model-metadata/` (descriptions only, no scores or code): `cfa-flumech`, `CFA-PyRenew_*`, `CFA_Pyrenew-Pyrenew_*_Flu`, `cfarenewal-cfaepimlight`, `Cornell_JHU-SCARCHhierarSIR`, `Cornell_JHU-hierarchSIR`, `ISU_NiemiLab-SIR`, `MOBS-GLEAM_FLUH`, `NAU_PyBNF-OracleSIHRS`, `NAU-epymorph`, `NU-PGF_FLUH`, `LosAlamos_NAU-CModel_Flu`, `PSI-PROF`, `Xi_lab-GLEAM_AI_hybrid`.
- Calculated here: Erlang/SEIR tail decay table (§0.2), via a numeric root of the characteristic equation.
- Verified by web search (metadata only, full texts not opened): Whitaker & Hamill (2002, MWR 130(7), EnSRF); Whitaker & Hamill (2012, MWR 140(9), RTPS/RTPP); Cori et al. (2013, AJE 178(9):1505–1512); Shaman et al. (2010, PLoS Biology). Still [LIT, UNVERIFIED] from memory: Lloyd (2001, Erlang stages); Lowen et al. (2007, humidity); Farr; Richards (1959); Gompertz. The three search budget was spent on the first four above.
- Not checked: any team's scores or code; humidity/weather archives.

## 8. Top 5 recommendations (final, supersedes §5 and §6 where they differ)

1. **Test D-3 (forward mean reversion) as the top candidate.** D-0 arm b removes forward β noise only and leaves the median unchanged, so it neither supports nor rules out reversion. D-3 is untested. §6's "most likely" ranking still stands as a hypothesis, not as a result.
2. **Test the ED intercept (D-2) next.** It is the main surviving candidate: post-peak h3 bias of about −0.3 log units persists after both ablations.
3. **Test an infection-to-admission delay kernel (§3.3) and S depletion (§0.2 item 7)** in the same D-2 pass. Neither was ablated yet.
4. **Keep backfill (D-5) as a small-effect item.** Dropping the last week moves post-peak bias about 11% and worsens WIS; low priority for model 1.
5. **Do not change `model_config.json` or widen intervals.** Diagnosis is a median bias; repair the observation and structure first, then re-run D-0-style ablations on all dev locations under a fresh pre-registration. Fix `METHODS.md` drift separately.
