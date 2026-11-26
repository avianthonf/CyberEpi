# Shadow-mode protocol (lab models, 2026-27)

Written 2026-11-26, before any truth exists for a shadow forecast. Committed to git
before the first scored week. Changes after this date are logged below with the
date and reason; the original text stays in git history.

## 1. What is shadowed

- **Lab models** are the candidates in `backtest/shadow.py` (`MODELS`). Each writes
  `forecasts/shadow/<model>/<ref>-<model>.csv` every Wednesday. The weekly workflow
  commits these files before the data they are scored on exists. They are never
  submitted to the CDC hub.
- **Reference models:**
  - `CyberEpi-EAKF` (model 1, submitted);
  - `FluSight-ensemble` (the hub's ensemble, `model-output/FluSight-ensemble`, read
    from the hub on the same reference dates);
  - `FluSight-baseline` (reported, not used for the verdict).
- **Target:** `wk inc flu hosp`, quantile output, horizons 0–3, all locations in the
  hub's truth (the US and the states and territories).
- **Unit of analysis:** a row is `(model, reference_date, location, horizon)`. A row
  is scored once the truth for its `target_end_date` is in the hub's
  `target-data/target-hospital-admissions.csv`. Each weekly run re-scores everything
  from the latest truth. Truth can be revised; a verdict uses the truth as of the
  verdict commit, and that commit is recorded.
- **Scorer:** `backtest/score_live.py` writes `backtest/results/live/scores.csv` (one
  row per scored forecast) and `summary.csv`. Only reference dates on or after
  2026-09-01 are scored.

## 2. Metrics

- **WIS** per row: `backtest/wis.py` (23 quantiles, the hub definition; equal to the
  sum of pinball losses divided by 11.5).
- **relWIS vs a reference R:** mean WIS of the lab model divided by mean WIS of R over
  the rows both have scored (identical rows). Below 1 means the lab model is better.
- **Coverage:** empirical share of truth inside the 50% interval (q0.25–q0.75) and the
  95% interval (q0.025–q0.975). Targets: 50% in [0.40, 0.60]; 95% in [0.90, 0.98].
- **Per-horizon** relWIS is reported for each horizon 0–3; the verdict uses the pooled
  series (below).

## 3. Tests

Loss series. For each reference week r, with common rows C_r for a lab model m and a
reference R:

    d_r = log( sum_{C_r} WIS_m / sum_{C_r} WIS_R )

A negative d_r means m beat R that week. Summing WIS within the week means large locations
still dominate that week's value (the sum is weighted by WIS, not by location count); the
log removes week-to-week scale and keeps the series symmetric. This weighting is pre-registered.

- **Diebold–Mariano with HAC variance.** Mean of d_r over the T weeks, with the
  standard error from a Bartlett-kernel (Newey–West) long-run variance using lag
  L = 3 (the horizon-3 targets of neighbouring reference weeks overlap). Compare with
  a t distribution on T−1 degrees of freedom, two-sided.
- **Block bootstrap over weeks.** Moving-block bootstrap of the series d_r, block
  length 3 weeks, B = 10,000 resamples, seed 20261126. The 95% percentile interval of
  the mean of d_r.
- Both tests use the same series; the verdict needs both to agree (section 5).

## 4. Minimum weeks before a verdict

No verdict, and no graduation, before **all** of these hold:

1. at least **20 scored reference weeks** (every row for horizons 0–3 has truth);
2. the hub truth shows the 2026-27 peak has passed (at least two consecutive weeks of
   decline after the season's peak in the US series), so that near-peak weeks are in
   the sample;
3. at least one verdict-ready commit of `backtest/results/live/` made after 1 and 2.

Before then the weekly files are descriptive only.

## 5. Multiple comparisons and the graduation rule

**Family.** Every lab model against each of the two references (CyberEpi-EAKF and
FluSight-ensemble) is one hypothesis. With K lab models there are 2K tests. Holm
step-down at family-wise alpha = 0.05 across all 2K p-values. A model added mid-season
joins the family from its first scored week; the family is recounted at each verdict
and includes every model ever registered in this protocol.

**Graduation.** A lab model graduates to Track A candidacy (eligible for submission
next season; not submitted this season) only if, at a verdict:

1. relWIS < 1 against CyberEpi-EAKF and against FluSight-ensemble;
2. the Holm-adjusted DM p-value < 0.05 against both references;
3. the bootstrap 95% interval of the mean d_r excludes 0 on the same side;
4. coverage is in the target ranges of section 2 at 50% and 95%;
5. no single horizon has relWIS > 1.10 against FluSight-ensemble (no hidden failure at
   one horizon).

Failing any condition, the model stays in the lab. A model with a bug fix that changes
its forecasts restarts its clock from the fix week. The graduation decision is recorded
in this file with the commit it was based on.

## 6. Scope limits

- No model is tuned on live scores once it is shadowed. Changes to a lab model are bug
  fixes only; log them below.
- Lab models are not submitted to the CDC hub in this season.
- Winners are re-tested on the next season's data before any submission.

## Change log

- 2026-11-26: protocol written (before any shadow truth exists).
