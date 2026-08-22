"""Diagnostic backtest: compare production EKF vs corrected EKF vs Cori baseline.

Tests against real CDC ILINet data scaled to city-region level (N=1M).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from scipy.stats import gamma as gamma_dist

ROOT = Path("/home/avinash/Projects/CyberEpi")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services" / "epi-engine"))

from seir_core import SEIRParams
from backtest.ekf_corrected import CorrectedSEIR_EKF

# ─── Cori Rt estimator ────────────────────────────────────────────────────

def estimate_rt_cori(
    ili_series: np.ndarray,
    serial_interval_mean: float = 5.2,
    serial_interval_sd: float = 2.8,
    window: int = 7,
) -> np.ndarray:
    """Cori et al. (2013) Bayesian Rt from incidence time series."""
    T = len(ili_series)
    if T <= window:
        return np.ones(T)
    
    var = serial_interval_sd ** 2
    b_si = var / serial_interval_mean
    a_si = serial_interval_mean / b_si
    
    max_s = 25
    s_idx = np.arange(1, max_s + 1)
    w = gamma_dist.cdf(s_idx + 0.5, a_si, scale=b_si) - gamma_dist.cdf(s_idx - 0.5, a_si, scale=b_si)
    w = w / np.sum(w)
    
    rt = np.zeros(T)
    prior_a, prior_b = 1.0, 5.0
    
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

# ─── Data loading ─────────────────────────────────────────────────────────

def load_ilinet() -> tuple[np.ndarray, np.ndarray]:
    """Load ILINet national data, return (epiweeks, wili)."""
    rows = []
    with open(ROOT / "backtest" / "ilinet_national.jsonl") as f:
        for line in f:
            rows.append(json.loads(line))
    
    parsed = [(r["epiweek"], float(r["wili"]))
              for r in rows if r.get("wili") is not None]
    parsed.sort()
    
    weeks = np.array([w for w, _ in parsed], dtype=np.int64)
    wili = np.array([v for _, v in parsed], dtype=np.float64)
    
    # Forward-fill any remaining NaN
    mask = np.isnan(wili)
    if mask.any():
        wili[mask] = np.interp(weeks[mask], weeks[~mask], wili[~mask])
    
    return weeks, wili

# ─── Run backtest ─────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("CyberEpi Diagnostic Backtest — Production vs Corrected EKF")
    print("=" * 70)
    
    weeks, wili = load_ilinet()
    n_weeks = len(weeks)
    print(f"\nLoaded {n_weeks} weeks of ILINet national wili")
    print(f"  range: week {weeks[0]} to {weeks[-1]}")
    print(f"  wili range: [{wili.min():.2f}, {wili.max():.2f}]%")
    
    # Scale to city-region level (N=1M instead of 330M national)
    # ILI fraction stays the same; absolute counts scale down
    N_region = 1_000_000
    
    # Observation: weekly new symptomatic cases ~ wili × N_region / 100
    # (wili is a percentage, so divide by 100)
    obs_series = (wili / 100.0)  # ILI fraction
    
    # ─── Test 1: Cori baseline (gold standard retrospective Rt) ──────────
    print("\n[Test 1] Cori Rt on retrospective ILI (baseline)")
    # Cori expects incidence counts, not fractions
    # Convert ILI fraction to weekly incidence: fraction × N_region
    incidence = obs_series * N_region
    rt_cori = estimate_rt_cori(incidence)
    print(f"  Rt range: [{rt_cori.min():.3f}, {rt_cori.max():.3f}]")
    print(f"  Rt mean: {rt_cori.mean():.3f}")
    
    # ─── Test 2: Corrected EKF ────────────────────────────────────────────
    print("\n[Test 2] Corrected EKF with proper observation model")
    
    # Initialize SEIR params
    gamma = 1 / 5.2
    sigma = 1 / 3.0
    beta_init = 1.2 * gamma  # Rt ~ 1.2 initially
    
    params = SEIRParams(
        beta=beta_init, sigma=sigma, gamma=gamma,
        rho=1.0, fA=0.3, fM=0.5, fS=0.2,
        alpha=0.05, h_rate=0.1, delta=0.05,
        mu=0.005, mu_icu=0.1,
        gamma_A=gamma, gamma_M=gamma, gamma_S=gamma,
        gamma_H=gamma*0.5, gamma_ICU=gamma*0.3,
        papp=0.12, N_pop=N_region,
    )
    
    # Initialize state
    x0 = np.zeros(10)
    x0[0] = N_region * 0.999  # S
    x0[1] = N_region * 0.0005  # E
    x0[2] = N_region * 0.0001  # IA
    x0[3] = N_region * 0.0002  # IM
    x0[4] = N_region * 0.0001  # IS
    x0[5] = N_region * 0.00005  # H
    x0[6] = N_region * 0.00001  # ICU
    x0[7] = 0.0  # R
    x0[8] = 0.0  # D
    x0[9] = np.log(beta_init)  # log_beta
    
    # Initial covariance
    P0 = np.eye(10)
    P0[:9, :9] *= (0.01 * N_region) ** 2  # SEIR compartments
    P0[9, 9] = 0.1 ** 2  # log_beta
    
    # Process and observation noise
    Q_beta = 0.01 ** 2  # weekly random walk on log_beta
    R_obs = (0.2 * obs_series.mean()) ** 2  # 20% relative observation noise
    
    ekf = CorrectedSEIR_EKF(params, Q_beta, R_obs)
    
    x = x0.copy()
    P = P0.copy()
    rt_ekf = np.zeros(n_weeks)
    chi2_series = np.zeros(n_weeks)
    
    for t in range(n_weeks):
        x, P, innovation, chi2 = ekf.step(x, P, obs_series[t])
        rt_ekf[t] = ekf.get_Rt(x)
        chi2_series[t] = chi2
    
    print(f"  EKF Rt range: [{rt_ekf.min():.3f}, {rt_ekf.max():.3f}]")
    print(f"  EKF Rt mean: {rt_ekf.mean():.3f}")
    print(f"  Mean chi2: {chi2_series.mean():.2f}")
    
    # ─── Test 3: Compare EKF vs Cori ─────────────────────────────────────
    print("\n[Test 3] EKF vs Cori comparison")
    
    # RMSE
    rmse = np.sqrt(np.mean((rt_ekf - rt_cori) ** 2))
    print(f"  RMSE: {rmse:.3f}")
    
    # Correlation
    corr = np.corrcoef(rt_ekf, rt_cori)[0, 1]
    print(f"  Correlation: {corr:.3f}")
    
    # Lead time: first crossing of Rt=1.0
    def first_cross_above(rt):
        for t in range(1, len(rt)):
            if rt[t - 1] < 1.0 and rt[t] >= 1.0:
                return t
        return None
    
    def first_cross_below(rt):
        for t in range(1, len(rt)):
            if rt[t - 1] > 1.0 and rt[t] <= 1.0:
                return t
        return None
    
    ekf_up = first_cross_above(rt_ekf)
    cori_up = first_cross_above(rt_cori)
    ekf_down = first_cross_below(rt_ekf)
    cori_down = first_cross_below(rt_cori)
    
    if ekf_up and cori_up:
        lead_up = cori_up - ekf_up
        print(f"  EKF detects Rt>1 at week {ekf_up}, Cori at week {cori_up}")
        print(f"  Lead time (up): {lead_up} weeks")
    
    if ekf_down and cori_down:
        lead_down = cori_down - ekf_down
        print(f"  EKF detects Rt<1 at week {ekf_down}, Cori at week {cori_down}")
        print(f"  Lead time (down): {lead_down} weeks")
    
    # ─── Test 4: Per-season peak detection ───────────────────────────────
    print("\n[Test 4] Per-season Rt peak timing")
    
    seasons = []
    for yr in range(2018, 2025):
        season_start = yr * 100 + 40
        season_end = (yr + 1) * 100 + 39
        mask = (weeks >= season_start) & (weeks <= season_end)
        if mask.sum() > 20:
            seasons.append((yr, mask))
    
    for yr, mask in seasons:
        rt_c = rt_cori[mask]
        rt_e = rt_ekf[mask]
        
        idx_peak_c = int(np.argmax(rt_c))
        idx_peak_e = int(np.argmax(rt_e))
        lead = idx_peak_c - idx_peak_e
        
        print(f"  Season {yr}-{yr+1}: Cori peak idx={idx_peak_c} (Rt={rt_c.max():.2f}), "
              f"EKF peak idx={idx_peak_e} (Rt={rt_e.max():.2f}), lead={lead} weeks")
    
    # ─── Save results ─────────────────────────────────────────────────────
    output = {
        "weeks": weeks.tolist(),
        "wili": wili.tolist(),
        "rt_cori": rt_cori.tolist(),
        "rt_ekf_corrected": rt_ekf.tolist(),
        "chi2": chi2_series.tolist(),
        "metrics": {
            "rmse": float(rmse),
            "correlation": float(corr),
            "lead_up": int(lead_up) if ekf_up and cori_up else None,
            "lead_down": int(lead_down) if ekf_down and cori_down else None,
        }
    }
    
    with open(ROOT / "backtest" / "diagnostic_results.json", "w") as f:
        json.dump(output, f, indent=2)
    
    print(f"\nResults saved to backtest/diagnostic_results.json")
    
    # ─── Verdict ──────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("VERDICT")
    print("=" * 70)
    
    if rmse < 0.3 and corr > 0.7:
        print(f"✓ Corrected EKF tracks Cori Rt (RMSE={rmse:.3f}, corr={corr:.3f})")
        if ekf_up and cori_up and lead_up > 0:
            print(f"✓ EKF detects Rt>1 {lead_up} weeks BEFORE retrospective analysis")
            print("  → Filter provides real-time early warning VALUE")
        else:
            print("✗ No lead time detected — EKF is not early enough")
    elif rmse < 0.5 and corr > 0.5:
        print(f"△ Corrected EKF partially tracks Cori (RMSE={rmse:.3f}, corr={corr:.3f})")
        print("  → Filter captures trends but needs tuning")
    else:
        print(f"✗ Corrected EKF does not track Cori (RMSE={rmse:.3f}, corr={corr:.3f})")
        print("  → Observation model or process noise needs adjustment")
    
    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
