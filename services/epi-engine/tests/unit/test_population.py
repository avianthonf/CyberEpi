"""Unit tests for Population Intelligence modules."""

import numpy as np

from src.population.hotspot import detect_hotspots
from src.population.metapop import metapop_rhs
from src.population.rt_estimator import estimate_rt


class TestRtEstimator:
    def test_rt_above_1_during_growth(self):
        # Exponential growth: 10, 20, 40, 80, 160, 320, 640, 1280
        cases = np.array([10 * 2**t for t in range(15)], dtype=float)
        res = estimate_rt(cases, window=7)
        assert res["mean"][10] > 1.0

    def test_rt_below_1_during_decline(self):
        # Exponential decline
        cases = np.array([1000 * 0.5**t for t in range(15)], dtype=float)
        res = estimate_rt(cases, window=7)
        assert res["mean"][10] < 1.0

    def test_rt_crosses_1_after_peak(self):
        # Bell curve peaked at t=7
        t = np.arange(20)
        cases = 100 * np.exp(-(t - 7)**2 / 8)
        res = estimate_rt(cases, window=7)
        # Before peak + window: Rt > 1
        assert res["mean"][7] > 1.0
        # Well after peak: Rt < 1
        assert res["mean"][15] < 1.0
        # Somewhere in between it crossed 1.0

class TestHotspotDetection:
    def test_hotspot_flagged_when_2sd_above_mean(self):
        patch_states = {f"p{i}": 10.0 for i in range(10)}
        patch_states["hot"] = 50.0 # 5SD above
        patch_growth = {pid: 1.0 for pid in patch_states} # Growing

        results = detect_hotspots(patch_states, patch_growth)
        hot_res = next(r for r in results if r["patch_id"] == "hot")
        assert hot_res["is_hotspot"] is True

    def test_declining_patch_not_flagged(self):
        patch_states = {"p1": 10.0, "hot": 50.0}
        patch_growth = {"p1": 1.0, "hot": -1.0} # Declining

        results = detect_hotspots(patch_states, patch_growth)
        hot_res = next(r for r in results if r["patch_id"] == "hot")
        # Higher than mean, but declining
        assert hot_res["is_hotspot"] is False

class TestMetapopODE:
    def test_conservation_across_patches(self):
        n_patches = 2
        y0_flat = np.array([
            990, 0, 10, 0, # S1, E1, I1, R1
            1000, 0, 0, 0  # S2, E2, I2, R2
        ], dtype=float)

        M = np.array([
            [0.9, 0.1],
            [0.2, 0.8]
        ])

        params = [{"beta": 0.5, "sigma": 0.2, "gamma": 0.1}] * 2

        dydt = metapop_rhs(0, y0_flat, params, M, n_patches)
        # Sum of rates should be zero for closed population
        assert abs(np.sum(dydt)) < 1e-10

    def test_zero_movement_decouples_patches(self):
        n_patches = 2
        y0_flat = np.array([
            900, 0, 100, 0,
            1000, 0, 0, 0
        ], dtype=float)
        M = np.eye(2) # No movement

        params = [{"beta": 0.5, "sigma": 0.2, "gamma": 0.1}] * 2
        dydt = metapop_rhs(0, y0_flat, params, M, n_patches)

        # Patch 2 has zero I and zero movement, so its rates should stay zero
        # except for maybe S->E if I_effective > 0.
        # But if M=eye, I_in_patch2 = I2 = 0.
        assert dydt[4] == 0 # dS2
        assert dydt[5] == 0 # dE2
