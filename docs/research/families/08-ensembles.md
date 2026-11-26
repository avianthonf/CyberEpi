# Family 08: forecast combination, stacking, expert advice, skill vs luck

Scope: how to combine our two models (EAKF, GBQR) and hub team models into one quantile
forecast for `wk inc flu hosp`, and how to tell whether a combiner's edge is skill or luck.
Track B candidates C1–C5 are specified in §7 with equations and pseudocode for
`backtest/shadow.py`.

Citation status: **[O]** = I opened the source (or its abstract/metadata record) in this
session. **[U]** = from memory, not opened; do not rely on it without checking.

## 0. Corrections to the first draft

- Claeskens, Magnus, Vasnev & Wang (2016) is in *International Journal of Forecasting* 32(3):
  754–762, not *Journal of Econometrics*. [O]
- Quantile averaging vs linear pool: the key reference is Lichtendahl, Grushka-Cockayne &
  Winkler (2013), *Management Science* 59(7):1594–1611. [O] Finding: the average quantile
  forecast has the same mean as the average probability forecast but is always sharper
  (lower variance); on SPF GDP and inflation data it beat the average probability forecast
  both when the latter was overconfident and when it was underconfident. [O] I earlier
  attributed the QA/LP result to Hora (2004) and claimed QA is "overdispersed-free"; both
  claims are withdrawn.
- Ranjan & Gneiting (2010), *JRSS-B* 72(1):71–91: the beta-transformed linear pool
  p = H_{α,β}(Σ w_i p_i), with H the Beta(α,β) CDF, nests the linear pool at α=β=1. The
  abstract summary says linear pooling is often uncalibrated; I did not open the full text
  to confirm the direction of its dispersion bias, so I no longer state it. [O for the
  model form; dispersion direction [U]]
- McAlinn & West (2019), *J. Econometrics* 210(1):155–169 (preprint arXiv:1601.07463). [O]
  The abstract says DBPS adapts to time-varying biases, miscalibration and dependence among
  forecasters. I did **not** verify the discount factor range or an intercept term in the
  paper; §7 C4 uses my own discounting and says so.
- Smith & Wallis (2009), *Oxford Bulletin of Economics and Statistics* 71(3):331–355. [O]
  Mechanism: estimation error in weights inflates the variance of weighted combinations; with
  equal weights the estimation error is zero.
- Herbster & Warmuth (1998), "Tracking the best expert", *Machine Learning*. [O] Fixed-share
  shares a fixed α of weight each trial; Variable-share is for losses in [0,1]; the paper's
  example sets α = 1/200 for about 5 shifts in 1000 trials. [O]
- Yao, Vehtari, Simpson & Gelman (2018), *Bayesian Analysis* 13(3):917–1007. [O] Stacking
  of predictive distributions with the log score; they prefer it to stacking of means.
- Ray & Reich (2018), "Prediction of infectious disease epidemics via weighted density
  ensembles", *PLoS Computational Biology* e1005910. [O] Weighted-density ensembles, weights
  that can depend on week of season; the regularised week-of-season weight (FW-reg-w) was
  the most stable; 14 retrospective seasons (1997/98–2010/11) plus 5 prospective seasons.
  Caveat from the paper: a small test set and correlated regions reduce the effective sample.
- Diebold & Mariano (1995), *JBES* 13(3):253–263. [O]
- Giacomini & White (2006), *Econometrica* 74(6):1545–1578. [O] Conditional predictive ability
  tests for the forecasting method (model + estimation), not just a fixed model.
- Freund, Schapire, Singer & Warmuth (1997), "Using and combining predictors that specialize",
  STOC, pp. 334–343. [O] Awake/abstaining experts: multiplicative weights where experts may
  abstain, with loss bounds that grow only logarithmically in the number of experts.
- Hansen, Lunde & Nason (2011), "The model confidence set", *Econometrica*. [O] Set of
  models not rejected as worst; size reflects how informative the data are.
- Politis & Romano (1994), "The stationary bootstrap", *JASA* 89(428). [O] Geometric-length
  blocks.
- Ding, Gibbs & Tibshirani (2025), "Calibrated multi-level quantile forecasting" (MultiQT),
  arXiv:2512.23671. [O] Online multi-level calibration wrapped around any quantile forecaster;
  keeps the quantiles ordered; maintains hidden and played offsets; isotonic projection (PAVA);
  claims no regret relative to the base forecaster; code at github.com/tiffanyding/multiQT. [O]
- Still [U] (cited from memory; open before relying on them): Bates & Granger (1969); Stock &
  Watson (2004); Timmermann (2006); Vincent (1912); Hansen (2005) SPA; White (2000) Reality
  Check; Bailey et al. (2017) backtest overfitting; Littlestone & Warmuth (1994); Jacobs et al.
  (1991); Raftery et al. (2005); Künsch (1989); Harvey, Leybourne & Newbold (1997) (the RCtest
  package documentation names it, but I did not read the paper). Gneiting & Raftery (2007).

## 1. What the hub actually does with combiners [O, from model-metadata and the FluSight-manuscripts model_types file]

Equal-weight pools and medians dominate:

- `FluSight-ensemble`: median of eligible quantile submissions (hubEnsembles). [O]
- `FluSight-lop_norm`: equal-weight linear opinion pool of all eligible quantile submissions. [O]
- `FluSight-trained_mean` / `FluSight-trained_med`: **learned weights.** Weighted mean or
  median over submissions from the prior six weeks; weights are a sigmoid transform of each
  forecast's relative WIS against the baseline; capped at 0.3. [O]
- `FluTurists-ensemble`: quantile average of three components, weights refit weekly by inverse
  WIS on this season's scored forecasts. [O]
- `UVAFluX-OptimWISE` and `UVAFluX-FS_OptimWISE`: weights chosen by minimising WIS over the
  most recent up to 4 weeks. [O]
- `ISU_NiemiLab-GPE`: linear pool with weights chosen by a Gibbs posterior. [O]
- `ACCIDDA-insightcast`: per location, the 5 candidates with the lowest WIS over 9
  seasonally aligned origins, then an equal-weight linear pool. [O] This is a selection-then-
  equal-weight design; it is the closest hub example of the "luck-aware" idea (select on CV,
  then don't learn weights).
- `MIGHTE-Nsemble`: for 2026-27, fixed weights replace adaptive weighting. [O]
- `Emory-EpiRSI`: fixed greedy ensemble selection of experts. [O]
- `MOBS-GLEAM_NCB_FLUH`: a neural contextual bandit selecting epidemic trajectories. [O] The
  closest hub method to event-gated selection.
- `UM-DeepOutbreak`: average of two deep forecasters, then post-hoc conformal calibration. [O]
- `CMU-TimeSeries_Cal`: MultiQT applied post hoc to the CMU ensemble. [O]
- `Sentinel-Ens`, `SahilLab-Trio`, `CU-STS_Residual`: equal-weight quantile averages, the last
  with a learned residual correction. [O] The metadata for CU-STS_Residual says learned weights
  gave no gain once the correction was applied. [O]
- `SigSci-TSENS`: equal weights across components. [O]

Not found in the hub metadata: Hedge/fixed-share, BMA, stacking of predictive distributions,
BPS, or mixture-of-experts under those names. [O: grep over 159 files for these terms]

What this means: the hub contains learned-weight combiners (trained_mean/med, OptimWISE, FluTurists-ensemble, GPE), but I found **no evaluation in the metadata** showing
they beat equal weights. Their results are in the hub's evaluation files, which I have not
read. I make no claim about their performance.

## 2. The combination puzzle [O for Smith & Wallis and the venue of Claeskens et al.; mechanism [U]]

**Theory.** Let forecast errors have covariance Σ. The optimal weights are w* ∝ Σ⁻¹1 (for
unbiased forecasts). Estimating them with Σ̂ replaces w* with ŵ. Smith & Wallis (2009) show
that the estimation error in ŵ inflates the variance of the combination relative to the equal
weight w = 1/M, which has no estimation error; in their simulations and their reappraisal of
Stock & Watson (2003) this error exceeds the gain from optimal weights unless the sample is
large. Claeskens et al. (2016) [O] give a simple theoretical account: when weights are random
(estimated), the combined forecast is biased and more variable than the fixed-weight
benchmark, so the "optimal" combination need not beat equal weights.

**Applied.** Effective sample size is small: about four seasons, each with about 30 weeks, but
weeks within a season are autocorrelated, and each location has at most 4 independent epidemic
episodes. A learned weight is therefore a noisy estimate, and its standard error is comparable
to its value. Shrink toward equal weights and gate on the test in §6.

**Uncertainty from combination.** Combining produces spread from two sources: each member's
predictive spread, and the disagreement between members. How the combiner treats the second
source is the main design choice (§3).

## 3. Quantile averaging vs linear pool [O: Lichtendahl et al. 2013]

Let F_A, F_B be the member predictive CDFs and q_A(τ), q_B(τ) their quantile functions at
levels τ.

- Quantile average (Vincentisation): q_QA(τ) = ½(q_A(τ) + q_B(τ)).
- Linear pool: F_LP(x) = ½(F_A(x) + F_B(x)), with q_LP(τ) = F_LP⁻¹(τ).

Lichtendahl et al. (2013) [O]: both have the same mean, and q_QA is always sharper (lower
variance) than the linear pool. The linear pool is wider when members disagree, and is bimodal
when they are far apart. In their SPF tests the quantile average did better than the
probability average both when the latter was overconfident and when it was underconfident.

Ranjan & Gneiting (2010) [O for the model form] propose the beta-transformed linear pool
H_{α,β}(Σ w_i p_i) to recalibrate the pool; it nests the linear pool at α=β=1.

Our shadow pair (`CyberEpi-MIX_QA`, `CyberEpi-MIX_LP`) is this comparison, the right live test.
Hub precedent: FluSight-lop_norm (linear pool) and FluSight-ensemble (median) coexist, and
Shandross et al. (PMC11230315, multi-model ensembles in infectious disease) report comparisons of linear pools, quantile means and quantile medians on FluSight 2021–23. Record [O]; the venue (*Statistics in Medicine*, 2026) is [U]; I did not read the numerical results, so these comparisons are as solid as that one record.

## 4. Stacking and Bayesian model averaging [O for Yao et al. 2018; BMA [U]]

**Stacking of predictive distributions (Yao et al. 2018).** For K members with leave-one-out
(here leave-one-season-out) predictive densities p_{k,−i}(y_i), choose

  ŵ = argmax_{w ∈ Δ^{K−1}} Σ_i log( Σ_k w_k p_{k,−i}(y_i) ).

They recommend this to stacking of means and to BMA when none of the models is true (M-open),
which is our situation. For quantile forecasts with WIS (not a density), the analogue is
argmin over the simplex of Σ_i WIS(Σ_k w_k F_{k,−i}), the CRPS-optimal pool [U: exact
statement of the CRPS-pool result from Gneiting & Ranjan (2013)].

**BMA [U].** w_k ∝ p(D | M_k) (Raftery et al. 2005). Marginal likelihoods concentrate on the
member that won the most recent peak. Use the posterior predictive spread as a disagreement
diagnostic, not as weights.

**Applied.** With two members the simplex is one parameter. Three leave-one-season-out folds
give three estimates; their spread is the honest standard error (§6).

## 5. Expert advice: Hedge, fixed share, sleeping experts [O for Herbster & Warmuth and Freund et al.]

**Hedge.** Weights v_{m,t} ∝ exp(−η Σ_{s≤t} ℓ_{m,s}), with losses ℓ bounded.

**Fixed share (Herbster & Warmuth 1998) [O].** After the Hedge update, mix each weight with
the average: v ← (1−α) v + α·mean(v) in weight space (equivalently a share step on log
weights). Each expert keeps weight at least α/M·(total), so it can recover after a slump.
The paper's example is α = 1/200 for about 5 shifts in 1000 trials. [O] With 12–52 weeks per
window, α ≈ 0.05 is an order-of-magnitude choice; it is not identified from our data and must
be fixed in advance.

**Sleeping / awake experts (Freund et al. 1997) [O].** Experts may abstain. This is the formal
version of event gating: a member is active only when its specialty condition holds as of the
reference date.

**Loss normalisation.** Hedge on raw WIS lets national and large states dominate. Normalise
per location by the scale of the equal-weight combiner over the trailing window (defined in
C1).

**Failure mode.** Hedge with a non-trivial η chases noise on short windows. Always combine with
the shrinkage of §6.

## 6. Skill-vs-luck tests and the luck gate

Tools:

- **Diebold–Mariano (1995) [O].** Works for arbitrary loss functions and serially correlated
  loss differentials. Small-sample correction: Harvey, Leybourne & Newbold (1997) [U; RCtest
  documentation names it]. For h-step-ahead differentials, use a HAC variance with bandwidth
  h−1; pool locations only after normalisation and treat locations as clusters.
- **Giacomini & White (2006) [O].** Conditional predictive ability: tests the forecasting method
  (model + estimation), with the test conditioned on information at R. This is the appropriate
  test for "does this combiner's rule beat equal weights going forward", as opposed to "is
  this set of weights better in-sample".
- **Hansen, Lunde & Nason (2011) MCS [O].** When many team models are compared, the set of
  models not rejected as worst. Controls family-wise error.
- **Block bootstrap over weeks.** Politis & Romano (1994) stationary bootstrap [O] with block
  length 4–6 weeks; Künsch (1989) moving blocks [U].
- **Data-snooping corrections (White 2000 Reality Check; Hansen 2005 SPA) [U].** We try 5
  combiners plus 2 existing ones; state the search size in advance.

**Luck gate (pre-registered, applies to any learned weight).**

Let, for each dev fold f (a held-out season) and each (location, horizon, week) row i,
d_i = WIS_i(combiner) − WIS_i(equal weights), normalised per location by the equal-weight
WIS mean in that location over the fold. Let D_f = mean of d_i over the fold, and let se_f be
its stationary-block-bootstrap standard error (block length 4 weeks, 2000 resamples).

  Gate: accept learned weights only if D_f < 0 **and** |D_f| > 2·se_f in **both** dev folds
  (2023-24 and 2024-25).

  Shrinkage: λ = clip(−min_f(D_f) / (2·max_f se_f), 0, 1) when the gate passes, else λ = 0.

  Final weights: w = λ·w_learned + (1−λ)·w_equal.

The factor 2 and the both-folds requirement are pre-registered guards against winner's curse.
λ = 0 reproduces equal weights exactly. Only the leave-one-season-out folds may set λ; the
2025-26 holdout is used up.

## 7. Track B combiners C1–C5 (shadow mode)

Common definitions (all as-of R; only truths for weeks ≤ R−7 are used when fitting):

- Members: m ∈ {A = CyberEpi-EAKF, B = CyberEpi-GBQR} (C5 uses hub team models).
- Row index i = (location l, horizon h, target date). Quantile arrays Q_m[i, τ] at the 23 hub
  levels τ ∈ T.
- WIS_m,i = wis.py's WIS (sum of the 23 pinball losses ÷ 11.5); do not reimplement.
- Quantile functions: q_m(τ) = Q_m[i,τ] (monotone after sorting).
- Pool quantile function: for a weight vector w, the linear pool evaluates F_w(x) = Σ_m w_m F_m(x),
  with each F_m piecewise linear through its quantile points and flat tails; q_LP,w(τ) is found
  by inverting F_w on a grid of 2001 points between min and max of the member quantiles.
- Quantile average: q_QA,w(τ) = Σ_m w_m Q_m[i,τ].

Shared pseudocode (shadow.py helpers):

```
def wis(q, y):                  # q: (23,) quantiles, y: scalar  (use wis.py in code)
def qa(Q, w):                   # Q: (M, 23), w: (M,) -> (23,)
    return w @ Q
def lp_quantiles(Q, w, grid_n=2001):
    lo, hi = Q.min(), Q.max(); x = linspace(lo, hi, grid_n)
    F = sum_m w_m * interp(x, sort(Q[m]), T, left=0, right=1)   # flat tails
    F = maximum.accumulate(F)
    return interp(T, F, x)       # invert; log count of plateaus
def stack_simplex(losses_by_w):  # generic: argmin over grid of w in Delta
```

Pre-registered constants: T = the 23 hub levels; grid for the simplex = steps of 0.05 (M=2)
or coordinate descent (M>2).

### C1. Luck-gated Hedge with fixed share (LG-FS)

Losses (per member, per row), normalised by the trailing equal-weight scale:

  ℓ_{m,t} = mean_i∈t WIS_{m,i} / (ε + S_{t}),  S_t = mean_{s∈[t−W,t)} mean_i∈s WIS_{QA,i}

with window W = 12 weeks (pre-registered), ε = 1e-3.

Log-weight recursion over the window (replayed from scratch each week, so no hidden state):

  v_{m,t} = −η Σ_{s=t−W}^{t−1} ℓ_{m,s}                      (Hedge)
  π_{t} = softmax(v_t)
  π̃_t = (1−α) π_t + α·(1/M)                                  (fixed share, α = 0.05)
  w_learned = π̃_{t}, η = 1 (pre-registered; η not tuned)

Shrink with the §6 gate: w = λ·w_learned + (1−λ)·w_equal; output quantiles q = Σ_m w_m Q_m
(quantile average, so C1 is a QA with learned weights).

```
def lg_fs(Q_hist, WIS_hist, Q_now, W=12, eta=1.0, alpha=0.05):
    ell = normalise(WIS_hist, by=equal_weight_scale(WIS_hist, W))  # (W, M)
    v = -eta * ell.sum(axis=0)
    pi = softmax(v)
    pi = (1 - alpha) * pi + alpha / M
    lam = luck_gate(WIS_hist, folds=dev_folds)                     # §6
    w = lam * pi + (1 - lam) * ones(M) / M
    return w @ Q_now
```

Expected behaviour: equal weights unless one member loses consistently over the trailing 12
weeks.

### C2. Event-gated linear pool (EG-LP)

Gate on a pre-registered, observable as-of event: the change in the NSSP ED-visit share for
flu, s_R = (ED_R − ED_{R−14}) / 2, where ED is the as-published value at R (from the hub
ED-visits target, published from Nov 2025; use the as-of version).

  g_R = 1 if s_R > 0 (rising), 0 otherwise.

Member weights in the pool:

  w_A(g) = ½ + s·(2g − 1),  w_B(g) = 1 − w_A(g),  s ∈ [−0.5, 0.5]

s is chosen on a pre-registered grid of 21 values by minimising trailing WIS of the linear pool
over the dev folds, then shrunk:

  s_final = λ·s_hat,  λ from §6 applied to the difference WIS(LP_{s_hat}) − WIS(LP_0).

Output: q = lp_quantiles(Q, w(g_R)).

```
def eg_lp(Q_now, ed_now, ed_2w_ago, s_grid, WIS_fold):
    g = (ed_now - ed_2w_ago) / 2 > 0
    s_hat = argmin_s mean_fold WIS(LP(s))               # pre-registered grid
    lam = luck_gate(WIS(LP(s_hat)) - WIS(LP(0)))        # §6, dev folds only
    s = lam * s_hat
    w = [0.5 + s*(2*g-1), 0.5 - s*(2*g-1)]
    return lp_quantiles(Q_now, w)
```

Risk: the ED series has seen revisions; use the as-of version throughout.

### C3. Disagreement-adaptive pool (DAP), corrected

The earlier version fixed κ = 0.5, which is a constant blend of QA and LP and does not adapt to
disagreement. Corrected: κ is a function of the members' disagreement in units of their own
spread, per row.

  m_A, m_B = medians of Q_A, Q_B;  w_A, w_B = 50% interval widths (q_0.75 − q_0.25) of each member
  d_i = |m_A − m_B| / ½(w_A + w_B + ε)      (dimensionless disagreement)
  κ_i = min(1, d_i / d_0),   d_0 = 1 (pre-registered)

  q_DAP(τ) = q_QA(τ) + κ_i · (q_LP(τ) − q_QA(τ))

When the members agree on the centre relative to their spread, κ→0 and the output is the
sharper quantile average (Lichtendahl et al. 2013 [O]). When they disagree by at least d_0 spread
units, κ=1 and the output is the linear pool, which carries the between-member spread. d_0 is
the only parameter; it is fixed before scoring.

```
def dap(Q_A, Q_B):
    d = abs(median(Q_A) - median(Q_B)) / (0.5*(iqr(Q_A) + iqr(Q_B)) + 1e-9)
    kappa = min(1.0, d / 1.0)
    qQA = 0.5*(Q_A + Q_B); qLP = lp_quantiles(stack([Q_A, Q_B]), [0.5, 0.5])
    return qQA + kappa*(qLP - qQA)
```

Note: when κ ∈ (0,1), q_DAP is no longer a linear pool or a quantile average; it is a
heuristic blend. Report κ per week so this is visible. Check monotonicity of q_DAP after the
blend; QA and LP are each monotone, so their convex combination is too, but apply sorting as a
guard and log its activations.

### C4. Bagged stacking with a discounted bias term (BS-DBPS, simplified)

This is **my** simplification of dynamic Bayesian predictive synthesis. McAlinn & West's
method is a density-based DLM; I have not verified its discount range or its intercept
parametrisation [U]. The version below uses conjugate, closed-form updates so it is cheap.

Stacking objective, discounted over weeks, with discount δ = 0.95 (pre-registered):

  ŵ(B) = argmin_{w∈Δ} Σ_{t<R} δ^{R−t} Σ_{i∈t} WIS_i(q_w),  q_w = Σ_m w_m Q_m

Bagging over block-bootstrap resamples of weeks (block length 4, B = 200):

  w_bag = (1/B) Σ_b ŵ(B_b)

Bias term per horizon h, on the quantile scale of the combined forecast, with a conjugate
normal prior N(0, τ²) and observation noise σ² estimated from discounted residuals:

  e_t = y_t − median(q_{w_bag,t}),   S_h = Σ_{t<R} δ^{R−t} e_t,   n_h = Σ_{t<R} δ^{R−t}
  b_h = S_h / (n_h + σ²/τ²)

with τ = 0.1 × (mean scale of y over the last season), pre-registered. The bias shifts all
quantiles of the pool by b_h.

Gate: λ from §6 on the difference WIS(q_bag + b) − WIS(q_EW). The bias term alone is the
learned correction that failed in the earlier after-the-fact shift (brief §5), so it is
included only if the gate passes; λ = 0 removes both the weights and the bias.

```
def bs_dbps(Q_hist, y_hist, delta=0.95, B=200, block=4, tau_rel=0.1):
    w_list = []
    for b in range(B):
        weeks = block_bootstrap_weeks(n_weeks, block)
        w_list.append(stack_simplex(Q_hist[weeks], y_hist[weeks], delta))
    w_bag = mean(w_list, axis=0)
    e = y_hist - median(Q_hist @ w_bag)
    disc = delta ** (R - t_hist)
    b = (disc*e).sum() / (disc.sum() + sigma2(e, disc) / tau2(y_hist))
    lam = luck_gate(...)
    return lam*(Q_now @ w_bag + b) + (1-lam)*(Q_now @ w_equal)
```

Failure mode: intercepts learned per phase repeat the earlier shift failure. With δ = 0.95
and about 30 weeks per season, the effective memory is about 20 weeks, roughly one epidemic.

### C5. Team-skill-tilted ensemble (TST), hub-wide

Equal-weight quantile average of the K = 5 hub models with the lowest trailing WIS, computed
per (location, horizon) over the 8 most recent scored weeks. Only models with all four horizons
and all 53 locations are eligible. K = 5 fixed before scoring.

  S_m(l,h) = mean WIS over the last 8 scored weeks;  T = argmin_K S_m(l,h)
  q_TST = (1/K) Σ_{m∈T} Q_m

Gate: λ from §6 on WIS(q_TST) − WIS(q_EW over all eligible models). Uses the hub archive from
`backtest/archive_scores.py`, which must exist before this runs.

Precedent: ACCIDDA-insightcast does CV-based top-5 selection followed by an equal-weight
linear pool [O]; the TST design tests that selection on the hub archive with the luck gate.

## 8. Ranked experiments

1. **[Track A] Shadow MIX_QA vs MIX_LP vs EAKF, GBQR, FluSight-ensemble for at least 8 scored
   weeks.** Pre-registered: primary metric relWIS vs EAKF; secondary coverage at 50/90%.
   Win: block-bootstrap CI of the difference excludes zero. Zero tuning.
2. **[Track A] Archive test of equal weights vs learned combiners** (C1, C4 weight part, C5),
   leave-one-season-out on 2023-24 and 2024-25, using the §6 gate. Expect equal weights to win.
   Only proceed to Track A if λ > 0 in both dev folds.
3. **[Track B] DAP (C3) shadow** vs MIX_QA and MIX_LP; d_0 = 1 pre-registered; no fit.
4. **[Track B] EG-LP (C2) shadow**, compare vs MIX_QA by phase using the summary.csv phase labels.
5. **[Track B] LG-FS (C1) and BS-DBPS (C4) shadow**; both reduce to equal weights unless the
   gate passes. Log λ weekly.
6. **[Track B] TST (C5)** after the archive run exists; hub-level, needs no new forecasts.

Stop rules: no combiner graduates on one season; no combiner is re-tuned after its first scored
week; every variant and its constants are committed to git before the first scored week.

## 9. Tests for the implementer

- Identical members in → QA, LP, DAP return the same quantiles.
- λ = 0 reproduces equal weights exactly (regression guard).
- Quantiles are non-decreasing for all combiners; count sorting activations and log them.
- WIS computed via `wis.py` only.
- Per-row κ (DAP) and λ (all) logged in `forecasts/shadow/diagnostics/`.

## References

Opened [O]:
- Lichtendahl, K. C., Grushka-Cockayne, Y. & Winkler, R. L. (2013). Is it better to average
  probabilities or quantiles? *Management Science* 59(7):1594–1611.
- Smith, J. & Wallis, K. F. (2009). A simple explanation of the forecast combination puzzle.
  *Oxford Bulletin of Economics and Statistics* 71(3):331–355.
- Claeskens, G., Magnus, J. R., Vasnev, A. L. & Wang, W. (2016). The forecast combination
  puzzle: a simple theoretical explanation. *International Journal of Forecasting* 32(3):754–762.
- Ranjan, R. & Gneiting, T. (2010). Combining probability forecasts. *JRSS-B* 72(1):71–91.
- Yao, Y., Vehtari, A., Simpson, D. & Gelman, A. (2018). Using stacking to average Bayesian
  predictive distributions. *Bayesian Analysis* 13(3):917–1007.
- McAlinn, K. & West, M. (2019). Dynamic Bayesian predictive synthesis in time series
  forecasting. *Journal of Econometrics* 210(1):155–169. (arXiv:1601.07463)
- Herbster, M. & Warmuth, M. K. (1998). Tracking the best expert. *Machine Learning*.
- Freund, Y., Schapire, R. E., Singer, Y. & Warmuth, M. K. (1997). Using and combining predictors
  that specialize. *STOC*, 334–343.
- Ray, E. L. & Reich, N. G. (2018). Prediction of infectious disease epidemics via weighted
  density ensembles. *PLoS Computational Biology*, e1005910.
- Diebold, F. X. & Mariano, R. S. (1995). Comparing predictive accuracy. *JBES* 13(3):253–263.
- Giacomini, R. & White, H. (2006). Tests of conditional predictive ability. *Econometrica*
  74(6):1545–1578.
- Hansen, P. R., Lunde, A. & Nason, J. M. (2011). The model confidence set. *Econometrica*.
- Politis, D. N. & Romano, J. P. (1994). The stationary bootstrap. *JASA* 89(428).
- Ding, T., Gibbs, I. & Tibshirani, R. J. (2025). Calibrated multi-level quantile forecasting.
  arXiv:2512.23671.
- FluSight-manuscripts `FluSight2024_25/model_types.csv` (github.com/cdcepi/FluSight-manuscripts).
- hubEnsembles documentation (hubverse-org.github.io/hubEnsembles).
- Shandross et al., PMC11230315 (multi-model ensembles in infectious disease). Record [O]; venue (*Statistics in Medicine*, 2026) [U]; results not read.

Unverified [U]:
- Bates, J. M. & Granger, C. W. J. (1969). *Operational Research Quarterly*.
- Stock, J. H. & Watson, M. W. (2004). *Journal of Forecasting*.
- Timmermann, A. (2006). Forecast combinations. *Handbook of Economic Forecasting*.
- Vincent, S. B. (1912). *Behavior Monographs*.
- Raftery, A. E., Gneiting, T., Balabdaoui, F. & Polakowski, M. (2005). *Monthly Weather Review*.
- Gneiting, T. & Ranjan, R. (2013). Combining predictive distributions. *Electronic Journal of
  Statistics*.
- Littlestone, N. & Warmuth, M. K. (1994). *Information and Computation*.
- Jacobs, R. A., Jordan, M. I., Nowlan, S. J. & Hinton, G. E. (1991). *Neural Computation*.
- Harvey, D., Leybourne, S. & Newbold, P. (1997). *IJF*.
- Künsch, H. R. (1989). *Annals of Statistics*.
- White, H. (2000). *Econometrica*. Hansen, P. R. (2005). *JBES*.
- Bailey, D. H., Borwein, J., López de Prado, M. & Zhu, Q. J. (2017). *Journal of Computational
  Finance*.
- Gneiting, T. & Raftery, A. E. (2007). *JASA*.
