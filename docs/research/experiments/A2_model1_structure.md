# A2 — Model 1 structure diagnostics (D-1, D-3, D-2), dev seasons

Status: **pre-registered 2026-11-26T01:08Z** (written before any variant code or run). Results are appended below "## Results".
Source: SYNTHESIS §6 item 1; report 02 §0.4, §8.1–8.2 (D-0 ablation, D-2, D-3).
Dev seasons only: 2023-24 and 2024-25, leave-one-season-out. 2025-26 is not used.
**ED caveat:** dev-season ED values are final (latest-revision) hub values; no as-published ED vintage exists before 2025-11. Every D-2 result, and every claim that depends on the ED stream, is labelled "ED final-only".

## Question

Model 1 (EAKF) is too steep in declines: its declining-phase median log error is about −0.35 at h=3 in pooled dev rows, and −0.62 in 2024-25 (A3 result). Candidate structural causes: (D-3) the forward log-β random walk has no reversion, so Rt drifts away from its recent level; (D-2) the ED observation `c·I/N` has no baseline intercept. D-1 is a diagnostic: the sign and size of admissions innovations by phase, with no model change.

## Arms (all with the unmodified observation layer, A3 lag-0 multiplier off)

- **U (unmodified):** `backtest/model_config.json`, `ili="final"`. Must be byte-identical to `backtest/results/dev_members/` EAKF files on every dev reference date (checked on 2 dates before reading results; the A2 driver also records the full identity count).
- **D-1 (diagnostic, no model change):** same run as U, recording the admissions innovation `y − ȳ` (prior ensemble mean of W at the update that precedes each origin), its sign and size, by as-of phase.
- **D-2:** ED intercept. Observation becomes `c·I/N + b` with a fixed per-location baseline `b`. `b` = minimum weekly ED value in that location's previous summer (Jun–Sep of the calendar year before the season starts), using final hub values. For 2023-24 this is Jun–Sep 2023; for 2024-25 it is Jun–Sep 2024. Both are before the season's first origin, so there is no look-ahead. Leave-one-season-out: each fold's `b` is computed from its own prior summer only. ED final-only.
- **D-3(hl, anchor):** forward mean reversion of log-β. Half-life `hl` ∈ {2, 4, 8} weeks. During the forward emission only (the filter history is unchanged): after each forward day's random-walk noise, `LB ← LB + (anchor − LB)·k`, with `k = 1 − 0.5^(1/(7·hl))`. Anchor (fixed across the 4 forward weeks):
  - `trailing6` = mean over the last 6 filter weeks (up to R−7) of the posterior ensemble-mean log-β. Run at hl = 2, 4, 8.
  - `season` = mean of the posterior ensemble-mean log-β over season-to-date weeks (from the season start up to R−7). Run at hl = 4 only.

  **Amendment 2026-11-26T01:20Z, before any variant code ran or any result was seen:** the first draft anchored at the ensemble mean at the origin. The forward walk is already zero-mean around that value, so that version only shrinks spread. It would repeat report 02's D-0 arm b, which left the h3 post-peak bias unchanged (−0.346 → −0.350). The anchors above can differ from the value at the origin.

## Pass criterion (fixed before running)

Phase = as-of 3-week growth rule (`dev_members._phase`, threshold 0.05 log/week). Bias = median of `log((median_forecast+1)/(observed+1))` per phase and horizon, as in `a3_obs_error.py`. Declining-phase headline horizon is h=3 (the SYNTHESIS number).

For an arm to **pass**, on **each fold separately**:
1. **Declining cut by ≥ one third:** `|bias_arm(declining, h=3)| ≤ (2/3)·|bias_U(declining, h=3)|`, and the sign of the bias does not flip.
2. **No peak-phase cost:** `|bias_arm(peak, h)| ≤ |bias_U(peak, h)| + 0.02` for every h = 0..3.

Both folds must pass for the arm to pass. Any arm that passes is reported as a **diagnostic candidate, not a change** to model 1.

Secondary, reported but not part of the decision: relWIS vs U and vs FluSight-baseline per horizon; cov50/cov90; declining and rising bias at h=0..3; runtime; D-1 innovation sign and size by phase.

Stop rule: none beyond the pass criterion. Each arm is reported whether it passes or not.

## Results

(to be appended)

Run 2026-11-26T01:25Z–01:40Z, after the pre-registration and amendment above. Driver `backtest/a2_structure.py`; outputs in `backtest/results/a2/` (summary.json, phase_bias_<season>.csv, d1_innovation_<season>.csv). The season-anchor arm was re-run in `backtest/results/a2/season_anchor_rerun/`: in the first run `run_vintage._cfg` did not pass `beta_anchor` through, so that arm silently ran as trailing6 (identical rows). **The `D3_season_hl4` entries in the top-level `results/a2` files are invalid; use the rerun.** The driver now exits if two arms produce identical rows.

**Bit-identity:** U arm byte-identical to `results/dev_members` on all 57 dev reference dates (both runs); smoke check on 4 dates before the full run. Scoring tests pass. No origin was skipped (every dev origin has an admissions vintage). ED final-only in every arm.

### Pass decision (declining h=3 cut ≥ 1/3 on both folds, no peak cost)

| Arm | Fold | declining h3 U → arm | cut ≥ 1/3? | peak cost ≤ 0.02? | Fold |
|---|---|---|---|---|---|
| D3 trailing6 hl2 | 2023-24 | −0.368 → −0.288 (−22%) | no | no (h1 −0.079 → −0.100) | FAIL |
| D3 trailing6 hl2 | 2024-25 | −0.616 → −0.611 (−1%) | no | no (h1 −0.353 → −0.375) | FAIL |
| D3 trailing6 hl4 | 2023-24 | −0.368 → −0.316 (−14%) | no | yes | FAIL |
| D3 trailing6 hl4 | 2024-25 | −0.616 → −0.619 | no | yes | FAIL |
| D3 trailing6 hl8 | 2023-24 | −0.368 → −0.341 (−7%) | no | yes | FAIL |
| D3 trailing6 hl8 | 2024-25 | −0.616 → −0.628 | no | yes | FAIL |
| D3 season hl4 | 2023-24 | −0.368 → −0.405 (worse) | no | no (h3 −0.218 → −0.308) | FAIL |
| D3 season hl4 | 2024-25 | −0.616 → −0.742 (worse) | no | no (h3 −0.669 → −0.773) | FAIL |
| D2 (ED final-only) | 2023-24 | −0.368 → −0.368 (0%) | no | yes | FAIL |
| D2 (ED final-only) | 2024-25 | −0.616 → −0.633 (worse) | no | yes | FAIL |

**Verdict: every arm fails on both folds. No diagnostic candidate.** Model 1 is unchanged.

### relWIS per horizon (h0, h1, h2, h3)

| Arm | 2023-24 vs U | 2023-24 vs baseline | 2024-25 vs U | 2024-25 vs baseline |
|---|---|---|---|---|
| U | 1, 1, 1, 1 | 0.738, 0.720, 0.809, 0.863 | 1, 1, 1, 1 | 0.680, 0.660, 0.666, 0.622 |
| D3 t6 hl2 | 1.001, 0.992, 0.975, 0.985 | 0.739, 0.714, 0.788, 0.850 | 0.996, 0.965, 0.927, 0.893 | 0.677, 0.637, 0.617, 0.556 |
| D3 t6 hl4 | 1.000, 0.991, 0.974, 0.966 | 0.738, 0.714, 0.788, 0.833 | 0.998, 0.979, 0.952, 0.924 | 0.679, 0.646, 0.634, 0.575 |
| D3 t6 hl8 | 1.000, 0.994, 0.982, 0.973 | 0.738, 0.716, 0.794, 0.839 | 0.999, 0.988, 0.973, 0.954 | 0.679, 0.652, 0.647, 0.594 |
| D3 season hl4 | 1.008, 1.002, 0.974, 0.958 | 0.744, 0.722, 0.787, 0.826 | 1.008, 1.000, 0.974, 0.956 | 0.685, 0.660, 0.649, 0.595 |
| D2 (ED final-only) | 0.996, 1.009, 1.060, 1.125 | 0.735, 0.726, 0.857, 0.970 | 0.910, 0.949, 0.925, 0.919 | 0.619, 0.626, 0.616, 0.572 |

### Reading (diagnostic; not part of the decision)

- **D-3 improves WIS without fixing the decline bias.** Trailing-6 reversion lowers h2–h3 WIS on both folds (up to −11% at h3 in 2024-25, hl2). The gain comes from a narrower, better-placed spread and from the peak phase: 2024-25 peak h3 −0.669 → −0.617. It also deepens the rising-phase under-forecast (2024-25 rising h3 −0.463 → −0.555 at hl2). The declining h3 bias moves by at most 22% (2023-24, hl2) and by about 0% in 2024-25. The decline bias is not a forward Rt walk without reversion. A season-mean anchor pulls β toward the low early-season level and makes every phase worse.
- **D-2 (ED final-only) moves rising and peak, not declining.** The intercept b is small: median 0.0005, US 0.0015 (minimum ED share in Jun–Sep). b lifts rising and peak forecasts (2024-25 rising h3 −0.463 → −0.288; peak h3 −0.669 → −0.555) and cuts 2024-25 WIS by 5–9%. It costs 6–13% at h2–h3 in 2023-24, so it is not consistent across folds. Declining bias is unchanged or worse. Report 02's hypothesis (the missing ED baseline drives the decline bias) is not supported.
- **D-1 (innovations, U run, last admissions update before each origin, log((y+1)/(ȳ+1))):**

  | Fold | Phase | n | median | share > 0 | median abs |
  |---|---|---|---|---|---|
  | 2023-24 | declining | 647 | +0.037 | 0.55 | 0.19 |
  | 2023-24 | peak | 224 | +0.022 | 0.52 | 0.21 |
  | 2023-24 | rising | 719 | +0.008 | 0.51 | 0.21 |
  | 2024-25 | declining | 742 | −0.022 | 0.48 | 0.20 |
  | 2024-25 | peak | 100 | +0.129 | 0.71 | 0.20 |
  | 2024-25 | rising | 430 | +0.082 | 0.63 | 0.22 |

  The one-week-ahead filter prior is nearly unbiased in declines: median innovation is within ±0.04 on both folds. The −0.35 to −0.62 h3 decline bias therefore builds up over the forward horizon, not at the analysis step. Candidates left: the admission-delay kernel and S depletion in the forward dynamics (report 02 §0.2 item 7, §3.3). In 2024-25 the filter runs low in rises and at the peak (63–71% positive innovations), consistent with the rising and peak bias.
- **Runtime:** 6 arms in 354 s on 9 workers (about 59 s per arm, the same as U). Season-anchor rerun with U: 133 s. The options add no measurable cost.
