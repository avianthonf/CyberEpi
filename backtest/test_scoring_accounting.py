"""Regression tests for WIS scoring accounting bug fixes.

Tests verify the actual bugs found in archive analysis:
1. Missing truth rows (blank observed/wis/wis_base) excluded from ratio
2. by_horizon relWIS computed as ratio of means, not aliased to mean(wis)
3. n_scored counts finite WIS only (using np.isfinite)
"""

import numpy as np
import pandas as pd
import pytest
from run_flusight import summarize


def make_quantile_forecast(location, ref_date, target_date, horizon, truth, width=20):
    """Helper: create standard 5-quantile forecast around truth."""
    quantiles = [0.025, 0.25, 0.5, 0.75, 0.975]
    rows = []
    for q in quantiles:
        rows.append(
            {
                "location": location,
                "reference_date": ref_date,
                "target_end_date": target_date,
                "horizon": horizon,
                "output_type": "quantile",
                "output_type_id": q,
                "value": truth + (q - 0.5) * width,
            }
        )
    return rows


def test_missing_truth_excluded_from_ratio():
    """Bug: missing truth rows created blank WIS, polluting relWIS ratio."""
    # Oracle has 2 rows; forecasts have 3 (one missing truth)
    oracle = pd.DataFrame(
        [
            {"location": "01", "target_end_date": pd.to_datetime("2023-01-14"), "oracle_value": 100.0},
            {"location": "02", "target_end_date": pd.to_datetime("2023-01-14"), "oracle_value": 150.0},
        ]
    )

    ref = pd.to_datetime("2023-01-07")
    target = pd.to_datetime("2023-01-14")

    # Forecasts for 3 locations, but loc="03" has no truth
    forecast_rows = []
    forecast_rows.extend(make_quantile_forecast("01", ref, target, 1, 100.0, width=20))
    forecast_rows.extend(make_quantile_forecast("02", ref, target, 1, 150.0, width=20))
    forecast_rows.extend(make_quantile_forecast("03", ref, target, 1, 200.0, width=20))  # no truth
    forecasts = pd.DataFrame(forecast_rows)

    # Baseline: 50% wider intervals
    baseline_rows = []
    baseline_rows.extend(make_quantile_forecast("01", ref, target, 1, 100.0, width=30))
    baseline_rows.extend(make_quantile_forecast("02", ref, target, 1, 150.0, width=30))
    baseline_rows.extend(make_quantile_forecast("03", ref, target, 1, 200.0, width=30))
    baseline = pd.DataFrame(baseline_rows)

    summary, _cmp = summarize(forecasts, oracle, baseline, "test")

    # Only 2 have truth, so n_comparison_rows = 2, all finite
    assert summary["n_comparison_rows"] == 2
    assert summary["n_finite_paired"] == 2
    assert summary["n_excluded_nonfinite"] == 0
    assert summary["n_scored_ours"] == 2  # finite WIS count
    assert summary["n_scored_base"] == 2

    # relWIS should be < 1 (narrower model beats wider baseline)
    # Expected: model width=20, baseline width=30 → relWIS ≈ 20/30 = 0.67
    assert 0.6 < summary["relWIS"] < 0.75


def test_by_horizon_relwis_is_ratio_not_alias():
    """Bug: by_horizon['relWIS'] was aliased to mean(wis), not ratio."""
    oracle = pd.DataFrame(
        [
            {"location": "US", "target_end_date": pd.to_datetime("2023-01-14"), "oracle_value": 100.0},
        ]
    )

    ref = pd.to_datetime("2023-01-07")
    target = pd.to_datetime("2023-01-14")

    # Model: width=20, Baseline: width=60 (3x wider)
    forecasts = pd.DataFrame(make_quantile_forecast("US", ref, target, 1, 100.0, width=20))
    baseline = pd.DataFrame(make_quantile_forecast("US", ref, target, 1, 100.0, width=60))

    summary, _cmp = summarize(forecasts, oracle, baseline, "test")

    # Verify by_horizon contains relWIS as ratio
    assert 1 in summary["by_horizon"]
    h1 = summary["by_horizon"][1]

    assert "wis" in h1
    assert "wis_base" in h1
    assert "relWIS" in h1

    # relWIS must be ratio, not equal to wis
    expected_ratio = h1["wis"] / h1["wis_base"]
    assert abs(h1["relWIS"] - expected_ratio) < 0.01

    # relWIS should be ≈ 1/3 (20 vs 60 width)
    assert 0.3 < h1["relWIS"] < 0.4

    # Bug would have made relWIS equal to wis (typically >> 1)
    assert h1["relWIS"] != h1["wis"]


def test_n_scored_counts_finite_wis_only():
    """Bug: n_scored_ours/base must count finite WIS only using np.isfinite."""
    oracle = pd.DataFrame(
        [
            {"location": "01", "target_end_date": pd.to_datetime("2023-01-14"), "oracle_value": 100.0},
            {"location": "02", "target_end_date": pd.to_datetime("2023-01-14"), "oracle_value": 150.0},
        ]
    )

    ref = pd.to_datetime("2023-01-07")
    target = pd.to_datetime("2023-01-14")

    # Model forecasts: both locations
    forecast_rows = []
    forecast_rows.extend(make_quantile_forecast("01", ref, target, 1, 100.0, width=20))
    forecast_rows.extend(make_quantile_forecast("02", ref, target, 1, 150.0, width=20))
    forecasts = pd.DataFrame(forecast_rows)

    # Baseline: loc="02" has NaN at median to create non-finite WIS
    baseline_rows = []
    baseline_rows.extend(make_quantile_forecast("01", ref, target, 1, 100.0, width=30))
    base_02 = make_quantile_forecast("02", ref, target, 1, 150.0, width=30)
    for row in base_02:
        if row["output_type_id"] == 0.5:
            row["value"] = np.nan
    baseline_rows.extend(base_02)
    baseline = pd.DataFrame(baseline_rows)

    summary, _cmp = summarize(forecasts, oracle, baseline, "test")

    # n_scored counts finite WIS only
    assert summary["n_scored_ours"] == 2  # both valid
    assert summary["n_scored_base"] == 1  # loc=02 has NaN → non-finite WIS
    assert summary["n_comparison_rows"] == 2
    assert summary["n_finite_paired"] == 1
    assert summary["n_excluded_nonfinite"] == 1


def test_coverage_exact_bounds():
    """Coverage should be 0.0 or 1.0 for trivial perfectly-calibrated case."""
    oracle = pd.DataFrame(
        [
            {"location": "US", "target_end_date": pd.to_datetime("2023-01-14"), "oracle_value": 100.0},
        ]
    )

    ref = pd.to_datetime("2023-01-07")
    target = pd.to_datetime("2023-01-14")

    # Perfect forecast: truth=100, intervals centered at 100
    forecasts = pd.DataFrame(make_quantile_forecast("US", ref, target, 1, 100.0, width=40))
    baseline = pd.DataFrame(make_quantile_forecast("US", ref, target, 1, 100.0, width=40))

    summary, _cmp = summarize(forecasts, oracle, baseline, "test")

    # Truth exactly at median → cov50/90/95 all = 1.0
    assert summary["cov50"] == 1.0
    assert summary["cov90"] == 1.0
    assert summary["cov95"] == 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
