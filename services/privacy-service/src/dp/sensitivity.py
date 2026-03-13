def regional_rt_sensitivity() -> float:
    """
    The sensitivity of Rt estimated over a window.
    Adding/removing one case changes Rt by at most 1/window_size.
    """
    window_size = 7.0
    return 1.0 / window_size

def hotspot_count_sensitivity() -> float:
    """
    One person changing their status can change the count by at most 1.
    """
    return 1.0

def aggregate_count_sensitivity(max_contribution: float = 1.0) -> float:
    """
    Sensitivity is bounded by the maximum allowed individual contribution.
    """
    return max_contribution
