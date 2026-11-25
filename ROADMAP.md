# Roadmap

This file is the contract for what gets worked on. If a task is not on it,
it does not get done until this file is changed first.

## Goal

**A flu forecaster whose accuracy is scored by someone else.**

CyberEpi's forecaster (SEIHDR model + ensemble Kalman filter, `backtest/`)
is submitted weekly to the CDC FluSight challenge for the 2026-27 season and
scored by the hub against data that did not exist when the forecast was made.
The result goes on a CV as a checkable fact, whether it is good or mediocre.

What counts as done: weekly submissions run without manual work, and a
public results page shows the honest backtest and the live scores side by side.

## Why this and not the full platform

- The patient app and six services are a working local demo, but cannot
  responsibly hold real patient data, and have no users or reason for users
  to return. Growing them adds surface to criticise, not evidence.
- The forecaster makes one measurable claim. Making that claim survive a
  hostile reviewer is worth more than any number of extra features.

## Known weaknesses in the current claim (relWIS 0.714)

These are what a reviewer would attack first, and what Phase 1 fixes.

1. **Revised data.** The backtest uses final, later-corrected admissions
   (`target-hospital-admissions.csv`), not the numbers known at each forecast
   date. Live forecasting only ever sees the early, incomplete numbers.
2. **Tuned on the test seasons.** EAKF-final settings were picked from a sweep
   over all three reported seasons, so the score is partly fitted.
3. **Weak comparison.** Only compared to the persistence baseline, not to the
   FluSight ensemble or other teams.

## Phases

### Phase 0 — Consolidate (done)
- Local delta restored into the repo; report clutter moved to `docs/archive/`.

### Phase 1 — Honest retest (done 2026-11-25)

Result (see BACKTEST_RESULTS.md): out of sample on as-published data,
relWIS **0.697 vs baseline** and **1.046 vs ensemble** (pooled 2024-25 and
2025-26). 90% intervals cover only ~74%. Checkpoint A outcome: beats
baseline, not ensemble → Phase 2.

From here the backtest numbers are frozen. Any model change (e.g. wider
intervals) may use all past seasons, and is judged only by live 2026-27
scores, never by re-scoring the backtest.

- Rebuild the backtest input from the hub's `time-series.csv`, using only the
  data version available at each forecast date (`as_of`).
- Split seasons: tune on 2023-24 only; score 2024-25 and 2025-26 untouched.
- Score against both FluSight-baseline and FluSight-ensemble, per season and
  horizon, with interval coverage.
- Document the ED-visit input limitation: as-of versions exist only from
  Nov 2025, so earlier seasons run without it or are labelled as using
  final data.
- Replace the headline numbers in README/BACKTEST_RESULTS with the honest ones,
  keeping the old ones labelled as superseded.

**Checkpoint A:** the honest numbers decide the next step.
- Beats ensemble → continue to Phase 2 without stopping.
- Beats baseline, not ensemble → continue to Phase 2 without stopping;
  aim is an honest mid-table entry.
- Loses to baseline → stop and decide with the owner; fix the model before
  anything goes public.

### Phase 2 — Live submission pipeline
- ~~Fix interval calibration before going live.~~ Investigated 2026-11-25
  (`backtest/calibrate.py`, `backtest/results/calibration.json`): forecasts
  run low (truth above the median ~65%), worst while an epidemic is
  *declining* (3-week median ~40% low): the model's post-peak decline is
  too steep. A per-horizon shift/widening fitted on past seasons does not
  hold up when a season is left out (horizons 1–3: no gain; horizon 0: helps
  two seasons, hurts the third). Decision: submit uncalibrated; fixing the
  decline-phase dynamics is the first model improvement, judged live.
- [done] Scheduled GitHub Action (`.github/workflows/weekly-forecast.yml`):
  Wednesdays after the CDC release, pulls hub data → forecasts with the frozen
  settings (`backtest/model_config.json`) → packages → validates against the
  hub's rules and official metadata schema. Refuses stale data; a missed week
  fails loudly. Produces a downloadable draft each week; never submits.
- [done] Model metadata and first submission prepared on the owner's fork
  (`avianthonf/FluSight-forecast-hub`, branch `CyberEpi-EAKF-2026-11-28`).
- [done] Second model `CyberEpi-GBQR` (backtest/MODEL2_PROTOCOL.md):
  pre-registered, frozen, holdout passed; runs weekly alongside model 1,
  submitted from reference date 2026-12-05, not designated for the CDC
  ensemble until it has a live record. Its holdout score is driven mostly by
  one peak call and is not claimed as "better than all teams".

**Checkpoint B (owner only):** team name, authors and the first pull request to
the CDC hub are public and in the owner's name, so they are never done without
explicit approval.

### Phase 3 — Show it
- README rewritten around the forecaster; the platform becomes a labelled
  "systems demo" section.
- Results page: honest backtest + live scores, updated weekly.
- Stop. From here the work is watching scores, not building.

## Parked (not forgotten, not worked on)

- Model 1: post-peak decline too steep (see Phase 2 note). Model 2 does not
  share this weakness but runs low in rising phases; a combination of the two
  is the natural next step once both have live scores.

- Public forecast dashboard fed by the live pipeline (first candidate after
  Phase 3; would reuse epi-engine and the app).
- Patient app and services beyond keeping them building.
- Cloud deployment configs in `deploy/free/`.

## Rules for working autonomously

- Work proceeds without asking inside the current phase. Decisions that stay
  inside the owner's own repositories are made and reported, not asked.
- Stop at a checkpoint, before anything public or in the owner's name, before
  deleting anything, and when a result contradicts this file.
- Report numbers as they come out, including bad ones.
