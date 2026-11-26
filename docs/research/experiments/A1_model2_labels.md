# A1 — Model 2 (GBQR) maturity-matched labels and backfill-corrected edge

Source: SYNTHESIS §6 item 2; 04 §6 E1; 06 §8.2 and Track A #2.
Scope: dev seasons 2023-24 and 2024-25, LOSO, as-of snapshots only. 2025-26 is not touched.

## 0. Pre-registration (written before any variant is run)

Registered: 2026-11-26T01:00:38Z (UTC). Variants are not run yet at this timestamp.

Variants (all opt-in; the default path is unchanged):

- `base`: current model 2 (`model2_config.json`), reproduced from the code path.
- `drop2`, `drop3`, `drop4`: a training row for horizon k is kept only if its label week t+k lies at or before the last observed week minus m weeks (m = 2, 3, 4). This removes labels built from the most recent first-report weeks.
- `backfill`: admissions in the panel are multiplied by a backfill ratio f(age), where age is the number of weeks between the target week and the as-of vintage. f(age) is the median over vintage pairs of final/published, using only vintages with as_of ≤ R − 8 weeks, and final = the newest vintage with as_of ≤ R. Applied to training and serving rows alike.

Pass criterion (fixed here):

1. Rising-phase share of truth below the 0.5 forecast ("rising below_median") must move toward 0.5 on BOTH folds. Concretely: for each fold, |share − 0.5| is smaller than for `base`, and the share lies in [0.35, 0.65].
2. Mean relWIS (vs FluSight-baseline) across the two folds must not be worse than `base`'s mean.

A variant passes only if both criteria hold. If none passes, the verdict is "no change". A pass on one fold alone is not a pass.

Phase is defined by as-of 3-week log growth with the existing threshold (0.05 per week), as in `dev_members.py`. Origins: the existing dev origin list (57 dates). A stale pick is recorded, not dropped. Origins whose pick falls in the 2024-04-27..2024-11-16 vintage gap are listed in the results.

## 1. Results

Run: 2026-11-26, finished about 01:20Z (after the §0 registration). Driver `backtest/a1_labels.py`; output `backtest/results/a1_labels/summary.json` and `<variant>.csv.gz`. 57 origins (30 + 27), 53 locations, 12,078 scored rows per variant (6,354 + 5,724), the same as `dev_members/summary.json`.

Data labelling: admissions are as-of (hub vintage picked by `pick_vintage`). **ED inputs are final values only** (no ED vintages before Nov 2025; A0 §3). Truth is the final oracle. No dev origin falls inside the 2024-04-27..2024-11-16 vintage gap (last 2023-24 origin 2024-05-04, first 2024-25 origin 2024-11-23), so none are excluded. The 3 stale picks (2024-11-30, 2024-12-14, 2025-01-11) are kept and use a vintage one week behind, as in the baseline.

`base` reproduces `dev_members` GBQR exactly: relWIS 0.741 / 0.622.

### 1.1 Primary metrics

| Variant | Fold | relWIS vs FluSight-baseline | relWIS vs base (90% block-bootstrap CI over dates) | Rising below_median | cov50 | cov90 |
|---|---|---|---|---|---|---|
| base | 2023-24 | 0.741 | 1 | 0.422 | 0.411 | 0.780 |
| base | 2024-25 | 0.622 | 1 | 0.212 | 0.375 | 0.726 |
| drop2 | 2023-24 | 0.744 | 1.004 (0.976–1.041) | 0.428 | 0.407 | 0.777 |
| drop2 | 2024-25 | 0.634 | 1.019 (0.999–1.040) | 0.197 | 0.374 | 0.718 |
| drop3 | 2023-24 | 0.745 | 1.005 (0.970–1.046) | 0.426 | 0.407 | 0.774 |
| drop3 | 2024-25 | 0.632 | 1.016 (1.002–1.033) | 0.185 | 0.380 | 0.720 |
| drop4 | 2023-24 | 0.747 | 1.008 (0.971–1.052) | 0.427 | 0.405 | 0.772 |
| drop4 | 2024-25 | 0.632 | 1.015 (1.002–1.027) | 0.182 | 0.379 | 0.718 |
| backfill | 2023-24 | 0.749 | 1.011 (1.000–1.020) | 0.410 | 0.410 | 0.780 |
| backfill | 2024-25 | 0.607 | 0.975 (0.965–0.985) | 0.235 | 0.383 | 0.734 |

Mean relWIS over the two folds: base 0.6818; drop2 0.6891; drop3 0.6884; drop4 0.6892; backfill 0.6782. Rising rows: n = 2,876 (2023-24) and 1,720 (2024-25).

### 1.2 Phase effect (relWIS vs base by as-of phase, 2023-24 / 2024-25)

| Variant | rising | peak | declining |
|---|---|---|---|
| drop2 | 0.990 / 1.027 | 1.024 / 1.041 | 1.031 / 0.999 |
| drop3 | 0.998 / 1.028 | 0.989 / 1.019 | 1.033 / 0.996 |
| drop4 | 1.003 / 1.025 | 0.953 / 1.017 | 1.049 / 0.995 |
| backfill | 1.016 / 0.974 | 0.999 / 0.936 | 1.005 / 1.001 |

Below-median share in the peak phase (base 0.567 / 0.350) and the declining phase (base 0.536 / 0.329) moves by at most 0.06 under any variant.

### 1.3 Backfill ratios (diagnostic)

f(age) is almost flat across ages 0–7. For example, R = 2025-02-01 gives 1.025–1.033, R = 2024-11-23 gives 1.029–1.033, and R = 2023-12-02 gives 0.96–1.00. Age 7 is about the same as age 0. So the difference between older and newer vintages is a level shift across all recent weeks (a reporting/coverage revision). It is not a lag-dependent first-report deficit. The variant therefore rescales the newest 8 weeks by about 3% and leaves a step at age 8. It does not correct the edge in the sense the hypothesis meant. Origins before about 2023-11-18 have no vintage older than R − 8 weeks, so they get no correction (e.g. 2023-10-14 is empty).

### 1.4 Runtime

Wall time for 57 origins on 8 processes: base 133 s (includes cache warm-up); drop2 112 s; drop3 77 s; drop4 76 s; backfill 80 s. No variant costs more than base. The ratio table costs under 1 s per origin.

## 2. Verdict (against the §0 criterion)

| Variant | 2023-24 rising: toward 0.5 and in [0.35, 0.65] | 2024-25 the same | Mean relWIS not worse | Pass |
|---|---|---|---|---|
| drop2 | yes (0.422 → 0.428) | no (0.212 → 0.197) | no (0.689 > 0.682) | **FAIL** |
| drop3 | yes (→ 0.426) | no (→ 0.185) | no (0.688) | **FAIL** |
| drop4 | yes (→ 0.427) | no (→ 0.182) | no (0.689) | **FAIL** |
| backfill | no (→ 0.410) | toward 0.5 (→ 0.235) but outside the range | yes (0.678) | **FAIL** |

No variant passes. Verdict: **no change to model 2.**

- Dropping the most recent labels does not reduce the rise bias. In 2024-25 it makes it slightly worse, and it costs 1.5–2% relWIS in that fold. This goes against the hypothesis (04 §6 E1) that the low-rise bias comes from lag-0/1 first-report labels.
- The NHSN vintages show no lag-dependent backfill (flat f(age)). That explains why neither mechanism moves the bias. It supports the 10 §6.3 item 4 reading that the rise bias is not a first-report artefact here.
- Backfill improves 2024-25 (0.975, CI excludes 1) but slightly worsens 2023-24 (1.011). The gain comes from a flat level rescale, not from edge correction. A level-revision correction would need its own pre-registration.
- The 2024-25 rising below_median of about 0.2 is far outside the range under every variant. It is a median-location problem (e.g. A11), not a label-maturity problem.

## 3. Files

- `backtest/gbqr.py`: opt-in module options `LABEL_DROP_M` (default 0) and `BACKFILL` (default False), plus `backfill_ratios(ref)`. Defaults were checked bit-identical against `results/dev_members` GBQR CSVs on 2023-12-02 and 2025-02-01.
- `backtest/a1_labels.py`: variant driver and scoring (new).
- `backtest/results/a1_labels/`: `summary.json` and per-variant forecasts (`*.csv.gz`).
