# A0 — As-of data audit (dev seasons 2023-24, 2024-25)

Scope: are the vintages used as "as-published at reference date R" actually as-published? Dev seasons only. Scripts in `/tmp/a0` (throwaway). No model code changed.

## Verdicts

| Source | Verdict | Basis |
|---|---|---|
| NHSN admissions (`wk inc flu hosp`) | **2024-25: PASS** (5 dates checked); **2023-24: UNVERIFIABLE** | Hub vintage vs Delphi v5 snapshot at the same date: 0.1–0.7% of location-weeks differ >5%, 0.6–1.7% differ at all. 2023-24 has no Delphi vintages. |
| NSSP ED visits (`wk inc flu prop ed visits`) | **FAIL** | Zero hub ED vintages before 2025-11-15 (72 versions, 2025-11-15..2026-11-25; none before 2025-06-30). Every dev-season ED pick is None. |
| Deadline rule in `pick_vintage` | **PASS** | 57/57 picks have `as_of <= R`; 0 deadline violations. |

## 1. Deadline compliance (`run_vintage.pick_vintage`)

- Dev origins: 2023-24 n=30 (2023-10-14..2024-05-04); 2024-25 n=27 (2024-11-23..2025-05-31). Every R gets a pick.
- Pick lag R − as_of: 2023-24 always 7 days; 2024-25 median 7 days, max 14 days.
- `pick_vintage` never selects a vintage published after R. PASS.
- 2024-25: all 27 origins get a pick, but only 24 distinct vintages (missing weekly versions force reuse, see §2).
- Stale picks (newest week one week older than expected): 3 of 27 in 2024-25 (R = 2024-11-30, 2024-12-14, 2025-01-11). 2023-24: 0.

## 2. Hub NHSN vintage coverage (`time-series.csv` / target-data-archive)

- 105 hub versions, 2023-09-23..2026-11-25.
- 2023-24: weekly versions through 2024-04-27.
- **Gap: no versions between 2024-04-27 and 2024-11-16.** Dev origins 2024-05 to 2024-11 cannot exist in the as-of store.
- 2024-25: missing weekly versions at 2024-12-07, 2025-01-04, 2025-01-18.
- Early versions label `max_week == as_of` (label is the week-end Saturday), so the newest-week stale check depends on that labelling.

### Revision size (hub pick vs. latest hub value, same location-week)

| Season | Share of pick cells differing from final | Share differing >5% | Share differing from first-published |
|---|---|---|---|
| 2023-24 | 0.29 (median over origins) | 0.12 (median), max 0.19 | all origins pooled: ~0.40 differ, 0.19 median >5% |
| 2024-25 | 0.18 | 0.05 | (pooled with 2023-24 above) |

Medians of absolute log difference are 0 because most cells are zero counts; the share metrics are the informative ones. Revision is large: using first-published vs final changes ~20% of cells by more than 5%.

Oracle (`oracle-output.csv` / latest hub vintage) equals the latest hub vintage exactly (8,762 cells, 0 differences). So the oracle is the final-vintage truth, not as-published.

## 3. NSSP ED-visit vintages

- Hub `target-data-archive/target-ed-visits-prop_*` and `time-series.csv` ED rows: first version 2025-11-15. No vintage at or before any dev reference date.
- `run_vintage.ed_map_at` returns None for every dev origin. With `--ili vintage`, `_run_job` hits `if not ili_map: continue` and **drops the origin silently** (no row, no trace entry). It does not fall back to final values. So `--ili vintage` on dev seasons yields no ED-informed forecasts and no record of the omission.
- `--ili final` uses final ED values for dev seasons. That is leakage-free relative to R only in the sense of values, not vintages: these are revised values presented as known at R.
- Delphi v5 NSSP snapshots: empty before 2024-04-18. Checked dates 2024-04-20..2025-02-15: nssp rows present from 2024-04-20. Hub has no NSSP vintage at any of these dates, so no hub-vs-Delphi vintage comparison is possible. Delphi snapshot vs hub-final NSSP (percent vs fraction ×100), unrounded: ~98% of cells differ at float precision (Delphi float32, 0.1-pct grid), median abs log ≈ 0, share >5% ≈ 1.5–2.8%. Not yet recomputed after rounding both sides to 0.1 pct; treat these as an upper bound, not evidence of revision.
- Deadline note: picks have as_of = R − 7 (max R − 14), i.e. before the Wednesday R − 3 submission deadline, so the stricter cutoff also passes.

## 4. Delphi v5 cross-check (NHSN)

Delphi NHSN snapshots are empty before report 2024-11-19 (2024-04-20 and 2024-11-16 returned no rows), so 2023-24 has nothing to check against. For 2024-25 the anonymous rate limit (3/min, repeated 429s) let 5 dates through. State level, weeks ≤ R − 7, hub vintage with the same date:

| Date | n | med abs log1p | share >5% | share differing |
|---|---|---|---|---|
| 2024-11-30 | 3344 | 0 | 0.0042 | 0.0063 |
| 2024-12-14 | 3448 | 0 | 0.0044 | 0.0139 |
| 2024-12-21 | 3500 | 0 | 0.0011 | 0.0100 |
| 2024-12-28 | 3552 | 0 | 0.0073 | 0.0169 |
| 2025-01-11 | 3656 | 0 | 0.0022 | 0.0145 |

The hub vintages match what Delphi recorded as public. In contrast, the Delphi snapshot vs final shows 3.5–4.5% >5% and 9–13% differing, so the hub vintages carry real as-of information. Dates after 2025-01-11 are unchecked (rate limit). Output: `/tmp/a0/delphi_vs_hub.csv`.

## 5. Fixes needed before A1–A3

1. **NSSP ED as-of:** no pre-2025-11 ED vintages exist in the hub. A1–A3 must either (a) declare ED for dev seasons as final-value only and label it so in results, or (b) obtain Delphi v5 NSSP snapshots (needs an API key; anonymous limit makes this slow). Until then, do not run `--ili vintage` on dev seasons.
2. **Silent drop in `_run_job`:** when `ili_map` is None under `--ili vintage`, the origin is skipped with no trace. Make this an explicit error or a recorded trace row.
3. **NHSN 2024-04-27..2024-11-16 gap:** dev origins in that window have no hub vintage, and Delphi v5 NHSN has nothing before 2024-11-19 either. Exclude those origins and state it.
4. **Stale picks:** 3 picks in 2024-25 use a vintage one week behind. Either tighten the pick to skip stale vintages or document them.
5. **Revision magnitude:** first-published vs final differs >5% for ~20% of cells. Any model evaluated against final values but fed first-published data should say so. Consider using the as-of store consistently for both training and scoring.
6. **Delphi key:** store an API key outside the repo for v5 bulk snapshot pulls.

## 6. Reproduction

Scripts (throwaway, not in repo): `/tmp/a0/hub_audit.py` (pick replay), `quant_hub.py`, `quant_ed.py`, `oracle_check.py`, `fetch.py` (Delphi snapshots), `compare_delphi.py`.
