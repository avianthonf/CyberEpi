"""Hotspot Detection with Differential Privacy."""

from typing import Any

import numpy as np


def detect_hotspots(
    patch_states: dict[str, float],
    patch_growth_rates: dict[str, float],
    particle_ensembles: dict[str, np.ndarray] | None = None
) -> list[dict[str, Any]]:
    """
    Detect hotspots based on spatial 2-sigma threshold and positive growth rate.
    patch_states: {patch_id: I_estimate}
    patch_growth_rates: {patch_id: dI/dt}
    """
    patch_ids = list(patch_states.keys())
    I_values = np.array([patch_states[pid] for pid in patch_ids])

    mu_I = np.mean(I_values)
    sigma_I = np.std(I_values)

    threshold = mu_I + 2 * sigma_I

    results = []
    for pid in patch_ids:
        I_val = patch_states[pid]
        growth = patch_growth_rates[pid]

        # Deterministic criteria
        is_hotspot = bool((I_val > threshold) and (growth > 0))

        hotspot_prob = 0.0
        if particle_ensembles is not None and pid in particle_ensembles:
            ensemble = particle_ensembles[pid]
            # Prob = fraction of particles satisfying both criteria
            # mu and sigma are spatial, so they apply to the ensemble means?
            # Or do we recalculate mu/sigma per ensemble realization?
            # Standard way: mu/sigma are population-wide constants for this step.
            count = np.sum((ensemble > threshold) & (growth > 0)) # simplified growth check
            hotspot_prob = float(count / len(ensemble))
        else:
            hotspot_prob = 1.0 if is_hotspot else 0.0

        results.append({
            "patch_id": pid,
            "I_estimate": I_val,
            "hotspot_prob": hotspot_prob,
            "is_hotspot": is_hotspot,
            "growth_rate": growth
        })

    return results

async def apply_differential_privacy(I_values: dict[str, float], epsilon: float = 2.0) -> dict[str, float]:
    """
    Add Laplace noise to I estimates for privacy.
    I_noisy = I + Lap(0, sensitivity/epsilon)
    sensitivity = 1.0

    Implemented locally (Laplace mechanism). A remote privacy-service call is
    not made because the current privacy-service endpoint contract differs.
    """
    sensitivity = 1.0
    scale = sensitivity / epsilon
    noisy_values = {}
    for pid, val in I_values.items():
        noise = np.random.laplace(0, scale)
        noisy_values[pid] = max(0.0, float(val + noise))
    return noisy_values

async def process_hotspot_states(states) -> list[dict[str, Any]]:
    # Filter to latest unique patch states
    latest_states = {}
    for s in states:
        if s.patch_id not in latest_states:
            latest_states[s.patch_id] = s

    # Apply DP to I_estimate
    raw_I = {pid: float(s.I) for pid, s in latest_states.items()}
    noised_I = await apply_differential_privacy(raw_I)

    results = []
    for pid, s in latest_states.items():
        results.append({
            "patch_id": pid,
            "hotspot_prob": s.hotspot_prob,
            "I_estimate": noised_I[pid],
            "is_hotspot": s.hotspot_prob > 0.8 # Threshold
        })

    return results
