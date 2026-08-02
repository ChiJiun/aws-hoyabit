from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lambda"))

from tools import derivatives, news, price, quant


def _success_result(source, reference=None, raw=None):
    return {
        "raw": raw or {},
        "source": source,
        "content_reference": reference or {},
        "summary": "ok",
    }


def test_price_result_has_c1_quality_and_normalized_pair():
    original = _success_result(
        "https://api.binance.com/api/v3/klines",
        {
            "as_of": "2026-08-01",
            "query_endpoint": "https://api.binance.com/api/v3/klines",
            "requested_range": "2026-07-20~2026-08-01",
        },
        [
            {"date": f"2026-07-{day:02d}", "close": 100 + day}
            for day in range(1, 22)
        ],
    )
    with patch("tools.price._ORIGINAL_GET_PRICE_OHLCV", return_value=original):
        result = price.get_price_ohlcv("btc", "2026-07-20", "2026-08-01", "驗證近期價格狀態")
    assert result["schema_version"] == "1.0"
    assert result["content_reference"]["pair"] == "BTCUSDT"
    assert result["content_reference"]["provider"] == "Binance Spot"
    assert "quality" in result["content_reference"]


def test_quant_detects_configured_a1_to_a4_anomalies():
    results = {
        "volume_zscore": {"value": 3.1, "percentile": 99.0},
        "bollinger_bandwidth": {"value": 2.0, "percentile": 5.0},
        "atr_pct": {"value": 8.0, "percentile": 95.0},
        "adx": {"value": 12.0, "percentile": 10.0},
    }
    flags = quant.detect_quant_anomalies(results, 20, "2026-08-01")
    assert {flag["signal_id"] for flag in flags} == {"A1", "A2", "A3", "A4"}
    assert all(flag["window"] == "20d" for flag in flags)


def test_derivatives_hyperliquid_failure_uses_binance_fallback():
    primary = {
        "error": "Hyperliquid timeout",
        "source": "https://api.hyperliquid.xyz/info",
        "content_reference": {},
    }
    fallback = _success_result(
        "https://fapi.binance.com",
        {
            "fetched_at": "2026-08-01T12:00:00+00:00",
            "endpoints_called": ["https://fapi.binance.com/fapi/v1/premiumIndex"],
            "funding_rate": 0.0001,
            "open_interest_qty": 10,
        },
    )
    with patch("tools.derivatives._ORIGINAL_GET_DERIVATIVES", return_value=primary), patch(
        "tools.derivatives._fetch_binance_futures", return_value=fallback
    ) as mock_fallback:
        result = derivatives.get_derivatives(
            "BTC", "hyperliquid", ["funding_rate", "open_interest"], "驗證槓桿是否堆積"
        )
    mock_fallback.assert_called_once()
    reliability = result["content_reference"]["quality"]["reliability"]
    assert result["status"] == "success"
    assert result["content_reference"]["provider"] == "Binance Futures"
    assert reliability["fallback_used"] is True
    assert reliability["attempts"] == 2
    assert result["content_reference"]["primary_source_error"] == "Hyperliquid timeout"


def test_derivatives_both_sources_fail_returns_c1_error():
    primary = {"error": "primary failed", "source": "hyperliquid", "content_reference": {}}
    fallback = {"error": "fallback failed", "source": "binance", "content_reference": {}}
    with patch("tools.derivatives._ORIGINAL_GET_DERIVATIVES", return_value=primary), patch(
        "tools.derivatives._fetch_binance_futures", return_value=fallback
    ):
        result = derivatives.get_derivatives(
            "BTC", "hyperliquid", ["funding_rate"], "驗證 funding 狀態"
        )
    assert result["status"] == "error"
    assert result["content_reference"]["quality"]["reliability"]["attempts"] == 2
    assert len(result["content_reference"]["quality"]["reliability"]["errors"]) == 2


def test_news_detects_density_and_major_event():
    now = datetime(2026, 8, 1, 12, tzinfo=timezone.utc)
    items = [
        {
            "title": f"Bitcoin ETF approval update {index}",
            "published_at": (now - timedelta(hours=index * 4)).isoformat(),
        }
        for index in range(8)
    ]
    items.append({
        "title": "Bitcoin market background",
        "published_at": (now - timedelta(days=10)).isoformat(),
    })
    flags = news.detect_news_anomalies(items, 14, now)
    ids = {flag["signal_id"] for flag in flags}
    assert "A7" in ids
    assert "A8" in ids
    assert all(set(("signal_id", "threshold", "as_of", "message")) <= set(flag) for flag in flags)
