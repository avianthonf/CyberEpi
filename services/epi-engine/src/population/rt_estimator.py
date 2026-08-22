"""Real-time Rt Estimation using the Cori et al. (2013) method."""


import numpy as np
from scipy.stats import gamma


def estimate_rt(
    case_series: np.ndarray,
    serial_interval_mean: float = 5.2,
    serial_interval_sd: float = 2.8,
    window: int = 7,
    prior_a: float = 1.0,
    prior_b: float = 5.0
) -> dict[str, np.ndarray]:
    """
    Estimate Rt from infectious case series.
    Cori et al. (2013): Bayesian estimation with Gamma prior.
    """
    T = len(case_series)
    if window >= T:
        return {
            "mean": np.zeros(T),
            "lower": np.zeros(T),
            "upper": np.zeros(T)
        }

    # 1. Discretized Serial Interval distribution w(s)
    # w(s) ~ Gamma(mu, sigma)
    # mean = a*b, var = a*b^2 => b = var/mean, a = mean/b = mean^2/var
    var = serial_interval_sd ** 2
    b_si = var / serial_interval_mean
    a_si = serial_interval_mean / b_si

    max_s = 25
    s_idx = np.arange(1, max_s + 1)
    # CDF(s+0.5) - CDF(s-0.5)
    w = gamma.cdf(s_idx + 0.5, a_si, scale=b_si) - gamma.cdf(s_idx - 0.5, a_si, scale=b_si)
    w = w / np.sum(w) # Normalize

    rt_mean = np.zeros(T)
    rt_lower = np.zeros(T)
    rt_upper = np.zeros(T)

    for t in range(window, T):
        # sum_c: total cases in the window [t-window, t]
        sum_c = np.sum(case_series[t - window + 1 : t + 1])

        # Lambda: Total infectiousness at time t
        # Lambda_t = sum_{s=1}^{t} case_series[t-s] * w[s-1]
        # For the window, we need the sum of Lambda over days [t-window, t]
        # BUT Cori Eq (2) usually uses a single day's Lambda or windowed?
        # Standard implementation (EpiEstim): Rt is constant over window.
        # Numerator = sum of cases in window. Denominator = sum of Lambda in window.

        total_lambda_window = 0.0
        for tau in range(t - window + 1, t + 1):
            tau_lambda = 0.0
            for s in range(1, min(tau, max_s) + 1):
                tau_lambda += case_series[tau - s] * w[s - 1]
            total_lambda_window += tau_lambda

        # Bayesian Update
        # Prior: Gamma(a, b) -> Posterior: Gamma(a + sum_c, 1 / (1/b + total_lambda))
        post_a = prior_a + sum_c
        # Note: prior_b in prompt is b in Gamma(a, scale=b)
        post_b = 1.0 / (1.0 / prior_b + total_lambda_window)

        rt_mean[t] = post_a * post_b
        rt_lower[t] = gamma.ppf(0.025, post_a, scale=post_b)
        rt_upper[t] = gamma.ppf(0.975, post_a, scale=post_b)

    return {
        "mean": rt_mean,
        "lower": rt_lower,
        "upper": rt_upper
    }
