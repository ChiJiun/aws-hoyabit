"""Unit tests for calc_atr_pct function."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambda"))

import pandas as pd
import numpy as np
from tools.quant import calc_atr_pct


def test_basic_calculation():
    """Test that calc_atr_pct returns correct ATR percentage values."""
    data = {
        "high": [110, 115, 112, 118, 120, 117, 125, 122, 119, 130],
        "low": [100, 105, 102, 108, 110, 107, 115, 112, 109, 120],
        "close": [105, 110, 108, 115, 118, 112, 120, 118, 115, 125],
    }
    df = pd.DataFrame(data)
    result = calc_atr_pct(df, window=3)

    # Should return a pandas Series
    assert isinstance(result, pd.Series), f"Expected Series, got {type(result)}"

    # Length should match input
    assert len(result) == len(df), f"Expected length {len(df)}, got {len(result)}"

    # First few values should be NaN (need window + 1 rows for prev_close shift)
    # Row 0: prev_close is NaN -> TR is NaN
    # Rows 1,2: TR is valid but rolling(3) needs 3 non-NaN values
    # So first non-NaN ATR should appear at index 3 (row 1,2,3 have valid TR)
    assert pd.isna(result.iloc[0]), "Row 0 should be NaN"

    # Non-NaN values should all be positive (prices are positive)
    valid_values = result.dropna()
    assert len(valid_values) > 0, "Should have at least some non-NaN values"
    assert (valid_values > 0).all(), "All valid ATR% values should be positive"


def test_manual_calculation():
    """Verify calculation against manual computation."""
    data = {
        "high": [50, 52, 51, 53],
        "low": [45, 47, 46, 48],
        "close": [48, 50, 49, 51],
    }
    df = pd.DataFrame(data)
    result = calc_atr_pct(df, window=2)

    # Row 0: prev_close = NaN -> TR = max(5, NaN, NaN) = 5 (max ignores NaN)
    # Row 1: prev_close = 48, TR = max(52-47, |52-48|, |47-48|) = max(5, 4, 1) = 5
    # Row 2: prev_close = 50, TR = max(51-46, |51-50|, |46-50|) = max(5, 1, 4) = 5
    # Row 3: prev_close = 49, TR = max(53-48, |53-49|, |48-49|) = max(5, 4, 1) = 5

    # ATR(window=2):
    # Row 0: NaN (rolling(2) needs 2 values)
    # Row 1: mean(5, 5) = 5.0 -> ATR% = (5/50)*100 = 10.0
    # Row 2: mean(5, 5) = 5.0 -> ATR% = (5/49)*100 ≈ 10.204
    # Row 3: mean(5, 5) = 5.0 -> ATR% = (5/51)*100 ≈ 9.804

    assert pd.isna(result.iloc[0])
    assert abs(result.iloc[1] - (5.0 / 50) * 100) < 0.001
    assert abs(result.iloc[2] - (5.0 / 49) * 100) < 0.001
    assert abs(result.iloc[3] - (5.0 / 51) * 100) < 0.001


def test_returns_series():
    """Test that the return type is a pandas Series."""
    data = {
        "high": [10, 12, 11, 13, 14],
        "low": [8, 9, 8, 10, 11],
        "close": [9, 11, 10, 12, 13],
    }
    df = pd.DataFrame(data)
    result = calc_atr_pct(df, window=2)
    assert isinstance(result, pd.Series)


if __name__ == "__main__":
    test_basic_calculation()
    print("PASSED: test_basic_calculation")
    test_manual_calculation()
    print("PASSED: test_manual_calculation")
    test_returns_series()
    print("PASSED: test_returns_series")
    print("\nAll tests passed!")
