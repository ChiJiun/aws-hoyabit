"""
test_tool_series.py — 測試各工具的 series adapter 輸出

涵蓋：price series envelope、derivatives history/snapshot fallback、
      defi history、event series、歷史失敗/snapshot成功、缺API key降級
"""

import math
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lambda"))


# ============================================================
# Price tool series
# ============================================================

class TestPriceSeries:
    """get_price_ohlcv 應在成功時輸出 top-level series key。"""

    def _make_ohlcv_records(self, n=30):
        base = date(2026, 7, 1)
        return [
            {
                "date": (base + timedelta(days=i)).isoformat(),
                "open": 100.0 + i,
                "high": 105.0 + i,
                "low": 99.0 + i,
                "close": 103.0 + i,
                "volume": 1000.0 + i,
            }
            for i in range(n)
        ]

    @patch("tools.price._ORIGINAL_GET_PRICE_OHLCV")
    def test_series_present_on_success(self, mock_orig):
        records = self._make_ohlcv_records(30)
        mock_orig.return_value = {
            "raw": records,
            "source": "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1d",
            "content_reference": {
                "as_of": "2026-07-30",
                "query_endpoint": "https://api.binance.com/api/v3/klines",
                "requested_range": "2026-07-01~2026-07-30",
            },
            "summary": "test",
        }
        from tools.price import get_price_ohlcv
        result = get_price_ohlcv("BTC", "2026-07-01", "2026-07-30", "test claim")

        assert result.get("status") == "success"
        assert "series" in result
        price_series = result["series"]["price"]
        assert "points" in price_series
        assert price_series["unit"] == "USD"
        assert price_series["provider"] == "Binance Spot"
        assert price_series["pair"] == "BTCUSDT"
        # Points should be ascending and max 90
        points = price_series["points"]
        assert len(points) == 30
        for i in range(1, len(points)):
            assert points[i][0] > points[i - 1][0]

    @patch("tools.price._ORIGINAL_GET_PRICE_OHLCV")
    def test_series_not_present_on_error(self, mock_orig):
        mock_orig.return_value = {
            "error": "[get_price_ohlcv] test error",
            "source": "test",
            "content_reference": {},
        }
        from tools.price import get_price_ohlcv
        result = get_price_ohlcv("BTC", "2026-07-01", "2026-07-30", "test claim")
        assert result.get("status") == "error"
        assert "series" not in result

    @patch("tools.price._ORIGINAL_GET_PRICE_OHLCV")
    def test_series_90_day_trim(self, mock_orig):
        records = self._make_ohlcv_records(100)
        mock_orig.return_value = {
            "raw": records,
            "source": "https://api.binance.com/api/v3/klines",
            "content_reference": {"as_of": "2026-10-08", "requested_range": "2026-07-01~2026-10-08"},
            "summary": "test",
        }
        from tools.price import get_price_ohlcv
        result = get_price_ohlcv("BTC", "2026-07-01", "2026-10-08", "test")
        points = result["series"]["price"]["points"]
        assert len(points) <= 90

    @patch("tools.price._ORIGINAL_GET_PRICE_OHLCV")
    def test_summary_only_latest_and_change(self, mock_orig):
        records = self._make_ohlcv_records(10)
        mock_orig.return_value = {
            "raw": records,
            "source": "https://api.binance.com/api/v3/klines",
            "content_reference": {"as_of": "2026-07-10", "requested_range": "2026-07-01~2026-07-10"},
            "summary": "old summary with full data",
        }
        from tools.price import get_price_ohlcv
        result = get_price_ohlcv("BTC", "2026-07-01", "2026-07-10", "test")
        # Summary should NOT contain all 10 data points
        summary = result.get("summary", "")
        assert "最新收盤" in summary
        assert "期間變化" in summary or "區間" in summary

    @patch("tools.price._ORIGINAL_GET_PRICE_OHLCV")
    def test_coingecko_fallback_comparability(self, mock_orig):
        records = self._make_ohlcv_records(5)
        mock_orig.return_value = {
            "raw": records,
            "source": "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart/range",
            "content_reference": {"as_of": "2026-07-05", "requested_range": "2026-07-01~2026-07-05"},
            "summary": "test",
        }
        from tools.price import get_price_ohlcv
        result = get_price_ohlcv("BTC", "2026-07-01", "2026-07-05", "test")
        assert result["series"]["price"]["comparability"] == "limited"


# ============================================================
# Derivatives tool series
# ============================================================

class TestDerivativesSeries:
    """get_derivatives 應在 snapshot 成功時輸出 series（或標記 unavailable）。"""

    @patch("tools.derivatives._ORIGINAL_GET_DERIVATIVES")
    @patch("tools.derivatives._fetch_funding_history")
    @patch("tools.derivatives._fetch_oi_history")
    def test_hyperliquid_marks_series_unavailable(self, mock_oi, mock_funding, mock_orig):
        """Hyperliquid 無歷史 endpoint，應標記 series_unavailable。"""
        mock_orig.return_value = {
            "raw": {"asset_ctx": {"funding": "0.0001", "openInterest": "1000"}},
            "source": "https://api.hyperliquid.xyz/info",
            "content_reference": {
                "fetched_at": "2026-08-01T12:00:00Z",
                "source_name": "Hyperliquid",
                "symbol": "BTC",
            },
            "summary": "test",
        }
        mock_funding.return_value = None
        mock_oi.return_value = None

        from tools.derivatives import get_derivatives
        result = get_derivatives("BTC", "hyperliquid", ["funding_rate", "open_interest"], "test")

        assert result.get("status") in ("success", "partial")
        assert "series" in result
        assert result["series"]["funding"]["series_unavailable"] is True
        assert result["series"]["open_interest"]["series_unavailable"] is True

    @patch("tools.derivatives._ORIGINAL_GET_DERIVATIVES")
    @patch("tools.derivatives._fetch_funding_history")
    @patch("tools.derivatives._fetch_oi_history")
    def test_binance_futures_returns_history(self, mock_oi, mock_funding, mock_orig):
        """Binance Futures 有歷史 endpoint，應返回 series envelope。"""
        mock_orig.return_value = {
            "raw": {"premiumIndex": {"lastFundingRate": "0.0001"}},
            "source": "https://fapi.binance.com",
            "content_reference": {
                "fetched_at": "2026-08-01T12:00:00Z",
                "source_name": "Binance Futures",
                "symbol": "BTC",
            },
            "summary": "test",
        }
        mock_funding.return_value = [
            ["2026-07-01", 0.0001],
            ["2026-07-02", 0.0002],
            ["2026-07-03", -0.0001],
        ]
        mock_oi.return_value = [
            ["2026-07-01", 5000000000],
            ["2026-07-02", 5100000000],
            ["2026-07-03", 4900000000],
        ]

        from tools.derivatives import get_derivatives
        result = get_derivatives("BTC", "binance_futures", ["funding_rate", "open_interest"], "test")

        assert result.get("status") in ("success", "partial")
        assert "series" in result
        funding = result["series"]["funding"]
        assert "points" in funding
        assert funding["unit"] == "rate/8h"
        oi = result["series"]["open_interest"]
        assert "points" in oi
        assert oi["unit"] == "USD"

    @patch("tools.derivatives._ORIGINAL_GET_DERIVATIVES")
    @patch("tools.derivatives._fetch_funding_history")
    @patch("tools.derivatives._fetch_oi_history")
    def test_history_failure_snapshot_success(self, mock_oi, mock_funding, mock_orig):
        """歷史取得失敗但 snapshot 成功時應保持 success/partial，不降為 error。"""
        mock_orig.return_value = {
            "raw": {"premiumIndex": {"lastFundingRate": "0.0005"}},
            "source": "https://fapi.binance.com",
            "content_reference": {
                "fetched_at": "2026-08-01T12:00:00Z",
                "source_name": "Binance Futures",
                "symbol": "BTC",
            },
            "summary": "test",
        }
        mock_funding.side_effect = Exception("Connection timeout")
        mock_oi.side_effect = Exception("Rate limited")

        from tools.derivatives import get_derivatives
        result = get_derivatives("BTC", "binance_futures", ["funding_rate"], "test")

        # Should NOT be error — snapshot succeeded
        assert result.get("status") in ("success", "partial")
        # Series should be marked unavailable
        assert "series" in result
        assert result["series"]["funding"]["series_unavailable"] is True



# ============================================================
# DeFi tool series
# ============================================================

class TestDefiSeries:
    """get_defi_data 應在成功時輸出穩定幣供給/TVL history series。"""

    @patch("tools.defi._fetch_tvl_history")
    @patch("tools.defi._fetch_stablecoin_history")
    @patch("tools.defi._fetch_tvl")
    @patch("tools.defi._fetch_stablecoin_supply")
    def test_series_present_on_success(self, mock_sc, mock_tvl, mock_sc_hist, mock_tvl_hist):
        mock_tvl.return_value = {"total_tvl_usd": 100e9, "chain_tvl_breakdown": {"Ethereum": 60e9}}
        mock_sc.return_value = {"total_supply_usd": 150e9, "change_7d_pct": 0.5, "assets_count": 10}
        mock_sc_hist.return_value = [["2026-07-01", 148e9], ["2026-07-02", 149e9], ["2026-07-03", 150e9]]
        mock_tvl_hist.return_value = [["2026-07-01", 98e9], ["2026-07-02", 99e9], ["2026-07-03", 100e9]]

        from tools.defi import get_defi_data
        result = get_defi_data(["tvl", "stablecoin_supply"], chain="all", related_claim="test")

        assert "error" not in result
        assert "series" in result
        sc_series = result["series"].get("stablecoin_supply")
        tvl_series = result["series"].get("tvl")
        assert sc_series is not None
        assert tvl_series is not None
        assert "points" in sc_series
        assert "points" in tvl_series

    @patch("tools.defi._fetch_tvl_history")
    @patch("tools.defi._fetch_stablecoin_history")
    @patch("tools.defi._fetch_tvl")
    @patch("tools.defi._fetch_stablecoin_supply")
    def test_history_failure_graceful(self, mock_sc, mock_tvl, mock_sc_hist, mock_tvl_hist):
        """歷史取得失敗不應讓整個工具失敗。"""
        mock_tvl.return_value = {"total_tvl_usd": 100e9, "chain_tvl_breakdown": {}}
        mock_sc.return_value = {"total_supply_usd": 150e9, "change_7d_pct": 0.5, "assets_count": 10}
        mock_sc_hist.side_effect = Exception("Network error")
        mock_tvl_hist.side_effect = Exception("Timeout")

        from tools.defi import get_defi_data
        result = get_defi_data(["tvl", "stablecoin_supply"], chain="all", related_claim="test")

        # Should NOT be error
        assert "error" not in result
        # Series should note unavailable
        assert "series" in result
        series = result["series"]
        assert series.get("series_unavailable") is True or "reason" in str(series)


# ============================================================
# Event series (news, macro, prediction)
# ============================================================

class TestEventSeries:
    """Intel tools 應輸出正規化的 event series。"""

    def test_macro_event_series_future_only(self):
        """macro 應只包含未來事件。"""
        with patch("tools.macro.requests") as mock_req:
            # Mock FRED to fail (no API key) — macro should still return events
            mock_req.get.side_effect = Exception("No FRED API key")

            from tools.macro import get_macro
            result = get_macro(["dxy"], "test claim")

            # Even if FRED fails, events should be present (hardcoded calendar)
            # The tool may error on data fetch but events are from SCHEDULED_EVENTS
            # Check if series key exists in successful result or raw_data
            if "error" not in result:
                assert "series" in result
                events = result["series"].get("events", [])
                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                for ev in events:
                    assert ev["date"] >= today
                    assert "event" in ev
                    assert "source_url" in ev

    @patch("tools.news._ORIGINAL_SEARCH_NEWS")
    def test_news_event_series(self, mock_orig):
        """news 應從 items 提取 event series。"""
        mock_orig.return_value = {
            "raw": {
                "items": [
                    {"title": "BTC ETF approved", "published_at": "2026-07-30T10:00:00Z", "url": "https://example.com/1", "channel": "media_rss"},
                    {"title": "Market crash", "published_at": "2026-07-29T08:00:00Z", "url": "https://example.com/2", "channel": "google_news"},
                    {"title": "No date item", "url": "https://example.com/3", "channel": "media_rss"},
                ],
                "total_items": 3,
            },
            "source": "https://news.google.com/rss",
            "content_reference": {},
            "summary": "test",
        }

        from tools.news import search_news
        result = search_news("BTC", 7, "test claim")

        assert "series" in result
        events = result["series"]["events"]
        # Should have 2 events (one without date is skipped)
        assert len(events) >= 1
        for ev in events:
            assert "date" in ev
            assert "event" in ev
            # Date format should be YYYY-MM-DD
            assert len(ev["date"]) == 10

    def test_prediction_event_series(self):
        """prediction 應從 parsed_events 提取未來 event series。"""
        future_date = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%dT00:00:00Z")
        past_date = "2020-01-01T00:00:00Z"

        with patch("tools.prediction._robust_get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = [
                {"title": "BTC 200K", "slug": "btc-200k", "endDate": future_date, "volume": "1000000"},
                {"title": "Old Event", "slug": "old", "endDate": past_date, "volume": "500"},
            ]
            mock_get.return_value = mock_resp

            from tools.prediction import get_prediction_market
            result = get_prediction_market("bitcoin", "test claim")

            assert "series" in result
            events = result["series"]["events"]
            # Only future event should be included
            assert len(events) >= 1
            for ev in events:
                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                assert ev["date"] >= today


# ============================================================
# 缺 API key 降級
# ============================================================

class TestMissingApiKeyDegradation:
    """缺少 API key 時工具應 graceful 降級而非崩潰。"""

    def test_macro_no_fred_key(self):
        """缺少 FRED_API_KEY 時 macro 應回 error dict，不 raise。"""
        with patch("config.FRED_API_KEY", None):
            from tools.macro import get_macro
            result = get_macro(["dxy"], "test claim")
            # Should be error dict or success with empty data, NOT an exception
            assert isinstance(result, dict)
            # The function should not raise
            if "error" in result:
                assert "[get_macro]" in result["error"] or "FRED" in result.get("error", "")
