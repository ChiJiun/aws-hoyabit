"""Tests for fetch_recent_from_exchange function."""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

# Add lambda/ to path so we can import the module
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lambda"))

from tools.price import fetch_recent_from_exchange


# Sample Binance kline response format:
# [open_time, open, high, low, close, volume, close_time, quote_vol, trades, taker_buy_base, taker_buy_quote, ignore]
SAMPLE_KLINES = [
    [1717200000000, "67000.00", "68500.50", "66500.00", "68100.25", "12345.678", 1717286399999, "0", 0, "0", "0", "0"],
    [1717286400000, "68100.25", "69000.00", "67800.00", "68900.00", "11234.567", 1717372799999, "0", 0, "0", "0", "0"],
    [1717372800000, "68900.00", "69500.00", "68000.00", "69200.50", "13456.789", 1717459199999, "0", 0, "0", "0", "0"],
]


@patch("tools.price.requests.get")
def test_returns_dataframe_with_correct_columns(mock_get):
    """fetch_recent_from_exchange should return a DataFrame with the expected columns."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = SAMPLE_KLINES
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    df = fetch_recent_from_exchange("BTC", "2024-06-01")

    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == ["date", "open", "high", "low", "close", "volume"]


@patch("tools.price.requests.get")
def test_date_column_format(mock_get):
    """date column should be YYYY-MM-DD strings."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = SAMPLE_KLINES
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    df = fetch_recent_from_exchange("BTC", "2024-06-01")

    for date_val in df["date"]:
        assert isinstance(date_val, str)
        # Validate format YYYY-MM-DD
        parts = date_val.split("-")
        assert len(parts) == 3
        assert len(parts[0]) == 4
        assert len(parts[1]) == 2
        assert len(parts[2]) == 2


@patch("tools.price.requests.get")
def test_numeric_columns_are_float(mock_get):
    """open, high, low, close, volume columns should be float."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = SAMPLE_KLINES
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    df = fetch_recent_from_exchange("BTC", "2024-06-01")

    for col in ["open", "high", "low", "close", "volume"]:
        assert df[col].dtype == float, f"Column {col} should be float, got {df[col].dtype}"


@patch("tools.price.requests.get")
def test_correct_api_params(mock_get):
    """Should call Binance API with correct parameters."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = []
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    fetch_recent_from_exchange("SOL", "2024-06-01")

    mock_get.assert_called_once()
    call_args = mock_get.call_args
    assert call_args[1]["params"]["symbol"] == "SOLUSDT"
    assert call_args[1]["params"]["interval"] == "1d"
    assert call_args[1]["params"]["limit"] == 1000
    assert "startTime" in call_args[1]["params"]


@patch("tools.price.requests.get")
def test_correct_row_count(mock_get):
    """Should return one row per kline entry."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = SAMPLE_KLINES
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    df = fetch_recent_from_exchange("BTC", "2024-06-01")

    assert len(df) == 3


@patch("tools.price.requests.get")
def test_correct_values_parsed(mock_get):
    """Should correctly parse kline values into DataFrame."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = SAMPLE_KLINES
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    df = fetch_recent_from_exchange("BTC", "2024-06-01")

    # First row checks
    assert df.iloc[0]["open"] == 67000.00
    assert df.iloc[0]["high"] == 68500.50
    assert df.iloc[0]["low"] == 66500.00
    assert df.iloc[0]["close"] == 68100.25
    assert df.iloc[0]["volume"] == 12345.678


@patch("tools.price.requests.get")
def test_empty_response(mock_get):
    """Should return empty DataFrame when API returns no data."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = []
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    df = fetch_recent_from_exchange("BTC", "2024-06-01")

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 0
    assert list(df.columns) == ["date", "open", "high", "low", "close", "volume"]
