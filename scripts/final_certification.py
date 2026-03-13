import numpy as np
from seir_core import SEIRParams, seir_extended, seir_metapopulation
import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'services', 'symptom-service'))
from src.services.deterioration import DeteriorationPredictor

def test_metapopulation_conservation():
    p1 = SEIRParams(beta=0.6, sigma=0.25, gamma=0.1, rho=0.5, fA=0.3, fM=0.5, fS=0.2, alpha=0.1, h_rate=0.05, delta=0.02, mu=0.01, mu_icu=0.05, gamma_A=0.1, gamma_M=0.1, gamma_S=0.1, gamma_H=0.1, gamma_ICU=0.1, papp=0.15, N_pop=100000)
    p2 = SEIRParams(beta=0.6, sigma=0.25, gamma=0.1, rho=0.5, fA=0.3, fM=0.5, fS=0.2, alpha=0.1, h_rate=0.05, delta=0.02, mu=0.01, mu_icu=0.05, gamma_A=0.1, gamma_M=0.1, gamma_S=0.1, gamma_H=0.1, gamma_ICU=0.1, papp=0.15, N_pop=200000)
    
    params_list = [p1, p2]
    M = np.array([[0.95, 0.05], [0.1, 0.9]]) # Movement matrix (Chapter 6.1)
    
    # State: 2 patches * 9 compartments
    y0 = np.zeros(18)
    y0[0] = p1.N_pop - 100
    y0[1] = 100
    y0[9] = p2.N_pop
    
    dy = seir_metapopulation(0, y0, params_list, M)
    
    # Sum of derivatives in each patch + flux must handle mass correctly.
    # Total pop change should be zero
    total_deriv = np.sum(dy)
    assert abs(total_deriv) < 1e-7
    print(f"Metapopulation Mass Conservation: {total_deriv}")

def test_deterioration_logic():
    predictor = DeteriorationPredictor()
    features = {
        'spo2_current': 91.0,
        'spo2_slope_48h': -1.5,
        'risk_score_acceleration': 1.6
    }
    res = predictor.predict(features)
    assert res['p_hospitalization_72h'] > 0.5 # Should be triggered by SpO2 < 92 heuristic
    assert len(res['alerts']) == 2
    print("Deterioration Alerts: Correctly Triggered")

def test_behavioral_feedback():
    p = SEIRParams(beta=0.6, sigma=0.25, gamma=0.1, rho=0.5, fA=0.3, fM=0.5, fS=0.2, alpha=0.1, h_rate=0.05, delta=0.02, mu=0.01, mu_icu=0.05, gamma_A=0.1, gamma_M=0.1, gamma_S=0.1, gamma_H=0.1, gamma_ICU=0.1, papp=0.15, N_pop=100000, L_perceived=100.0)
    
    # Low prevalence
    y_low = np.array([99990, 10, 0, 0, 0, 0, 0, 0, 0])
    dy_low = seir_extended(0, y_low, p)
    
    # High prevalence
    y_high = np.array([50000, 0, 0, 10000, 40000, 0, 0, 0, 0])
    dy_high = seir_extended(0, y_high, p)
    
    # Force of infection should be suppressed in high prevalence even if S is lower
    # beta_eff = beta / (1 + 5 * I_frac * L)
    # I_frac_high = 0.5. denominator = 1 + 5 * 0.5 * 100 = 251.
    # beta_eff = 0.6 / 251 ~= 0.002
    
    print(f"Low prevalence dy[1] (E): {dy_low[1]}")
    print(f"High prevalence dy[0] (S change): {dy_high[0]}")
    assert abs(dy_high[0]) < 100.0 # Should be heavily suppressed

if __name__ == "__main__":
    test_metapopulation_conservation()
    test_deterioration_logic()
    test_behavioral_feedback()
    print("GOLD STANDARD CERTIFICATION: ALL SYSTEMS GREEN")
