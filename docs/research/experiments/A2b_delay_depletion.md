# A2b — Model 1 forward-dynamics arms: infection-to-admission delay, susceptible depletion

Status: **pre-registered 2026-11-26T03:51Z** (written before any variant code or run). Results are appended below "## Results".
Source: A2 result doc (`A2_model1_structure.md`), "Reading": the one-week filter prior is unbiased in declines (median innovation within ±0.04), so the decline bias builds in the forward run. Candidates left: the admission-delay kernel and S depletion (report 02 §0.2 item 7, §3.3).
Dev seasons only: 2023-24 and 2024-25, leave-one-season-out. 2025-26 is not used.
**ED caveat:** dev-season ED values are final-only. Any claim that depends on the ED stream is labelled ED final-only. These arms do not change the ED observation.

## Arms (all with the unmodified filter and observation layer)

- **U (unmodified):** `backtest/model_config.json`, `ili="final"`. Must be byte-identical to `backtest/results/dev_members/` EAKF files on every dev reference date (checked on 2 dates before reading results; the driver also records the full identity count).
- **DELAY:** infection-to-admission delay in the forward emission only. Daily admission incidence is `inc_t = hir·σ·E_t` (the same flow that feeds the W accumulator). Observed admissions on forward day t are `a_t = Σ_s k(t−s)·inc_s`, where `k` is a discrete Erlang-2 kernel with mean 6 days (scale 3 days per stage), normalized to sum to 1 over lags 0–30. Pre-origin incidence is back-extrapolated as a constant `inc_0` (the origin value), because the filter state does not carry the pre-origin pipeline. The weekly block forecast is the sum of `a_t` over the block's 7 days. The filter's W observation update is unchanged. Setting: one kernel, mean 6 days, no tuning.
- **DEPL:** susceptible-depletion correction in the forward dynamics only. After each forward day's random-walk noise, `LB ← LB + (γ−1)·log(S/N)` with γ = 2. This is the forward dynamics implied by an effective FOI `β·(S/N)^γ`, so it depletes transmission more strongly than the native `β·S/N` term. It is applied only in the forward emission. The filter history and observation layer are unchanged. Setting: γ = 2 only.

  **Amendment 2026-11-26T03:55Z, before any variant code ran or any result was seen:** applying `LB ← LB + (γ−1)·log(S/N)` every day compounds the correction, so β collapses with no bound. The correct form uses depletion relative to the origin, applied incrementally: each forward day `LB ← LB + (γ−1)·(log S_t − log S_{t−1})`. After t days the total shift is `(γ−1)·log(S_t/S_origin)`, so the effective FOI is `β_origin·(S_t/N)·(S_t/S_origin)^(γ−1)`. γ = 2 unchanged.

Both arms are opt-in options. Defaults (`delay_mean_days=0`, `depletion_gamma=1`) must leave the code path byte-identical to U.

## Pass criterion (same rule as A2, fixed before running)

Phase = as-of 3-week growth rule (`dev_members._phase`, threshold 0.05 log/week). Bias = median of `log((median_forecast+1)/(observed+1))` per phase and horizon. Declining-phase headline horizon is h=3.

For an arm to **pass**, on **each fold separately**:
1. **Declining cut by ≥ one third:** `|bias_arm(declining, h=3)| ≤ (2/3)·|bias_U(declining, h=3)|`, and the sign does not flip.
2. **No peak-phase cost:** `|bias_arm(peak, h)| ≤ |bias_U(peak, h)| + 0.02` for every h = 0..3.

Both folds must pass. A passing arm is reported as a **diagnostic candidate, not a change** to model 1.

Secondary, reported but not part of the decision: relWIS vs U and vs FluSight-baseline per horizon; cov50/cov90; declining and rising bias at h=0..3; runtime. Report the WIS whether or not an arm passes.

Stop rule: none beyond the pass criterion.

## Results

(to be appended)

Run 2026-11-26T03:53Z–03:56Z, after the pre-registration and amendment above. Driver `backtest/a2b_delay.py`; outputs in `backtest/results/a2b/` (summary.json, phase_bias_<season>.csv).

**Bit-identity:** U arm byte-identical to `results/dev_members` on all 57 dev reference dates. A smoke check on 4 dates (2 per season) passed before the full run. The driver's identical-rows guard confirmed both options are wired through. No ED-dependent change in either arm (ED final-only in every arm, as in U).

### Pass decision (declining h=3 cut ≥ 1/3 on both folds, no peak cost)

| Arm | Fold | declining h3 U → arm | cut ≥ 1/3? | peak cost ≤ 0.02? | Fold |
|---|---|---|---|---|---|
| DELAY (Erlang-2, mean 6 d) | 2023-24 | −0.368 → −0.141 (−62%) | yes | yes (peak h0–h3 all smaller in magnitude) | PASS |
| DELAY | 2024-25 | −0.616 → −0.320 (−48%) | yes | yes (peak h3 −0.669 → −0.400) | PASS |
| DEPL (γ = 2) | 2023-24 | −0.368 → −0.455 (worse) | no | no (h3 −0.218 → −0.396) | FAIL |
| DEPL | 2024-25 | −0.616 → −0.721 (worse) | no | no (h3 −0.669 → −0.879) | FAIL |

**Verdict: DELAY passes on both folds and is a diagnostic candidate, not a change to model 1. DEPL fails on both folds.**

### relWIS per horizon (h0, h1, h2, h3)

| Arm | 2023-24 vs U | 2023-24 vs baseline | 2024-25 vs U | 2024-25 vs baseline |
|---|---|---|---|---|
| U | 1, 1, 1, 1 | 0.738, 0.720, 0.809, 0.863 | 1, 1, 1, 1 | 0.680, 0.660, 0.666, 0.622 |
| DELAY | 0.958, 0.912, 0.892, 0.905 | 0.707, 0.657, 0.721, 0.781 | 0.989, 0.934, 0.920, 0.933 | 0.672, 0.616, 0.612, 0.580 |
| DEPL | 1.024, 1.027, 0.989, 0.959 | 0.756, 0.739, 0.800, 0.827 | 1.041, 1.048, 1.004, 0.983 | 0.708, 0.691, 0.668, 0.611 |

### Coverage cov50/cov90 (h0, h1, h2, h3)

| Arm | 2023-24 | 2024-25 |
|---|---|---|
| U | .42/.82, .46/.85, .48/.88, .50/.88 | .33/.70, .35/.73, .35/.75, .36/.76 |
| DELAY | .39/.77, .39/.77, .41/.82, .46/.84 | .32/.66, .32/.66, .36/.71, .38/.75 |
| DEPL | .42/.81, .44/.82, .43/.84, .44/.83 | .32/.68, .32/.68, .29/.66, .27/.63 |

### Reading (diagnostic; not part of the decision)

- **The forward delay explains most of the decline bias.** Without a delay, the forward run turns the current infection trajectory into admissions immediately. In a decline, admissions then fall as fast as infections, which are already further down. The kernel carries the earlier, higher infections into the forward weeks. Declining bias at h0–h3 shrinks on both folds (2024-25: −0.217/−0.345/−0.493/−0.616 → −0.090/−0.080/−0.168/−0.320). Peak bias also shrinks. WIS improves 4–11% at every horizon on both folds.
- **Costs of DELAY.** Rising-phase bias gets worse in 2023-24 (h3 −0.092 → −0.134; h0 −0.020 → −0.074) and at h0–h1 in 2024-25 (h1 −0.294 → −0.333). In a rise the kernel holds forecasts at lagged, lower infection levels. cov90 falls 1–5 points, because convolution smooths across members and narrows the spread. 2024-25 cov90 was already low (0.70–0.76).
- **Caveat on structure.** The filter's admissions observation is still undelayed (W = same-day `hir·σ·E`). Only the forward emission is delayed, so the filter and the forecast now disagree on the observation model. Before the delay becomes a model change, it should also go into the observation operator; the filter would then re-estimate HIR and β. The pre-origin incidence is back-filled as constant, which understates the delayed pipeline in declines and overstates it in rises. One kernel (mean 6 d) was run with no tuning.
- **DEPL is the wrong direction.** Extra forward depletion steepens every phase: declining h3 gets worse on both folds, and rising h3 degrades from −0.463 to −0.887 in 2024-25. The decline bias is not under-modelled depletion.
- **Runtime:** 3 arms in 192 s on 8 workers (about 64 s per arm, the same as U). The delay convolution adds no measurable cost.
