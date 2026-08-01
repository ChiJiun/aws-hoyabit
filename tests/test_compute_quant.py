"""Unit tests for compute_quant function."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambda"))

import pandas as pd
import numpy as np
from unittest.mock import patch

from tools.quant import compute_quant


def _make_ohlcv_df(n=100):
    """Create a realistic OHLCV DataFrame for testing."""
    np.random.seed(42)
    close = 100 + np.cumsum(np.random.randn(n) * 2)
    high = close + np.abs(np.random.randn(n)) * 3
    low = close - np.abs(np.random.randn(n)) * 3
    open_price = close + np.random.randn(n) * 1
    volume = np.abs(np.random.randn(n)) * 1000 + 500

    return pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n),
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })


class TestComputeQuantSuccess:
    """Tests for successful compute_quant executions."""

    def test_returns_dict_with_required_keys(self):
        """Property 13: On success, returned dict contains raw, source, content_reference, summary."""
        df = _make_ohlcv_df()
        with patch("storage.read_baseline_csv", return_value=df):
            result = compute_quant("BTC", ["atr_pct"], 14, "test claim")

        assert isinstance(result, dict)
        assert "raw" in result
        assert "source" in result
        assert "content_reference" in result
        assert "summary" in result

    def test_source_is_local_pandas(self):
        df = _make_ohlcv_df()
        with patch("storage.read_baseline_csv", return_value=df):
            result = compute_quant("BTC", ["atr_pct"], 14, "test claim")

        assert result["source"] == "local_pandas_computation"

    def test_atr_pct_has_value_and_percentile(self):
        """Property 14: Each indicator result includes raw value AND percentile rank (0-100)."""
        df = _make_ohlcv_df()
        with patch("storage.read_baseline_csv", return_value=df):
            result = compute_quant("BTC", ["atr_pct"], 14, "test claim")

        assert "atr_pct" in result["raw"]
        assert "value" in result["raw"]["atr_pct"]
        assert "percentile" in result["raw"]["atr_pct"]
        assert 0 <= result["raw"]["atr_pct"]["percentile"] <= 100

    def test_bollinger_bandwidth_has_value_and_percentile(self):
        df = _make_ohlcv_df()
        with patch("storage.read_baseline_csv", return_value=df):
            result = compute_quant("BTC", ["bollinger_bandwidth"], 20, "test claim")

        assert "bollinger_bandwidth" in result["raw"]
        assert "value" in result["raw"]["bollinger_bandwidth"]
        assert "percentile" in result["raw"]["bollinger_bandwidth"]
        assert 0 <= result["raw"]["bollinger_bandwidth"]["percentile"] <= 100

    def test_adx_has_value_and_percentile(self):
        df = _make_ohlcv_df()
        with patch("storage.read_baseline_csv", return_value=df):
            result = compute_quant("BTC", ["adx"], 14, "test claim")

        assert "adx" in result["raw"]
        assert "value" in result["raw"]["adx"]
        assert "percentile" in result["raw"]["adx"]
        assert 0 <= result["raw"]["adx"]["percentile"] <= 100

    def test_volume_zscore_has_value_and_percentile(self):
        df = _make_ohlcv_df()
        with patch("storage.read_baseline_csv", return_value=df):
            result = compute_quant("BTC", ["volume_zscore"], 14, "test claim")

        assert "volume_zscore" in result["raw"]
        assert "value" in result["raw"]["volume_zscore"]
        assert "percentile" in result["raw"]["volume_zscore"]
        assert 0 <= result["raw"]["volume_zscore"]["percentile"] <= 100

    def test_realized_vol_has_value_and_percentile(self):
        df = _make_ohlcv_df()
        with patch("storage.read_baseline_csv", return_value=df):
            result = compute_quant("BTC", ["realized_vol"], 14, "test claim")

        assert "realized_vol" in result["raw"]
        assert "value" in result["raw"]["realized_vol"]
        assert "percentile" in result["raw"]["realized_vol"]
        assert 0 <= result["raw"]["realized_vol"]["percentile"] <= 100

    def test_multiple_features(self):
        """Compute multiple features in one call."""
        df = _make_ohlcv_df()
        features = ["atr_pct", "bollinger_bandwidth", "adx", "volume_zscore", "realized_vol"]
        with patch("storage.read_baseline_csv", return_value=df):
            result = compute_quant("BTC", features, 14, "test claim")

        assert "error" not in result
        for f in features:
            assert f in result["raw"], f"Missing feature {f} in raw"
            assert f in result["content_reference"], f"Missing feature {f} in content_reference"

    def test_content_reference_includes_window(self):
        """Requirement 11.5: content_reference includes indicator name, window, value, percentile."""
        df = _make_ohlcv_df()
        with patch("storage.read_baseline_csv", return_value=df):
            result = compute_quant("BTC", ["atr_pct"], 14, "test claim")

        ref = result["content_reference"]["atr_pct"]
        assert "value" in ref
        assert "percentile" in ref
        assert "window" in ref
        assert ref["window"] == 14

    def test_summary_is_nonempty_string(self):
        df = _make_ohlcv_df()
        with patch("storage.read_baseline_csv", return_value=df):
            result = compute_quant("BTC", ["atr_pct"], 14, "test claim")

        assert isinstance(result["summary"], str)
        assert len(result["summary"]) > 0


class TestComputeQuantCorrelation:
    """Tests for correlation feature."""

    def test_correlation_with_compare_symbol(self):
        """Requirement 11.4: When compare_symbol is provided, compute correlation."""
        df_a = _make_ohlcv_df(100)
        np.random.seed(99)
        df_b = _make_ohlcv_df(100)

        with patch("storage.read_baseline_csv", side_effect=[df_a, df_b]):
            result = compute_quant("BTC", ["correlation"], 30, "test claim", compare_symbol="ETH")

        assert "correlation" in result["raw"]
        corr_val = result["raw"]["correlation"]["value"]
        assert -1 <= corr_val <= 1

    def test_correlation_without_compare_symbol(self):
        """Correlation without compare_symbol returns None value."""
        df = _make_ohlcv_df()
        with patch("storage.read_baseline_csv", return_value=df):
            result = compute_quant("BTC", ["correlation"], 30, "test claim", compare_symbol=None)

        assert "correlation" in result["raw"]
        assert result["raw"]["correlation"]["value"] is None


class TestComputeQuantErrorHandling:
    """Tests for error handling (Property 12)."""

    def test_returns_error_dict_on_file_not_found(self):
        """Property 12: For ANY input, compute_quant returns dict (never throws)."""
        with patch("storage.read_baseline_csv", side_effect=FileNotFoundError("not found")):
            result = compute_quant("INVALID", ["atr_pct"], 14, "test claim")

        assert isinstance(result, dict)
        assert "error" in result
        assert "source" in result
        assert result["source"] == "local_pandas_computation"

    def test_returns_error_dict_on_exception(self):
        with patch("storage.read_baseline_csv", side_effect=ValueError("bad data")):
            result = compute_quant("BTC", ["atr_pct"], 14, "test claim")

        assert isinstance(result, dict)
        assert "error" in result
        assert "ValueError" in result["error"]

    def test_never_throws_exception(self):
        """Property 12: Function never raises, always returns dict."""
        with patch("storage.read_baseline_csv", side_effect=RuntimeError("unexpected")):
            result = compute_quant("BTC", ["atr_pct"], 14, "test claim")

        # Should not reach here if it threw
        assert isinstance(result, dict)
        assert "error" in result

    def test_error_dict_has_content_reference(self):
        with patch("storage.read_baseline_csv", side_effect=Exception("fail")):
            result = compute_quant("BTC", ["atr_pct"], 14, "test claim")

        assert "content_reference" in result
        assert result["content_reference"] == {}


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
