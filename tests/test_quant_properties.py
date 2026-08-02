"""
Property-based tests for tools/quant.py using Hypothesis.

Validates:
- Property 14: 技術指標含百分位 — 每個指標結果包含原始數值與 0-100 百分位
- Property 15: 相關係數值域 — calc_correlation 結果必在 [-1, 1] 區間
- Property 12: 工具永不拋錯 — 任何輸入下 compute_quant 回傳 dict 而非拋例外

驗證: 需求 11.3、11.4、20.2
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambda"))

import numpy as np
import pandas as pd
from unittest.mock import patch


def _mock_price_data(df):
    """直接注入 quant 所需的標準價格結果，讓 property tests 完全離線。"""
    frame = df.copy()
    if "date" in frame.columns:
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    as_of = None if frame.empty else str(frame["date"].iloc[-1])
    result = {
        "schema_version": "1.0",
        "status": "success",
        "raw": frame.to_dict(orient="records"),
        "source": "test_fixture",
        "content_reference": {
            "as_of": as_of,
            "query_endpoint": "test://ohlcv",
        },
        "summary": "offline property test fixture",
        "anomaly_flags": [],
    }
    return patch("tools.price._ORIGINAL_GET_PRICE_OHLCV", return_value=result)


from hypothesis import given, settings, assume
from hypothesis import strategies as st

from tools.quant import compute_quant, calc_correlation


# ---------------------------------------------------------------------------
# Strategies: 生成有效 OHLCV DataFrame
# ---------------------------------------------------------------------------

@st.composite
def ohlcv_dataframe(draw, min_rows=30, max_rows=200):
    """Generate a valid OHLCV DataFrame with positive prices and reasonable volume."""
    n = draw(st.integers(min_value=min_rows, max_value=max_rows))

    # Generate positive close prices via random walk
    start_price = draw(st.floats(min_value=10.0, max_value=10000.0))
    pct_changes = draw(
        st.lists(
            st.floats(min_value=-0.08, max_value=0.08),
            min_size=n - 1,
            max_size=n - 1,
        )
    )
    closes = [start_price]
    for pct in pct_changes:
        closes.append(closes[-1] * (1 + pct))

    closes = np.array(closes)
    # Ensure all prices are positive
    closes = np.abs(closes) + 0.01

    # Generate high >= close and low <= close
    high_offsets = draw(
        st.lists(
            st.floats(min_value=0.0, max_value=0.05),
            min_size=n,
            max_size=n,
        )
    )
    low_offsets = draw(
        st.lists(
            st.floats(min_value=0.0, max_value=0.05),
            min_size=n,
            max_size=n,
        )
    )
    highs = closes * (1 + np.array(high_offsets))
    lows = closes * (1 - np.array(low_offsets))

    # Open is between low and high
    open_fracs = draw(
        st.lists(
            st.floats(min_value=0.0, max_value=1.0),
            min_size=n,
            max_size=n,
        )
    )
    opens = lows + (highs - lows) * np.array(open_fracs)

    # Volume: positive
    volumes = draw(
        st.lists(
            st.floats(min_value=100.0, max_value=1e9),
            min_size=n,
            max_size=n,
        )
    )

    df = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n),
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    })
    return df


@st.composite
def close_series_dataframe(draw, min_rows=5, max_rows=100):
    """Generate a DataFrame with a 'close' column for correlation tests."""
    n = draw(st.integers(min_value=min_rows, max_value=max_rows))
    start = draw(st.floats(min_value=1.0, max_value=10000.0))
    pct_changes = draw(
        st.lists(
            st.floats(min_value=-0.1, max_value=0.1),
            min_size=n - 1,
            max_size=n - 1,
        )
    )
    closes = [start]
    for pct in pct_changes:
        closes.append(closes[-1] * (1 + pct))
    closes = np.abs(np.array(closes)) + 0.01
    return pd.DataFrame({"close": closes})


# ---------------------------------------------------------------------------
# Property 14: 技術指標含百分位
# ---------------------------------------------------------------------------

class TestProperty14TechnicalIndicatorsContainPercentile:
    """
    Property 14: 每個指標結果包含原始數值與 0-100 百分位。

    **Validates: Requirements 11.3**
    """

    @given(df=ohlcv_dataframe(min_rows=30, max_rows=150))
    @settings(max_examples=100)
    def test_atr_pct_has_value_and_percentile(self, df):
        """ATR% indicator result includes 'value' (finite) and 'percentile' (0-100)."""
        with _mock_price_data(df):
            result = compute_quant("BTC", ["atr_pct"], 14, "test claim")

        assert isinstance(result, dict)
        if "error" not in result:
            assert "atr_pct" in result["raw"]
            indicator = result["raw"]["atr_pct"]
            assert "value" in indicator
            assert "percentile" in indicator
            assert np.isfinite(indicator["value"])
            assert 0 <= indicator["percentile"] <= 100

    @given(df=ohlcv_dataframe(min_rows=30, max_rows=150))
    @settings(max_examples=100)
    def test_bollinger_bandwidth_has_value_and_percentile(self, df):
        """Bollinger Bandwidth includes 'value' (finite) and 'percentile' (0-100)."""
        with _mock_price_data(df):
            result = compute_quant("BTC", ["bollinger_bandwidth"], 20, "test claim")

        assert isinstance(result, dict)
        if "error" not in result:
            assert "bollinger_bandwidth" in result["raw"]
            indicator = result["raw"]["bollinger_bandwidth"]
            assert "value" in indicator
            assert "percentile" in indicator
            assert np.isfinite(indicator["value"])
            assert 0 <= indicator["percentile"] <= 100

    @given(df=ohlcv_dataframe(min_rows=30, max_rows=150))
    @settings(max_examples=100)
    def test_adx_has_value_and_percentile(self, df):
        """ADX indicator result includes 'value' (finite) and 'percentile' (0-100)."""
        with _mock_price_data(df):
            result = compute_quant("BTC", ["adx"], 14, "test claim")

        assert isinstance(result, dict)
        if "error" not in result:
            assert "adx" in result["raw"]
            indicator = result["raw"]["adx"]
            assert "value" in indicator
            assert "percentile" in indicator
            assert np.isfinite(indicator["value"])
            assert 0 <= indicator["percentile"] <= 100

    @given(df=ohlcv_dataframe(min_rows=30, max_rows=150))
    @settings(max_examples=100)
    def test_volume_zscore_has_value_and_percentile(self, df):
        """Volume Z-score includes 'value' (finite) and 'percentile' (0-100)."""
        with _mock_price_data(df):
            result = compute_quant("BTC", ["volume_zscore"], 14, "test claim")

        assert isinstance(result, dict)
        if "error" not in result:
            assert "volume_zscore" in result["raw"]
            indicator = result["raw"]["volume_zscore"]
            assert "value" in indicator
            assert "percentile" in indicator
            assert np.isfinite(indicator["value"])
            assert 0 <= indicator["percentile"] <= 100

    @given(df=ohlcv_dataframe(min_rows=30, max_rows=150))
    @settings(max_examples=100)
    def test_realized_vol_has_value_and_percentile(self, df):
        """Realized volatility includes 'value' (finite) and 'percentile' (0-100)."""
        with _mock_price_data(df):
            result = compute_quant("BTC", ["realized_vol"], 14, "test claim")

        assert isinstance(result, dict)
        if "error" not in result:
            assert "realized_vol" in result["raw"]
            indicator = result["raw"]["realized_vol"]
            assert "value" in indicator
            assert "percentile" in indicator
            assert np.isfinite(indicator["value"])
            assert 0 <= indicator["percentile"] <= 100

    @given(
        df=ohlcv_dataframe(min_rows=30, max_rows=150),
        feature=st.sampled_from(["atr_pct", "bollinger_bandwidth", "adx", "volume_zscore", "realized_vol"]),
        window=st.integers(min_value=5, max_value=28),
    )
    @settings(max_examples=100)
    def test_any_feature_percentile_bounded_0_100(self, df, feature, window):
        """For any feature and valid window, percentile is always in [0, 100]."""
        with _mock_price_data(df):
            result = compute_quant("BTC", [feature], window, "testing percentile bounds")

        assert isinstance(result, dict)
        if "error" not in result:
            indicator = result["raw"][feature]
            assert 0 <= indicator["percentile"] <= 100


# ---------------------------------------------------------------------------
# Property 15: 相關係數值域
# ---------------------------------------------------------------------------

class TestProperty15CorrelationRange:
    """
    Property 15: calc_correlation 結果必在 [-1, 1] 區間。

    **Validates: Requirements 11.4**
    """

    @given(
        df_a=close_series_dataframe(min_rows=10, max_rows=100),
        df_b=close_series_dataframe(min_rows=10, max_rows=100),
        window=st.integers(min_value=3, max_value=50),
    )
    @settings(max_examples=100)
    def test_correlation_always_in_minus1_to_1(self, df_a, df_b, window):
        """For any two price series and window, correlation is in [-1, 1]."""
        result = calc_correlation(df_a, df_b, window)
        assert isinstance(result, float)
        assert -1.0 <= result <= 1.0

    @given(
        df_a=close_series_dataframe(min_rows=2, max_rows=5),
        df_b=close_series_dataframe(min_rows=2, max_rows=5),
        window=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=100)
    def test_correlation_short_series_in_range(self, df_a, df_b, window):
        """Even with very short series, correlation stays in [-1, 1]."""
        result = calc_correlation(df_a, df_b, window)
        assert isinstance(result, float)
        assert -1.0 <= result <= 1.0

    @given(
        n=st.integers(min_value=5, max_value=50),
        price=st.floats(min_value=1.0, max_value=10000.0),
        window=st.integers(min_value=3, max_value=30),
    )
    @settings(max_examples=100)
    def test_constant_prices_return_valid_range(self, n, price, window):
        """Constant price series (zero variance) returns value in [-1, 1]."""
        df_a = pd.DataFrame({"close": [price] * n})
        df_b = pd.DataFrame({"close": [price * 2] * n})
        result = calc_correlation(df_a, df_b, window)
        assert isinstance(result, float)
        assert -1.0 <= result <= 1.0


# ---------------------------------------------------------------------------
# Property 12: 工具永不拋錯
# ---------------------------------------------------------------------------

class TestProperty12ToolNeverRaises:
    """
    Property 12: 任何輸入下 compute_quant 回傳 dict 而非拋例外。

    **Validates: Requirements 20.2**
    """

    @given(
        symbol=st.text(min_size=0, max_size=5),
        features=st.lists(
            st.sampled_from(["atr_pct", "bollinger_bandwidth", "adx", "volume_zscore", "realized_vol", "correlation"]),
            min_size=1,
            max_size=6,
        ),
        window=st.integers(min_value=1, max_value=100),
    )
    @settings(max_examples=100)
    def test_never_raises_on_exception_from_storage(self, symbol, features, window):
        """When storage raises any exception, compute_quant returns dict with 'error' key."""
        with patch("storage.read_baseline_csv", side_effect=Exception("simulated failure")):
            result = compute_quant(symbol, features, window, "test claim")

        assert isinstance(result, dict)
        assert "error" in result

    @given(df=ohlcv_dataframe(min_rows=30, max_rows=100))
    @settings(max_examples=100)
    def test_never_raises_on_valid_data(self, df):
        """With valid OHLCV data, compute_quant always returns a dict."""
        features = ["atr_pct", "bollinger_bandwidth", "adx", "volume_zscore", "realized_vol"]
        with _mock_price_data(df):
            result = compute_quant("BTC", features, 14, "test claim")

        assert isinstance(result, dict)

    @given(
        features=st.lists(
            st.sampled_from(["atr_pct", "bollinger_bandwidth", "adx", "volume_zscore", "realized_vol", "correlation"]),
            min_size=1,
            max_size=6,
        ),
        window=st.integers(min_value=1, max_value=50),
    )
    @settings(max_examples=100)
    def test_never_raises_on_empty_dataframe(self, features, window):
        """With an empty DataFrame, compute_quant returns dict (possibly with error)."""
        empty_df = pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
        with _mock_price_data(empty_df):
            result = compute_quant("BTC", features, window, "test claim")

        assert isinstance(result, dict)

    @given(
        features=st.lists(
            st.sampled_from(["atr_pct", "bollinger_bandwidth", "adx", "volume_zscore", "realized_vol"]),
            min_size=1,
            max_size=5,
        ),
        window=st.integers(min_value=1, max_value=50),
    )
    @settings(max_examples=100)
    def test_never_raises_on_single_row_dataframe(self, features, window):
        """With a single-row DataFrame, compute_quant returns dict without raising."""
        single_df = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=1),
            "open": [100.0],
            "high": [105.0],
            "low": [95.0],
            "close": [102.0],
            "volume": [1000.0],
        })
        with _mock_price_data(single_df):
            result = compute_quant("BTC", features, window, "test claim")

        assert isinstance(result, dict)

    @given(
        n=st.integers(min_value=5, max_value=30),
        features=st.lists(
            st.sampled_from(["atr_pct", "bollinger_bandwidth", "adx", "volume_zscore", "realized_vol"]),
            min_size=1,
            max_size=5,
        ),
        window=st.integers(min_value=1, max_value=50),
    )
    @settings(max_examples=100)
    def test_never_raises_on_nan_filled_dataframe(self, n, features, window):
        """With a NaN-filled DataFrame, compute_quant returns dict without raising."""
        nan_df = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=n),
            "open": [np.nan] * n,
            "high": [np.nan] * n,
            "low": [np.nan] * n,
            "close": [np.nan] * n,
            "volume": [np.nan] * n,
        })
        with _mock_price_data(nan_df):
            result = compute_quant("BTC", features, window, "test claim")

        assert isinstance(result, dict)

    @given(
        n=st.integers(min_value=10, max_value=50),
        features=st.lists(
            st.sampled_from(["atr_pct", "bollinger_bandwidth", "adx", "volume_zscore", "realized_vol"]),
            min_size=1,
            max_size=5,
        ),
        window=st.integers(min_value=1, max_value=50),
    )
    @settings(max_examples=100)
    def test_never_raises_on_zero_prices(self, n, features, window):
        """With zero prices (potential division by zero), compute_quant returns dict."""
        zero_df = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=n),
            "open": [0.0] * n,
            "high": [0.0] * n,
            "low": [0.0] * n,
            "close": [0.0] * n,
            "volume": [0.0] * n,
        })
        with _mock_price_data(zero_df):
            result = compute_quant("BTC", features, window, "test claim")

        assert isinstance(result, dict)
