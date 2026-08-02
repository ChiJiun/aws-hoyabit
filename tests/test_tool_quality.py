from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
import sys

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lambda"))

from tools.quality import (
    ToolHttpError,
    evaluate_freshness,
    request_with_retry,
    standardize_tool_result,
)


def test_freshness_fresh_stale_and_unknown():
    reference = "2026-08-01T12:00:00+00:00"
    assert evaluate_freshness("2026-08-01T11:59:30Z", 60, reference)["status"] == "fresh"
    assert evaluate_freshness("2026-08-01T11:58:00Z", 60, reference)["status"] == "stale"
    assert evaluate_freshness(None, 60, reference)["status"] == "unknown"


def test_standardize_success_preserves_legacy_fields_and_adds_quality():
    result = standardize_tool_result(
        {"raw": {"x": 1}, "source": "https://example.test", "summary": "ok", "content_reference": {}},
        provider="Example",
        endpoint="https://example.test",
        symbol="btc",
        pair="BTCUSDT",
        timeframe="snapshot",
        window="snapshot",
        unit={"x": "count"},
        as_of="2026-08-01T11:59:30Z",
        reference_time="2026-08-01T12:00:00Z",
        max_age_seconds=60,
    )
    assert result["schema_version"] == "1.0"
    assert result["status"] == "success"
    assert result["raw"] == {"x": 1}
    assert result["summary"] == "ok"
    assert result["content_reference"]["provider"] == "Example"
    assert result["content_reference"]["freshness_status"] == "fresh"
    assert result["anomaly_flags"] == []


def test_standardize_error_keeps_trace_metadata():
    result = standardize_tool_result(
        {"error": "timeout", "source": "https://example.test", "content_reference": {}},
        provider="Example",
        endpoint="https://example.test",
        symbol="BTC",
        pair="BTCUSDT",
        timeframe="snapshot",
        window="snapshot",
        unit={},
        max_age_seconds=60,
    )
    assert result["status"] == "error"
    assert result["content_reference"]["freshness_status"] == "unknown"
    assert result["content_reference"]["quality"]["reliability"]["attempts"] == 1


def _response(status_code=200):
    response = MagicMock()
    response.status_code = status_code
    response.headers = {}
    if status_code >= 400 and status_code not in {429, 500, 502, 503, 504}:
        response.raise_for_status.side_effect = requests.HTTPError(f"HTTP {status_code}")
    else:
        response.raise_for_status.return_value = None
    return response


def test_request_retries_connection_error_then_succeeds():
    success = _response(200)
    with patch("tools.quality.requests.get", side_effect=[requests.ConnectionError("down"), success]) as mock_get:
        response, metadata = request_with_retry(
            "GET", "https://example.test", max_attempts=2, sleep_func=lambda _: None
        )
    assert response is success
    assert mock_get.call_count == 2
    assert metadata["attempts"] == 2
    assert metadata["errors"]


def test_request_retries_429_and_marks_rate_limit():
    limited = _response(429)
    limited.headers = {"Retry-After": "0"}
    success = _response(200)
    with patch("tools.quality.requests.get", side_effect=[limited, success]) as mock_get:
        _, metadata = request_with_retry(
            "GET", "https://example.test", max_attempts=2, sleep_func=lambda _: None
        )
    assert mock_get.call_count == 2
    assert metadata["rate_limited"] is True


def test_request_does_not_retry_non_transient_400():
    bad_request = _response(400)
    with patch("tools.quality.requests.get", return_value=bad_request) as mock_get:
        try:
            request_with_retry(
                "GET", "https://example.test", max_attempts=2, sleep_func=lambda _: None
            )
            raise AssertionError("expected ToolHttpError")
        except ToolHttpError as exc:
            assert exc.request_metadata["attempts"] == 1
    mock_get.assert_called_once()
