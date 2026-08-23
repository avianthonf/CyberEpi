# CyberEpi Backtest & Hub-Compliance Findings — Audited vs Code

Audit of the original findings list against the current code (post-fecd25b,
"no look-ahead / deterministic seed / h>=0 scoring"). Each item is marked
VERIFIED-FIXED, FALSE-ALARM, or STILL-OPEN with the fixing commit.

## 1. Look-ahead in `run_location` — FALSE ALARM (verified 2026-08-23)

The original finding claimed `run_location` saw the whole seasonal series at
once. Reading the loop (`backtest/run_flusight.py` `run_location`): the filter
steps **one week at a time** (`filt.step_week(y, ili)`), and forecasts are
emitted only after processing week `w_end`, from the current filter state
`filt.X` (`emit_rows(filt.X, ...)`). No future truth value is read before the
emission point. `emit_rows`/`forecast_quantiles` consume only the filter state
plus PRNG noise. Status: no leakage.

## 2. Missing audit directories — VERIFIED-FIXED

`backtest/out/flu/` holds all run artifacts (rows/trace/cmp/summary). Kept
git-ignored; the committed summary tables in BACKTEST_RESULTS.md are the
auditable record.

## 3. Rigid batch architecture — VERIFIED-FIXED

`run_flusight.py` now supports prospective single-origin mode:
`--reference-date YYYY-MM-DD` runs the filter through week `R-7` for the given
locations and emits hub-format rows for that origin only (see
`backtest/package_submission.py` for hub-conformant file output).

## 4. Horizon -1 rows not scored — WORKING AS INTENDED

Horizon -1 (nowcast of the already-reported week) is emitted for calibration
diagnostics but excluded from WIS/relWIS, matching FluSight hub policy
("will not be scored in summary evaluations"). The exclusion is explicit in
`summarize()` (`rows = rows[rows["horizon"] >= 0]`).

## 5. Coverage via point interpolation — VERIFIED-FIXED

`summarize()` now uses exact quantile lookup (`_q_lookup`) with `np.interp`
only as a fallback for non-standard grids. For the standard 23-level grid the
values are identical; the change removes the fragility.

## 6. No hub-conformant submission files — VERIFIED-FIXED

`backtest/package_submission.py` partitions combined rows into
`model-output/<model_id>/<reference_date>-<model_id>.csv` and renders
`model-metadata/<model_id>.yml`. `backtest/validate_submission.py` enforces
the hub schema (columns, 23 quantile levels, horizons, location codes,
target_end_date = reference_date + 7h).
