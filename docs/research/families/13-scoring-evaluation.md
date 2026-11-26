# Family 13: Scoring and evaluation

Scope: proper scores, WIS decomposition, log-scale WIS, CDC-style evaluation, power for relWIS differences, and an audit of `docs/research/SHADOW_PROTOCOL.md` and `backtest/score_live.py`. The protocol is not edited here; fixes are proposals.

Sources opened: `backtest/wis.py`, `backtest/archive_scores.py`, `backtest/score_live.py`, `backtest/results/archive/{summary.csv,pairwise.csv,rows.parquet}`, `docs/research/{HANDOFF,PROBLEM_BRIEF,SHADOW_PROTOCOL}.md`, hub `target-data/target-hospital-admissions.csv` and `model-output/*`. Scratch analyses are in `/tmp/r13/` (not part of the repo).

## 1. Theory

**Proper scores.** A score S(F, y) is proper if E_G[S(F, Y)] is minimised at F = G, and strictly proper if the minimiser is unique (Gneiting & Raftery 2007, JASA). Proper scores reward honest quantiles and intervals; improper ones can be gamed by widening or narrowing intervals.

**WIS.** For a predictive median m and K central intervals with levels α_k, with lower/upper bounds l_k, u_k:

IS_α = (u − l) + (2/α)·[(l − y)·1{y<l} + (y − u)·1{y>u}]

WIS = (1/(K+½)) · [½·|y − m| + Σ_k (α_k/2)·IS_{α_k}]

(Bracher et al. 2021, PLOS Comp Biol.) With the 23 quantile levels in this repo, K = 11 and K+½ = 11.5. WIS is the average of the 23 pinball losses divided by 11.5 (`archive_scores.py` line 92 uses this identity). It is proper and approximates CRPS as the quantile grid gets finer.

**Decomposition** (Bracher et al. 2021). WIS·(K+½) = Sharpness + Overprediction + Underprediction, where

- Sharpness = Σ_k (α_k/2)(u_k − l_k)
- Overprediction = Σ_k (l_k − y)₊ + ½(m − y)₊
- Underprediction = Σ_k (y − u_k)₊ + ½(y − m)₊

I checked this identity numerically in scratch code (`/tmp/r13/analysis.py`) against `backtest/wis.py` for all selected models; it holds to 1e-9.

**Log-scale WIS.** Quantiles map monotonically under log1p, so a log-scale WIS is the same formula applied to log1p(q) and log1p(y). It penalises relative error and is less dominated by the largest locations and peaks.

**Uncertainty.** Week-to-week differences in WIS are serially correlated (epidemic phases). The DM test is a t-type test on the mean loss differential with a HAC variance (Diebold & Mariano 1995, JBES). Its small-sample reliability depends on T and the HAC choice. The protocol uses Newey–West with L=3 and t(T−1) (SHADOW_PROTOCOL §3). Newey–West and the stationary bootstrap (Politis & Romano 1994) are the standard HAC and resampling tools, but I did not open these sources (see Unverified).

**CDC-style evaluation.** The hub's pairwise relative WIS (`archive_scores.py` lines 165–187) takes, for each model, the geometric mean over opponents of the mean-WIS ratio on common rows, then divides by the FluSight-baseline. Taking the geometric mean removes the arbitrary choice of opponent but makes the score non-additive across seasons.

## 2. Application to this problem

- WIS definition in the repo matches the hub. The archive scorer and the live scorer both compute it from the 23 quantiles, with the same pinball identity.
- Live scoring (`score_live.py`) computes relWIS as the ratio of mean WIS on identical rows, against CyberEpi-EAKF and FluSight-ensemble.
- The protocol's per-week statistic d_r = log(Σ WIS_m / Σ WIS_R), with DM/HAC and bootstrap on d_r, is pre-registered in SHADOW_PROTOCOL §3. Weekly sums are dominated by the US: in 2025-26 the US is 112 of 5,936 ensemble rows (1.9%) but 45.6% of the ensemble's raw WIS. That weighting is the protocol's choice; it should be checked by a sensitivity analysis (see Track A).

**Decomposition, selected hub models (count scale, mean WIS per row, 2025-26; from `/tmp/r13/analysis.py`):**

| model | WIS | sharpness | over | under |
|---|---|---|---|---|
| FluSight-ensemble | 115.2 | 31.0 | 26.3 | 57.9 |
| FluSight-baseline | 174.9 | 24.9 | 52.8 | 97.2 |
| OHT_JHU-nbxd | 99.1 | 37.9 | 39.0 | 22.3 |
| CMU-TimeSeries | 102.5 | 38.1 | 11.7 | 52.8 |
| UVAFluX-Ensemble | 202.5 | 29.9 | 114.2 | 58.4 |

In 2024-25 most models' WIS is dominated by underprediction (truth above the upper bound during rises), e.g. FluSight-ensemble 176.7 total, 129.8 under. [INFERENCE] Forecasts were too low in early-season rises and too high after peaks, a pattern that would be consistent with a lag bias. This needs a phase-stratified check before it is used.

**Log-scale vs count-scale relWIS vs FluSight-ensemble** (identical rows, selected models):

| season | model | relWIS count | relWIS log |
|---|---|---|---|
| 2025-26 | NAU-FourCAT | 0.919 | 1.202 |
| 2025-26 | CEPH-Rtrend_fluH | 1.001 | 1.322 |
| 2025-26 | LosAlamos_NAU-CModel_Flu | 1.689 | 1.953 |
| 2024-25 | UVAFluX-Ensemble | 1.196 | 1.460 |
| 2023-24 | LosAlamos_NAU-CModel_Flu | 3.840 | 2.117 |

Several rankings flip sign relative to 1.0 between the two scales (e.g. NAU-FourCAT, 0.92 count vs 1.20 log). The scale choice is therefore not a cosmetic detail; it must be pre-registered as a co-primary or sensitivity analysis.

**Pairwise and phase.** `pairwise.csv` gives FluSight-ensemble 0.651 (2025-26) and 0.667 (2024-25) relative to FluSight-baseline = 1.0. The 2026-27 season is provisional (phases in `archive_scores.py` are set to "provisional" for it).

## 3. Evidence

- Bracher et al. 2021, PLOS Comp Biol, "Evaluating epidemic forecasts in an interval format" (opened via search summary, https://journals.plos.org/ploscompbiol/article?id=10.1371%2Fjournal.pcbi.1008618). WIS definition, decomposition, and CRPS approximation.
- Gneiting & Raftery 2007, JASA 102(477), "Strictly proper scoring rules, prediction, and estimation" (opened via search summary, https://doi.org/10.1198/016214506000001437). Propriety and the interval score.
- Diebold & Mariano 1995, JBES 13(3), "Comparing predictive accuracy" (opened via search summary, https://www.tandfonline.com/doi/abs/10.1080/07350015.1995.10524599). DM framework.
- scoringutils WIS reference (opened, https://epiforecasts.io/scoringutils/reference/wis.html). Confirms the WIS weights and the median-twice convention question.
- FluSight team usage in hub `model-metadata/`: not inspected in this pass, so I make no claim about which teams use which scores.

## 4. Failure modes

1. **US domination.** Weekly sums weight the US by raw WIS. A model can win on the US while losing on most states (protocol §3 pre-registers this; sensitivity not planned).
2. **Scale sensitivity.** Count and log relWIS disagree in sign for several models (table above).
3. **Small T and HAC.** With T ≈ 20 weeks and L=3, the HAC variance is unstable; t(T−1) is not a reliable reference when d_r is autocorrelated.
4. **Multiple tests.** Holm over 2K p-values assumes independence; the tests share rows and are positively correlated, so Holm is conservative (fine for a gate, costly for power).
5. **Truth vintage.** Truth values are revised. A verdict on one vintage may not hold on another; the protocol records a commit but the scorer does not record the truth snapshot.
6. **Coverage targets.** 50% in [0.40, 0.60] and 95% in [0.90, 0.98] are ranges, not proper scores. They are reasonable checks but are not a substitute for WIS.
7. **Phase labels.** Phases are defined from final truth, so they are unavailable in real time. They are only usable for retrospective stratification.

## 5. Cost

WIS and decomposition on hub quantiles for 15 models: ~20 s on this machine (single process). Full archive regeneration via `archive_scores.py` with 4 workers: about 2 minutes (previous run). Live scoring is trivial in cost; the weekly 30-minute budget is not a constraint for scoring.

## 6. Power analysis (relWIS differences)

Per-week d_r = log(Σ WIS_lab / Σ WIS_FluSight-ensemble) over identical rows (horizons 0–3), from `backtest/results/archive/rows.parquet` (`/tmp/r13/power.py`). Lab set: 8 models × 2 completed seasons (2024-25, 2025-26) = 15 season rows. FluSight-baseline is excluded: it is a reference, not a lab model. An earlier pass included it and inflated σ and ρ.

- Pooled within-season SD of d_r: σ ≈ 0.239 (RMS over 15 rows). Worst lab row: CU-ensemble 2025-26, SD 0.432.
- Lag-1 autocorrelation of within-season residuals: ρ₁ ≈ 0.54 (range −0.03 to 0.76). Lag-2: ρ₂ ≈ 0.25 (range −0.27 to 0.54). AR(1) with ρ₁=0.54 gives inflation (1+ρ)/(1−ρ) ≈ 3.36; truncated at lag 2, 1+2(ρ₁+ρ₂) ≈ 2.57. I report both.
- Weeks T for 80% power, two-sided α=0.05, effect = relWIS reduction x (δ = −ln(1−x)), AR-inflated (factor 3.36):

| effect | T (pooled σ=0.239) | T (worst row σ=0.432) | T if iid |
|---|---|---|---|
| 5% | ≈ 573 | ≈ 1,870 | ≈ 171 |
| 10% | ≈ 136 | ≈ 444 | ≈ 40 |
| 20% | ≈ 30 | ≈ 99 | ≈ 9 |

With the protocol's minimum T = 20 weeks, the minimal detectable effect is ≈ 21–24% (pooled σ; inflation 2.57 to 3.36). [INFERENCE] Two seasons and eight pairs chosen as top models make this optimistic for weaker pairs, and a fresh season may have larger σ. The conclusion holds: 20 weeks cannot resolve 5–10% differences, and even iid needs 40 weeks for 10%.

## 7. Audit of SHADOW_PROTOCOL.md and score_live.py

**score_live.py**

- Computes WIS, coverage and relWIS (mean WIS ratio on identical rows). It does **not** implement the protocol's per-week d_r, DM/HAC, the moving-block bootstrap, Holm correction, the horizon-level relWIS > 1.10 check, or the peak-passed condition. These are required by SHADOW_PROTOCOL §3–5 but are absent from the scorer, so graduation cannot be decided from its output.
- relWIS is a ratio of means over rows, not a mean of per-week log ratios. This is not the protocol's statistic.
- Truth is loaded from the hub's latest vintage; the vintage is not recorded in outputs.
- Horizon filter (0–3) and quantile pivot are correct; coverage indices (q[6], q[16] for 50%; q[1], q[21] for 95%) match LEVELS.

**SHADOW_PROTOCOL.md**

- §3 d_r weights by WIS sums; no sensitivity analysis.
- DM with L=3 and t(T−1) at T ≈ 20 is fragile (see §4).
- The gate requires relWIS < 1 vs both references and Holm p < 0.05 for both, which is very demanding given §6 power.
- No log-scale check, no per-location check, no truth-vintage requirement.

## 8. Ranked experiments

Track A (no 2025-26 holdout; pre-registered; leave-one-season-out over 2023-24, 2024-25, 2025-26):

1. **Scale sensitivity.** Pre-register log-scale WIS as a co-primary or sensitivity analysis; report count and log relWIS for all candidates. Design: archive rows, leave-one-season-out. Pass rule: sign agreement across seasons. (Track A.)
2. **Per-location pooled log-relWIS.** Sensitivity to the US-dominated d_r: mean over locations of per-location log ratios, with block bootstrap. (Track A.)
3. **HAC/small-sample check.** Compare DM with NW L=3, DM with Andrews bandwidth, and stationary bootstrap on archived d_r series; report size under the null using permuted/sign-flipped differences. (Track A.)
4. **Power curve.** Simulate weeks needed for 5/10/20% effects with the empirical d_r covariance (block bootstrap), and set the minimum T in the protocol accordingly. (Track A.)
5. **Shadow-mode gate implementation.** Extend `score_live.py` to emit per-week d_r, DM/HAC p, bootstrap CI, Holm-adjusted p, horizon relWIS, and the truth vintage; test on archived 2025-26 rows in replay mode, no look-ahead. (Track B: implementation and shadow run.)

## 9. Unverified items

- Politis & Romano 1994, stationary bootstrap — [unverified: not opened; cited from memory].
- Newey & West 1987, HAC covariance — [unverified: not opened; cited from memory].
- Holm 1979, sequentially rejective procedure — [unverified: not opened; cited from memory].

## Top 5

1. Add log-scale WIS as a pre-registered co-primary or sensitivity analysis; the count and log relWIS disagree in sign for several models.
2. Replace the US-weighted d_r with a per-location pooled log-relWIS as a sensitivity check, since the US is 45.6% of ensemble WIS from 1.9% of rows.
3. Implement the protocol's DM/HAC, bootstrap, Holm, horizon check, and truth-vintage recording in `score_live.py`; today it outputs only ratio-of-means relWIS.
4. Recognise that T = 20 weeks gives ≈ 21–24% minimal detectable effect (lab models only, AR-inflated, pooled σ); tighten the gate or extend the minimum.
5. Replace the t(T−1) reference with a block-bootstrap or Andrews-HAC check, verified by size simulation on archived d_r before graduation.
