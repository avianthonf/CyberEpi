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

### Phase 1 — Honest retest
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

**Checkpoint A (stop and decide with the owner):** the honest numbers decide
the next step.
- Beats ensemble → Phase 2 as is.
- Beats baseline, not ensemble → Phase 2; aim is an honest mid-table entry.
- Loses to baseline → fix the model before anything goes public.

### Phase 2 — Live submission pipeline
- Scheduled GitHub Action: pull latest hub data → forecast → validate with the
  hub's own rules → produce the submission file.
- Model metadata and first submission.

**Checkpoint B (owner only):** team name, authors and the first pull request to
the CDC hub are public and in the owner's name, so they are never done without
explicit approval.

### Phase 3 — Show it
- README rewritten around the forecaster; the platform becomes a labelled
  "systems demo" section.
- Results page: honest backtest + live scores, updated weekly.
- Stop. From here the work is watching scores, not building.

## Parked (not forgotten, not worked on)

- Public forecast dashboard fed by the live pipeline (first candidate after
  Phase 3; would reuse epi-engine and the app).
- Patient app and services beyond keeping them building.
- Cloud deployment configs in `deploy/free/`.

## Rules for working autonomously

- Work proceeds without asking inside the current phase.
- Stop at a checkpoint, before anything public or in the owner's name, before
  deleting anything, and when a result contradicts this file.
- Report numbers as they come out, including bad ones.
