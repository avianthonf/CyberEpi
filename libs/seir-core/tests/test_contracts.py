"""Contract tests for seir_core public API.

These tests pin observable behavioral promises — not implementation details.
Each test must fail on any plausible regression of the documented contract.
"""

import numpy as np
import pytest

from seir_core import (
    SEIRParams,
    compute_load,
    compute_R0,
    compute_Rt,
    run_seir,
    seir_base,
    seir_extended,
)
from seir_core.seir import behavioral_contact_factor, seir_metapopulation

# ---------------------------------------------------------------------------
# Canonical fixture — reused across all tests for determinism
# ---------------------------------------------------------------------------


@pytest.fixture
def params():
    return SEIRParams(
        beta=0.5,
        sigma=0.33,
        gamma=0.2,
        rho=0.8,
        fA=0.4,
        fM=0.5,
        fS=0.1,
        alpha=0.05,
        h_rate=0.15,
        delta=0.1,
        mu=0.005,
        mu_icu=0.2,
        gamma_A=0.25,
        gamma_M=0.2,
        gamma_S=0.15,
        gamma_H=0.1,
        gamma_ICU=0.07,
        papp=0.12,
        N_pop=1_000_000,
    )


# ---------------------------------------------------------------------------
# 1. SEIRParams validation
# ---------------------------------------------------------------------------


class TestSEIRParamsValidation:
    def _base_kwargs(self):
        return dict(
            beta=0.5,
            sigma=0.33,
            gamma=0.2,
            rho=0.8,
            fA=0.4,
            fM=0.5,
            fS=0.1,
            alpha=0.05,
            h_rate=0.15,
            delta=0.1,
            mu=0.005,
            mu_icu=0.2,
            gamma_A=0.25,
            gamma_M=0.2,
            gamma_S=0.15,
            gamma_H=0.1,
            gamma_ICU=0.07,
            papp=0.12,
            N_pop=1000,
        )

    def test_rejects_N_pop_zero(self):
        kw = self._base_kwargs()
        kw["N_pop"] = 0
        with pytest.raises(ValueError):
            SEIRParams(**kw)

    def test_rejects_N_pop_negative(self):
        kw = self._base_kwargs()
        kw["N_pop"] = -1
        with pytest.raises(ValueError):
            SEIRParams(**kw)

    def test_rejects_negative_beta(self):
        kw = self._base_kwargs()
        kw["beta"] = -0.01
        with pytest.raises(ValueError):
            SEIRParams(**kw)

    def test_rejects_negative_sigma(self):
        kw = self._base_kwargs()
        kw["sigma"] = -1.0
        with pytest.raises(ValueError):
            SEIRParams(**kw)

    def test_rejects_negative_gamma(self):
        kw = self._base_kwargs()
        kw["gamma"] = -0.1
        with pytest.raises(ValueError):
            SEIRParams(**kw)

    def test_rejects_fractions_not_summing_to_one(self):
        # fA + fM + fS = 0.9, clearly wrong
        kw = self._base_kwargs()
        kw["fA"] = 0.3
        kw["fM"] = 0.3
        kw["fS"] = 0.3
        with pytest.raises(ValueError):
            SEIRParams(**kw)

    def test_rejects_fractions_exceeding_one(self):
        kw = self._base_kwargs()
        kw["fA"] = 0.5
        kw["fM"] = 0.5
        kw["fS"] = 0.1  # sum = 1.1
        with pytest.raises(ValueError):
            SEIRParams(**kw)

    def test_accepts_zero_rates(self):
        # Zero rates are mathematically degenerate but valid inputs
        kw = self._base_kwargs()
        kw["beta"] = 0.0
        p = SEIRParams(**kw)
        assert p.beta == 0.0

    def test_accepts_exact_fraction_sum(self):
        # Exact float: 0.4 + 0.5 + 0.1 = 1.0 — must not raise
        kw = self._base_kwargs()
        p = SEIRParams(**kw)
        assert p.fA + p.fM + p.fS == pytest.approx(1.0)

    def test_frozen(self):
        kw = self._base_kwargs()
        p = SEIRParams(**kw)
        with pytest.raises((AttributeError, TypeError)):
            p.beta = 99.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 2. seir_base — shape and conservation
# ---------------------------------------------------------------------------


class TestSeirBase:
    def test_output_shape(self):
        y = np.array([990.0, 5.0, 3.0, 2.0])
        result = seir_base(0.0, y, beta=0.3, sigma=0.2, gamma=0.1, N=1000)
        assert result.shape == (4,)

    def test_returns_ndarray(self):
        y = np.array([990.0, 5.0, 3.0, 2.0])
        result = seir_base(0.0, y, beta=0.3, sigma=0.2, gamma=0.1, N=1000)
        assert isinstance(result, np.ndarray)

    def test_population_conserving(self):
        # Sum of derivatives must be 0 — no population enters or leaves
        y = np.array([900.0, 50.0, 30.0, 20.0])
        result = seir_base(0.0, y, beta=0.5, sigma=0.33, gamma=0.2, N=1000)
        assert result.sum() == pytest.approx(0.0, abs=1e-12)

    def test_conservation_at_equilibrium(self):
        # Disease-free state: only S filled, derivatives all zero
        y = np.array([1000.0, 0.0, 0.0, 0.0])
        result = seir_base(0.0, y, beta=0.5, sigma=0.33, gamma=0.2, N=1000)
        assert result.sum() == pytest.approx(0.0, abs=1e-12)

    def test_conservation_t_independent(self):
        # ODE is autonomous — t argument does not change the result
        y = np.array([800.0, 100.0, 60.0, 40.0])
        r0 = seir_base(0.0, y, beta=0.4, sigma=0.25, gamma=0.15, N=1000)
        r7 = seir_base(7.0, y, beta=0.4, sigma=0.25, gamma=0.15, N=1000)
        np.testing.assert_array_equal(r0, r7)


# ---------------------------------------------------------------------------
# 3. seir_extended — shape and conservation
# ---------------------------------------------------------------------------


class TestSeirExtended:
    def test_output_shape(self, params):
        y = np.array([params.N_pop - 10, 10, 0, 0, 0, 0, 0, 0, 0], dtype=float)
        result = seir_extended(0.0, y, params)
        assert result.shape == (9,)

    def test_returns_ndarray(self, params):
        y = np.array([params.N_pop - 10, 10, 0, 0, 0, 0, 0, 0, 0], dtype=float)
        result = seir_extended(0.0, y, params)
        assert isinstance(result, np.ndarray)

    def test_population_conserving_no_control(self, params):
        # Without vaccination (u2=0), total population is conserved: sum(dy/dt) == 0
        y = np.array([params.N_pop - 100, 50, 20, 15, 10, 3, 1, 1, 0], dtype=float)
        result = seir_extended(0.0, y, params)
        assert result.sum() == pytest.approx(0.0, abs=1e-10)

    def test_population_conserving_with_control(self, params):
        # With isolation+mask control, vaccination moves S→R but total still conserved
        y = np.array([params.N_pop - 100, 50, 20, 15, 10, 3, 1, 1, 0], dtype=float)
        u = np.array([0.3, 0.0, 0.5])  # isolation + masks, no vaccination
        result = seir_extended(0.0, y, params, u=u)
        assert result.sum() == pytest.approx(0.0, abs=1e-10)

    def test_disease_free_gives_zero_derivatives(self, params):
        # No exposed or infectious: all derivatives must be zero
        y = np.array([float(params.N_pop), 0, 0, 0, 0, 0, 0, 0, 0])
        result = seir_extended(0.0, y, params)
        np.testing.assert_allclose(result, 0.0, atol=1e-12)


# ---------------------------------------------------------------------------
# 4. run_seir — non-negativity, conservation, shape consistency
# ---------------------------------------------------------------------------


class TestRunSeir:
    def test_non_negativity(self, params):
        y0 = np.array([params.N_pop - 10, 10, 0, 0, 0, 0, 0, 0, 0], dtype=float)
        res = run_seir(y0, (0, 30), np.linspace(0, 30, 31), params)
        assert np.all(res.y >= 0)

    def test_population_conservation(self, params):
        y0 = np.array([params.N_pop - 10, 10, 0, 0, 0, 0, 0, 0, 0], dtype=float)
        res = run_seir(y0, (0, 30), np.linspace(0, 30, 31), params)
        # Each column sums to N_pop within 1 person
        column_sums = res.y.sum(axis=0)
        assert np.all(np.abs(column_sums - params.N_pop) < 1.0)

    def test_t_and_y_length_match(self, params):
        t_eval = np.linspace(0, 20, 41)
        y0 = np.array([params.N_pop - 5, 5, 0, 0, 0, 0, 0, 0, 0], dtype=float)
        res = run_seir(y0, (0, 20), t_eval, params)
        assert len(res.t) == res.y.shape[1]

    def test_t_eval_respected(self, params):
        t_eval = np.linspace(0, 15, 16)
        y0 = np.array([params.N_pop - 5, 5, 0, 0, 0, 0, 0, 0, 0], dtype=float)
        res = run_seir(y0, (0, 15), t_eval, params)
        assert len(res.t) == 16

    def test_solver_result_has_message(self, params):
        y0 = np.array([params.N_pop - 5, 5, 0, 0, 0, 0, 0, 0, 0], dtype=float)
        res = run_seir(y0, (0, 10), None, params)
        assert isinstance(res.message, str)
        assert len(res.message) > 0

    def test_nan_y0_raises_runtime_error(self, params):
        y0 = np.array([np.nan, 0, 0, 0, 0, 0, 0, 0, 0], dtype=float)
        with pytest.raises(RuntimeError):
            run_seir(y0, (0, 10), None, params)

    def test_disease_free_stays_disease_free(self, params):
        # No exposed or infectious: all compartments except S remain zero
        y0 = np.array([float(params.N_pop), 0, 0, 0, 0, 0, 0, 0, 0])
        t_eval = np.linspace(0, 30, 31)
        res = run_seir(y0, (0, 30), t_eval, params)
        np.testing.assert_allclose(res.y[0, :], params.N_pop, atol=1e-6)
        np.testing.assert_allclose(res.y[1:, :], 0.0, atol=1e-6)


# ---------------------------------------------------------------------------
# 5. compute_R0 and compute_Rt
# ---------------------------------------------------------------------------


class TestR0Rt:
    def test_R0_positive(self, params):
        r0 = compute_R0(params)
        assert r0 > 0

    def test_R0_scales_with_beta(self, params):
        # Doubling beta must double R0 (linear relationship)
        r0_base = compute_R0(params)
        kw = params.__dict__.copy()
        kw["beta"] *= 2
        r0_double = compute_R0(SEIRParams(**kw))
        assert r0_double == pytest.approx(r0_base * 2, rel=1e-9)

    def test_Rt_equals_R0_times_S_over_N(self, params):
        S = 600_000.0
        N = float(params.N_pop)
        rt = compute_Rt(params, S, N)
        r0 = compute_R0(params)
        assert rt == pytest.approx(r0 * S / N, rel=1e-12)

    def test_Rt_equals_R0_when_fully_susceptible(self, params):
        # At S = N the effective R equals R0
        N = float(params.N_pop)
        rt = compute_Rt(params, N, N)
        r0 = compute_R0(params)
        assert rt == pytest.approx(r0, rel=1e-12)

    def test_Rt_zero_at_zero_susceptible(self, params):
        rt = compute_Rt(params, 0.0, float(params.N_pop))
        assert rt == pytest.approx(0.0, abs=1e-12)

    def test_Rt_proportional_to_S(self, params):
        N = float(params.N_pop)
        rt_half = compute_Rt(params, N / 2, N)
        rt_full = compute_Rt(params, N, N)
        assert rt_half == pytest.approx(rt_full / 2, rel=1e-12)


# ---------------------------------------------------------------------------
# 6. compute_load
# ---------------------------------------------------------------------------


class TestComputeLoad:
    def test_load_equals_H_plus_ICU(self):
        y = np.zeros((9, 5))
        y[5, :] = 100.0  # H
        y[6, :] = 50.0  # ICU
        load = compute_load(y)
        np.testing.assert_array_equal(load, 150.0)

    def test_load_ignores_other_compartments(self):
        y = np.ones((9, 3)) * 999.0
        y[5, :] = 10.0
        y[6, :] = 20.0
        load = compute_load(y)
        np.testing.assert_array_equal(load, 30.0)

    def test_load_zero_when_no_hospitalised(self):
        y = np.zeros((9, 4))
        y[0, :] = 1000.0  # everyone susceptible
        load = compute_load(y)
        np.testing.assert_array_equal(load, 0.0)

    def test_load_shape_matches_time_axis(self):
        T = 17
        y = np.zeros((9, T))
        y[5, :] = np.arange(T, dtype=float)
        y[6, :] = 1.0
        load = compute_load(y)
        assert load.shape == (T,)

    def test_load_single_timestep(self):
        y = np.zeros((9, 1))
        y[5, 0] = 7.0
        y[6, 0] = 3.0
        load = compute_load(y)
        assert load[0] == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# 7. behavioral_contact_factor
# ---------------------------------------------------------------------------


class TestBehavioralContactFactor:
    def test_returns_one_when_L_zero(self):
        assert behavioral_contact_factor(0.05, 0.0) == 1.0

    def test_returns_one_when_L_negative(self):
        assert behavioral_contact_factor(0.05, -1.0) == 1.0

    def test_returns_one_when_I_frac_zero(self):
        assert behavioral_contact_factor(0.0, 5.0) == 1.0

    def test_returns_one_when_I_frac_negative(self):
        assert behavioral_contact_factor(-0.01, 5.0) == 1.0

    def test_returns_one_at_both_zero(self):
        assert behavioral_contact_factor(0.0, 0.0) == 1.0

    def test_below_one_when_both_positive(self):
        result = behavioral_contact_factor(0.1, 1.0)
        assert result < 1.0

    def test_decreases_as_L_increases(self):
        # Higher perceived loss → stronger behavioural reduction
        r_low = behavioral_contact_factor(0.1, 1.0)
        r_high = behavioral_contact_factor(0.1, 5.0)
        assert r_high < r_low

    def test_decreases_as_I_frac_increases(self):
        r_low = behavioral_contact_factor(0.05, 2.0)
        r_high = behavioral_contact_factor(0.20, 2.0)
        assert r_high < r_low

    def test_positive(self):
        # Factor is always a probability-like value in (0, 1]
        result = behavioral_contact_factor(0.5, 10.0)
        assert 0.0 < result <= 1.0

    def test_exact_formula(self):
        # Regression-pin the formula: 1 / (1 + 5 * I_frac * L)
        I_frac, L = 0.1, 2.0
        expected = 1.0 / (1.0 + 5.0 * I_frac * L)
        assert behavioral_contact_factor(I_frac, L) == pytest.approx(expected)


# ---------------------------------------------------------------------------
# 8. seir_metapopulation — output shape and global conservation
# ---------------------------------------------------------------------------


class TestSeirMetapopulation:
    def test_output_shape(self, params):
        n = 3
        y = np.zeros(n * 9)
        # Give each patch a population
        for i in range(n):
            y[i * 9] = params.N_pop  # all susceptible
        M = np.zeros((n, n))
        result = seir_metapopulation(0.0, y, [params] * n, M)
        assert result.shape == (n * 9,)

    def test_population_globally_conserved(self, params):
        # Without migration and with no initial infection, derivatives sum to 0
        n = 2
        y = np.zeros(n * 9)
        y[0] = 900.0
        y[9] = 800.0
        M = np.zeros((n, n))
        result = seir_metapopulation(0.0, y, [params] * n, M)
        assert result.sum() == pytest.approx(0.0, abs=1e-10)

    def test_migration_conserves_global_population(self, params):
        # With migration, cross-patch fluxes are antisymmetric → global sum still 0
        n = 2
        y = np.zeros(n * 9)
        y[0] = 990.0  # patch 0 S
        y[1] = 10.0  # patch 0 E
        y[9] = 1000.0  # patch 1 S
        M = np.array([[0.0, 0.05], [0.02, 0.0]])
        result = seir_metapopulation(0.0, y, [params] * n, M)
        assert result.sum() == pytest.approx(0.0, abs=1e-10)
