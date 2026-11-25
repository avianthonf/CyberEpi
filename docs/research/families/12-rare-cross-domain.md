# Family 12: Rare, old, forgotten and cross-domain ideas

Research agent 12 of 13. Written 2026-11-25 for the CyberEpi FluSight effort (see `../PROBLEM_BRIEF.md`).

## Executive summary (10 lines)

1. The best cheap idea from outside epidemiology is the **analog ensemble** from weather post-processing (Delle Monache 2013), applied to our own past forecasts. Its predictive distribution is the set of outcomes that followed past forecasts *in a similar state*, so the correction depends on phase. A global shift is not phase-aware, which is likely why ours failed.
2. **Lagged-average forecasting** (Hoffman & Kalnay 1983) gives free ensemble members: our own forecasts from last week, and last week's public FluSight-ensemble, re-aligned by one horizon step.
3. **Linear pool, not quantile averaging, for model 1 + model 2.** Quantile averaging is always sharper (Lichtendahl et al. 2013). Our intervals are too narrow and the two models fail in opposite phases, so a linear pool (mixture), widened when the models disagree, is the theoretically right combiner.
4. A luck-aware combiner comes straight from **Bühlmann credibility (1967)**, **James-Stein/Efron-Morris (1975)** and **Glicko (Glickman 1999)**: shrink skill differences toward equal weights in proportion to their noise.
5. **Event gating** is honest only if a feature is shown to *predict the loss differential*, which is exactly the **Giacomini-White (2006) conditional predictive ability** test. Ray & Reich (2018) already built feature-weighted flu ensembles, but that work was barely followed up.
6. **Farr's law (1840) / Brownlee**: model the change in the weekly growth rate (curvature of log incidence) as a pooled, phase-specific constant. This gives a cheap turning-point member that neither the SEIR nor the GBQR model has.
7. **Empirical dynamic modelling** (Sugihara & May 1990; S-maps 1994; multiview embedding, Ye & Sugihara 2016) on a composite attractor pooled over 53 locations handles short, noisy series. Perretti et al. (2013) showed it can beat a correctly specified mechanistic model.
8. **Taylor's power law** (ecology, 1961) gives a principled way to scale interval width across 53 very differently sized locations. **Adaptive conformal inference** (2021) keeps realised coverage on target online.
9. **Hierarchical model discrepancy** (Kennedy & O'Hagan 2001; Osthus et al. 2019, a winner of the CDC flu challenge) is the principled form of the post-peak bias correction that failed. It borrows the discrepancy across seasons rather than fitting it freely.
10. The ranked experiments are at the end. Four are cheap enough to run in shadow mode from next Wednesday. Track A candidates: E1 (linear-pool combination of models 1 and 2), E2 (analog-ensemble recalibration) and E4 (Taylor-law + ACI width wrapper).

## How the sources were checked (read this first)

- In this session the fetch tool could not reach most academic hosts. The hosts that failed to resolve included `pmc.ncbi.nlm.nih.gov`, `www.ncbi.nlm.nih.gov`, `arxiv.org` and `archive-ouverte.unige.ch`.
- Every citation below was therefore confirmed through web-search index records: titles, authors, venues, DOIs and abstracts, with the URL of the record shown. I did **not** read full texts.
- Statements that go beyond what an abstract or index record showed, and that come from my own background knowledge, are marked **[unverified]**.
- No citation is invented. Where sources disagreed (for example on a year), I say so.
- To verify: allow `pmc.ncbi.nlm.nih.gov`, `arxiv.org` and `projecteuclid.org` in the environment's network settings and re-read the starred items.

---

## Part 1. The ideas

Each idea follows the brief's format: **Source & theory**, **Translation**, **What it adds**, **Evidence**, **Cost & test**.

### 1. Farr's law and Brownlee's epidemic curves (1840, 1906), as a "curvature" member

**Source & theory.**
- William Farr observed that epidemics rise and fall at a rate that itself changes steadily: the "rate of increase keeps falling". He never wrote this as an equation. Brownlee and others later formalised it and fitted Pearson curves to epidemics.
  - W. J. Martin, "The epidemic curve of smallpox", J. Hygiene: https://www.cambridge.org/core/services/aop-cambridge-core/content/view/47124E8E5E8037A960BEDE29B2E86FD5/S0022172400034367a.pdf/the-epidemic-curve-of-smallpox.pdf
  - Brownlee 1906, "Statistical studies in immunity: the theory of an epidemic", Proc. R. Soc. Edinburgh: https://www.cambridge.org/core/journals/proceedings-of-the-royal-society-of-edinburgh/article/statistical-studies-in-immunity-the-theory-of-an-epidemic/A977DF53CCFCB01F7564311F573F99C2
- Martin reports that Brownlee also hypothesised that infectivity falls as an epidemic progresses. Martin also notes that the fitted curve types could not be used to classify epidemics.
- Santillana et al. (2018), "Relatedness of the Incidence Decay with Exponential Adjustment (IDEA) model, 'Farr's law' and compartmental difference equation SIR models" (Infect. Dis. Model. 3:1–12), show that Farr's law and IDEA are the same thing. Both approximate SIR when transmission changes through control or behaviour, not only through depletion of susceptibles. https://arxiv.org/abs/1603.01134v1 ; https://pmc.ncbi.nlm.nih.gov/articles/PMC6326218
- In modern notation, let y_t be weekly incidence and g_t = log y_t − log y_{t−1} the weekly growth rate. Farr's "ratio of ratios", (y_t/y_{t−1}) / (y_{t−1}/y_{t−2}), is constant, so Δg_t = d is constant. Log incidence is then quadratic in t, which gives a Gaussian-shaped curve. **[unverified]**: this exact algebraic reading is the standard modern one (Bregman & Langmuir's 1990 AIDS application used it); I did not open that paper.

**Translation.**
- Work in log1p of the rate per 100k, location ℓ.
- Estimate the current growth g_ℓ,t from the last two as-published weeks. A nowcast correction for the last week is possible but not needed.
- Forecast g_ℓ,t+k = g_ℓ,t + k·d̂_ℓ,φ, where φ is the epidemic phase (growth, near-peak, decline).
- Estimate d̂ by credibility pooling (idea 12):
  d̂_ℓ,φ = Z·d̄_ℓ,φ(current season, last 3–4 weeks) + (1−Z)·d̄_φ(all locations, past seasons).
- Brownlee's asymmetric curves enter by giving decline its own d_decline. Empirically, flu declines decelerate more slowly than rises accelerate, and post-peak d should be close to 0, i.e. a constant decay rate. **[unverified as a general flu fact; check on our data first.]**
- Get the predictive distribution by bootstrapping (g_t, d) residuals from past seasons in the same phase.

**What it adds.**
- Model 1 runs low in declines. A 3-week median that is about 40% low is consistent with the SEIR's accelerating, susceptible-depletion-driven fall. A Farr member with d_decline ≈ 0 says "keep falling at the current rate", which is the opposite bias.
- Model 2 runs low in rises. Farr's positive-g, slowly-negative-d extrapolation keeps the rise going. It is a natural third member whose errors are not those of either current model.

**Evidence.**
- Farr-style curve fitting is an old forecasting baseline, with mixed results.
- IDEA was used in real time for Ebola and MERS **[unverified: not opened]**.
- No FluSight evidence that I could find.

**Cost & test.**
- Trivial: microseconds per location.
- Test (Track B): pre-register the phase definition (idea 9), the window length (3 weeks) and the bootstrap.
- Score alone and as a member of the E1 pool, on 2023-24 and 2024-25 leave-one-season-out (LOSO).
- d̄_φ for the left-out season is computed only from the other season (plus 2022-23 final data, flagged as not as-of).

### 2. Kermack–McKendrick's full age-of-infection model, gamma stages, and sub-epidemics

**Source & theory.**
- Kermack & McKendrick (1927) wrote a renewal equation with infectiousness depending on age of infection. The ODE SIR model is only its exponential special case.
  - Breda, Diekmann, de Graaf, Pugliese & Vermiglio (2012), "On the formulation of epidemic models (an appraisal of Kermack and McKendrick)", J. Biol. Dyn. 6(S2):103–117: https://research-portal.uu.nl/en/publications/on-the-formulation-of-epidemic-models-an-appraisal-of-kermack-and/
- Wearing, Rohani & Keeling (2005), "Appropriate models for the management of infectious diseases", PLoS Med 2(7):e174, show the consequences of exponential latent and infectious periods. Such periods change epidemic shape and underestimate R0. The gamma ("method of stages", linear chain trick) version uses n sub-compartments at rate nγ. https://rohanilab.ecology.uga.edu/wp-content/uploads/2013/11/Wearing_rohani_keeling2005.pdf
- Chowell, Tariq & Hyman (2019, BMC Medicine) model a wave as a sum of overlapping sub-epidemics. A state's flu season is plausibly a sum of asynchronous sub-epidemics across strains (A/H1, A/H3, B), age groups and sub-regions. Such sums have long, slow tails. https://bmcmedicine.biomedcentral.com/track/pdf/10.1186/s12916-019-1406-6

**Translation.** Model 1 is a single homogeneous SEIR per state with exponential periods. Two minimal, pre-registered variants:
- (a) **Erlang stages**: E→E2, I→I2 (n=2), same mean durations.
- (b) **Two-pool SEIR**: two weakly coupled populations with independent log β, one seeded later. This mimics an A wave followed by a B wave, or a metro area followed by rural areas. It is a lighter cousin of the Baroyan–Rvachev network (idea 4).

**What it adds.** It is the only structural (not post-hoc) fix for model 1's too-steep post-peak decline. A sum of two lagged sub-epidemics decays more slowly than one.

**Evidence.**
- The theory is solid.
- No FluSight-specific test was found.
- The Chowell group reports that sub-epidemic ensembles beat simple growth models on interval score (see their 2019 paper and the 2022 medRxiv ensemble preprint: https://medrxiv.org/content/10.1101/2022.06.19.22276608v1.full).

**Cost & test.**
- (a) roughly doubles the E and I states and is cheap. (b) doubles the state vector, about 2× runtime, which is fine within 30 minutes.
- Track B. Changing model 1's frozen settings requires a fresh pre-registration.
- Primary metric: relWIS in decline-phase rows only. This metric is the one the idea targets and must be written down before running.

### 3. Bartlett's critical community size and Taylor's power law, for interval width across locations

**Source & theory.**
- Bartlett (1957), "Measles periodicity and community size", JRSS A 120:48. Small populations behave more stochastically, with fade-outs and irregular timing. https://pmc.ncbi.nlm.nih.gov/articles/PMC2842776 (citing review) ; catalogue record: https://catalogosiidca.csuca.org/Record/UCR.000471281/Similar
- Taylor (1961), "Aggregation, variance and the mean", Nature 189:732–735. Across ecological samples, variance = a·mean^b, linear on log–log axes. https://repository.rothamsted.ac.uk/item/8v52z/aggregation-variance-and-the-mean ; review: https://arxiv.org/pdf/1505.02033

**Translation.**
- On the count scale, the forecast-error variance at horizon h should follow Var(y − ŷ | ŷ) ≈ a_h · ŷ^{b_h}.
  - b=1 is Poisson-like (small states).
  - b=2 is constant relative error (large states).
  - In between suggests a mixture.
- Fit (a_h, b_h) by regressing log squared errors (or log of empirical interval half-widths) on log ŷ, pooled across locations and dev seasons, out of sample.
- Use it as a width wrapper. Rescale each location's centred quantiles so the implied spread matches a_h ŷ^{b_h/2}, but never narrower than the model's own spread. The brief says intervals are too narrow.

**What it adds.**
- A two-parameter-per-horizon, population-aware width rule. It replaces ad-hoc per-location inflation, which overfits with 4 seasons.
- Raw WIS is dominated by large locations, while coverage is counted per row. A Taylor-law rule fixes both small-state undercoverage and large-state overwidth in one shot.

**Evidence.**
- Taylor's law holds in hundreds of species.
- That it holds for epidemic counts is plausible but **[unverified]** for NHSN admissions. It must be checked on the dev residuals before use. The check is itself a deliverable: plot log variance against log mean.

**Cost & test.**
- Trivial cost.
- Track A candidate, because it is a calibration wrapper with only 2 parameters per horizon.
- Test: fit on one dev season, apply to the other. Pre-registered acceptance: WIS no worse than 1.00× raw, and 90% coverage closer to nominal in both folds.

### 4. Baroyan–Rvachev (USSR, 1960s–80s) and Cliff & Haggett: the forgotten operational network forecaster

**Source & theory.**
- Baroyan, Rvachev et al. (1971), "Computer modelling of influenza epidemics for the whole country (USSR)", Adv. Appl. Prob. 3(2):224–226. A country-level model using daily registered morbidity from individual cities. https://opact.sdu.edu.tr/vufind/SummonRecord/FETCH-LOGICAL-c1337-eadad91cd6c76d53c0fea6bc4398926919ef6b273ab589d0668cfb8ed0cb94513
- Rvachev (1971), Doklady AN SSSR 198(1):68–70, "An experiment on computer prognostication of influenza epidemic": https://mathnet.ru/eng/dan36143
- Ivannikov & Ogarkov (2012), J. Infectology 4(3):101–106. A retrospective of operational forecasts from 1971 to 1985 by the Institute of Influenza. It reports daily forecasts for 100 cities up to 3 months ahead, including peak timing. https://core.ac.uk/download/267960898.pdf
- The structure was a discrete SEIR-type local model plus a linear inter-city migration model: https://www.aimspress.com/article/10.3934/mbe.2018009
- Rvachev & Longini (1985, Math. Biosci. 75:3–22) globalised it with airline links: https://portal.mardi4nfdi.de/wiki/Publication:1060157
- Cliff, Haggett & Ord (1986), *Spatial aspects of influenza epidemics* (Pion), is the geographers' parallel tradition (cited at https://link.springer.com/article/10.1007/s10109-006-0027-8).
- Viboud et al. (2006, Science 312:447), "Synchrony, waves, and spatial hierarchies in the spread of influenza". In the US, spread follows commuting flows rather than distance, and synchrony is higher among populous states. https://ento.psu.edu/files/viboudetal2006.pdf

**Translation.** The spatial-family agent will cover metapopulation models. The rare lesson here is operational.
- The Soviet system was a **fixed-structure model re-anchored on the latest counts each day**. Its skill reportedly came from *timing*: a city's wave starts after its network neighbours' waves start.
- For us, the cheap version is a **"wave-arrival lead" feature**: the commuting-weighted mean of other states' recent growth rates, Σ_j w_ℓj g_j,t with gravity weights w_ℓj ∝ P_ℓ P_j / d_ℓj², normalised.
- Add it to model 2's features, or use it as a gate input (C4).

**What it adds.** It gives model 2 a leading signal during rises, where model 2 runs low.

**Evidence.**
- The USSR claims are self-reported (2012 retrospective) and not independently verified.
- Viboud 2006 supports a hierarchy in US flu spread.

**Cost & test.**
- Cheap.
- Track B: add one feature to a shadow copy of GBQR. Compare against the frozen GBQR on LOSO dev, with the feature definition fixed in advance.

### 5. Analogues: Lorenz → van den Dool → Viboud (flu) → the weather "analog ensemble"

**Source & theory.**
- Lorenz (1969), "Atmospheric predictability as revealed by naturally occurring analogues", J. Atmos. Sci. 26:636–646. Over 400,000 state pairs, he found no truly good analogues. https://research.amanote.com/publication/R5_x3XMBKQvf0BhiaAio/atmospheric-predictability-as-revealed-by-naturally-occurring-analogues
- van den Dool (1994), "Searching for analogues, how long must we wait?", Tellus A 46:314–324. The record needed for good analogues grows explosively with dimension, which led to the practice of shrinking the feature space before searching. https://cpc.ncep.noaa.gov/products/predictions/experimental/bulletin/Dec97/a63.html (secondary)
- Viboud, Boëlle, Carrat, Valleron & Flahault (2003), "Prediction of the spread of influenza epidemics by the method of analogues", Am. J. Epidemiol. 158:996–1006. On French ILI (21 regions, 938 weeks), analogues beat autoregressive models over 1–10 weeks ahead. https://scilit.com/publications/80539d81a37c7e3e42ec5fbf0ad99b43
- Delle Monache et al. (2013), "Probabilistic weather prediction with an analog ensemble", MWR 141:3498–3516. Find past *forecasts* from the same model that resemble today's forecast; the *observations that verified them* form the ensemble. https://opensky.library.ucar.edu/islandora/object/articles%3A12922
- Delle Monache et al. (2011): analog and analog-Kalman post-processing removes bias and reduces random error. https://ams.confex.com/ams/91Annual/webprogram/Paper181496.html

**Translation: AnEn on our own models.** For model m at a new (ℓ, R, h):
1. Build a low-dimensional predictor vector, keeping van den Dool's dimension lesson in mind:
   x = (log1p rate_obs, g_1wk, g_2wk, Δlog ED, model m's median growth over h, model m's log spread).
   Standardise each component across the training pool.
2. Search the archive of model m's *as-of backtest forecasts* at the same horizon h, in other seasons only. Use all locations and weeks within ±6 weeks of season week. Find the K nearest neighbours by weighted Euclidean distance (weights fixed a priori, e.g. equal).
3. For each neighbour i, take its realised log ratio r_i = log((y_i+1)/(ŷ_i^{med}+1)).
4. The predictive distribution is ŷ^{med}·exp(r), where r is drawn from {r_i}, optionally kernel-smoothed. Read quantiles off directly.
5. Blend with model m's own quantiles via a linear pool, weight λ fixed a priori (e.g. 0.5), to guard against small K.

**What it adds.** This is the key point against our failed global shift and widening.
- AnEn conditions the correction on state. "Declining, model says −40% over 3 weeks, ED falling slowly" draws on past cases like that, where model 1 was too low.
- Growth states draw on growth cases, where model 1 may be fine.
- It widens intervals exactly where the model was historically wrong, and nowhere else.

**Evidence.**
- Strong in weather post-processing.
- Analogues beat AR for flu (Viboud 2003).
- Not tested on FluSight to my knowledge.

**Cost & test.**
- KNN over about 10–20k archived rows takes seconds.
- **Track A candidate** if it passes.
- Pre-register: K=50, feature list, distance weights, λ=0.5, and that the neighbour pool excludes the scored season.
- LOSO on 2023-24 and 2024-25 for model 1 (model 2's archive is shorter).
- Acceptance: relWIS(AnEn-wrapped / raw) < 0.97 in **both** folds, and 90% coverage within 85–95%.
- Because the earlier shift failed out of sample, also pre-register a phase-split report.

### 6. Empirical dynamic modelling: simplex projection, S-maps, composite attractors, multiview embedding

**Source & theory.**
- Sugihara & May (1990), "Nonlinear forecasting as a way of distinguishing chaos from measurement error in time series", Nature 344:734–741. Simplex projection uses nearest neighbours in a time-delay embedding (Takens) and was applied to measles and chickenpox. https://www.nature.com/articles/344734a0.pdf
- Sugihara (1994), "Nonlinear forecasting for the classification of natural time series", Phil. Trans. R. Soc. A 348:477–495. It introduces **S-maps**, locally weighted linear maps whose locality parameter θ>0 tests for state-dependence. It also introduces **composite attractors** for many *short* series. https://scilit.com/publications/1d1bede45ec043dfd0d1bfbcaef05470
- Ye & Sugihara (2016), "Information leverage in interconnected ecosystems: overcoming the curse of dimensionality", Science 353:922–925. Multiview embedding combines many alternative embeddings and is "particularly effective for short and noisy time series". https://aitopics.org/doc/journals:C3AE7273
- Perretti, Munch & Sugihara (2013), PNAS 110:5253–5257. Model-free state-space reconstruction out-forecast the *correctly specified* mechanistic model. MCMC fits of mechanistic models drifted from the true parameters. Hartig & Dormann disputed this and the authors replied ("the true model myth"). https://ar5iv.arxiv.org/html/1305.3544 (critique) ; reply cited at https://pmc.ncbi.nlm.nih.gov/articles/PMC3801006

**Translation.**
- Library: all (ℓ, season) trajectories of z = log1p(rate), normalised per location by its season peak to date, which is an as-of quantity. This forms a composite attractor.
- Embedding: (z_t, z_{t−1}, z_{t−2}, log ED_t, log ED_{t−1}), with E chosen by leave-one-season-out simplex skill.
- S-map forecast of z_{t+k}: a locally weighted regression with weights exp(−θ‖x−x_i‖/d̄).
  - θ is chosen once on dev.
  - θ>0 means state-dependent dynamics. That is the honest statistical version of model 2's learned "at rates this high, epidemics peak soon".
- Multiview: build all embeddings from {rate lags, ED lags, national rate lag}, keep the top √(#views) by in-sample skill, and average.
- Uncertainty: from neighbour spread, then recalibrate as in idea 5.

**What it adds.**
- A third non-parametric view of turning points.
- Weak at extrapolating to unprecedented peaks; the 2024-25 national peak of 55.5k was far above earlier ones. Normalising by season-to-date peak only partly fixes this.

**Evidence.**
- Strong in ecology.
- Flu: Deyle et al. (2016, PNAS 113:13081) used EDM/CCM on global flu to argue that absolute humidity drives outbreaks, but the causality claims are contested. https://escholarship.org/uc/item/0247p6d0

**Cost & test.**
- Seconds.
- Track B member. Pre-register E, τ=1, θ grid and library rules.
- Score alone and in the E1 pool.

### 7. Convergent cross mapping (CCM) as a driver screen, used with care

Deyle et al. (2016) above, and the Baskerville & Cobey critique noted in the same search record, show that CCM inference is fragile under seasonal synchrony.
- **Translation:** use CCM only as a *screening* tool to decide which event streams (humidity, school terms) are worth a gate weight. Never use it as proof of causation.
- **Cost:** low. **Track B, low priority.**

### 8. Lagged-average forecasting: free ensemble members from the past

**Source & theory.** Hoffman & Kalnay (1983), "Lagged average forecasting, an alternative to Monte Carlo forecasting", Tellus A 35:100–118.
- Ensemble members are operational forecasts started at earlier times, averaged at a common verification time.
- Both lagged and Monte Carlo ensembles beat a single forecast, largely by pulling toward climatology.
- Their spread tracked lost predictability.
- https://dx.doi.org/10.3402/tellusa.v35i2.11425 ; https://ntrs.nasa.gov/citations/19840014007

**Translation.**
- Our forecast at reference date R for target date T = R + 7h has siblings: the same model run at R−7 (horizon h+1) and at R−14 (horizon h+2).
- Also the **public FluSight-ensemble from R−7**, which the hub holds in `model-output/FluSight-ensemble/` (92 files). Its h+1 quantiles target our h-week date.
- Lagged members are stale but independent of this week's revisions. They hedge against a bad latest data point, such as a first report at 78% or 142% of the final value.

**What it adds.**
- Free members whose errors are partly decorrelated from the current run.
- The lagged CDC ensemble brings in 30+ teams' information legally. We are not copying the current week's ensemble, which is not available at our deadline.

**Evidence.**
- Standard in numerical weather prediction, where time-lagged ensembles are used operationally.
- In FluSight it is untested to my knowledge.

**Cost & test.**
- Zero compute.
- Before use, confirm per file that the ensemble CSV for R−7 was merged into the hub before our deadline at R. Use hub commit timestamps, offline, by the experimenter.
- Track B first. Track A only if the pool wins in shadow mode.

### 9. Regime models for epidemic phase: Hamilton (1989), Le Strat & Carrat (1999)

**Source & theory.**
- Hamilton (1989), Econometrica 57:357–384: autoregression parameters switch according to a hidden Markov chain, inferred by filtering. https://econpapers.repec.org/RePEc:ecm:emetrp:v:57:y:1989:i:2:p:357-84
- Le Strat & Carrat (1999), Stat. Med. 18:3463–3478: hidden Markov models that segment influenza indicators into epidemic and non-epidemic phases. https://search.r-project.org/CRAN/refmans/surveillance/html/algo.hmm.html

**Translation.** A 4-state HMM on (g_t, Δlog ED_t) per location, with emissions shared across locations:
- pre-season (g≈0, low level)
- growth (g>0)
- peak (|g| small, high level)
- decline (g<0)

The *filtered* posterior π_t(φ) from as-of data is the phase signal used by ideas 1, 5 and the combinations. Filtered means smoothing is not used, because that would be look-ahead.

**What it adds.** A principled, probabilistic phase label instead of hand thresholds. "Near peak" becomes a probability that can gate weights smoothly.

**Cost & test.**
- Seconds; fit by EM on dev seasons.
- Infrastructure for Track B.
- Test: phase-classification lag versus the final-data peak week, reported but not optimised.

### 10. Model Output Statistics and verification culture (Glahn & Lowry 1972; Murphy 1993; Dawid 1984)

**Source & theory.**
- MOS regresses observations on model outputs to post-process numerical forecasts. It was introduced operationally in 1972 and is still in use. https://www.weather.gov/media/mdl/AMSGlahnSymp2015_Dallavalle_paper.pdf ; https://vlab.noaa.gov/web/mdl/mos
- Murphy (1993), "What is a good forecast?", Weather & Forecasting 8:281–293. Distinguishes consistency, quality and value, and lists nine attributes of quality. https://stafforini.com/works/murphy-1993-what-good-forecast/ ; https://wmo.int/node/37326
- Dawid (1984), "Statistical theory: the prequential approach", JRSS A 147:278–292. Judge a method only by its sequential forecasts. https://www.cs.ubc.ca/~murphyk/MLRG/dawid84Prequential.pdf

**Translation.**
- (a) MOS is what our failed shift tried to be. The meteorological lesson is that MOS predictors include **the state** (season, lead time, regime), not just a constant. That is ideas 5 and 18.
- (b) Adopt Murphy's *distributions-oriented* verification. Report WIS decomposed by phase × horizon × location-size tercile, plus PIT histograms per phase. Report this *before* proposing any fix.
- (c) The prequential principle is already our shadow-mode rule. Cite it in the CV record as the methodological basis.

**Cost:** low. **Track A hygiene.**

### 11. Econometrics: combination theory that matters directly here

**Bates & Granger (1969), "The combination of forecasts".**
- Optimal weights estimated from samples often lose to the simple average.
- https://portal.mardi4nfdi.de/wiki/Publication:135294 ; review https://people.duke.edu/~clemen/bio/Published%20Papers/13.CombiningReview-Clemen-IJOF-89.pdf

**Claeskens, Magnus, Vasnev & Wang (2016), "The forecast combination puzzle: a simple theoretical explanation", IJF 32:754–762.**
- Estimated weights are random, which biases the combination and inflates its variance.
- This is the formal reason a combiner must be "luck-aware".
- https://econpapers.repec.org/RePEc:eee:intfor:v:32:y:2016:i:3:p:754-762

**Geweke & Amisano (2011), "Optimal prediction pools", J. Econometrics 164:130–141.**
- Under log score, optimal linear pools keep several models with positive weight, including models that are clearly inferior alone.
- https://econpapers.repec.org/RePEc:eee:econom:v:164:y:2011:i:1:p:130-141
- Implication: do not drop model 1 because model 2 scores better. Their errors are in opposite phases.

**Lichtendahl, Grushka-Cockayne & Winkler (2013), "Is it better to average probabilities or quantiles?", Mgmt Sci 59:1594–1611.**
- Quantile averaging (Vincentization) has the same mean but is always **sharper** than probability averaging (the linear pool).
- https://econpapers.repec.org/RePEc:inm:ormnsc:v:59:y:2013:i:7:p:1594-1611
- Vincentization is named after S. B. Vincent (1912, rat learning curves) and was characterised by Genest (1992, Ann. Stat. 20:1137). https://projecteuclid.org/euclid.aos/1176348676
- Gneiting & Ranjan (2013, EJS 7:1747–1782) show the linear pool of calibrated components is itself miscalibrated (over-dispersed). They propose spread-adjusted and beta-transformed pools. https://projecteuclid.org/journals/electronic-journal-of-statistics/volume-7/issue-none/Combining-predictive-distributions/10.1214/13-EJS823.full
- **The direct implication for us:**
  - The FluSight-ensemble is a quantile median or mean, i.e. Vincentization-like, and therefore sharp.
  - Our individual models are *under*-dispersed (90% interval covers about 74%), and models 1 and 2 disagree in sign by phase.
  - So the right combiner for model 1 + model 2 is the **linear pool**, which mixes and widens exactly when they disagree. Then apply an optional beta transform, fitted on dev, to tune the dispersion.
  - Quantile averaging would only reproduce the narrowness.

**Litterman (1986), Minnesota prior, JBES 4:25–38.**
- Shrink VAR coefficients toward a random walk. A small Bayesian VAR beat commercial forecasts on GNP.
- https://ideas.repec.org:443/a/bes/jnlbes/v4y1986i1p25-38.html
- Translation: any learned combiner or gate weight gets a prior centred on "equal weights / persistence", with tightness set by dev cross-validation.

**Giacomini & White (2006), "Tests of conditional predictive ability", Econometrica 74:1545–1578.**
- Tests whether information available today predicts which forecast will be more accurate, and gives a two-step rule for picking the forecast conditional on current information.
- https://econpapers.repec.org/RePEc:ecm:emetrp:v:74:y:2006:i:6:p:1545-1578
- **This is the honest gatekeeper for "event-gated combiners".**
- Regress the loss differential Δ_t = WIS₁ − WIS₂ on gate features x_{t−h}. If β is not significantly non-zero on dev (HAC errors, block by week), the gate is noise and must not be used.

**MIDAS (Ghysels, Santa-Clara & Valkanov 2004).**
- Regressions mixing sampling frequencies with parsimonious lag polynomials. https://escholarship.org/content/qt9mf223rs/qt9mf223rs.pdf
- Relevance is limited: hub data are weekly. If an honest daily archive of NSSP or wastewater is ever built prospectively, MIDAS beta-lag weighting is the parsimonious way to use it.
- Track B, prospective only.

### 12. Actuarial science: credibility theory and the chain ladder

**Source & theory.**
- Bühlmann (1967), "Experience rating and credibility", ASTIN Bulletin 4(3):199–207, links credibility to Bayesian estimation. https://www.casact.org/abstract/experience-rating-and-credibility ; https://econpapers.repec.org/RePEc:cup:astinb:v:4:y:1967:i:03:p:199-207_00
- The credibility premium is P = Z·X̄_own + (1−Z)·μ_collective, with Z = n/(n + k) and k = E[σ²(Θ)] / Var[μ(Θ)]: the expected within-risk process variance over the variance of the hypothetical means between risks.
- **[unverified: this is the standard Bühlmann formula from textbooks; I saw only the abstract.]**
- Efron & Morris (1975), "Data analysis using Stein's estimator and its generalizations", JASA 70:311–319. Batting averages after 45 at-bats are shrunk toward the grand mean and predict the rest of the season better. This is the canonical *skill vs luck* demonstration. https://www.medicine.mcgill.ca/epidemiology/hanley/bios602/MultilevelData/EfronMorrisJASA1975.pdf
- Mack (1993), "Distribution-free calculation of the standard error of chain ladder reserve estimates", ASTIN Bull. 23:213–225, applies chain ladder to run-off triangles with honest standard errors. https://www.casact.org/library/astin/vol23no2/213.pdf
- The epidemiological twin is Höhle & an der Heiden (2014), Biometrics 70:993–1002, on Bayesian nowcasting of reporting triangles. https://staff.math.su.se/hoehle/pubs/hoehle_anderheiden2014-preprint.pdf

**Translation.**
- (a) **Credibility combiner weights.** See C1 below. A model's estimated advantage in a cell (phase × horizon) is credited in proportion to Z, where Z falls when weekly loss differences are noisy or few.
- (b) **Credibility for location-level corrections.** Any per-location bias or width factor equals Z_ℓ × (own estimate) + (1−Z_ℓ) × (pooled estimate). This replaces both "global only", which underfits, and "per location", which overfits.
- (c) **Chain-ladder revision factors** for h=−1 and h=0. The nowcasting agent will cover this. Mack's distribution-free standard error is the old, cheap way to put honest width on the revision multiplier: the as-published first report is about 96% of final on average, with a range of 78–142%.

**Cost & test.** Trivial. (a) and (b) are Track A-capable because they *reduce* the effective number of free parameters.

### 13. Sports ratings: Elo, Glicko, Dixon–Coles, i.e. skill vs luck over time

**Source & theory.**
- Glickman (1999), "Parameter estimation in large dynamic paired comparison experiments", JRSS C 48:377–394. Glicko adds a rating deviation (RD) to Elo. RD shrinks with evidence and grows with inactivity, so stale ratings are trusted less. https://econpapers.repec.org/RePEc:bla:jorssc:v:48:y:1999:i:3:p:377-394 ; https://search.r-project.org/CRAN/refmans/PlayerRatings/html/glicko.html
- Dixon & Coles (1997), JRSS C 46:265–280: time-down-weighted likelihood for team strength, with profitable betting. https://eprints.lancs.ac.uk/id/eprint/19492

**Translation.** Each (week, location, horizon) is a "match" between models. Outcome s = 1 if model A's WIS is lower, 0.5 for a tie within 2%.
- Glicko update per cell c = (phase, horizon) gives a rating r_m,c and a deviation RD_m,c.
- At each season start, RD² ← min(RD² + c², RD_max²). This is Glicko's forgetting and matches the brief's fact that "season-to-season differences exceed score gaps".
- The combination weight is

  w_m,c ∝ exp(κ · (r_m,c − r̄_c) / √(1 + 3q²RD_m,c²/π²)),

  where the denominator is Glicko's g(RD) attenuation. Uncertain ratings get pulled toward equal weight.

**What it adds.** An interpretable, CV-friendly "luck-aware" combiner whose state (ratings ± RD) can be published weekly.

**Evidence.**
- Glicko is used in chess and many sports.
- No forecasting-combination evidence was found. This is a novel use.

**Cost & test.** Trivial. Track B (C1 nests it).

### 14. Online learning for switching regimes: fixed share; adaptive conformal

- Herbster & Warmuth (1998), "Tracking the best expert" (Machine Learning). The fixed-share update gives each expert a fraction α of the weight, so the learner can follow the best expert when it switches. α=0 gives Bayesian model averaging. https://arxiv.org/pdf/1008.4532 (secondary). **[unverified: venue confirmed only from my memory, as the search agent noted.]**
- Gibbs & Candès (2021), "Adaptive conformal inference under distribution shift", NeurIPS 34. Update the target miscoverage online, α_{t+1} = α_t + γ(α − err_t). Long-run coverage is guaranteed whatever the data process. https://proceedings.neurips.cc/paper/2021/hash/0d441de75945e5acbc865406fc9a2559-Abstract.html

**Translation.**
- Fixed share across {model 1, model 2, Farr, EDM, lagged ensemble} with α fixed a priori (e.g. 0.05/week). The models genuinely switch "best" status at the peak.
- ACI per horizon on the final pooled interval, targeting 90% and 50% coverage. With weekly feedback lagged by h+1 weeks, update only on resolved targets.

**Cost:** trivial. **ACI is a Track A candidate** (calibration agent may duplicate; see E4).

### 15. Judgement aggregation: superforecasting, extremizing, prediction markets

- Satopää et al. (2014), IJF 30:344–356: logit aggregation with a single extremizing parameter. https://econpapers.repec.org/RePEc:eee:intfor:v:30:y:2014:i:2:p:344-356
- Baron et al. (2014), Decision Analysis 11:133–145: averaging compresses probabilities toward 0.5, so aggregates should be made more extreme. https://econpapers.repec.org/RePEc:inm:ordeca:v:11:y:2014:i:2:p:133-145
- Farrow et al. (2017), PLoS Comput Biol 13:e1005248, "Epicast": aggregated human forecasts often beat statistical systems at short horizons. https://ideas.repec.org/a/plo/pcbi00/1005248.html
- Polgreen, Nelson & Neumann (2007), Clin. Infect. Dis. 44:272–279: the Iowa flu activity prediction market was right 71% of the time in the target week and 50% one week ahead. https://iemweb.biz.uiowa.edu/?p=375

**Translation.**
- (a) **Categorical rate-change target.** Our pmf is likely derived from the quantile forecast. Apply a one-parameter extremizer p_k ∝ p̄_k^a and fit a on dev by log score.
  - a>1 extremizes; a<1 anti-extremizes.
  - Given known under-dispersion, expect a<1 for our models and a>1 for the linear pool.
  - Same for the peak-week pmf.
- (b) Lagged human-judgement forecasts (Metaculus-cp, FluSight-HJudge_ensemble from R−7, both in the hub) as Hoffman–Kalnay members (idea 8).

**Cost:** trivial. (a) is Track A-capable for the unclaimed categorical targets.

### 16. Information theory: permutation entropy as a predictability gauge

**Source & theory.** Scarpino & Petri (2019), "On the predictability of infectious disease outbreaks", Nat. Commun. 10:898.
- Permutation entropy is a model-free measure of predictability, applied in rolling windows.
- It reveals an "entropy barrier" that is usually beyond the time scale of a single outbreak.
- https://www.nature.com/articles/s41467-019-08616-0

**Translation.**
- Rolling permutation entropy H_ℓ,t, order 3, over the last 8–10 weeks of as-of growth rates. Pool with national data to stabilise it.
- Use it as (i) a gate feature (C4) and (ii) a width covariate: high H → widen and shrink toward baseline.

**Evidence.** Untested for short-horizon admissions. The window is short, so H is noisy. It must pass the Giacomini–White screen.

**Cost:** trivial. **Track B.**

### 17. Early-warning signals of critical transitions, for turning points

**Source & theory.** O'Regan & Drake (2013), Theor. Ecol. 6:333–357.
- Approaching R_eff = 1 slows the dynamics, which shows up as rising autocorrelation and variance.
- Leading indicators of *elimination* were highly predictive; emergence was harder.
- https://daphnia.ecology.uga.edu/drakelab/?p=668

**Translation.**
- A seasonal peak is R_eff crossing 1 from above, the "elimination side" crossing, which is the easier case in their theory.
- Compute rolling lag-1 autocorrelation and variance of detrended weekly growth rates. Use them as features for the peak probability in the HMM (idea 9), or as gate features.

**What it adds.** A theoretical basis for turning-point anticipation that does not rely on "rates this high peak soon".

**Evidence.**
- Theory and simulations; measles re-emergence and elimination.
- For seasonal flu peaks at weekly resolution: none. Speculative.

**Cost:** trivial. **Track B, low prior.**

### 18. Model discrepancy: Kennedy–O'Hagan (2001) → Los Alamos "Dante" (Osthus et al. 2019)

**Source & theory.**
- Kennedy & O'Hagan (2001), JRSS B 63:425–464: y = m(θ, x) + δ(x) + ε, where the discrepancy δ is a Gaussian process separate from noise. https://econpapers.repec.org/RePEc:bla:jorssb:v:63:y:2001:i:3:p:425-464
- Osthus, Gattiker, Priedhorsky & Del Valle (2019), "Dynamic Bayesian influenza forecasting in the United States with hierarchical discrepancy", Bayesian Analysis 14:261–312.
  - SIR plus a discrepancy term modelled *hierarchically across seasons*, so a partial season borrows discrepancy shape from earlier ones.
  - It outperformed all entries in the 2015-16 and 2016-17 CDC challenges.
  - https://projecteuclid.org/euclid.ba/1533866670

**Translation.**
- Model 1's post-peak low bias is a discrepancy δ(φ, τ_since_peak, h) of the SEIR relative to reality.
- Instead of a free shift, which failed under LOSO, put a hierarchical prior on it:

  δ_s,ℓ(τ) = δ̄(τ) + u_s(τ) + v_ℓ(τ), with u_s ~ GP(0, σ_s²K), v_ℓ ~ GP(0, σ_ℓ²K),

  where s is the season, and τ is the filtered weeks-since-peak or the phase posterior.
- The forecast adds E[δ | data so far this season] and its *variance*. The variance term automatically widens intervals in phases where discrepancy is uncertain.

**What it adds.** The principled form of the correction that failed, with between-season variance (σ_s²) built in. With only 2–3 seasons, σ_s² will be large, so the correction will be modest and the widening honest. This is the credibility logic again.

**Cost & test.**
- A small GP or AR(1)-in-τ fit: seconds.
- Track B, but a strong Track A candidate *if* LOSO shows gains in both folds.
- This idea and idea 5 (AnEn) are rivals. Pre-register both and pick by LOSO.

### 19. Under-cited one-offs from the 2013–2019 CDC challenges

- **Ray & Reich (2018), feature-weighted density ensembles**, PLoS Comput Biol 14:e1005910.
  - Weights depend on region, target, week of season, component uncertainty and recent incidence.
  - The authors themselves note the feature sets were limited.
  - https://ideas.repec.org/a/plo/pcbi00/1005910.html ; https://arxiv.org/abs/1703.10936
  - This is the direct ancestor of "event-gated combiners" and was not developed much further. **[unverified: "not followed up" is my reading of the literature, not a systematic citation count.]**
- **Yamana, Kandula & Shaman (2017)**, PLoS Comput Biol 13:e1005801. Superensemble weights *stratified* by forecast characteristics or geography beat unstratified weights. https://econpapers.repec.org/RePEc:plo:pcbi00:1005801
- **Brooks et al. (2018), "delta density"**, PLoS Comput Biol 14:e1006134.
  - Chains one-week-ahead change distributions; CDC's most accurate 2015/16 entry.
  - Note: its iterated change distributions are close in spirit to model 2's target, the change in log rate. A conditional-density chaining of model 2's h=1 output into h=2–3 is a cheap variant.
  - https://www.stat.cmu.edu/~ryantibs/papers/deltadens.pdf
- **Reich et al. (2019)**, PNAS 116:3146–3154: reporting delays were strongly and negatively associated with accuracy in some regions. This supports investing in revision nowcasting at h=−1/0. https://stacks.cdc.gov/view/cdc/77374

### 20. Considered and rejected or deprioritised (sanity filter)

- **Hope-Simpson's latency/"seasonal stimulus" hypothesis** (J. Hyg. 1981, 86:35–47; https://pubmed.ncbi.nlm.nih.gov/7462597/). The mechanism (reactivated latent carriers) is not supported by modern virology **[my assessment]**. Keep only the empirical point that seasonality is strongly latitude-structured, which is already used through week-of-season features. No experiment.
- **Reinforcement learning / contextual bandits** for model selection. With about 60 season-weeks of dev data, a learned policy is unidentifiable. Fixed share (idea 14) is the low-variance version of the same goal.
- **GARCH-style error-volatility widening** (Engle 1982, ARCH) **[unverified: not searched]**. Plausible (forecast errors cluster near peaks), but ACI plus the AnEn and discrepancy variance already cover it.
- **Critical community size as a model component.** Fade-out matters for measles, not for US-state flu admissions in season. Only the variance-scaling lesson is kept (idea 3).

---

## Part 2. Novel combinations (precise algorithms)

Notation:
- Location ℓ, reference date R, horizon h ∈ {0, …, 3}, target y.
- Component models m ∈ M = {EAKF, GBQR, Farr, EDM, lag-Ens, lag-EAKF}.
- Each component gives a CDF F_m(·) for log1p(rate), built from its 23 quantiles by monotone interpolation with exponential tails.
- Phase posterior π_t(φ) from the filtered HMM (idea 9), φ ∈ {pre, grow, peak, decl}.
- All quantities are computed from data as published by R. Loss for model m at a *resolved* row i is L_m,i = WIS on the log1p scale, so that large states do not dominate the weights. Raw-count WIS is still reported.

### C1. Credibility–Glicko luck-aware linear pool (CGL-pool)

**Step 1: loss differentials.** For each resolved row i, cell c(i) = (phase at forecast time, h), and reference model 0 (equal-weight pool):

  d_m,i = L_m,i − L_0,i.

**Step 2: Bühlmann credibility of each model's skill in each cell.**
- Pool the current season's resolved rows with past seasons. Past seasons are down-weighted by a Dixon–Coles factor ρ^{seasons ago}, with ρ = 0.5 fixed.
- Compute per cell:

  d̄_m,c = weighted mean of d_m,i in cell c
  s²_m,c = within-cell variance, inflated for autocorrelation: n_eff = n_c (1−ρ₁)/(1+ρ₁), with ρ₁ the lag-1 autocorrelation of weekly d
  τ²_m = between-cell variance of the d̄_m,c, minus the average of s²_m,c/n_eff, floored at 0
  Z_m,c = n_eff / (n_eff + s²_m,c / τ²_m)
  μ_m,c = Z_m,c · d̄_m,c + (1 − Z_m,c) · d̄_m,·      (the global mean for model m, itself credibility-shrunk toward 0 the same way)

**Step 3: Glicko-style uncertainty and season-start forgetting.**
- Posterior variance of μ: V_m,c = (1 − Z_m,c) τ²_m.
- At each season start add c₀² (fixed a priori) to every V. Old evidence is trusted less, and the weights start near equal each season.

**Step 4: weights with a soft phase gate.** At forecast time:

  w_m(R, ℓ, h) ∝ Σ_φ π_R,ℓ(φ) · exp( −η · μ_m,(φ,h) / √(1 + V_m,(φ,h)/s₀²) )

- η and s₀ are fixed a priori (e.g. η = 1/median|d|).
- Uncertain advantages are attenuated, as in Glicko's g(RD).

**Step 5: fixed-share smoothing.** w ← (1−α) w + α/|M|, with α = 0.05.

**Step 6: linear pool, then dispersion control.**
- F_pool(z) = Σ_m w_m F_m(z).
- Optionally apply a beta transform G = B_{a,b}(F_pool) (Gneiting & Ranjan 2013), with a=b fitted on dev by WIS. Then extract the 23 quantiles.

**Why it is luck-aware.** A model's weight moves away from equal only to the extent that its advantage in this phase is (a) repeated (n_eff), (b) consistent (low s²) and (c) larger than between-cell noise (τ²). Brief streaks, such as model 2's single well-timed national peak, earn little credit.

### C2. Phase-gated analog ensemble with discrepancy variance (PG-AnEn)

1. For each component m and horizon h, build the AnEn residual library from that model's archived as-of forecasts (idea 5): predictors x_i and log residuals r_i.
2. For the new row, find the K = 50 nearest neighbours, using as distance the standardised predictor distance *plus* a phase term λ_φ · ‖π_R − π_i‖₁.
3. Corrected component CDF: F̃_m(z) = (1/K) Σ_k F_m(z − r_k) with kernel smoothing (bandwidth by Silverman's rule on {r_k}).
4. Shrink toward the raw component: F̂_m = ω F̃_m + (1−ω) F_m, with ω = K/(K + K₀) (credibility again; K₀ = 50 fixed).
5. Feed {F̂_m} into C1's pool.

This attacks both brief problems directly. Each model's phase-specific bias (model 1 in decline, model 2 in growth) is corrected *before* pooling, and intervals widen where the historical residuals are dispersed.

### C3. Lagged multi-source pool with a Minnesota prior (LMP)

- Members: current EAKF, GBQR, Farr and EDM; lag-1 versions of EAKF and GBQR (forecast at R−7, horizon h+1); lag-1 FluSight-ensemble; and lag-1 Metaculus-cp where present.
- Weights maximise the dev log score of the linear pool (Geweke–Amisano), penalised toward the equal-weight vector w⁰:

  ŵ = argmax_{w ∈ simplex} Σ_i log Σ_m w_m f_m(y_i) − λ ‖log w − log w⁰‖²

  This is Litterman's idea: shrink toward the naive benchmark. λ is chosen by LOSO on dev.
- Report the weights. If lag-1 FluSight-ensemble gets most of the weight, that is itself a finding: our models add little beyond a stale consensus.

### C4. Event-gated credibility weights with a Giacomini–White admission test (EG-CW)

**Event stream x_t**, all as-of:
- phase posterior π_t;
- permutation entropy H_t (idea 16);
- holiday flag (epi weeks 51–1);
- reporting-regime flag (voluntary NHSN period);
- last week's revision magnitude |log(v_new/v_old)| for the latest two weeks;
- ED–admissions divergence Δlog ED − Δlog adm;
- early-warning signal (lag-1 autocorrelation of growth);
- wave-arrival lead (idea 4).

**Admission test, run once on dev and pre-registered.** For each pair (EAKF, GBQR) and each h, regress

  Δ_i = L_EAKF,i − L_GBQR,i = β₀ + β' x_{t(i)} + e_i

- Use HAC (Newey–West) standard errors with lag h+1 and week-clustered blocks.
- Run the Giacomini–White Wald test on β.
- Keep only features with p < 0.01 in *both* LOSO folds with the same sign.

**Gate.**

  w(x) = softmax( W x + b ), where W is fitted by penalised log score with a ridge prior centred at 0 and b set to C1's credibility weights

- With no admitted features, W = 0 and EG-CW reduces to C1.
- This is the "combiner gated by real-world event streams through learned weights" the owner asked for. The guard is that the gate can only be turned on by a test of conditional predictive ability, never by an in-sample improvement.

### C5. Farr–EDM turning-point member with a Taylor-law + ACI wrapper (FET)

1. **Point dynamics.** Growth forecast g_{t+k} = g_t + Σ_{j≤k} d_j:
   - d_j from an S-map on the composite attractor in (g, Δg, Δlog ED) space;
   - shrunk toward the phase-pooled Farr constant d̄_φ with credibility Z.
2. **Width.** Count-scale standard deviation s_h = √(a_h ŷ^{b_h}) (Taylor law fitted on dev residuals). Form quantiles from a log-normal with matching median and variance.
3. **Calibration.** Per horizon, ACI on the nominal levels: α_{t+1} = α_t + γ(α − 1{y ∉ interval}), with γ = 0.02, updated on resolved targets only.

This gives a cheap, interpretable member focused on turning points whose errors should be uncorrelated with the SEIR's.

---

## Part 3. Test protocol shared by all experiments

1. **Data discipline.**
   - Every feature, library, archive and weight uses only as-of data (`time-series.csv` versions with `as_of` ≤ R).
   - Neighbour libraries and credibility statistics for a left-out season exclude that season entirely.
   - 2022-23 may serve only as library or training data, flagged "final-data, not as-of", and never for scoring.
2. **Dev folds.**
   - LOSO on 2023-24 and 2024-25. 2025-26 is used up and is reported only as "already seen".
   - Rows: h = 0..3, all 53 locations, the same rows for all compared models.
3. **Pre-registration.**
   - Before running, commit a file per experiment with the fixed hyperparameters, primary metric and acceptance rule.
   - Primary metric: relWIS against the relevant incumbent.
   - Secondary metrics: 50% and 90% coverage; WIS by phase.
4. **Uncertainty in the comparison.**
   - Use a block bootstrap over reference weeks (all locations and horizons of a week resampled together), 2,000 draws.
   - Report a 90% interval of relWIS.
   - "Win" requires relWIS < 1 in both folds *and* a bootstrap upper bound < 1.02. This deliberately hard rule fits a CV-grade record.
5. **Shadow mode 2026-27.**
   - Every surviving experiment runs weekly from the next Wednesday, with outputs committed with timestamps.
   - Scoring is done only against data published after the run.
   - Promotion to Track A requires a pre-registered shadow win over at least 15 resolved weeks, including at least one turning point.
6. **Runtime.** Every item below fits the GitHub runner: KNN, HMM filtering, credibility arithmetic and S-maps take seconds. The C2 archive needs the model 1 and model 2 backtest archives, which already exist offline.

## Part 4. Ranked experiments

| Rank | ID | Experiment | Track | Cost | Why this rank |
|---|---|---|---|---|---|
| 1 | E1 | **Linear pool (mixture) of model 1 + model 2**, equal weights, optional beta-transform dispersion fitted on dev; compared against quantile averaging of the same two | **A** (if it wins) | trivial | Theory (Lichtendahl 2013; Gneiting & Ranjan 2013; Geweke & Amisano 2011) says this is the right combiner for two under-dispersed models with opposite-phase errors. No learned weights, so it is hard to attack. |
| 2 | E2 | **Analog-ensemble recalibration of model 1** (idea 5 / C2 step 1–4) | **A** candidate | low | Phase-conditional correction is the principled answer to the failed global shift. Strong weather evidence. |
| 3 | E3 | **Lagged members**: add lag-1 FluSight-ensemble and lag-1 own forecasts to the E1 pool (C3 with λ→∞, i.e. equal weights) | B → A | zero | Free, independent information. Must first confirm file timestamps. |
| 4 | E4 | **Taylor-law width + ACI wrapper** on the final submission | **A** candidate | trivial | Directly targets narrow intervals with ~2 parameters per horizon, plus an online guarantee. |
| 5 | E5 | **CGL-pool** (C1) across all members | B | low | The owner's "luck-aware combiner", built from actuarial and sports theory, with E1 nested as its zero-information limit. |
| 6 | E6 | **Hierarchical discrepancy for model 1** (idea 18) vs E2, head to head | B (A if it beats E2) | low–med | The Los Alamos lineage; the principled alternative to AnEn. |
| 7 | E7 | **Farr curvature member** (idea 1) and **FET** (C5) | B | trivial | A new turning-point view; tests "decline at a constant rate" against SEIR depletion. |
| 8 | E8 | **EDM / multiview S-map member** (idea 6) | B | low | Non-parametric state dependence on a composite attractor; good small-data credentials. |
| 9 | E9 | **Event-gated weights with GW admission** (C4) | B | low | The owner's event-gated combiner. Likely outcome: few features admitted, which is itself a reportable honest result. |
| 10 | E10 | **Extremizing / anti-extremizing** of categorical pmfs (rate change, peak week) | A candidate (unclaimed targets) | trivial | Unclaimed points; one parameter. |
| 11 | E11 | **Erlang-stage / two-pool SEIR** for model 1 (idea 2) | B | med | The structural fix for the steep decline; needs a new frozen-settings pre-registration. |
| 12 | E12 | **Wave-arrival lead feature** for GBQR (idea 4) | B | low | Targets model 2's low bias during rises. |
| 13 | E13 | **Permutation entropy / early-warning features** as width or gate covariates (ideas 16–17) | B | trivial | Speculative; run inside E9's admission test rather than separately. |

**Order of work.**
1. E1, E3 and E4 need no new models: set them up this week, LOSO on dev, then start them in shadow mode next Wednesday.
2. E2 and E6 compete; run both offline and pre-register the choice rule.
3. E5 and E9 then stack on top of the winners.
4. E7, E8 and E11 add members to the pool.

## References (record URLs as found; full texts not opened, see the note at top)

- Baroyan O.V., Rvachev L.A. et al. 1971. Computer modelling of influenza epidemics for the whole country (USSR). Adv Appl Prob 3:224–226. https://opact.sdu.edu.tr/vufind/SummonRecord/FETCH-LOGICAL-c1337-eadad91cd6c76d53c0fea6bc4398926919ef6b273ab589d0668cfb8ed0cb94513
- Rvachev L.A. 1971. An experiment on computer prognostication of influenza epidemic. Doklady AN SSSR 198:68–70. https://mathnet.ru/eng/dan36143
- Ivannikov Yu.G., Ogarkov P.I. 2012. An experience of mathematical computing forecasting of the influenza epidemics for big territory. J Infectology 4(3):101–106. https://core.ac.uk/download/267960898.pdf
- Rvachev L.A., Longini I.M. 1985. A mathematical model for the global spread of influenza. Math Biosci 75:3–22. https://portal.mardi4nfdi.de/wiki/Publication:1060157
- Santillana M. et al. 2018. Relatedness of the IDEA model, "Farr's law" and SIR. Infect Dis Model 3:1–12. https://arxiv.org/abs/1603.01134v1
- Martin W.J. The epidemic curve of smallpox (on Farr and Brownlee). https://www.cambridge.org/core/services/aop-cambridge-core/content/view/47124E8E5E8037A960BEDE29B2E86FD5/S0022172400034367a.pdf/the-epidemic-curve-of-smallpox.pdf
- Brownlee J. 1906. Statistical studies in immunity: the theory of an epidemic. Proc R Soc Edinb. https://www.cambridge.org/core/journals/proceedings-of-the-royal-society-of-edinburgh/article/statistical-studies-in-immunity-the-theory-of-an-epidemic/A977DF53CCFCB01F7564311F573F99C2
- Breda D. et al. 2012. On the formulation of epidemic models (an appraisal of Kermack and McKendrick). J Biol Dyn 6:103–117. https://research-portal.uu.nl/en/publications/on-the-formulation-of-epidemic-models-an-appraisal-of-kermack-and/
- Wearing H.J., Rohani P., Keeling M.J. 2005. Appropriate models for the management of infectious diseases. PLoS Med 2:e174. https://rohanilab.ecology.uga.edu/wp-content/uploads/2013/11/Wearing_rohani_keeling2005.pdf
- Chowell G., Tariq A., Hyman J.M. 2019. Sub-epidemic wave model. BMC Med. https://bmcmedicine.biomedcentral.com/track/pdf/10.1186/s12916-019-1406-6
- Bartlett M.S. 1957. Measles periodicity and community size. JRSS A 120:48. https://catalogosiidca.csuca.org/Record/UCR.000471281/Similar
- Taylor L.R. 1961. Aggregation, variance and the mean. Nature 189:732–735. https://repository.rothamsted.ac.uk/item/8v52z/aggregation-variance-and-the-mean
- Hope-Simpson R.E. 1981. The role of season in the epidemiology of influenza. J Hyg 86:35–47. https://pubmed.ncbi.nlm.nih.gov/7462597/
- Viboud C. et al. 2006. Synchrony, waves, and spatial hierarchies in the spread of influenza. Science 312:447–451. https://ento.psu.edu/files/viboudetal2006.pdf
- Viboud C. et al. 2003. Prediction of the spread of influenza epidemics by the method of analogues. Am J Epidemiol 158:996–1006. https://scilit.com/publications/80539d81a37c7e3e42ec5fbf0ad99b43
- Lorenz E.N. 1969. Atmospheric predictability as revealed by naturally occurring analogues. J Atmos Sci 26:636–646. https://research.amanote.com/publication/R5_x3XMBKQvf0BhiaAio/atmospheric-predictability-as-revealed-by-naturally-occurring-analogues
- van den Dool H.M. 1994. Searching for analogues, how long must we wait? Tellus A 46:314–324. https://cpc.ncep.noaa.gov/products/predictions/experimental/bulletin/Dec97/a63.html
- Delle Monache L. et al. 2013. Probabilistic weather prediction with an analog ensemble. MWR 141:3498–3516. https://opensky.library.ucar.edu/islandora/object/articles%3A12922
- Delle Monache L. et al. 2011. Kalman filter and analog schemes to post-process NWP. https://ams.confex.com/ams/91Annual/webprogram/Paper181496.html
- Hoffman R.N., Kalnay E. 1983. Lagged average forecasting, an alternative to Monte Carlo forecasting. Tellus A 35:100–118. https://dx.doi.org/10.3402/tellusa.v35i2.11425
- Glahn H.R., Lowry D.A. 1972. MOS (history). https://www.weather.gov/media/mdl/AMSGlahnSymp2015_Dallavalle_paper.pdf
- Murphy A.H. 1993. What is a good forecast? Weather Forecast 8:281–293. https://stafforini.com/works/murphy-1993-what-good-forecast/
- Dawid A.P. 1984. Statistical theory: the prequential approach. JRSS A 147:278–292. https://www.cs.ubc.ca/~murphyk/MLRG/dawid84Prequential.pdf
- Sugihara G., May R.M. 1990. Nonlinear forecasting as a way of distinguishing chaos from measurement error. Nature 344:734–741. https://www.nature.com/articles/344734a0.pdf
- Sugihara G. 1994. Nonlinear forecasting for the classification of natural time series. Phil Trans R Soc A 348:477–495. https://scilit.com/publications/1d1bede45ec043dfd0d1bfbcaef05470
- Ye H., Sugihara G. 2016. Information leverage in interconnected ecosystems. Science 353:922–925. https://aitopics.org/doc/journals:C3AE7273
- Perretti C.T., Munch S.B., Sugihara G. 2013. Model-free forecasting outperforms the correct mechanistic model. PNAS 110:5253–5257. https://ar5iv.arxiv.org/html/1305.3544
- Deyle E.R. et al. 2016. Global environmental drivers of influenza. PNAS 113:13081–13086. https://escholarship.org/uc/item/0247p6d0
- Hamilton J.D. 1989. A new approach to the economic analysis of nonstationary time series. Econometrica 57:357–384. https://econpapers.repec.org/RePEc:ecm:emetrp:v:57:y:1989:i:2:p:357-84
- Le Strat Y., Carrat F. 1999. Monitoring epidemiologic surveillance data using hidden Markov models. Stat Med 18:3463–3478. https://search.r-project.org/CRAN/refmans/surveillance/html/algo.hmm.html
- Bates J.M., Granger C.W.J. 1969. The combination of forecasts. Oper Res Q 20:451–468. https://portal.mardi4nfdi.de/wiki/Publication:135294
- Claeskens G. et al. 2016. The forecast combination puzzle. IJF 32:754–762. https://econpapers.repec.org/RePEc:eee:intfor:v:32:y:2016:i:3:p:754-762
- Geweke J., Amisano G. 2011. Optimal prediction pools. J Econom 164:130–141. https://econpapers.repec.org/RePEc:eee:econom:v:164:y:2011:i:1:p:130-141
- Lichtendahl K.C., Grushka-Cockayne Y., Winkler R.L. 2013. Is it better to average probabilities or quantiles? Mgmt Sci 59:1594–1611. https://econpapers.repec.org/RePEc:inm:ormnsc:v:59:y:2013:i:7:p:1594-1611
- Genest C. 1992. Vincentization revisited. Ann Stat 20:1137–1142. https://projecteuclid.org/euclid.aos/1176348676
- Gneiting T., Ranjan R. 2013. Combining predictive distributions. EJS 7:1747–1782. https://projecteuclid.org/journals/electronic-journal-of-statistics/volume-7/issue-none/Combining-predictive-distributions/10.1214/13-EJS823.full
- Litterman R.B. 1986. Forecasting with Bayesian vector autoregressions: five years of experience. JBES 4:25–38. https://ideas.repec.org:443/a/bes/jnlbes/v4y1986i1p25-38.html
- Giacomini R., White H. 2006. Tests of conditional predictive ability. Econometrica 74:1545–1578. https://econpapers.repec.org/RePEc:ecm:emetrp:v:74:y:2006:i:6:p:1545-1578
- Ghysels E., Santa-Clara P., Valkanov R. 2004. The MIDAS touch. https://escholarship.org/content/qt9mf223rs/qt9mf223rs.pdf
- Bühlmann H. 1967. Experience rating and credibility. ASTIN Bull 4:199–207. https://www.casact.org/abstract/experience-rating-and-credibility
- Efron B., Morris C. 1975. Data analysis using Stein's estimator and its generalizations. JASA 70:311–319. https://www.medicine.mcgill.ca/epidemiology/hanley/bios602/MultilevelData/EfronMorrisJASA1975.pdf
- Mack T. 1993. Distribution-free calculation of the standard error of chain ladder reserve estimates. ASTIN Bull 23:213–225. https://www.casact.org/library/astin/vol23no2/213.pdf
- Höhle M., an der Heiden M. 2014. Bayesian nowcasting during the STEC O104:H4 outbreak. Biometrics 70:993–1002. https://staff.math.su.se/hoehle/pubs/hoehle_anderheiden2014-preprint.pdf
- Glickman M.E. 1999. Parameter estimation in large dynamic paired comparison experiments. JRSS C 48:377–394. https://econpapers.repec.org/RePEc:bla:jorssc:v:48:y:1999:i:3:p:377-394
- Dixon M.J., Coles S.G. 1997. Modelling association football scores and inefficiencies in the football betting market. JRSS C 46:265–280. https://eprints.lancs.ac.uk/id/eprint/19492
- Herbster M., Warmuth M. 1998. Tracking the best expert (fixed share). Secondary: https://arxiv.org/pdf/1008.4532
- Gibbs I., Candès E. 2021. Adaptive conformal inference under distribution shift. NeurIPS 34. https://proceedings.neurips.cc/paper/2021/hash/0d441de75945e5acbc865406fc9a2559-Abstract.html
- Satopää V.A. et al. 2014. Combining multiple probability predictions using a simple logit model. IJF 30:344–356. https://econpapers.repec.org/RePEc:eee:intfor:v:30:y:2014:i:2:p:344-356
- Baron J. et al. 2014. Two reasons to make aggregated probability forecasts more extreme. Decis Anal 11:133–145. https://econpapers.repec.org/RePEc:inm:ordeca:v:11:y:2014:i:2:p:133-145
- Farrow D.C. et al. 2017. A human judgment approach to epidemiological forecasting. PLoS Comput Biol 13:e1005248. https://ideas.repec.org/a/plo/pcbi00/1005248.html
- Polgreen P.M., Nelson F.D., Neumann G.R. 2007. Use of prediction markets to forecast infectious disease activity. Clin Infect Dis 44:272–279. https://iemweb.biz.uiowa.edu/?p=375
- Scarpino S.V., Petri G. 2019. On the predictability of infectious disease outbreaks. Nat Commun 10:898. https://www.nature.com/articles/s41467-019-08616-0
- O'Regan S.M., Drake J.M. 2013. Theory of early warning signals of disease emergence and leading indicators of elimination. Theor Ecol 6:333–357. https://daphnia.ecology.uga.edu/drakelab/?p=668
- Kennedy M.C., O'Hagan A. 2001. Bayesian calibration of computer models. JRSS B 63:425–464. https://econpapers.repec.org/RePEc:bla:jorssb:v:63:y:2001:i:3:p:425-464
- Osthus D. et al. 2019. Dynamic Bayesian influenza forecasting in the United States with hierarchical discrepancy. Bayesian Anal 14:261–312. https://projecteuclid.org/euclid.ba/1533866670
- Ray E.L., Reich N.G. 2018. Prediction of infectious disease epidemics via weighted density ensembles. PLoS Comput Biol 14:e1005910. https://ideas.repec.org/a/plo/pcbi00/1005910.html
- Yamana T.K., Kandula S., Shaman J. 2017. Individual versus superensemble forecasts of seasonal influenza outbreaks in the United States. PLoS Comput Biol 13:e1005801. https://econpapers.repec.org/RePEc:plo:pcbi00:1005801
- Brooks L.C. et al. 2018. Nonmechanistic forecasts of seasonal influenza with iterative one-week-ahead distributions. PLoS Comput Biol 14:e1006134. https://www.stat.cmu.edu/~ryantibs/papers/deltadens.pdf
- Reich N.G. et al. 2019. A collaborative multiyear, multimodel assessment of seasonal influenza forecasting in the United States. PNAS 116:3146–3154. https://stacks.cdc.gov/view/cdc/77374
- Montero-Manso P. et al. 2020. FFORMA: feature-based forecast model averaging. IJF 36:86–92. https://ideas.repec.org/a/eee/intfor/v36y2020i1p86-92.html (FFORMA, second in M4, is the ML cousin of C4's gate; it needs thousands of series, so it is not recommended here.)
