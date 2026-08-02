"""
Unit tests for get_price_ohlcv function.
Verifies: Requirements 6.1, 6.6 | Property 12, 13
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

# Add lambda/ to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lambda"))

import evidence
from tools.price import get_price_ohlcv


def _make_baseline_df():
    """Create a sample baseline DataFrame covering 2024-01-01 ~ 2024-01-10."""
    dates = [f"2024-01-{d:02d}" for d in range(1, 11)]
    return pd.DataFrame({
        "date": dates,
        "open": [100.0 + i for i in range(10)],
        "high": [105.0 + i for i in range(10)],
        "low": [95.0 + i for i in range(10)],
        "close": [102.0 + i for i in range(10)],
        "volume": [1000.0 + i * 100 for i in range(10)],
    })


def _make_large_baseline_df():
    """Create a baseline DataFrame covering 2024-01-01 ~ 2026-05-31."""
    dates = pd.date_range("2024-01-01", "2026-05-31", freq="D").strftime("%Y-%m-%d").tolist()
    n = len(dates)
    return pd.DataFrame({
        "date": dates,
        "open": [100.0 + i * 0.1 for i in range(n)],
        "high": [105.0 + i * 0.1 for i in range(n)],
        "low": [95.0 + i * 0.1 for i in range(n)],
        "close": [102.0 + i * 0.1 for i in range(n)],
        "volume": [1000.0 + i for i in range(n)],
    })


@pytest.fixture(autouse=True)
def reset_evidence():
    """Reset evidence stores before each test."""
    evidence.reset_stores()
    yield
    evidence.reset_stores()


class TestGetPriceOhlcvBaseline:
    """Tests for get_price_ohlcv reading baseline CSV and filtering dates."""

    def test_returns_data_within_baseline_range(self):
        """Req 6.1, 6.2: Returns OHLCV data from baseline CSV for valid date range."""
        df = _make_baseline_df()
        with patch("tools.price.storage.read_baseline_csv", return_value=df):
            result = get_price_ohlcv("SOL", "2024-01-01", "2024-01-10", "need SOL price data")
        assert "error" not in result
        assert "raw" in result
        assert "source" in result
        assert "content_reference" in result
        assert "summary" in result
        assert result["content_reference"]["pair"] == "SOLUSDT"
        assert result["content_reference"]["rows"] == 10

    def test_returns_error_for_empty_date_range(self):
        """Returns error dict when no data exists in the specified range."""
        df = _make_baseline_df()
        with patch("tools.price.storage.read_baseline_csv", return_value=df):
            result = get_price_ohlcv("SOL", "2019-01-01", "2019-01-31", "old date range test")
        assert "error" in result
        assert "content_reference" in result
        assert result["status"] == "error"
        assert result["content_reference"]["freshness_status"] == "unknown"
        assert result["content_reference"]["provider"] == "Competition baseline CSV"

    def test_filters_date_range_correctly(self):
        """Verifies date filtering works — only dates within range are returned."""
        df = _make_baseline_df()
        with patch("tools.price.storage.read_baseline_csv", return_value=df):
            result = get_price_ohlcv("BTC", "2024-01-03", "2024-01-07", "BTC mid data")
        assert "error" not in result
        records = result["raw"]
        assert len(records) == 5
        for row in records:
            assert "2024-01-03" <= row["date"] <= "2024-01-07"

    def test_content_reference_includes_pair_range_rows(self):
        """Property 13: content_reference includes pair, range, rows."""
        df = _make_baseline_df()
        with patch("tools.price.storage.read_baseline_csv", return_value=df):
            result = get_price_ohlcv("ETH", "2024-01-01", "2024-01-05", "ETH price check")
        assert "error" not in result
        cr = result["content_reference"]
        assert "pair" in cr
        assert "range" in cr
        assert "rows" in cr
        assert cr["pair"] == "ETHUSDT"
        assert cr["rows"] == 5


class TestGetPriceOhlcvNeverThrows:
    """Property 12: get_price_ohlcv never raises unhandled exceptions."""

    def test_storage_failure_returns_error_dict(self):
        """If storage.read_baseline_csv raises, function should catch and return error."""
        with patch("tools.price.storage.read_baseline_csv", side_effect=FileNotFoundError("mock")):
            result = get_price_ohlcv("BTC", "2024-01-01", "2024-01-31", "test storage failure")
        assert isinstance(result, dict)
        assert "error" in result
        assert "source" in result
        assert "content_reference" in result

    def test_unexpected_exception_returns_error_dict(self):
        """Any unexpected exception should be caught and returned as error dict."""
        with patch("tools.price.storage.read_baseline_csv", side_effect=RuntimeError("unexpected")):
            result = get_price_ohlcv("SOL", "2024-01-01", "2024-01-31", "test unexpected error")
        assert isinstance(result, dict)
        assert "error" in result
        assert "RuntimeError" in result["error"]


class TestGetPriceOhlcvSuccessFormat:
    """Property 13: Successful returns always have raw, source, content_reference, summary."""

    def test_success_has_all_four_fields(self):
        df = _make_baseline_df()
        with patch("tools.price.storage.read_baseline_csv", return_value=df):
            result = get_price_ohlcv("BNB", "2024-01-01", "2024-01-10", "BNB price for analysis")
        assert "error" not in result
        assert "raw" in result
        assert "source" in result
        assert "content_reference" in result
        assert "summary" in result

    def test_raw_is_list_of_records(self):
        df = _make_baseline_df()
        with patch("tools.price.storage.read_baseline_csv", return_value=df):
            result = get_price_ohlcv("XRP", "2024-01-01", "2024-01-10", "XRP price records")
        assert "error" not in result
        assert isinstance(result["raw"], list)
        if result["raw"]:
            record = result["raw"][0]
            assert "date" in record
            assert "open" in record
            assert "high" in record
            assert "low" in record
            assert "close" in record
            assert "volume" in record


class TestGetPriceOhlcvFallback:
    """Req 6.5: CoinGecko fallback when Binance fails."""

    def test_binance_failure_tries_coingecko(self):
        """When end_date > BASELINE_END_DATE and Binance fails, try CoinGecko."""
        baseline_df = _make_large_baseline_df()
        mock_recent_df = pd.DataFrame([{
            "date": "2026-06-15",
            "open": 100.0,
            "high": 105.0,
            "low": 95.0,
            "close": 102.0,
            "volume": 1000.0,
        }])

        with patch("tools.price.storage.read_baseline_csv", return_value=baseline_df):
            with patch("tools.price.fetch_recent_from_exchange", side_effect=Exception("Binance down")):
                with patch("tools.price._fetch_recent_from_coingecko", return_value=mock_recent_df) as mock_cg:
                    result = get_price_ohlcv("SOL", "2026-05-01", "2026-06-15", "test fallback")
                    mock_cg.assert_called_once()
                    # Should succeed (baseline + coingecko data)
                    assert "error" not in result

    def test_both_sources_fail_returns_error(self):
        """When both live sources fail, reject stale baseline-only data."""
        baseline_df = _make_large_baseline_df()

        with patch("tools.price.storage.read_baseline_csv", return_value=baseline_df):
            with patch("tools.price.fetch_recent_from_exchange", side_effect=Exception("Binance down")):
                with patch("tools.price._fetch_recent_from_coingecko", side_effect=Exception("CG down")):
                    result = get_price_ohlcv("SOL", "2024-01-01", "2026-06-15", "test both fail")
                    assert "error" in result
                    assert "拒絕以基準資料冒充目前資料" in result["error"]

    def test_no_recent_fetch_when_end_date_within_baseline(self):
        """When end_date <= BASELINE_END_DATE, should NOT call fetch_recent."""
        baseline_df = _make_large_baseline_df()

        with patch("tools.price.storage.read_baseline_csv", return_value=baseline_df):
            with patch("tools.price.fetch_recent_from_exchange") as mock_fetch:
                result = get_price_ohlcv("SOL", "2024-01-01", "2024-06-30", "within baseline")
                mock_fetch.assert_not_called()
                assert "error" not in result
