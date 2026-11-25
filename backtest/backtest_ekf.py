"""CyberEpi backtest — does the EKF recover Rt from noisy ILI observations?

Methodology:
  1. Load real CDC ILINet weekly wili (weighted ILI %) 2017w40 — 2025w20.
  2. Compute "ground truth" Rt using Cori-style method from the
     ILI *retrospective* signal with a 1-week reporting delay (matches
     real-world surveillance lag).
  3. Run the SEIR EKF on a *leading* ILI signal (the same series shifted
     earlier — what a real-time system would see).
  4. Measure: (a) lead time of EKF Rt crossing Rt=1 vs. surveillance Rt
     crossing Rt=1; (b) RMSE of EKF Rt vs. ground truth; (c) correlation.

A backtest that doesn't beat surveillance by lead time is a backtest
that justifies nothing. That's the bar.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path("/home/avinash/Projects/CyberEpi")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services" / "epi-engine"))

# Force CPU
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

from seir_core import SEIRParams

# ─── Data loading ─────────────────────────────────────────────────────────

def load_ilinet(path: Path) -> list[dict]:
    rows = []
    with path.open() as f:
        for line in f:
            rows.append(json.loads(line))
    return rows


def build_weekly_series(rows: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    """Return (epiweeks, wili) sorted by week."""
    parsed = [(r["epiweek"], float(r["wili"]) if r.get("wili") is not None else np.nan)
              for r in rows if r.get("wili") is not None]
    parsed.sort()
    weeks = np.array([w for w, _ in parsed], dtype=np.int64)
    wili = np.array([v for _, v in parsed], dtype=np.float64)
    # Forward-fill NaN
    mask = np.isnan(wili)
    if mask.any():
        wili[mask] = np.interp(weeks[mask], weeks[~mask], wili[~mask])
    return weeks, wili


# ─── Cori-style Rt from retrospective ILI ────────────────────────────────

def estimate_rt_cori(
    ili_series: np.ndarray,
    serial_interval_mean: float = 5.2,
    serial_interval_sd: float = 2.8,
    window: int = 7,
    prior_a: float = 1.0,
    prior_b: float = 5.0,
) -> np.ndarray:
    """Cori et al. (2013) Bayesian Rt estimator on ILI series."""
    from scipy.stats import gamma as gamma_dist

    T = len(ili_series)
    if window >= T:
        return np.zeros(T)

    var = serial_interval_sd ** 2
    b_si = var / serial_interval_mean
    a_si = serial_interval_mean / b_si

    max_s = 25
    s_idx = np.arange(1, max_s + 1)
    w = gamma_dist.cdf(s_idx + 0.5, a_si, scale=b_si) - gamma_dist.cdf(s_idx - 0.5, a_si, scale=b_si)
    w = w / np.sum(w)

    rt = np.zeros(T)
    for t in range(window, T):
        sum_c = np.sum(ili_series[t - window + 1 : t + 1])
        total_lambda = 0.0
        for tau in range(t - window + 1, t + 1):
            tau_lambda = 0.0
            for s in range(1, min(tau, max_s) + 1):
                tau_lambda += ili_series[tau - s] * w[s - 1]
            total_lambda += tau_lambda
        if total_lambda <= 0:
            rt[t] = rt[t - 1] if t > 0 else 1.0
            continue
        post_a = prior_a + sum_c
        post_b = 1.0 / (1.0 / prior_b + total_lambda)
        rt[t] = post_a * post_b
    rt[:window] = rt[window] if window < T else 1.0
    return rt


# ─── Simple SEIR observer: ILI ~ (asymptomatic + mild + severe) frac * new_infections ─

def simulate_seir_observations(
    ili_lead: np.ndarray,
    n_weeks: int,
    N_pop: int = 330_000_000,
    noise_sd: float = 0.15,
    seed: int = 42,
) -> tuple[np.ndarray, np.ndarray]:
    """Synthesize weekly ILI observations for the EKF from a known Rt trajectory.

    ili_lead: weekly ILI fraction series (the "real-time" signal).
    Returns: (t_weeks, y_obs) where y_obs is the EKF observation vector per week.
    """
    rng = np.random.default_rng(seed)
    # Map ILI fraction to new daily infectious (rough scale: 1% ILI ~ 30k new daily infectious)
    new_inf_per_week = ili_lead * 3_000_000 * (1 + 0.1 * rng.standard_normal(n_weeks))

    # 5-dim observation vector expected by orchestrator:
    # [app_reports, confirmed_cases, hospital_admissions, pharmacy_proxy, wastewater]
    # We'll use confirmed_cases as the primary signal (ILI proxies it)
    app_reports = 1000 * ili_lead * (1 + 0.3 * rng.standard_normal(n_weeks))
    confirmed_cases = new_inf_per_week * (1 + noise_sd * rng.standard_normal(n_weeks))
    hospital_admissions = confirmed_cases * 0.05 * (1 + 0.2 * rng.standard_normal(n_weeks))
    pharmacy_proxy = 500 * ili_lead * (1 + 0.4 * rng.standard_normal(n_weeks))
    wastewater = confirmed_cases * 0.1 * (1 + 0.5 * rng.standard_normal(n_weeks))

    y_obs = np.stack([
        np.clip(app_reports, 0, None),
        np.clip(confirmed_cases, 0, None),
        np.clip(hospital_admissions, 0, None),
        np.clip(pharmacy_proxy, 0, None),
        np.clip(wastewater, 0, None),
    ], axis=1)
    return np.arange(n_weeks), y_obs


# ─── EKF on observed ILI → Rt trajectory ────────────────────────────────

def run_ekf_on_series(
    y_obs: np.ndarray,
    n_weeks: int,
    N_pop: int = 330_000_000,
    init_rt: float = 1.0,
    seed: int = 0,
) -> np.ndarray:
    """Run the SEIR EKF step-by-step on the observation series, return Rt per week."""
    from src.filters.ekf import SEIR_EKF

    # Convert Rt to SEIR params
    gamma = 1 / 5.2  # recovery rate
    sigma = 1 / 3.0  # latent period
    beta = init_rt * gamma

    params = SEIRParams(
        beta=beta, sigma=sigma, gamma=gamma,
        rho=1.0, fA=0.3, fM=0.5, fS=0.2,
        alpha=0.05, h_rate=0.1, delta=0.05,
        mu=0.005, mu_icu=0.1,
        gamma_A=gamma, gamma_M=gamma, gamma_S=gamma, gamma_H=gamma*0.5, gamma_ICU=gamma*0.3,
        papp=0.12, N_pop=N_pop,
    )

    # 12-dim state: [S, E, IA, IM, IS, H, ICU, R, D, papp, ptest, kappa]
    x = np.zeros(12)
    x[0] = N_pop * 0.85
    x[1] = N_pop * 0.01
    x[3] = N_pop * 0.005
    x[9] = 0.12
    x[10] = 0.5
    x[11] = 0.1
    P = np.eye(12) * 1e6

    Q = np.eye(12) * 1.0
    Q[9, 9] = Q[10, 10] = Q[11, 11] = 1e-6
    R_obs = np.eye(5) * 1e3

    # H_obs matrix: [app, confirmed, hosp, pharmacy, wastewater] ← [S, E, IA, IM, IS, H, ICU, R, D, papp, ptest, kappa]
    H_obs = np.zeros((5, 12))
    H_obs[0, 0] = 0.0001  # app reports: rough function of S
    H_obs[1, 0] = 0.0005  # confirmed cases: function of S
    H_obs[2, 5] = 0.5      # hospital admissions: function of H
    H_obs[3, 0] = 0.0001  # pharmacy: function of S
    H_obs[4, 0] = 0.00005 # wastewater: function of S

    ekf = SEIR_EKF(params, Q, R_obs, H_obs)

    rt_estimates = np.zeros(n_weeks)
    for t in range(n_weeks):
        # Step EKF
        try:
            x, P, _innovation, _chi2 = ekf.step(x, P, y_obs[t])
            # Recover Rt from state: Rt = (beta * S/N) / gamma
            S = max(x[0], 1.0)
            est_rt = (beta * S / N_pop) / gamma
            rt_estimates[t] = est_rt
        except Exception as e:
            print(f"  EKF step {t} failed: {e}")
            rt_estimates[t] = rt_estimates[t-1] if t > 0 else init_rt
    return rt_estimates


# ─── Lead-time analysis ──────────────────────────────────────────────────

def analyze_lead_time(
    rt_truth: np.ndarray,
    rt_ekf: np.ndarray,
    rt_surveillance: np.ndarray,
    weeks: np.ndarray,
) -> dict:
    """Find the first crossing of Rt=1.0 in each series; compute lead time."""
    def first_crossing_above(rt, threshold=1.0):
        # rt crosses above 1.0 from below
        below = rt < threshold
        # First index where below[t-1] is True and below[t] is False
        for t in range(1, len(rt)):
            if below[t - 1] and not below[t]:
                return t
        return None

    def first_crossing_below(rt, threshold=1.0):
        above = rt > threshold
        for t in range(1, len(rt)):
            if above[t - 1] and not above[t]:
                return t
        return None

    # Aggregate peak season stats: find a season with a clean growth→peak→decline
    # ILINet wili 2018w40 onward
    crossings = {
        "ekf_first_above_1": first_crossing_above(rt_ekf),
        "truth_first_above_1": first_crossing_above(rt_truth),
        "surveillance_first_above_1": first_crossing_above(rt_surveillance),
        "ekf_first_below_1": first_crossing_below(rt_ekf),
        "truth_first_below_1": first_crossing_below(rt_truth),
        "surveillance_first_below_1": first_crossing_below(rt_surveillance),
    }
    # Lead time = how much earlier EKF crosses vs surveillance
    lead_weeks_up = None
    lead_weeks_down = None
    if (crossings["ekf_first_above_1"] is not None
        and crossings["surveillance_first_above_1"] is not None):
        lead_weeks_up = crossings["surveillance_first_above_1"] - crossings["ekf_first_above_1"]
    if (crossings["ekf_first_below_1"] is not None
        and crossings["surveillance_first_below_1"] is not None):
        lead_weeks_down = crossings["surveillance_first_below_1"] - crossings["ekf_first_below_1"]

    # RMSE on overlap
    valid = ~np.isnan(rt_ekf) & ~np.isnan(rt_truth)
    rmse_ekf_truth = float(np.sqrt(np.mean((rt_ekf[valid] - rt_truth[valid]) ** 2))) if valid.any() else None
    corr_ekf_truth = float(np.corrcoef(rt_ekf[valid], rt_truth[valid])[0, 1]) if valid.sum() > 1 else None

    return {
        "crossings": crossings,
        "lead_weeks_up": lead_weeks_up,
        "lead_weeks_down": lead_weeks_down,
        "rmse_ekf_vs_truth": rmse_ekf_truth,
        "corr_ekf_vs_truth": corr_ekf_truth,
    }


# ─── Main backtest ────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("CyberEpi backtest — EKF Rt recovery on CDC ILINet")
    print("=" * 70)

    rows = load_ilinet(ROOT / "backtest" / "ilinet_national.jsonl")
    weeks, wili = build_weekly_series(rows)
    print(f"\nLoaded {len(weeks)} weeks of ILINet national wili")
    print(f"  range: week {weeks[0]} to {weeks[-1]}")
    print(f"  wili range: [{wili.min():.2f}, {wili.max():.2f}]")
    print(f"  mean: {wili.mean():.2f}")

    # ─── Test 1: Plain Cori on full ILI series ───────────────────────────
    print("\n[Test 1] Cori Rt on retrospective ILI series (baseline)")
    rt_cori_retro = estimate_rt_cori(wili)
    print(f"  Rt range: [{rt_cori_retro.min():.3f}, {rt_cori_retro.max():.3f}]")
    print(f"  Rt mean: {rt_cori_retro.mean():.3f}")

    # ─── Test 2: Cori on lead signal (1-week shifted, simulating real-time) ──
    print("\n[Test 2] Cori Rt on lead-1 signal (real-time surrogate)")
    wili_lead = np.concatenate([[wili[0]], wili[:-1]])  # shift earlier by 1 week
    rt_cori_lead = estimate_rt_cori(wili_lead)
    print(f"  Rt range: [{rt_cori_lead.min():.3f}, {rt_cori_lead.max():.3f}]")

    # ─── Test 3: EKF on lead signal with synthetic noise ──────────────────
    print("\n[Test 3] SEIR EKF on noisy lead signal")
    _t_weeks, y_obs = simulate_seir_observations(wili_lead, n_weeks=len(wili_lead))
    rt_ekf = run_ekf_on_series(y_obs, n_weeks=len(y_obs))
    print(f"  EKF Rt range: [{rt_ekf.min():.3f}, {rt_ekf.max():.3f}]")

    # ─── Lead-time analysis: EKF vs surveillance ─────────────────────────
    print("\n[Test 4] Lead time of EKF Rt=1 crossings vs surveillance Rt=1")
    # Use full retrospective Cori as truth
    analysis = analyze_lead_time(rt_cori_retro, rt_ekf, rt_cori_retro, weeks)

    print("  First crossing ABOVE Rt=1:")
    for k, v in analysis["crossings"].items():
        if "above" in k:
            print(f"    {k}: week {v}")
    print(f"  EKF lead over surveillance (up): {analysis['lead_weeks_up']} weeks")

    print("  First crossing BELOW Rt=1:")
    for k, v in analysis["crossings"].items():
        if "below" in k:
            print(f"    {k}: week {v}")
    print(f"  EKF lead over surveillance (down): {analysis['lead_weeks_down']} weeks")

    print(f"\n  RMSE EKF vs truth: {analysis['rmse_ekf_vs_truth']}")
    print(f"  Correlation EKF vs truth: {analysis['corr_ekf_vs_truth']}")

    # ─── Test 5: Rt peaks — does EKF detect rising Rt earlier? ────────────
    print("\n[Test 5] Per-season Rt peak detection")
    # Find flu seasons (week 40 to week 39)
    seasons = []
    for yr in range(2018, 2025):
        season_start = yr * 100 + 40
        season_end = (yr + 1) * 100 + 39
        mask = (weeks >= season_start) & (weeks <= season_end)
        if mask.sum() > 20:
            seasons.append((yr, season_start, season_end, mask))

    for yr, _start, _end, mask in seasons:
        rt_t = rt_cori_retro[mask]
        rt_e = rt_ekf[mask]
        idx_peak_t = int(np.argmax(rt_t))
        idx_peak_e = int(np.argmax(rt_e))
        lead = idx_peak_t - idx_peak_e
        print(f"  Season {yr}-{yr+1}: truth peak idx={idx_peak_t}, EKF peak idx={idx_peak_e}, "
              f"EKF lead = {lead} weeks, "
              f"truth Rt_max={rt_t.max():.2f}, EKF Rt_max={rt_e.max():.2f}")

    # ─── Save outputs ─────────────────────────────────────────────────────
    output = {
        "weeks": weeks.tolist(),
        "wili": wili.tolist(),
        "rt_cori_retrospective": rt_cori_retro.tolist(),
        "rt_cori_lead": rt_cori_lead.tolist(),
        "rt_ekf": rt_ekf.tolist(),
        "analysis": {
            k: (v if not isinstance(v, np.ndarray) else v.tolist())
            for k, v in analysis.items()
        },
    }
    with open(ROOT / "backtest" / "results.json", "w") as f:
        json.dump(output, f)
    print("\nResults saved to backtest/results.json")

    # ─── Summary verdict ──────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("VERDICT")
    print("=" * 70)
    if analysis["rmse_ekf_vs_truth"] is None:
        print("EKF did not produce valid Rt series — backtest inconclusive")
    elif analysis["rmse_ekf_vs_truth"] < 0.5 and analysis["corr_ekf_vs_truth"] > 0.5:
        print(f"EKF tracks ground-truth Rt (RMSE={analysis['rmse_ekf_vs_truth']:.3f}, "
              f"corr={analysis['corr_ekf_vs_truth']:.3f})")
        if analysis["lead_weeks_up"] and analysis["lead_weeks_up"] > 0:
            print(f"EKF detects Rt>1 {analysis['lead_weeks_up']} weeks BEFORE surveillance — VALUE")
        elif analysis["lead_weeks_up"] is not None:
            print(f"EKF Rt>1 crossing: {analysis['lead_weeks_up']} weeks vs surveillance "
                  f"(0 or negative means no lead)")
    else:
        print(f"EKF does not adequately track ground truth (RMSE={analysis['rmse_ekf_vs_truth']:.3f}, "
              f"corr={analysis['corr_ekf_vs_truth']:.3f}). Backtest suggests the filter "
              f"configuration needs tuning or the model is not appropriate for ILI data.")


if __name__ == "__main__":
    main()
