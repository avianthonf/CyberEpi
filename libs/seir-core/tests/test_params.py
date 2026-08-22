import pytest

from seir_core import SEIRParams


def test_invalid_N_pop():
    with pytest.raises(ValueError, match="N_pop must be greater than 0"):
        SEIRParams(
            beta=0.5, sigma=0.33, gamma=0.2, rho=0.8,
            fA=0.4, fM=0.5, fS=0.1, alpha=0.05,
            h_rate=0.15, delta=0.1, mu=0.005, mu_icu=0.2,
            gamma_A=0.25, gamma_M=0.2, gamma_S=0.15,
            gamma_H=0.1, gamma_ICU=0.07, papp=0.12, N_pop=0
        )
    with pytest.raises(ValueError, match="N_pop must be greater than 0"):
        SEIRParams(
            beta=0.5, sigma=0.33, gamma=0.2, rho=0.8,
            fA=0.4, fM=0.5, fS=0.1, alpha=0.05,
            h_rate=0.15, delta=0.1, mu=0.005, mu_icu=0.2,
            gamma_A=0.25, gamma_M=0.2, gamma_S=0.15,
            gamma_H=0.1, gamma_ICU=0.07, papp=0.12, N_pop=-100
        )

def test_invalid_parameters():
    with pytest.raises(ValueError, match="must be non-negative"):
        SEIRParams(
            beta=-0.1, sigma=0.33, gamma=0.2, rho=0.8,
            fA=0.4, fM=0.5, fS=0.1, alpha=0.05,
            h_rate=0.15, delta=0.1, mu=0.005, mu_icu=0.2,
            gamma_A=0.25, gamma_M=0.2, gamma_S=0.15,
            gamma_H=0.1, gamma_ICU=0.07, papp=0.12, N_pop=1000
        )
