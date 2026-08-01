"""
Unit tests for calc_percentile_rank function.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambda"))

import pandas as pd
import numpy as np
import pytest
from tools.quant import calc_percentile_rank


class TestCalcPercentileRank:
    """Tests for the calc_percentile_rank function."""

    def test_minimum_value_returns_zero_or_near_zero(self):
        """Value smaller than all history should rank at or near 0."""
        series = pd.Series(range(1, 101))  # 1 to 100
        result = calc_percentile_rank(series, 0)
        assert result == 0.0

    def test_maximum_value_returns_100(self):
        """Value >= all history should rank at 100."""
        series = pd.Series(range(1, 101))  # 1 to 100
        result = calc_percentile_rank(series, 100)
        assert result == 100.0

    def test_median_value(self):
        """Median value should rank around 50."""
        series = pd.Series(range(1, 101))  # 1 to 100
        result = calc_percentile_rank(series, 50)
        assert result == 50.0

    def test_lookback_limits_window(self):
        """Only the last `lookback` values should be considered."""
        # First 50 values are low (1-50), last 10 values are high (91-100)
        series = pd.Series(list(range(1, 51)) + list(range(91, 101)))
        # With lookback=10, only [91..100] are considered
        result = calc_percentile_rank(series, 95, lookback=10)
        # 95 is <= 5 out of 10 values (91,92,93,94,95) -> 50%
        assert result == 50.0

    def test_empty_series_returns_50(self):
        """Empty series should return 50 as default."""
        series = pd.Series([], dtype=float)
        result = calc_percentile_rank(series, 42)
        assert result == 50.0

    def test_all_nan_series_returns_50(self):
        """Series with all NaN values should return 50."""
        series = pd.Series([np.nan, np.nan, np.nan])
        result = calc_percentile_rank(series, 10)
        assert result == 50.0

    def test_series_with_some_nan(self):
        """NaN values should be excluded from the calculation."""
        series = pd.Series([np.nan, 1, 2, 3, np.nan, 4, 5])
        # Valid values: [1, 2, 3, 4, 5]; current=3 -> 3/5 = 60%
        result = calc_percentile_rank(series, 3)
        assert result == 60.0

    def test_result_always_between_0_and_100(self):
        """Result should always be within [0, 100]."""
        series = pd.Series([10, 20, 30, 40, 50])
        # Below minimum
        assert 0 <= calc_percentile_rank(series, -100) <= 100
        # Above maximum
        assert 0 <= calc_percentile_rank(series, 1000) <= 100

    def test_single_value_series(self):
        """Series with one value: equal -> 100%, less -> 0%."""
        series = pd.Series([5.0])
        assert calc_percentile_rank(series, 5.0) == 100.0
        assert calc_percentile_rank(series, 4.0) == 0.0

    def test_series_shorter_than_lookback(self):
        """When series is shorter than lookback, use all available data."""
        series = pd.Series([1, 2, 3, 4, 5])
        result = calc_percentile_rank(series, 3, lookback=365)
        # 3 values <= 3 out of 5 -> 60%
        assert result == 60.0

    def test_returns_float(self):
        """Result should always be a float."""
        series = pd.Series([1, 2, 3, 4, 5])
        result = calc_percentile_rank(series, 3)
        assert isinstance(result, float)
