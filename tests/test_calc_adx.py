"""Unit tests for calc_adx function."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambda"))

import pandas as pd
import numpy as np
from tools.quant import calc_adx


def test_basic_calculation():
    """Test that calc_adx returns correct ADX values with sufficient data."""
    data = {
        "high": [110, 115, 112, 118, 120, 117, 125, 122, 119, 130,
                 128, 132, 135, 131, 140, 138, 142, 145, 143, 150],
        "low": [100, 105, 102, 108, 110, 107, 115, 112, 109, 120,
                118, 122, 125, 121, 130, 128, 132, 135, 133, 140],
        "close": [105, 110, 108, 115, 118, 112, 120, 118, 115, 125,
                  124, 130, 132, 128, 137, 135, 140, 142, 138, 148],
    }
    df = pd.DataFrame(data)
    result = calc_adx(df, window=5)

    # Should return a pandas Series
    assert isinstance(result, pd.Series), f"Expected Series, got {type(result)}"

    # Length should match input
    assert len(result) == len(df), f"Expected length {len(df)}, got {len(result)}"

    # ADX values should be between 0 and 100 (where valid)
    valid_values = result.dropna()
    assert len(valid_values) > 0, "Should have at least some non-NaN values"
    assert (valid_values >= 0).all(), "All valid ADX values should be >= 0"
    assert (valid_values <= 100).all(), "All valid ADX values should be <= 100"


def test_strong_trend_high_adx():
    """ADX should be higher during a strong uptrend."""
    # Monotonically increasing prices => strong trend => high ADX
    n = 40
    highs = [100 + i * 3 for i in range(n)]
    lows = [95 + i * 3 for i in range(n)]
    closes = [98 + i * 3 for i in range(n)]
    df_trend = pd.DataFrame({"high": highs, "low": lows, "close": closes})

    result = calc_adx(df_trend, window=14)
    # After sufficient warmup, ADX for a strong trend should be > 25
    last_adx = result.iloc[-1]
    assert last_adx > 25, f"Strong trend ADX should be > 25, got {last_adx}"


def test_sideways_low_adx():
    """ADX should be relatively lower during a sideways/ranging market."""
    # Noisy sideways data oscillating around 100 with no net trend
    np.random.seed(42)
    n = 80
    base = 100.0
    # Random walk that mean-reverts around base
    closes = []
    c = base
    for _ in range(n):
        c = base + (c - base) * 0.8 + np.random.normal(0, 1)
        closes.append(c)
    closes = np.array(closes)
    highs = closes + np.random.uniform(0.5, 2.0, n)
    lows = closes - np.random.uniform(0.5, 2.0, n)

    df_flat = pd.DataFrame({"high": highs, "low": lows, "close": closes})

    result = calc_adx(df_flat, window=14)
    last_adx = result.iloc[-1]
    # Sideways market should generally produce ADX below 30
    assert last_adx < 30, f"Sideways ADX should be < 30, got {last_adx}"


def test_returns_series():
    """Test that the return type is a pandas Series."""
    data = {
        "high": [10, 12, 11, 13, 14, 15, 16, 14, 17, 18],
        "low": [8, 9, 8, 10, 11, 12, 13, 11, 14, 15],
        "close": [9, 11, 10, 12, 13, 14, 15, 13, 16, 17],
    }
    df = pd.DataFrame(data)
    result = calc_adx(df, window=3)
    assert isinstance(result, pd.Series)


def test_real_data():
    """Test calc_adx with real BTC baseline data."""
    csv_path = os.path.join(
        os.path.dirname(__file__), "..", "data", "baseline", "BTC_daily_ohlcv.csv"
    )
    if not os.path.exists(csv_path):
        return  # Skip if data not available

    df = pd.read_csv(csv_path)
    # Ensure column names are lowercase
    df.columns = [c.lower() for c in df.columns]
    result = calc_adx(df, window=14)

    assert isinstance(result, pd.Series)
    assert len(result) == len(df)
    # After warmup period, all values should be valid and in range
    valid = result.iloc[30:]
    assert valid.notna().all(), "After warmup, all ADX values should be valid"
    assert (valid >= 0).all() and (valid <= 100).all()


if __name__ == "__main__":
    test_basic_calculation()
    print("PASSED: test_basic_calculation")
    test_strong_trend_high_adx()
    print("PASSED: test_strong_trend_high_adx")
    test_sideways_low_adx()
    print("PASSED: test_sideways_low_adx")
    test_returns_series()
    print("PASSED: test_returns_series")
    test_real_data()
    print("PASSED: test_real_data")
    print("\nAll tests passed!")
