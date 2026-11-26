# Family 07: calibration and conformal methods

Scope: PIT diagnostics, isotonic recalibration, EMOS-type parametric post-processing, conformal prediction (split, CQR, ACI, conformal PID), and why our post-hoc fix (`backtest/calibrate.py`) failed. Evidence and numbers come from the repo and hub files I opened. Literature: "search-verified" means I read a search-engine abstract, not the full paper. "[unverified]" means it is from memory and I did not check it.

## 0. Summary of the diagnosis

- Our model 1 (EAKF) is under-covered: 90% intervals cover 73–75% (2024-25 and 2025-26), 50% intervals cover 35–39% (`backtest/results/honest/summary-test-chosen.json`). Model 2 is closer: 90% coverage 0.80 on the 2025-26 holdout (`backtest/results/model2/summary-holdout-2025-26.json`).
- The shortfall is mostly **bias, not width**. Model 1 runs low in declines and model 2 runs low in rises (PROBLEM_BRIEF §5). A miscalibration whose sign depends on epidemic phase cannot be fixed by one global transform.
- `calibrate.py` fits one shift `b` and one log-scale width `k` per horizon, for all phases and all 53 locations. Its fit is in-sample for 2024-25 and 2025-26 (see §3.4), so its reported gain is optimistic. In the one clean out-of-sample fold it was worse, and at h=0 it lowered held-out coverage. It did not move in-sample coverage either (§3.2).
- The right next step is a diagnostic first (PIT by phase, horizon, and size class, on as-published data), then a scale-free, phase-aware conformal layer tested leave-one-season-out. Nothing of this should go to Track A until it wins in shadow.

## 1. Theory

### 1.1 Calibration and PIT

For a forecast CDF $F_t$ and outcome $y_t$, the probability integral transform $u_t = F_t(y_t)$ is Uniform(0,1) when the forecasts are probabilistically calibrated. Calibration in the quantile sense (Kuleshov, Fenner & Ermon 2018, ICML; search-verified) means $P(Y \le F_X^{-1}(p)) = p$ for all $p$. Sharpness is the separate goal of making $F$ narrow. Gneiting, Balabdaoui & Raftery (2007, JRSSB) [unverified] set the "maximise sharpness subject to calibration" principle. Histogram of $u_t$ shows the shape of the miscalibration: U-shape = too narrow; hump = too wide; skew = bias. Conditional PIT (by phase, horizon, size class) answers our question, which a pooled PIT hides.

For a 23-level quantile forecast we only observe $F$ at 23 points. PIT is then approximated by linear interpolation between levels; the tails beyond 0.01 and 0.99 are unknown and must be extrapolated or excluded.

### 1.2 Isotonic recalibration (Kuleshov et al. 2018)

Let $\hat F_t$ be the model's CDF and $\hat u_t = \hat F_t(y_t)$. Fit a non-decreasing map $R:[0,1]\to[0,1]$ by isotonic regression of the indicator $\mathbf 1\{\hat u_t \le p\}$ on $p$, using the empirical CDF of PITs as target. The recalibrated forecast is $R(\hat F_t)$, which is a CDF because $R$ is monotone. Properties: non-parametric, consistent in the large-sample limit, but it needs many calibration points. With 53 locations times about 30 weeks times 4 horizons per season, there are about 6,000 points per season, but these are strongly dependent across locations (national shocks) and weeks (autocorrelation), so the effective sample is far smaller. Isotonic can also reshape tails erratically when the calibration set is small.

### 1.3 EMOS and its relatives

Gneiting, Raftery, Westveld & Goldman (2005, MWR 133(5):1098–1118, doi:10.1175/MWR2904.1; search-verified) post-process an ensemble of size $M$ into a Gaussian $N(a + \sum_m b_m x_m,\ c + d\, s^2)$, where $s^2$ is the ensemble variance. Parameters are fitted by minimising the average CRPS over a training window. Parametric, few parameters, uses spread-skill. Extensions: analog EMOS (Junk, Delle Monache & Alessandrini 2015, MWR; search-verified); mixture EMOS for wind (search-verified); Baran & Lerch (2018, Int. J. Forecasting; arXiv:1607.08096, search-verified) combine EMOS predictive distributions with the beta-transformed linear pool.

Our analogue: the EAKF gives $M=300$ members, so an EMOS-type layer on log1p counts is directly possible. On the count scale, use a log-normal or a shifted and scaled logistic on $\log(1+y)$.

### 1.4 Combining distributions

Linear pool $G(y)=\sum_i w_i F_i(y)$ widens. The beta-transformed linear pool (BLP) of Ranjan & Gneiting (2010, JRSSB 72(1):71–91) and Gneiting & Ranjan (2013, EJS, doi:10.1214/13-ejs823; search-verified) is $G_{\alpha,\beta}(y)=B_{\alpha,\beta}\!\big(\sum_i w_i F_i(y)\big)$, where $B_{\alpha,\beta}$ is the Beta CDF. It nests the linear pool at $\alpha=\beta=1$, and it can sharpen or widen the combined distribution. This is the "calibrated combiner" bridge to Family 08.

### 1.5 Split conformal

Given exchangeable calibration scores $s_i = \mathrm{score}(x_i, y_i)$, the set $C(x)=\{y:\mathrm{score}(x,y)\le \hat q\}$, with $\hat q$ the $\lceil (n+1)(1-\alpha)\rceil/n$ empirical quantile of the scores, has $P(Y\in C)\ge 1-\alpha$ marginally, for any predictor and without distributional assumptions. Requirement: exchangeability of calibration and test points. Time series break this (seasonality, drift, reporting regime changes), which motivates the adaptive variants below.

### 1.6 Conformalized quantile regression (CQR)

Romano, Patterson & Candès (2019, NeurIPS; arXiv:1905.03222; search-verified). With a quantile model giving $\hat q_{\mathrm{lo}}(x)$ and $\hat q_{\mathrm{hi}}(x)$, the score is $E_i = \max\{\hat q_{\mathrm{lo}}(x_i)-y_i,\ y_i-\hat q_{\mathrm{hi}}(x_i)\}$ and the interval is $[\hat q_{\mathrm{lo}}(x)-Q_{1-\alpha}(E),\ \hat q_{\mathrm{hi}}(x)+Q_{1-\alpha}(E)]$. It is adaptive (widths follow the input) and valid in finite samples. For a 23-quantile forecast we can apply CQR per quantile pair (0.01/0.99, 0.025/0.975, …). Known limitation: the correction is one constant per pair and horizon, which is a shift of the tails, not of the median.

### 1.7 Adaptive conformal inference (ACI)

Gibbs & Candès (2021, NeurIPS; arXiv:2106.00170; search-verified). Track the effective level $\alpha_t$ online:
$$\alpha_{t+1}=\alpha_t+\gamma\,(\alpha-\mathrm{err}_t),\qquad \mathrm{err}_t=\mathbf 1\{Y_t\notin C_t(\alpha_t)\}.$$
Guarantee: the long-run miscoverage average converges to $\alpha$ for any sequence (no exchangeability), with error $O(1/(\gamma T)+\gamma)$-type bounds (I did not check the exact constants). Step size $\gamma$ trades adaptivity against stability. Angelopoulos, Barber & Bates (2024; arXiv:2402.01139; search-verified) add decaying steps $\eta_t\propto t^{-1/2-\epsilon}$, which give worst-case and i.i.d. guarantees at once.

### 1.8 Conformal PID

Angelopoulos, Candès & Tibshirani (arXiv:2307.16895; search-verified; the Scholar page lists NeurIPS 2023). The threshold update is a PID controller on the miscoverage error: the proportional term tracks the current error, the integral term the accumulated error (classical ACI), and the derivative term reacts to systematic trends. Authors test it on COVID-19 statewide deaths and find better coverage than the CDC ensemble. The PID form matters for us because seasonal waves produce systematic, not random, errors.

### 1.9 Neural conformal control

Li & Rodríguez (arXiv:2412.18144; search-verified): a neural model that learns the conformal correction. Used in the hub by UM-DeepOutbreak (see §2.3).

## 2. Application to this problem

### 2.1 What must be calibrated

- Count scale vs rate: our score is on counts, and the largest locations (US, CA, TX, NY) dominate. Calibrate on $\log(1+y)$ or on the rate per 100k, then map back. Per-location scale normalisation before pooling.
- Horizon: four horizons with very different error scales (h=0 is a nowcast of the latest week under revisions).
- Phase: rising, near peak (±2 weeks), declining (PROBLEM_BRIEF §5). Phase is known at forecast time from the last weeks of data, so it is a legitimate conditioning variable. Its boundaries must be fixed before testing.
- Data vintage: residuals must come from as-published forecasts (look-ahead rule 1). The current fit uses `rows-test-chosen.csv`, which has ILI set to "final" (`summary-test-chosen.json` config), so its residuals may be optimistic. The ED-vintage run gives almost the same result (2025-26 cov50 0.378 vs 0.386; relWIS 0.759 vs 0.766), so the effect is small, but it should be checked by the vintage backtest.

### 2.2 Proposed pipeline (lab)

1. **Diagnostics (no model change):** PIT histograms and interval coverage of the current outputs, conditional on phase, horizon, and size class, from `backtest/results/archive/rows.parquet`-style rows built on as-published data. Costs nothing and tells us which of bias or width dominates.
2. **Scale-free shift and width:** on $z=\log(1+y)$ with per-location scale, fit a phase-specific shift $b_{\text{phase}}$ and width $k_{\text{phase}}$, pinball loss on $z$ (not counts). Leave-one-season-out over 2023-24 and 2024-25 only.
3. **Split conformal on residuals,** rolling origin: scores $E=\max\{\hat q_{lo}-z,\ z-\hat q_{hi}\}$ on the 2 outermost quantile pairs, per horizon and phase, with an exchangeable calibration window of prior seasons. Compare to step 2.
4. **ACI wrapper** on top of the best of 2–3, with $\gamma\in\{0.005, 0.01, 0.02\}$, restarted at the start of each season. Shadow only.
5. **Isotonic PIT map** (Kuleshov) on the EAKF's ensemble, as a second opinion.
6. **EMOS on the EAKF ensemble:** Gaussian on $\log(1+y)$ with ensemble mean and spread, fitted by CRPS on the 2023-24 and 2024-25 seasons only.

Cost on the 4-CPU, 30-minute budget: steps 1–3 are O(53 × 4 × 23 × T) and take seconds. Isotonic and EMOS are O(n log n) and O(n) per fit. The full grid in `calibrate.py` (about 100 × 60 cells, each a pass over all rows) is the most expensive piece and is not needed weekly; it should be refitted offline and only the parameters shipped.

### 2.3 Hub precedent

From the hub `model-metadata/` (opened YAML text, not the models' papers):
- **CMU-TimeSeries_Cal**: post-hoc online quantile calibration (MultiQT; Ding, Gibbs & Tibshirani 2025, cited in the file [unverified]), additive offset per (location, horizon), learning rate 0.018, cold start each season.
- **UM-DeepOutbreak**: ensemble of diffusion and transformer models with post-hoc Neural Conformal Control.
- **JPAT-FluGBM** and **PLANET_NEU-ClaudeScience**: fixed widening about the median (1.25 for hospital, 1.4 for ED), calibrated on 2023-24 to 2025-26 backtests. Note: the second of these also uses one pooled backfill correction.
- **FluCast-SeasonalRidge**: "horizon-specific empirical uncertainty calibration" from mature rolling-origin errors.

Hub evidence on whether calibration helps is not in the metadata. The archive scorer (`backtest/archive_scores.py`) can answer this with coverage by team, and was still being rerun at the time I read the repo. [INFERENCE] Widening and offset methods are common; no metadata file reports a leave-one-season-out test of them.

## 3. Why our post-hoc fix failed

### 3.1 What the fix is

`backtest/calibrate.py`: for each horizon, a grid search over $b\in[0,0.6]$ (step 0.02) and $k\in[0.8,2.5]$ (step 0.05) on log1p-transformed quantiles around the median:
$$\tilde q_\tau = \mathrm{round}\big(\exp(m + b + k(\log(1+q_\tau)-m))-1\big),$$
with $m=\log(1+q_{0.5})$, minimising the average pinball loss against truth **on the count scale**. Stored in `results/calibration.json`.

### 3.2 Fitted parameters and in-sample effect

| h | b | k | pinball ratio vs raw | cov50 raw → cal | cov90 raw → cal |
|---|---|---|---|---|---|
| 0 | 0.10 | 0.85 | 0.909 | 0.377 → 0.372 | 0.750 → 0.724 |
| 1 | 0.00 | 1.05 | 0.999 | 0.403 → 0.413 | 0.772 → 0.792 |
| 2 | 0.00 | 1.00 | 1.000 | 0.408 → 0.408 | 0.793 → 0.793 |
| 3 | 0.00 | 0.90 | 0.997 | 0.423 → 0.385 | 0.808 → 0.766 |

Reading: almost all of the in-sample pinball gain at h=0 is the upward shift $b=0.10$ (about +10% on the $1+y$ scale). The fitted $k<1$ at h=0 and h=3 narrows intervals, which lowers coverage. So the optimiser is not asking for wider intervals: the "intervals too narrow" lever (PROBLEM_BRIEF §7.2) is not supported by these fits. At h=3 the fit lowers coverage (cov90 0.808 → 0.766) and gains almost nothing in loss (ratio 0.997).

Coverage in the raw model is already close to the figure of 0.75 at 90% for h=0, which is well below 0.90. A pinball-optimal shift cannot raise coverage here: the shift moves the median, the tails stay where they were, and a narrower $k$ compensates. The fit therefore trades coverage for pinball loss.

### 3.3 Leave-one-season-out

From `calibration.json` `loso`:

| held-out season | h=0 b, k | h=0 pinball ratio | h=1 ratio | h=2 ratio | h=3 ratio |
|---|---|---|---|---|---|
| 2023-24 | 0.10, 0.90 | 0.885 | 1.007 | 1.007 | 0.991 |
| 2024-25 | 0.06, 0.90 | 0.896 | 0.999 | 1.000 | 1.001 |
| 2025-26 (holdout) | 0.12, 0.80 | **1.044** | 1.045 | 1.004 | 1.000 |

Findings:
- Parameters are unstable across folds: $b$ 0.06–0.12 and $k$ 0.80–0.90 at h=0; $k$ 0.9–1.1 at h=1.
- On the one clean fold (2025-26 held out, fit on 2023-24 and 2024-25), the fix **raises** pinball loss at h=0 by 4% and at h=1 by 4.5%. It only helps at h=0 when the held-out season resembles the training seasons.
- The 2023-24 fold's coverage at h=0 falls from 0.817 to 0.791 (cov90, raw → cal). The fix narrows the bands and moves coverage further from 0.90.
- The h=0 result is the one the fix was supposed to fix most, and it is the most seasonal.

### 3.4 Contamination

`calibration.json` `sources` lists `rows-tune-b0.03-o0.1-f0.03-final.csv` and `rows-test-chosen.csv`. The `test-chosen` summary covers 2024-25 and 2025-26 (`summary-test-chosen.json`). So the **in-sample** parameters in the `params` block were fit on the 2025-26 holdout, which the brief says is used up. Those `params`, and the 0.909 ratio, are therefore optimistic. The `loso` block is the only honest part, and its 2025-26 row is the only out-of-sample evidence I found. Do not use the `params` block for anything live until it is refitted without 2025-26.

### 3.5 Diagnosis of the failure

1. **One global transform across phases.** Model 1's bias flips sign with phase (too low in declines, PROBLEM_BRIEF §5). A single positive $b$ lifts declines, which is right, and lifts rises and peaks, which are already fine or too high. The gain in one phase is paid for in another. Fit by phase or accept that a global fit cannot work.
2. **Wrong loss scale.** The pinball loss is computed on counts. The US national series and the four largest states dominate; the shift that helps them may hurt small states. A log- or rate-scale loss weights all 53 locations (the brief lists the same issue for WIS in §3).
3. **Loss-optimal is not coverage-calibrated.** Pinball loss is minimised by the true quantiles only when they exist; with few seasons it can be lowered by moving the median even when coverage gets worse (see h=0 in 2023-24). Coverage must be a constraint or a second objective, not an afterthought.
4. **Too few independent episodes.** Four seasons (3 with truth, 2 for development) give about 2–3 independent epidemic shapes. Each (b, k) pair is an estimate from about 3 draws. Leave-one-season-out is the right check, and it failed to be stable.
5. **Symmetric log-scale width.** Widening in $\log(1+y)$ around the median is symmetric in log space, so it widens the upper tail in count terms much more than the lower. Declines (truth above the band) need asymmetric tails. This may be part of why $k$ gets pulled below 1.
6. **Rounding and monotonicity.** Rounding to integer counts after the transform, and clipping at zero, can break the 0.01 and 0.99 tails at low counts. Minor, but it adds noise at low counts.
7. **Contamination (§3.4).** The fit used the holdout, so the reported gain was never a real test.

Conclusion: the post-hoc fix was a single-phase bias correction with an in-sample, loss-on-counts fit. The LOSO failure is what one should expect from that design with this data.

## 4. Evidence, failure modes, and cost

### 4.1 Evidence by method

- EMOS: strong in weather with large ensembles (Gneiting et al. 2005, search-verified). Applied to flu, no evidence found in the hub metadata. Ensemble size 300 is ample; the EAKF ensemble may be too concentrated (its coverage is under) so the spread-skill term may be the key test.
- Isotonic PIT: Kuleshov et al. (2018; search-verified) report gains on time series and RL tasks, with a sizeable calibration set. Our sample is small; expect instability.
- CQR: finite-sample coverage, shorter intervals than split conformal (Romano et al. 2019; search-verified). Applies cleanly to model 2's 23-quantile output.
- ACI: coverage over time with drift (Gibbs & Candès 2021; search-verified). The natural wrapper for a weekly forecaster. Its step size is the main tuning parameter, and with about 1 truth per location per week, adaptation is slow.
- Conformal PID: better coverage than the CDC ensemble on COVID deaths (Angelopoulos et al., arXiv:2307.16895; search-verified, numbers not read).
- Hub teams: as in §2.3.

### 4.2 Failure modes to expect

- Exchangeability violated by seasonality and reporting regime changes: split conformal can be valid marginally but wrong in phase.
- Few seasons: any calibration with more than 2–3 parameters per horizon will overfit; LOSO must be the selection rule.
- Revisions: calibration fitted on mature (finalised) truth will be too narrow for the nowcast, as the h=0 under-coverage suggests. Use the as-published truth from `time-series.csv` for scoring.
- Counts: large-count bias dominates raw scores; a scale-free loss is needed, or the national series will drive the fit.
- Mis-specified phase boundaries: near-peak assignment is a choice made after seeing the data; fix it in advance.

### 4.3 Cost on the 4-CPU, 30-minute budget

Weekly: applying stored (b, k) or conformal offsets is negligible. Refit: steps 1–3 seconds; ACI update per week is O(53 × 4 × 23); isotonic and EMOS seconds. The grid search in `calibrate.py` (about 100×60 cells × rows) is minutes and should stay offline.

## 5. Ranked experiments

Pre-registration rules for all of them (write the rules before running): no look-ahead (as-published data only; truth known only after the scored date); development on 2023-24 and 2024-25, leave-one-season-out; the 2025-26 holdout is not used for any choice; primary metric is pinball loss on log1p counts, with per-location scale; coverage at 50% and 90% is a constraint (|cov − nominal| ≤ 0.05 averaged over seasons); acceptance requires gains in both held-out seasons, not on average. Shadow mode for Track B; Track A only with strong evidence.

1. **[Track A, free] PIT and coverage diagnostics** of current model 1 and model 2 output, by phase, horizon, and size class, on as-published data. Decision: if bias dominates within phase, go to 2; if width dominates, go to 3. Pre-registered thresholds: a phase-bin coverage gap ≥ 0.10 counts as a finding.

2. **[Track A] Scale-free, phase-specific shift and width** (step 2 of §2.2). Null: the current global (b, k) on count scale. Win: lower pinball loss on log1p counts in both LOSO folds (2023-24 and 2024-25 as held-out) with no coverage constraint violation. Refit without 2025-26 (see §3.4) before any test.

3. **[Track A] Split conformal correction of model 2's outermost quantile pairs** (CQR, per horizon, with exchangeable calibration window of prior seasons). Null: the uncorrected GBQR quantiles. Win: cov90 closer to 0.90 in both folds without widening the 50% band beyond 0.55. Model 2 is not yet designated, so the test is cheap and the risk is low.

4. **[Track B, shadow] ACI wrapper** over the best of 2–3, with γ ∈ {0.005, 0.01, 0.02}, reset each season. Pre-registered: γ fixed in advance at 0.01; success if running cov90 is within 0.03 of 0.90 after 20 weeks. Run live in shadow from the next week.

5. **[Track B, shadow] PID conformal** (Angelopoulos et al., arXiv:2307.16895) on the EAKF ensemble quantiles, with the derivative term included. Compare to experiment 4 on the same weeks.

6. **[Track B] EMOS on the EAKF ensemble** (log1p, Gaussian, CRPS fit on 2023-24 and 2024-25). Null: the raw EAKF quantiles. Test: relWIS on the held-out season.

7. **[Track B] Isotonic PIT map** on the EAKF ensemble, with cross-calibration folds by season. Expected to be unstable; included to measure the gap.

8. **[Track B] Beta-transformed pool of EAKF and GBQR** (Ranjan & Gneiting 2010; Gneiting & Ranjan 2013), fitted by log score on LOSO. Cross-reference Family 08 for the combiner; here only the calibration step.

9. **[Track B] Fixed widening by horizon** (the 1.25 / 1.4 factor used by the hub models in §2.3) as a naive baseline. Its value is as a reference, not as a candidate.

### Shadow-mode notes

- Experiments 4–6 need forecasts saved with the as-published data at each reference date and scored when truth exists. Keep the raw quantiles as a reference model so calibration gains are measured against it.
- Scoring: WIS on counts (as the CDC does), plus coverage at 50% and 90%, plus the scale-free pinball on log1p counts. Report by phase.

## 6. References

Opened or search-verified (abstracts read, full text not read):
- Gneiting, T., Raftery, A.E., Westveld, A.H., Goldman, T. (2005). Calibrated probabilistic forecasting using ensemble model output statistics and minimum CRPS estimation. Monthly Weather Review 133(5):1098–1118. doi:10.1175/MWR2904.1.
- Kuleshov, V., Fenner, N., Ermon, S. (2018). Accurate uncertainties for deep learning using calibrated regression. ICML, PMLR 80. arXiv:1807.00263.
- Romano, Y., Patterson, E., Candès, E.J. (2019). Conformalized quantile regression. NeurIPS. arXiv:1905.03222.
- Gibbs, I., Candès, E.J. (2021). Adaptive conformal inference under distribution shift. NeurIPS. arXiv:2106.00170.
- Angelopoulos, A.N., Barber, R.F., Bates, S. (2024). Online conformal prediction with decaying step sizes. arXiv:2402.01139.
- Angelopoulos, A.N., Candès, E.J., Tibshirani, R.J. (2023). Conformal PID control for time series prediction. arXiv:2307.16895.
- Li, R., Rodríguez, A. (2024). Neural conformal control for time series forecasting. arXiv:2412.18144.
- Ranjan, R., Gneiting, T. (2010). Combining probability forecasts. JRSS-B 72(1):71–91. doi:10.1111/j.1467-9868.2009.00726.x [the DOI is from memory; the journal and pages come from the OUP page snippet].
- Gneiting, T., Ranjan, R. (2013). Combining predictive distributions. Electronic Journal of Statistics 7. doi:10.1214/13-ejs823.
- Baran, S., Lerch, S. (2018). Combining predictive distributions for statistical post-processing of ensemble forecasts. Int. J. Forecasting. arXiv:1607.08096.
- Junk, C., Delle Monache, L., Alessandrini, S. (2015). Analog-based ensemble model output statistics. MWR 143(7).

From memory, not checked: Gneiting, T., Balabdaoui, F., Raftery, A.E. (2007). Probabilistic forecasts, calibration and sharpness. JRSS-B 69(2):243–268 [unverified]; Taillardat, M. et al. (2016). Calibrated ensemble forecasts using quantile regression forests and ensemble model output statistics. MWR [unverified]; Bracher, J. et al. (2021). Evaluating epidemic forecasts in an interval format (WIS). PLOS Computational Biology [unverified]; Ding, Gibbs & Tibshirani (2025), MultiQT [unverified; named only in CMU-TimeSeries_Cal.yml].

Repo and hub files opened: `docs/research/PROBLEM_BRIEF.md`, `docs/research/HANDOFF.md`, `backtest/calibrate.py`, `backtest/results/calibration.json`, `backtest/results/honest/summary-test-chosen.json`, `backtest/results/honest/summary-test-chosen-edvintage.json`, `backtest/results/model2/summary-holdout-2025-26.json`, `backtest/METHODS.md` §4, `docs/archive/backtest-findings.md` §1, §4, and the hub `model-metadata/` lines cited in §2.3.

## 7. Top five recommendations (for the main agent)

1. Run the PIT and coverage-by-phase diagnostic now (Track A, free). It decides between bias and width fixes.
2. Refit `calibrate.py` without 2025-26 and on a log or rate scale with phase conditioning; report only LOSO on 2023-24 and 2024-25. Do not ship the current `params`.
3. Test split CQR on model 2's outer quantiles (Track A candidate, low risk).
4. Wire ACI (γ=0.01) and PID conformal as shadow models on EAKF quantiles.
5. Treat the current fix as a failed experiment: do not extend it; record the LOSO table in the shadow protocol as the baseline.
