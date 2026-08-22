import pytest
from pydantic import ValidationError

from src.models.parameters import RegionParams


def test_valid_params_accepted():
    params = {
        "beta": 0.5, "sigma": 0.33, "gamma": 0.2, "rho": 0.8,
        "fA": 0.4, "fM": 0.5, "fS": 0.1, "alpha": 0.05,
        "h_rate": 0.15, "delta": 0.1, "mu": 0.005, "mu_icu": 0.2,
        "gamma_A": 0.25, "gamma_M": 0.2, "gamma_S": 0.15,
        "gamma_H": 0.1, "gamma_ICU": 0.07, "papp": 0.12, "N_pop": 1000000,
        "region_id": "test_region", "source": "manual_override"
    }
    obj = RegionParams(**params)
    assert obj.beta == 0.5

def test_fA_fM_fS_must_sum_to_1():
    params = {
        "beta": 0.5, "sigma": 0.33, "gamma": 0.2, "rho": 0.8,
        "fA": 0.5, "fM": 0.5, "fS": 0.5, # Sum = 1.5
        "alpha": 0.05, "h_rate": 0.15, "delta": 0.1, "mu": 0.005, "mu_icu": 0.2,
        "gamma_A": 0.25, "gamma_M": 0.2, "gamma_S": 0.15,
        "gamma_H": 0.1, "gamma_ICU": 0.07, "papp": 0.12, "N_pop": 1000000,
        "region_id": "test_region", "source": "manual_override"
    }
    with pytest.raises(ValidationError) as excinfo:
        RegionParams(**params)
    assert "fA + fM + fS must sum to 1.0" in str(excinfo.value)

def test_beta_out_of_range_rejected():
    params = {
        "beta": 6.0, # Max is 5.0
        "sigma": 0.33, "gamma": 0.2, "rho": 0.8,
        "fA": 0.4, "fM": 0.5, "fS": 0.1, "alpha": 0.05,
        "h_rate": 0.15, "delta": 0.1, "mu": 0.005, "mu_icu": 0.2,
        "gamma_A": 0.25, "gamma_M": 0.2, "gamma_S": 0.15,
        "gamma_H": 0.1, "gamma_ICU": 0.07, "papp": 0.12, "N_pop": 1000000,
        "region_id": "test_region", "source": "manual_override"
    }
    with pytest.raises(ValidationError):
        RegionParams(**params)

def test_N_pop_below_1000_rejected():
    params = {
        "beta": 0.5, "sigma": 0.33, "gamma": 0.2, "rho": 0.8,
        "fA": 0.4, "fM": 0.5, "fS": 0.1, "alpha": 0.05,
        "h_rate": 0.15, "delta": 0.1, "mu": 0.005, "mu_icu": 0.2,
        "gamma_A": 0.25, "gamma_M": 0.2, "gamma_S": 0.15,
        "gamma_H": 0.1, "gamma_ICU": 0.07, "papp": 0.12,
        "N_pop": 500, # Min is 1000
        "region_id": "test_region", "source": "manual_override"
    }
    with pytest.raises(ValidationError):
        RegionParams(**params)
