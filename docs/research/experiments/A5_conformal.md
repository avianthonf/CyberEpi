# A5 — Horizon-wise conformalized quantile adjustment (log1p) on dev members

Status: **pre-registered 2026-11-26, before the driver `backtest/a5_conformal.py` was run.** Results are appended below "## Results".
Source: SYNTHESIS §2 (A5); family 07 §2.2 step 3; A4 result (season-fitted widths did not transfer).
Models: CyberEpi-EAKF, CyberEpi-GBQR, CyberEpi-MIX_LP (dev_members, unmodified; read only).
Seasons: 2023-24 and 2024-25, leave-one-season-out (LOSO). 2025-26 is not used. Truth: hub oracle final values. ED not used.

## Question

Does a horizon-wise CQR adjustment on the log1p scale, with a calibration set drawn only from data that was available at the reference date, bring the pooled 50% and 90% intervals to nominal without costing WIS? Does a rolling in-season window do better than prior-season residuals, given that A4 showed season-fitted widths do not transfer?

## Method (fixed before running)

1. **Scores.** For each (model, reference date, location, horizon 0–3), z = log1p(value) and z_y = log1p(truth). Two CQR scores on the nominal pairs: `E50 = max(q0.25 − z_y, z_y − q0.75)` and `E90 = max(q0.05 − z_y, z_y − q0.95)`.
2. **Quantile.** For each calibration set, `Q_α = k-th smallest score`, with `k = ceil((n+1)(1−α))`, `α = 0.5` for E50 and `α = 0.10` for E90. If `k > n`, use the largest score. Q may be negative (intervals shrink).
3. **Adjustment.** The 0.25/0.75 quantiles shift by ∓Q50 and the 0.05/0.95 by ∓Q90. Each other level τ shifts by ∓ np.interp(|τ−0.5|, [0, 0.25, 0.45], [0, Q50, Q90]), so the median is unchanged and levels beyond 0.05/0.95 take the Q90 shift. Back-transform with expm1, clip at 0, round to integers (hub format), and enforce non-decreasing order. Horizon −1 rows are left unmodified (not scored).
4. **Window (a): prior-season residuals (LOSO).** For test season T, scores come from all rows of the other dev season S (all horizons 0–3, all locations, using the final truth). Q is per (model, horizon). This is not time-causal for fold 2023-24, because S = 2024-25 is later. It is causal for fold 2024-25.
5. **Window (b): rolling in-season window, W = 8 origins, prior-season warm start.** At reference date r in season T, the calibration set is:
   - (i) in-season rows whose reference date is one of the W origins before r (r−7, …, r−7W), **and** whose `target_end_date ≤ r − 7 days`, so the truth was published before r; plus
   - (ii) if fewer than W in-season origins contribute (k < W, counted per horizon), warm-start rows (same horizon) from season S. These come from the block of W − k consecutive S origins that ends just before S-index i (r's index in T's origin list); if i < W − k, the block is S-index 0 … W − k − 1.
   Q is recomputed per (r, model, horizon). Fold 2023-24's warm start comes from a later season, so its window (b) is not causal; this is disclosed in the verdict.

## Metrics

- cov50 and cov90 on the pooled forecasts (all locations, horizons 0–3) for the test season.
- WIS via `run_flusight.summarize`. relWIS vs unmodified: WIS of the adjusted arm divided by WIS of the unmodified arm, overall and per horizon. relWIS vs FluSight-baseline: `summarize`'s relWIS, overall and per horizon.
- Runtime per (model, window), in seconds.

## Pass rule (fixed before running)

A model × window passes only if **on both folds**:
1. cov50 ∈ [0.45, 0.55] and cov90 ∈ [0.85, 0.95] for the pooled forecasts, and
2. relWIS vs unmodified (overall, horizons 0–3) ≤ 1.00.

Per-horizon relWIS, runtime, and window (a) vs window (b) differences are reported, not part of the decision.

## Risks and controls

- Two seasons only. LOSO estimates are noisy; the fold is the unit of evidence.
- Window (b) at season start has few in-season scores, so the warm start dominates early origins.
- Final truth is used as the outcome, so the calibration does not match what was known at the time. This is the same convention as the dev-member scoring, and it can overstate causal performance.
- The unmodified arm is read from dev_members, which are never written.

## Results

Run 2026-11-26T03:57Z (one run, after pre-registration; nothing changed after). Driver `backtest/a5_conformal.py`; output `backtest/results/a5/summary.json`. dev_members mtimes unchanged. Scoring tests 4/4 pass. `ruff check backtest` passes. Runtime: 47 s total (load 1.2 s; scoring dominates). The adjustment itself takes 0.07–0.10 s (a) and 0.16–0.20 s (b) per model-season, i.e. negligible weekly.

### Pass decision (cov50 ∈ [.45,.55], cov90 ∈ [.85,.95], relWIS vs U ≤ 1.00, both folds)

| Model | Window | Fold | cov50 / cov90 (U → adj) | relWIS vs U | relWIS vs baseline (U → adj) | Fold | Verdict |
|---|---|---|---|---|---|---|---|
| EAKF | a | 2023-24 | .467/.856 → .652/.973 | 1.126 | 0.799 → 0.900 | FAIL | **FAIL** |
| EAKF | a | 2024-25 | .349/.734 → .388/.798 | 1.001 | 0.650 → 0.650 | FAIL | |
| EAKF | b | 2023-24 | → .565/.929 | 1.074 | 0.799 → 0.859 | FAIL | **FAIL** |
| EAKF | b | 2024-25 | → .470/.866 | 1.058 | 0.650 → 0.687 | FAIL (WIS) | |
| GBQR | a | 2023-24 | .411/.780 → .557/.932 | 0.982 | 0.741 → 0.728 | FAIL (cov50 .557) | **FAIL** |
| GBQR | a | 2024-25 | .375/.726 → .476/.872 | 0.921 | 0.622 → 0.573 | pass | |
| GBQR | b | 2023-24 | → .537/.906 | 0.999 | 0.741 → 0.740 | pass | **PASS** (caveat) |
| GBQR | b | 2024-25 | → .500/.855 | 0.978 | 0.622 → 0.609 | pass | |
| MIX_LP | a | 2023-24 | .540/.911 → .607/.960 | 1.044 | 0.672 → 0.702 | FAIL | **FAIL** |
| MIX_LP | a | 2024-25 | .444/.827 → .435/.827 | 0.999 | 0.543 → 0.542 | FAIL (cov) | |
| MIX_LP | b | 2023-24 | → .560/.919 | 1.056 | 0.672 → 0.710 | FAIL | **FAIL** |
| MIX_LP | b | 2024-25 | → .480/.857 | 1.047 | 0.543 → 0.568 | FAIL (WIS) | |

**Verdict: GBQR × window (b) passes the pre-registered rule; the other five model × window cells fail.** Caveats on the pass:
- The 2023-24 fold of (b) takes its warm start from 2024-25, which is later (pre-registered disclosure). The warm start is 33% of calibration origins on average in that fold (37% in 2024-25). Only the 2024-25 fold is fully causal.
- The 2023-24 margin is thin: relWIS 0.999, and h0/h1 get worse (1.040, 1.032), offset by h3 (0.966).
- One pass in six cells, two seasons: treat it as a candidate for shadow/forward testing, not as Track A evidence on its own.

### relWIS per horizon (h0, h1, h2, h3)

| Model | Fold | U vs baseline | (a) vs U | (a) vs baseline | (b) vs U | (b) vs baseline |
|---|---|---|---|---|---|---|
| EAKF | 2023-24 | .738 .720 .809 .863 | 1.114 1.095 1.105 1.162 | .822 .788 .894 1.002 | 1.041 1.033 1.058 1.119 | .768 .744 .855 .965 |
| EAKF | 2024-25 | .680 .660 .666 .622 | 1.005 .999 1.000 1.001 | .684 .659 .666 .623 | 1.059 1.055 1.065 1.052 | .720 .697 .709 .654 |
| GBQR | 2023-24 | .561 .642 .761 .850 | 1.115 1.041 .981 .925 | .625 .669 .747 .786 | 1.040 1.032 1.010 .966 | .583 .663 .769 .822 |
| GBQR | 2024-25 | .659 .656 .625 .590 | .975 .949 .922 .882 | .642 .622 .576 .520 | .977 .965 .977 .988 | .643 .633 .610 .583 |
| MIX_LP | 2023-24 | .601 .615 .682 .724 | 1.084 1.038 1.037 1.040 | .652 .639 .708 .753 | 1.010 1.018 1.044 1.099 | .607 .626 .713 .796 |
| MIX_LP | 2024-25 | .610 .565 .541 .509 | 1.000 1.000 1.000 .998 | .610 .565 .541 .508 | 1.027 1.048 1.054 1.048 | .626 .592 .571 .534 |

Mean log1p shifts (Q50, Q90) by horizon, window (a): EAKF fit on 2024-25 = (.10,.30) h0 → (.23,.62) h3; fit on 2023-24 = (.05,.15) → (.00,.07). MIX_LP fit on 2023-24 = 0 at all horizons (2023-24 is already covered).

### Reading (not part of the decision)

- **Season-to-season transfer (window a) repeats A4.** The width a season asks for depends on that season's bias. It over-widens 2023-24 (cov90 up to .96–.97 for EAKF and MIX_LP) and leaves 2024-25 short (EAKF .798, MIX_LP .827). Coverage misses the band in opposite directions on the two folds. Making the correction horizon-wise and on log1p does not fix this. GBQR is the exception, because its under-coverage is similar in both seasons (cov90 .78/.73).
- **The rolling window (b) is robust on coverage, not on WIS.** It hits cov90 within [.85,.95] for every model on both folds (.855–.929), and cov50 within the band on 2024-25 for all models. On 2023-24, cov50 overshoots slightly for EAKF (.565) and MIX_LP (.560); GBQR (.537) is inside the band. So tracking recent residuals does transfer where a season-fitted width did not. But for EAKF and MIX_LP the extra width costs 4–7% WIS on both folds. Their misses come from median bias (phase-dependent, family 07 §3), and symmetric widening pays for coverage with sharpness. Only GBQR, whose shortfall is mostly width, gains WIS.
- **Width is the wrong lever for the pool.** MIX_LP is already near nominal in 2023-24 (.540/.911). The pass rule's cov band is reachable for it only by widening that costs WIS. This matches the SYNTHESIS exclusion of interval widening as a fix for median bias.
- **Next:** if adopted at all, GBQR + window (b) belongs in shadow first (B-series, frozen W = 8). It should not change the submitted model on two-season evidence. The relevant comparison is B4 (ACI), which targets the same running coverage.
