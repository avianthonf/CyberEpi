from src.control.game_theory import information_effect, nash_contact_rate


def test_nash_contact_decreases_with_prevalence():
    N = 1000000
    beta0 = 0.5
    L = 50.0

    c_low = nash_contact_rate(100, N, beta0, L)
    c_high = nash_contact_rate(10000, N, beta0, L)

    assert c_high < c_low

def test_information_effect():
    L_base = 10.0
    L_low = information_effect(0.8, L_base)
    L_high = information_effect(2.5, L_base)

    assert L_low == L_base # Rt < 1, no extra effect
    assert L_high > L_base
    assert L_high == L_base * (1 + 0.5 * 1.5)

def test_nash_equilibrium_existence():
    # Test a wide range of prevalence
    N = 1000000
    beta0 = 0.3
    L = 100.0
    for I in [1, 100, 1000, 10000, 100000]:
        c_star = nash_contact_rate(I, N, beta0, L)
        assert 0 <= c_star <= 100
