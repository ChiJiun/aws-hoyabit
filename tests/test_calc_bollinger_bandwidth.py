"""Unit tests for calc_bollinger_bandwidth function."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambda"))

import pandas as pd
import numpy as np
from tools.quant import calc_bollinger_bandwidth


def test_basic_calculation():
    """Test that calc_bollinger_bandwidth returns correct values."""
    data = {
        "close": [100, 102, 101, 103, 105, 104, 106, 108, 107, 110],
    }
    df = pd.DataFrame(data)
    result = calc_bollinger_bandwidth(df, window=5)

    # Should return a pandas Series
    assert isinstance(result, pd.Series), f"Expected Series, got {type(result)}"

    # Length should match input
    assert len(result) == len(df), f"Expected length {len(df)}, got {len(result)}"

    # First (window - 1) values should be NaN due to rolling
    for i in range(4):
        assert pd.isna(result.iloc[i]), f"Row {i} should be NaN"

    # Non-NaN values should all be positive (bandwidth is always positive)
    valid_values = result.dropna()
    assert len(valid_values) > 0, "Should have at least some non-NaN values"
    assert (valid_values > 0).all(), "All valid bandwidth values should be positive"


def test_manual_calculation():
    """Verify calculation against manual computation."""
    data = {
        "close": [10.0, 12.0, 11.0, 13.0, 14.0],
    }
    df = pd.DataFrame(data)
    result = calc_bollinger_bandwidth(df, window=3)

    # Row 2 (first valid): close[0:3] = [10, 12, 11]
    # SMA = (10 + 12 + 11) / 3 = 11.0
    # std = std([10, 12, 11], ddof=1) = 1.0
    # upper = 11.0 + 2*1.0 = 13.0
    # lower = 11.0 - 2*1.0 = 9.0
    # bandwidth = (13.0 - 9.0) / 11.0 = 4.0 / 11.0 ≈ 0.3636

    expected_bw_2 = 4.0 / 11.0
    assert abs(result.iloc[2] - expected_bw_2) < 0.001, (
        f"Row 2: expected {expected_bw_2:.4f}, got {result.iloc[2]:.4f}"
    )

    # Row 3: close[1:4] = [12, 11, 13]
    # SMA = (12 + 11 + 13) / 3 = 12.0
    # std = std([12, 11, 13], ddof=1) = 1.0
    # bandwidth = (4 * 1.0) / 12.0 = 4.0 / 12.0 ≈ 0.3333
    expected_bw_3 = 4.0 / 12.0
    assert abs(result.iloc[3] - expected_bw_3) < 0.001, (
        f"Row 3: expected {expected_bw_3:.4f}, got {result.iloc[3]:.4f}"
    )


def test_constant_prices():
    """When all prices are equal, std is 0, bandwidth should be 0."""
    data = {
        "close": [50.0, 50.0, 50.0, 50.0, 50.0],
    }
    df = pd.DataFrame(data)
    result = calc_bollinger_bandwidth(df, window=3)

    # Constant prices -> std = 0 -> bandwidth = 0
    valid_values = result.dropna()
    assert (valid_values == 0.0).all(), "Constant prices should yield 0 bandwidth"


def test_returns_series():
    """Test that the return type is a pandas Series."""
    data = {
        "close": [10, 12, 11, 13, 14],
    }
    df = pd.DataFrame(data)
    result = calc_bollinger_bandwidth(df, window=3)
    assert isinstance(result, pd.Series)


if __name__ == "__main__":
    test_basic_calculation()
    print("PASSED: test_basic_calculation")
    test_manual_calculation()
    print("PASSED: test_manual_calculation")
    test_constant_prices()
    print("PASSED: test_constant_prices")
    test_returns_series()
    print("PASSED: test_returns_series")
    print("\nAll tests passed!")
