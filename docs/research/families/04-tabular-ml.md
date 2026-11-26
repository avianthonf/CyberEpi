# Family 04: tabular ML (GBQR, QRF, NGBoost, GAMLSS), pooling, target transforms, features

Scope: quantile/distributional tabular learners for weekly flu admissions; pooling across locations; target transforms; feature design. Diagnosis of why model 2 (CyberEpi-GBQR) runs low in rises. Read with `docs/research/PROBLEM_BRIEF.md` and `backtest/MODEL2_PROTOCOL.md`.

Evidence labels: **[code]** = read in `backtest/gbqr.py` / `run_vintage.py`; **[res]** = read in `backtest/results/`; **[hub]** = read in hub `model-metadata/`; **[INFERENCE]** = not observed.

---

## 1. Theory

### 1.1 Quantile regression (linear)
Koenker and Bassett (1978) define regression quantiles as minimisers of the check loss, sum over t of rho_tau(y_t − x_t'β), with rho_tau(u) = u(tau − 1{u<0}). The fitted conditional quantile is linear in x, so it extrapolates linearly outside the training range. Uncertainty comes from the set of quantile fits, one per level; they can cross unless constrained [Koenker & Bassett 1978, *Econometrica* 46(1):33–50, doi:10.2307/1913643, opened via search summary].

### 1.2 Gradient-boosted quantile regression (LightGBM, GBQR)
Gradient boosting with the pinball loss. For LightGBM's `quantile` objective, after each tree is grown, leaf values are replaced by the alpha-quantile of the residuals in the leaf ("leaf renewal") [LightGBM source `src/objective/regression_objective.hpp`, opened via search summary]. Consequences:
- The model is piecewise constant in x. Predictions cannot exceed the range of targets seen in a leaf. A rise larger than any seen in training is predicted at most as the largest training leaf value.
- The initial score is an unconditional quantile over all training rows. With few extreme examples, boosting must spend trees to move away from it. `min_data_in_leaf` (50 here) prevents leaves that isolate rare rises, so rare rising states get averaged into milder ones.
- Each (horizon, quantile) is a separate model; quantile crossing is removed by sorting [code, lines 148–152]. This is a post-hoc fix; it does not make the quantile functions coherent.

### 1.3 Quantile regression forests (QRF)
Meinshausen (2006) keeps all training responses in each leaf and estimates the conditional CDF as a weighted empirical CDF over the training responses; quantiles are obtained by inverting it [Meinshausen 2006, *JMLR* 7:983–999, opened via search summary]. Consequence: predictive distributions are supported on the training responses. They cannot extrapolate beyond the largest observed change, which is exactly the regime that matters in a rise. Predictions are also averages over leaves, so they shrink toward the typical response of similar cases.

### 1.4 NGBoost
Duan et al. (2020) boost the parameters of a chosen parametric distribution (for example Normal, Student-t, Negative Binomial) using natural gradients of a proper scoring rule [Duan et al., ICML 2020, PMLR v119/duan20a, arXiv:1910.03225, opened via search summary]. Uncertainty is the fitted distribution. The output is a full distribution from a parametric family, so it extrapolates along the family's parametrisation, but a wrong family misstates tails.

### 1.5 GAMLSS
Rigby and Stasinopoulos (2005) model every parameter of a chosen distribution (location, scale, skew, kurtosis) as an additive function of covariates, fitted by penalised likelihood [Rigby & Stasinopoulos 2005, *JRSS-C* 54(3):507–554, doi:10.1111/j.1467-9876.2005.00510.x, opened via search summary]. Linear or spline location terms extrapolate; skew distributions can model asymmetric rises. Cost is low, and it is the most interpretable option of the four.

### 1.6 Why uncertainty is wrong in this problem
All four produce the same kind of uncertainty: a conditional distribution of the future value given features, learned from as-published data. For counts with reporting lags, the learned distribution is only as good as the match between training labels and what will be scored (see §4 on revisions).

---

## 2. Application to our models

### 2.1 What model 2 does [code]
- Panel: `build_panel` takes one as-of snapshot (`pick_vintage`: latest version published by R with newest week ≤ R−7) and uses it for every training row and every feature [code, lines 85–88; run_vintage.py lines 78–85]. So at origin R, **all training labels and features come from a single snapshot**.
- Features: lr = log1p(rate per 100k), d1..d4 (log-rate changes), ED log share (final values in backtest), its 1–2 week changes, sin/cos day of year [code, lines 105–114].
- Target: y_k = lr(t+k) − lr(t), k = h+1+gap, rows kept where the label exists [code, lines 115–116, 139].
- Fit: LightGBM quantile, num_leaves 15 or 7, n_estimators 300 or 150, lr 0.05, min_data_in_leaf 50, n_jobs=1, per (k, quantile) [code, lines 137–145].
- Prediction: anchor at the newest observed week (gap ≤ 2), add predicted change to lr, back-transform with expm1 and population, round, clip at zero [code, lines 148–163].
- Dev results (summary files): 2023-24 relWIS vs baseline 0.741 (L7/T300), 0.759 (L15/T300), 0.756 (L7/T150); coverage of 50% interval 0.39–0.43, 90% interval 0.75–0.81 [res/model2/summary-dev-*.json]. Holdout 2025-26 cov50 0.44, cov90 0.80 [res/model2/summary-holdout-2025-26.json].

### 2.2 Phase evidence across the archive [res]
`backtest/results/archive/summary.csv` gives `below_median` = share of truths below the model median (`archive_scores.py` line 97). In rising weeks, a low `below_median` means the model runs low.

| Model (season, phase = rising) | below_median | Note |
|---|---|---|
| FluSight-baseline (2023-24 / 24-25 / 25-26) | 0.17 / 0.09 / 0.05 | persistence cannot rise |
| FluSight-ensemble (2023-24 / 24-25 / 25-26) | 0.27 / 0.16 / 0.12 | benchmark rise floor |
| CMU-TimeSeries (2023-24 / 24-25 / 25-26) | 0.22 / 0.22 / 0.22 | pooled quantile/regression |
| CU-ARNB_Net (2025-26) | 0.23 | residual NN |


Caveats: `phase` is defined in `archive_scores.phases()` (lines 101–115) with the peak taken as the idxmax of truth observed so far. Because 2026-27 is still rising, its labels are artefacts and are excluded here. Only 2023-24 to 2025-26 are used. `phase` conditions on the ex-post peak, so it is a diagnostic only, never a selection rule. The ensemble's own rise values (0.27 / 0.16 / 0.12) give the floor against which model 2's excess low bias should be read.

### 2.3 Hub evidence on pooled-LightGBM teams [hub]
- DMAPRIME-QR: LightGBM quantile, pooled, one model per horizon and quantile, log-change target [hub model-metadata/DMAPRIME-QR.yml, lines 15–16].
- FluTurists-gbqr: LightGBM pinball on log1p rate, lags, growth, lag-52, Fourier seasonality, lagged ED share; uses a revision-ratio correction on the two newest weeks [hub model-metadata/FluTurists-gbqr.yml, lines 18–24].
- DXRSI-T0: median of three components, one of which is pooled LightGBM with size-tercile persistence quantiles [hub DXRSI-T0.yml, line 14].
- CU-STS_base / CU-STS_Residual: pooled LightGBM on per-capita log growth, refit weekly [hub].
- DMAPRIME-HYB: pooled CNN-LSTM on log1p change from the last observed week, per-horizon calibration [hub].

Model 2 is a close analogue of DMAPRIME-QR and FluTurists-gbqr. Their 2026-27 phase values are not used as evidence (see caveat in §2.2).

---

## 3. Diagnosis: why model 2 runs low in rises

Ranked by my confidence. None has been tested; each has a proposed test in §6.

### H1 (highest): train–serve mismatch from one as-of snapshot, revision-induced [code + INFERENCE]
- At origin R, every training label (lr(t+k)) and every feature (lr(t), d1..d4) is read from one snapshot. In that snapshot, the most recent weeks are first reports, typically ~89–96% of their final values (backtest facts in `PROBLEM_BRIEF.md` §2 and `MODEL2_PROTOCOL.md` §Result).
- In training, the labels with t+k near R−7 are immature. The model learns the change from an immature edge to an immature target.
- At serving time the feature at R−7 is immature, but the scored truth is the mature value. Training never shows a mature target paired with an immature edge.
- In a rise, reporting incompleteness at the edge is largest and growth is steepest. The learned mapping therefore sees smaller changes than the scored truth. This predicts exactly the observed sign: truth above median, growing with horizon (protocol: up to 71% above median at 3 weeks).
- Magnitude [INFERENCE]: a 10% edge deficit alone is a log-change of about 0.1, which at high rates is a large share of the predicted rise.
- Code check [code, gbqr.py lines 85–88, 105–116]: labels `y{k}` are `lr.shift(-k)` inside the same single snapshot, so labels near the edge come from preliminary values. Features and labels share one vintage, which is the mechanism.

### H2: tree damping in the tail (leaf averaging and the unconditional init) [code + INFERENCE]
- Rising, high-growth rows are rare among ~50k pooled rows, dominated by off-season near-zero changes. With `min_data_in_leaf=50` and an unconditional initial quantile, extreme-growth leaves are small and get averaged with milder ones. Boosting at lr 0.05 with 150–300 trees may not fully reach the tail.
- Evidence: dev runs with more leaves (L15) gave a similar bias, so capacity is not the only constraint. Mild support only.

### H3: pooled size and rate mix [code + INFERENCE]
- Features are rates, so national and large states, which peak earlier and differently, share trees with small states whose counts are noisy. A rise in a large state is averaged with a noisy small-state rise. No population-tier or national-leading feature exists.

### H4: calendar seasonality and early seasons [code + INFERENCE]
- sin/cos of day-of-year associate "November" with the typical early rise and with timing of the first peak. A season that starts earlier or later than training (2026-27 is early per the brief) gets calendar-driven predictions. Sign of the effect is ambiguous.
- Early dev origins (2023-24) have little prior data; the early-origin bias may dominate the dev number [INFERENCE, check training row counts per origin].

### H5 (low): live ED mismatch [code]
- Backtest uses final ED (`ED_SOURCE = final`); live uses the latest published file, whose newest weeks are preliminary. Small effect expected; the protocol shows 0.584 → 0.622 for as-published ED.

What the evidence does **not** support: that the trees are "wrong about rises" in general. Every team in the archive, including the ensemble, runs low in rising weeks (table in §2.2), so part of the bias is the nature of rising-phase forecasting from as-published data. The model-2-specific part is probably H1 plus H2.

---

## 4. Target transforms and pooling

- **log1p(rate) change** (model 2): normalises by population, makes changes additive, and back-transforms to a non-negative count. Quantile equivariance holds through monotone transforms, so back-transformed quantiles are valid quantiles of the count. Weakness: small-rate locations get large relative change noise.
- **Fourth-root** (FluTurists-ensemble's AR component [hub]): variance-stabilising, closer to linear in growth for large counts.
- **Per-capita log growth** (CU-STS_base [hub]): same as log1p at low rates.
- **Pooling**: full pooling (model 2, DMAPRIME-QR) gives data for rises but mixes populations. Size-tercile pooling (DXRSI-T0 persistence component [hub]) keeps the rise statistics local to comparable locations. Hierarchical/partial pooling belongs to family 11.
- Expected effect on H1: none of these fixes the snapshot maturity; they only change the scale. Fix H1 first, then compare transforms.

---

## 5. Failure modes

1. Immature edge in training labels (H1), which looks like a model bias but is a data-version mismatch.
2. Tree extrapolation limit: a rise beyond training range is clipped (QRF, GBQR).
3. Quantile crossing and non-monotone medians across horizons when models are fitted separately.
4. Parametric tail misspecification (NGBoost Normal on log-change; GAMLSS wrong skew).
5. Learned timing from one season (calendar features) or a single peak call (protocol: one national call drives the holdout).
6. Overfit tuning on two dev seasons; the holdout is spent.
7. Calibration: model 2 dev cov50 ≈ 0.41 at target 0.5 — tails too narrow even where the median is biased.

---

## 6. Experiments (ranked)

All tests: forecasts at origin R use only data published by R (as-of snapshot for all inputs). Dev seasons 2023-24 and 2024-25; a method is accepted only if it wins on both dev seasons separately. Leave-one-season-out is used only as a robustness check, and forecasts never train on a future season. Pre-register primary metric (dev mean relWIS vs FluSight-baseline and vs model 2) and the rising-phase target (below_median between 0.35 and 0.65 in rising weeks, from archive definition). Holdout 2025-26 is spent; use 2026-27 shadow for any new candidate.

**E1 (Track A candidate; highest priority). Maturity-corrected edge.**
- Variant a: drop training labels whose target week is within m weeks of R−7 (m = 2, 3, 4).
- Variant b: correct the last 1–2 weeks of the snapshot by backfill ratios estimated from *older* as-of snapshots (ratio of value at age a to final, by lag a). Apply the same correction to training rows and serving rows.
- Compare against current model 2 on dev. Pass criterion: rising below_median moves toward 0.5 on both dev seasons and mean relWIS does not worsen.
- Cost: negligible (no extra fits beyond the ratio estimation).

**E2 (Track B, diagnostic). Linear pooled quantile regression on the same features** (Koenker–Bassett). Tests H2: if the linear model's rising bias is smaller than GBQR's, trees are damping.

**E3 (Track A/B). Tree regularisation and constraints.** min_data_in_leaf ∈ {10, 20, 50}; monotone constraints on d1..d4 (increasing); n_estimators ∈ {150, 300, 600}; num_leaves ∈ {7, 15}. Pre-register: choose by dev rising-phase bias and relWIS jointly. Cost: 92 fits per origin, plausibly within the weekly budget [INFERENCE: measure before committing].

**E4 (Track B). Feature changes.** (a) remove sin/cos; (b) season-onset timing (weeks since the first week above a threshold this season) in place of calendar; (c) national-rise feature for state rows; (d) population tier. Test for H3/H4.

**E5 (Track B). Distributional learners, shadow only.** QRF (same features), NGBoost with Negative Binomial or Student-t on log-change, GAMLSS with location linear in d1 and skew-t. Report extrapolation cases separately (rises above training max).

**E6 (Track B). Target transform comparison.** log1p change vs fourth-root vs per-capita log growth, after E1 is applied.

**E7 (Track A candidate only if E1 wins). Revised-data check.** Re-run dev with the holdout-style ED-as-published robustness; no new data.

---

## 7. Cost on a 4-CPU, 30-minute weekly budget [INFERENCE unless noted]
- GBQR as now: 92 LightGBM fits per origin, single-threaded, about 10k–50k rows: likely seconds to a minute per origin. Measure before relying on it.
- QRF: a forest per origin plus leaf lookups; similar order, more memory.
- NGBoost: one distribution boosting run per horizon; similar or slower per fit.
- GAMLSS: cheap per fit; diagnostics slower.
- E1 adds only the backfill-ratio step (table lookup).
- Backtests across all origins: minutes to tens of minutes offline; acceptable.

---

## 8. References (opened via web search summaries or repository files)
- Koenker, R. & Bassett, G. (1978). Regression quantiles. *Econometrica* 46(1):33–50. doi:10.2307/1913643.
- Meinshausen, N. (2006). Quantile regression forests. *JMLR* 7:983–999. https://www.jmlr.org/papers/v7/meinshausen06a.html
- Duan, T. et al. (2020). NGBoost: natural gradient boosting for probabilistic prediction. *ICML* (PMLR 119). arXiv:1910.03225.
- Rigby, R. A. & Stasinopoulos, D. M. (2005). Generalized additive models for location, scale and shape. *JRSS-C* 54(3):507–554. doi:10.1111/j.1467-9876.2005.00510.x.
- LightGBM quantile objective and leaf renewal: `src/objective/regression_objective.hpp` (github.com/microsoft/LightGBM); parameter docs lightgbm.readthedocs.io.
- Ke, G. et al. (2017). LightGBM: a highly efficient gradient boosting decision tree. *NeurIPS*. **[unverified: not opened; cited for the library only]**
- Hub: `model-metadata/DMAPRIME-QR.yml`, `FluTurists-gbqr.yml`, `DXRSI-T0.yml`, `CU-STS_base.yml`, `CU-STS_Residual.yml`, `DMAPRIME-HYB.yml`, `CMU-TimeSeries.yml`, `CU-ARNB_Net.yml` (opened locally).
- Repo: `backtest/gbqr.py`, `backtest/run_vintage.py`, `backtest/archive_scores.py`, `backtest/MODEL2_PROTOCOL.md`, `backtest/results/model2/*.json`, `backtest/results/archive/summary.csv`.

---

## 9. Top recommendations
1. **E1 (Track A candidate):** fix the revision mismatch in model 2 (maturity-matched labels and backfill-corrected edge), tested on both dev seasons first. This is the most likely cause of the rise bias.
2. **E2:** add a linear pooled quantile regression on the same features to test whether trees damp rises (Track B diagnostic).
3. **E3:** tune min_data_in_leaf and monotone constraints, selected on dev rising-phase bias jointly with relWIS.
4. **E5 (Track B shadow):** NGBoost with Negative Binomial and GAMLSS skew-t as shadow models; QRF only as a bounded-support comparison.
5. **Do not submit** any calendar or ED-feature change without E1 done. Read the ED feature as final in backtest (look-ahead relative to live), so E7 must be run before any ED claim.
