"""Unit tests for calc_correlation function."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambda"))

import pandas as pd
import numpy as np
from tools.quant import calc_correlation


def _make_df(closes):
    """Helper: 建立包含 close 欄位的 DataFrame。"""
    return pd.DataFrame({"close": closes})


def test_perfect_positive_correlation():
    """兩組報酬率完全正相關的價格序列，相關係數應為 1.0。"""
    # 使用相同的日報酬率序列產生完美正相關
    returns = [0.05, -0.03, 0.02, 0.04, -0.01]
    closes_a = [100.0]
    closes_b = [200.0]
    for r in returns:
        closes_a.append(closes_a[-1] * (1 + r))
        closes_b.append(closes_b[-1] * (1 + r))
    df_a = _make_df(closes_a)
    df_b = _make_df(closes_b)
    result = calc_correlation(df_a, df_b, window=5)
    assert abs(result - 1.0) < 0.01, f"Expected ~1.0, got {result}"


def test_perfect_negative_correlation():
    """報酬率完全反向的兩組價格，相關係數應為 -1.0。"""
    returns = [0.05, -0.03, 0.02, 0.04, -0.01]
    closes_a = [100.0]
    closes_b = [200.0]
    for r in returns:
        closes_a.append(closes_a[-1] * (1 + r))
        closes_b.append(closes_b[-1] * (1 - r))  # 反向報酬率
    df_a = _make_df(closes_a)
    df_b = _make_df(closes_b)
    result = calc_correlation(df_a, df_b, window=5)
    assert abs(result - (-1.0)) < 0.01, f"Expected ~-1.0, got {result}"


def test_result_in_valid_range():
    """結果必定在 [-1, 1] 範圍內（Property 15）。"""
    np.random.seed(42)
    closes_a = np.cumsum(np.random.randn(50)) + 100
    closes_b = np.cumsum(np.random.randn(50)) + 100
    df_a = _make_df(closes_a)
    df_b = _make_df(closes_b)
    result = calc_correlation(df_a, df_b, window=30)
    assert -1.0 <= result <= 1.0, f"Result {result} is out of [-1, 1]"


def test_returns_float():
    """回傳型別應為 float。"""
    df_a = _make_df([100, 105, 110, 115, 120])
    df_b = _make_df([200, 210, 205, 215, 220])
    result = calc_correlation(df_a, df_b, window=3)
    assert isinstance(result, float), f"Expected float, got {type(result)}"


def test_insufficient_data_returns_zero():
    """資料不足時應回傳 0.0（中性相關）。"""
    df_a = _make_df([100])
    df_b = _make_df([200])
    result = calc_correlation(df_a, df_b, window=5)
    assert result == 0.0, f"Expected 0.0, got {result}"


def test_constant_prices_returns_zero():
    """價格不變（標準差為零）時應回傳 0.0，不能是 NaN。"""
    df_a = _make_df([100, 100, 100, 100, 100])
    df_b = _make_df([200, 200, 200, 200, 200])
    result = calc_correlation(df_a, df_b, window=3)
    assert result == 0.0, f"Expected 0.0, got {result}"
    assert not np.isnan(result), "Should not return NaN"


def test_window_parameter():
    """window 參數應限制使用的報酬率天數。"""
    # 構造：前半段報酬率反向，後半段報酬率同向
    # 先用反向報酬率產生 4 天
    closes_a = [100.0, 95.0, 90.0, 85.0, 80.0]
    closes_b = [100.0, 105.0, 110.0, 115.0, 120.0]
    # 接著用同向報酬率產生 4 天
    same_returns = [0.05, 0.03, 0.04, 0.02]
    for r in same_returns:
        closes_a.append(closes_a[-1] * (1 + r))
        closes_b.append(closes_b[-1] * (1 + r))
    df_a = _make_df(closes_a)
    df_b = _make_df(closes_b)
    # 用 window=4 只看最後 4 天報酬率（同向）
    result = calc_correlation(df_a, df_b, window=4)
    assert result > 0.5, f"Expected strong positive correlation for last 4 days, got {result}"


if __name__ == "__main__":
    test_perfect_positive_correlation()
    print("PASSED: test_perfect_positive_correlation")
    test_perfect_negative_correlation()
    print("PASSED: test_perfect_negative_correlation")
    test_result_in_valid_range()
    print("PASSED: test_result_in_valid_range")
    test_returns_float()
    print("PASSED: test_returns_float")
    test_insufficient_data_returns_zero()
    print("PASSED: test_insufficient_data_returns_zero")
    test_constant_prices_returns_zero()
    print("PASSED: test_constant_prices_returns_zero")
    test_window_parameter()
    print("PASSED: test_window_parameter")
    print("\nAll tests passed!")
