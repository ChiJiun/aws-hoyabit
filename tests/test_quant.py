"""
test_quant.py — quant.py 屬性測試 (Property-Based Testing)

使用 Hypothesis 框架驗證 quant.py 的核心正確性屬性。
驗證: 需求 11.3、11.4、20.2
"""

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambda"))

import numpy as np
import pandas as pd
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from tools.quant import calc_correlation, compute_quant


# ─── Strategies ───────────────────────────────────────────────────────────────

@st.composite
def ohlcv_dataframe_strategy(draw, min_rows=100, max_rows=200):
    """Generate a valid OHLCV DataFrame with realistic constraints.

    Ensures: high >= low, high >= open, high >= close.
    Uses numpy random seeded from Hypothesis for efficient generation.
    """
    n_rows = draw(st.integers(min_value=min_rows, max_value=max_rows))
    base_price = draw(st.floats(min_value=100.0, max_value=50000.0, allow_nan=False, allow_infinity=False))
    seed = draw(st.integers(min_value=0, max_value=2**32 - 1))

    rng = np.random.default_rng(seed)

    # Random walk for close prices
    pct_changes = rng.uniform(-0.05, 0.05, size=n_rows)
    closes = np.cumprod(1 + pct_changes) * base_price
    closes = np.maximum(closes, 1.0)

    # Open: close +/- small offset
    open_offsets = rng.uniform(-0.03, 0.03, size=n_rows)
    opens = closes * (1 + open_offsets)
    opens = np.maximum(opens, 1.0)

    # High: max(open, close) * (1 + small positive offset)
    high_offsets = rng.uniform(0.001, 0.05, size=n_rows)
    highs = np.maximum(opens, closes) * (1 + high_offsets)

    # Low: min(open, close) * (1 - small positive offset)
    low_offsets = rng.uniform(0.001, 0.05, size=n_rows)
    lows = np.minimum(opens, closes) * (1 - low_offsets)
    lows = np.maximum(lows, 0.01)

    # Volume
    volumes = rng.uniform(1000.0, 1e9, size=n_rows)

    df = pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    })

    return df


@st.composite
def small_ohlcv_dataframe_strategy(draw, min_rows=50, max_rows=100):
    """Generate a smaller valid OHLCV DataFrame for correlation tests."""
    n_rows = draw(st.integers(min_value=min_rows, max_value=max_rows))
    base_price = draw(st.floats(min_value=100.0, max_value=50000.0, allow_nan=False, allow_infinity=False))
    seed = draw(st.integers(min_value=0, max_value=2**32 - 1))

    rng = np.random.default_rng(seed)

    pct_changes = rng.uniform(-0.05, 0.05, size=n_rows)
    closes = np.cumprod(1 + pct_changes) * base_price
    closes = np.maximum(closes, 1.0)

    open_offsets = rng.uniform(-0.03, 0.03, size=n_rows)
    opens = closes * (1 + open_offsets)
    opens = np.maximum(opens, 1.0)

    high_offsets = rng.uniform(0.001, 0.05, size=n_rows)
    highs = np.maximum(opens, closes) * (1 + high_offsets)

    low_offsets = rng.uniform(0.001, 0.05, size=n_rows)
    lows = np.minimum(opens, closes) * (1 - low_offsets)
    lows = np.maximum(lows, 0.01)

    volumes = rng.uniform(1000.0, 1e9, size=n_rows)

    df = pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    })

    return df


# Supported features for compute_quant (excluding correlation which needs compare_symbol)
single_features = st.sampled_from([
    "atr_pct", "bollinger_bandwidth", "adx", "volume_zscore", "realized_vol", "range_ratio"
])

# Window sizes (reasonable for technical indicators)
window_strategy = st.integers(min_value=7, max_value=30)


# ─── Property 14: 技術指標含百分位 ───────────────────────────────────────────
# Validates: Requirements 11.3

@given(
    df=ohlcv_dataframe_strategy(),
    feature=single_features,
    window=window_strategy,
)
@settings(max_examples=100)
def test_property_14_indicators_contain_percentile(df, feature, window):
    """Property 14: 每個指標結果包含原始數值與 0-100 百分位。

    For any valid OHLCV DataFrame and supported feature, compute_quant returns
    results where each indicator has both a `value` and a `percentile` field,
    with percentile between 0 and 100.

    **Validates: Requirements 11.3**
    """
    assume(len(df) >= window + 50)

    mock_price_result = {
        "raw": df,
        "source": "test_mock",
        "content_reference": {"symbol": "BTC", "period": "test"},
        "summary": "Mock price data",
    }

    with patch("tools.price.get_price_ohlcv", return_value=mock_price_result):
        result = compute_quant(
            symbol="BTC",
            features=[feature],
            window=window,
            related_claim="test claim for property testing",
        )

    # Result must be a dict
    assert isinstance(result, dict)

    # If no error, verify the indicator structure
    if "error" not in result:
        assert "raw" in result
        raw = result["raw"]
        assert feature in raw

        indicator = raw[feature]
        assert "value" in indicator
        assert "percentile" in indicator

        # If value is not None, percentile must be between 0 and 100
        if indicator["value"] is not None:
            assert indicator["percentile"] is not None
            assert 0 <= indicator["percentile"] <= 100


# ─── Property 15: 相關係數值域 ───────────────────────────────────────────────
# Validates: Requirements 11.4

@given(
    df_a=small_ohlcv_dataframe_strategy(),
    df_b=small_ohlcv_dataframe_strategy(),
    window=st.integers(min_value=5, max_value=30),
)
@settings(max_examples=100)
def test_property_15_correlation_in_range(df_a, df_b, window):
    """Property 15: calc_correlation 結果必在 [-1, 1] 區間。

    For any two valid OHLCV DataFrames, calc_correlation() returns a value
    in the range [-1, 1].

    **Validates: Requirements 11.4**
    """
    assume(len(df_a) > window + 2)
    assume(len(df_b) > window + 2)

    corr = calc_correlation(df_a, df_b, window)

    assert isinstance(corr, float)
    assert -1.0 <= corr <= 1.0


# ─── Property 12: 工具永不拋錯 ───────────────────────────────────────────────
# Validates: Requirements 20.2

@given(
    symbol=st.text(min_size=0, max_size=20),
    features=st.lists(st.text(min_size=0, max_size=30), min_size=0, max_size=5),
    window=st.integers(min_value=-100, max_value=1000),
    related_claim=st.text(min_size=0, max_size=100),
)
@settings(max_examples=100)
def test_property_12_compute_quant_never_raises(symbol, features, window, related_claim):
    """Property 12: 任何輸入下 compute_quant 回傳 dict 而非拋例外。

    For ANY input (including invalid/garbage data, empty features, negative windows,
    wrong types), compute_quant must return a dict and never raise an exception.

    **Validates: Requirements 20.2**
    """
    # Test with various mock responses including errors, None, empty DataFrames
    mock_responses = [
        {"error": "API failed"},
        {"raw": pd.DataFrame(), "source": "empty", "content_reference": {}, "summary": "empty"},
        {"raw": None, "source": "none", "content_reference": {}, "summary": "none"},
        None,
        "invalid_string",
        42,
        pd.DataFrame({"close": [1, 2, 3]}),
    ]

    for mock_resp in mock_responses:
        with patch("tools.price.get_price_ohlcv", return_value=mock_resp):
            result = compute_quant(
                symbol=symbol,
                features=features,
                window=window,
                related_claim=related_claim,
            )

        # Must always return a dict
        assert isinstance(result, dict), f"compute_quant returned {type(result)} instead of dict"


@given(
    symbol=st.just("BTC"),
    window=window_strategy,
)
@settings(max_examples=100)
def test_property_12_compute_quant_exception_in_price(symbol, window):
    """Property 12: get_price_ohlcv 拋出例外時 compute_quant 仍回傳 dict。

    When the underlying price function raises an exception, compute_quant
    must catch it and return a dict with an error key.

    **Validates: Requirements 20.2**
    """
    def raise_error(*args, **kwargs):
        raise RuntimeError("Simulated network failure")

    with patch("tools.price.get_price_ohlcv", side_effect=raise_error):
        result = compute_quant(
            symbol=symbol,
            features=["atr_pct", "bollinger_bandwidth"],
            window=window,
            related_claim="test claim",
        )

    assert isinstance(result, dict)
    assert "error" in result
