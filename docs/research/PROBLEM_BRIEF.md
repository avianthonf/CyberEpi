# Problem brief: CDC FluSight influenza forecasting

Read this whole document before researching. It is the shared description of
the problem for every research agent. Facts here were checked against the hub
and our repository on 2026-11-25.

## 1. The task

The CDC FluSight challenge asks teams, every week of the flu season, to
forecast **weekly new laboratory-confirmed influenza hospital admissions** in
53 US locations: the national total, 50 states, DC and Puerto Rico.

- **Season:** forecasts run roughly October/November to May. Submissions are
  due Wednesday 11pm US Eastern. The **reference date** is the Saturday after
  the deadline. Epidemiological weeks run Sunday–Saturday.
- **Horizons:** h = −1, 0, 1, 2, 3 weeks relative to the reference date. h=−1
  is last week (already happened, not fully reported), h=0 the current week.
  Our own evaluation uses h=0..3.
- **Data lag:** at the deadline the latest available admissions are for the
  week ending the Saturday before (reference date − 7 days). Official counts
  are published Fridays (a preliminary version Wednesdays).
- **Targets in the 2026-27 hub** (`hub-config/tasks.json`; all optional):
  1. `wk inc flu hosp`: quantiles (23 levels: 0.01, 0.025, 0.05, 0.10, …,
     0.95, 0.975, 0.99) and/or samples. **This is the main target; our
     submissions use it.**
  2. `wk flu hosp rate change`: categorical probabilities (pmf) over
     large_decrease, decrease, stable, increase, large_increase, defined from
     the change in rate per 100k relative to the last observed week (exact
     thresholds: hub `README.md` / `model-output/README.md`).
  3. `peak week inc flu hosp`: pmf over season weeks.
  4. `peak inc flu hosp`: quantiles of the season's peak weekly count.
  5. `wk inc flu prop ed visits`: quantiles of the share of ED visits for flu
     (NSSP), h=−1..3.
- **One file per team model per week**; a team may submit more than one model
  if they differ in method. Models may be "designated" for inclusion in the
  CDC ensemble.

## 2. The data

All in the hub `cdcepi/FluSight-forecast-hub` (a full local copy is at
`/home/user/flusight-forecast-hub`).

- **Admissions (NHSN):** `target-data/target-hospital-admissions.csv`, the
  latest version: weekly counts and rate per 100k by location, from
  2022-02 onward (earlier HHS Protect data exists from 2020).
  US national peaks: 26.8k (2022-12-03), 21.7k (2023-12-30), 55.5k
  (2025-02-08), 42.5k (2026-01-03). The 2026-27 season is already at 13.7k
  on 2026-11-21 and rising (an early season).
- **As-published versions:** `target-data/time-series.csv` holds every
  published version (`as_of`, from 2023-09-23). First reports average ~96% of
  final nationally (range 78–142%); in 2025-26 ~89%. Some weeks have no
  archived version (212 of 2,915 location-dates in our backtest).
- **Reporting regime changes:** hospital reporting to NHSN was mandatory,
  then voluntary for part of 2024 (roughly May–Oct), then mandatory again.
  Counts in the voluntary period are less complete.
- **ED visits (NSSP):** `target-data/target-ed-visits-prop.csv`, share of ED
  visits for flu, weekly by location. Published versions exist in the hub
  only from Nov 2025; earlier values are final (revised) data.
- **Scoring truth:** `target-data/oracle-output.csv` (hubverse format).
- **Every team's past forecasts:** `model-output/<team-model>/` (148 models,
  seasons 2023-24 onward in this hub), with method descriptions in
  `model-metadata/*.yml`. This is the largest body of evidence about which
  methods work on this exact task. Teams include mechanistic, statistical,
  ML, ensemble and human-judgement models (e.g. Metaculus-cp,
  FluSight-HJudge_ensemble, UMass-flusion, CMU-TimeSeries, MOBS-GLEAM_FLUH,
  PSI-PROF, LosAlamos-DoSiDo, NEU_ISI-AdaptiveEnsemble).
- **Other sources** (not in the hub): ILINet, FluSurv-NET, clinical lab
  positivity, wastewater (NWSS, WastewaterSCAN), Delphi Epidata API,
  weather, school calendars, search trends. Most lack an archive of values
  as they were known at the time.

## 3. How forecasts are judged

- **WIS (weighted interval score)** per (location, reference date, horizon),
  on the count scale:
  WIS = (1/(K+½)) · ( ½|y − m| + Σₖ (αₖ/2) · ISₖ ), where ISₖ is the interval
  score of the central (1−αₖ) interval: width + (2/αₖ)·(distance by which y
  falls outside). Equivalently, WIS is proportional to the average pinball
  (quantile) loss over the submitted quantiles, and approximates CRPS.
  It rewards sharpness and penalises misses; it is **not scale-free**, so
  large locations (US national, CA, TX, NY) dominate pooled raw WIS.
- **relWIS:** mean WIS of a model ÷ mean WIS of a reference (FluSight-baseline
  or FluSight-ensemble) on the same rows. The CDC's own evaluations use
  pairwise relative WIS across models (geometric mean of pairwise ratios),
  sometimes on log-transformed counts.
- **Coverage:** share of truths inside the 50% and 95% intervals.
- **Categorical targets:** typically scored by log score or Brier score.
- **Reference models:** FluSight-baseline (flat persistence with empirical
  quantiles) and FluSight-ensemble (quantile median/mean of all designated
  submissions). Beating the ensemble over a season is rare for a single model.

## 4. Our models

Code in `/home/user/CyberEpi/backtest/`. Both run every Wednesday in
`.github/workflows/weekly-forecast.yml` (GitHub runner, 4 CPUs, 30-minute
limit, Python: numpy, pandas, scipy, lightgbm, scikit-learn).

**Model 1, CyberEpi-EAKF** (designated; `eakf.py`, `seir_fast.py`,
`METHODS.md`). SEIR with an admissions accumulator per location; state
(S, E, I, R, log β, log HIR, W, log c); β, HIR, c follow geometric random
walks. Ensemble square-root filter (M=300) assimilates weekly admissions and
the NSSP ED fraction. Forecasts roll the ensemble forward with log-β drift.
No age structure, no spatial coupling, no strain dynamics. Settings frozen
by a rule committed before testing.

**Model 2, CyberEpi-GBQR** (not designated yet, submitted from 2026-12-05;
`gbqr.py`, `MODEL2_PROTOCOL.md`). LightGBM quantile regression pooled across
locations; one model per (horizon, quantile); target is the change in
log1p(rate per 100k) from the last observed week; features are log rate and
its 1–4-week changes, log ED fraction and its 1–2-week changes, and week of
season (sin/cos). Refitted every week on as-published data.

## 5. Honest results so far

Backtests use only the data version published at each forecast date.

| | 2023-24 | 2024-25 | 2025-26 |
|---|---|---|---|
| Model 1 relWIS vs baseline | (tuning) | 0.650 | 0.766 |
| Model 1 relWIS vs ensemble | — | 0.966 | 1.163 |
| Model 2 relWIS vs baseline | 0.741 (dev) | 0.624 (dev) | 0.385 (holdout) |
| Model 2 relWIS vs ensemble | — | — | 0.584 (holdout) |

- Model 1: strongest at h=0 (0.88 vs ensemble), worse at h=2–3 (1.08–1.11).
  90% intervals cover ~74%. **Runs low while epidemics decline** (post-peak
  fall too steep; 3-week medians ~40% low in declining phases). An
  after-the-fact shift/widening fitted on past seasons did not hold up when
  a season was left out.
- Model 2: **runs low while epidemics rise.** Its 2025-26 holdout gain comes
  mostly from one well-timed national peak call (learned "at rates this high,
  epidemics peak soon"), which is legitimate but fragile.
- The ED-visit input carries most of model 1's skill (relWIS 3.3–4.2 without
  it, 0.80–0.85 with it, on 2023-24).
- The best of 45 real 2025-26 teams scored 0.86 vs the ensemble on our rows.

## 6. Rules for any idea we test

These exist because there are only ~4 seasons of data, and score gaps between
good methods are smaller than season-to-season differences.

1. **No look-ahead.** At forecast date R a model may use only data published
   by R (as-of versions). External data without an as-published archive is
   either reconstructed honestly or tested only prospectively.
2. **The 2025-26 holdout is used up** for both models. Development may use
   2023-24 and 2024-25 (and 2022-23 where data allows), leave-one-season-out.
3. **Comparison rules are written before results** (pre-registration).
4. **Shadow mode is the real test.** Experimental models run live every week
   of 2026-27, saved and timestamped in git, not submitted, and are scored
   against data that did not exist when they ran. Ideas that win there can
   be submitted next season.
5. **Two tracks.** Track A: changes to what we submit to the CDC (strong
   evidence required). Track B: lab experiments, unconventional ideas
   welcome, shadow mode only.
6. **Cost:** a weekly run must fit the GitHub runner (4 CPUs, 30 minutes for
   everything). Backtests may run longer offline.

## 7. Known levers (our current view, to be challenged)

1. Turning points: peak and decline phases decide most of the score.
2. Calibration: our intervals are too narrow.
3. Incomplete recent data (nowcasting the revisions).
4. Combining our two models, whose errors occur in opposite phases.
5. The other targets (rate change, peak, ED share) are unclaimed points.

## 8. What the owner wants

A CV-worthy, honest, hard-to-attack forecasting record, scored by the CDC.
Wide, deep exploration of every documented technique (including old, rare,
cross-domain and ahead-of-their-time ideas), and unconventional but sane
ensembles, e.g. combiners that account for luck vs skill, or that weight
models by real-world event streams through learned weights. Track B ideas do
not need to be submittable; they need to be testable honestly.
