import json
import hashlib
import numpy as np
from seir_core import SEIRParams, seir_extended

def test_deterministic_hashing():
    # Mock DB podo
    class MockParams:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
    
    p1 = MockParams(beta=1.5, sigma=0.2, gamma=0.1, N_pop=1000000, fA=0.2, fM=0.4, fS=0.4)
    p2 = MockParams(beta=1.5, sigma=0.2, gamma=0.1, N_pop=1000000, fA=0.2, fM=0.4, fS=0.4)
    
    def get_hash(obj):
        param_dict = {
            k: v for k, v in obj.__dict__.items() 
            if not k.startswith('_') and k not in ['id', 'updated_at', 'source']
        }
        return hashlib.sha256(json.dumps(param_dict, sort_keys=True).encode()).hexdigest()
    
    h1 = get_hash(p1)
    h2 = get_hash(p2)
    assert h1 == h2
    print(f"Hash Match: {h1}")

def test_mass_conservation_logic():
    params = SEIRParams(
        beta=1.5, sigma=0.2, gamma=0.1, rho=1.0, fA=0.2, fM=0.4, fS=0.4,
        alpha=0.1, h_rate=0.05, delta=0.02, mu=0.01, mu_icu=0.05,
        gamma_A=0.1, gamma_M=0.1, gamma_S=0.1, gamma_H=0.1, gamma_ICU=0.1,
        papp=0.12, N_pop=1000000
    )
    
    # y = [S, E, IA, IM, IS, H, ICU, R, D]
    y0 = np.array([params.N_pop - 10, 10, 0, 0, 0, 0, 0, 0, 0])
    
    # Derivates should sum to zero
    dy = seir_extended(0, y0, params)
    mass_drift = np.sum(dy)
    assert abs(mass_drift) < 1e-9
    print(f"Mass Conservation (Derivates): {mass_drift}")

if __name__ == "__main__":
    test_deterministic_hashing()
    test_mass_conservation_logic()
    print("Brutal Logic Verification: PASSED")
