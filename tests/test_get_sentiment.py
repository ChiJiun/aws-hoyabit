"""
Unit tests for get_sentiment function.

Tests verify:
- Successful API call returns unified format dict with raw/source/content_reference/summary
- content_reference includes API endpoint, query time range, index values, classification text
- Failure returns error dict (never raises exceptions)
- Various lookback_days values are handled correctly
"""

import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambda"))

from tools.sentiment import get_sentiment


# --- Mock API response ---
_MOCK_API_RESPONSE = {
    "name": "Fear and Greed Index",
    "data": [
        {"value": "72", "value_classification": "Greed", "timestamp": "1719792000"},
        {"value": "65", "value_classification": "Greed", "timestamp": "1719705600"},
        {"value": "55", "value_classification": "Neutral", "timestamp": "1719619200"},
        {"value": "48", "value_classification": "Neutral", "timestamp": "1719532800"},
        {"value": "40", "value_classification": "Fear", "timestamp": "1719446400"},
    ],
}

_MOCK_EMPTY_RESPONSE = {"name": "Fear and Greed Index", "data": []}


class TestGetSentimentSuccess:
    """Test successful API calls return correct format."""

    @patch("tools.sentiment.requests.get")
    def test_success_returns_required_keys(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = _MOCK_API_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = get_sentiment("測試市場情緒", lookback_days=5)

        assert "raw" in result
        assert "source" in result
        assert "content_reference" in result
        assert "summary" in result
        assert "error" not in result

    @patch("tools.sentiment.requests.get")
    def test_content_reference_has_required_fields(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = _MOCK_API_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = get_sentiment("測試市場情緒", lookback_days=5)
        cr = result["content_reference"]

        assert "api_endpoint" in cr
        assert "query_time_range" in cr
        assert "current_index" in cr
        assert "current_classification" in cr

    @patch("tools.sentiment.requests.get")
    def test_current_value_parsed_correctly(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = _MOCK_API_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = get_sentiment("測試市場情緒", lookback_days=5)
        cr = result["content_reference"]

        assert cr["current_index"] == 72
        assert cr["current_classification"] == "Greed"

    @patch("tools.sentiment.requests.get")
    def test_trend_calculation(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = _MOCK_API_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = get_sentiment("測試市場情緒", lookback_days=5)
        cr = result["content_reference"]

        # current=72, oldest=40, change=+32
        assert cr["value_change"] == 32
        assert cr["oldest_index"] == 40

    @patch("tools.sentiment.requests.get")
    def test_source_contains_api_url(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = _MOCK_API_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = get_sentiment("測試市場情緒", lookback_days=5)

        assert "alternative.me" in result["source"]
        assert "limit=5" in result["source"]

    @patch("tools.sentiment.requests.get")
    def test_summary_in_traditional_chinese(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = _MOCK_API_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = get_sentiment("測試市場情緒", lookback_days=5)

        assert "恐懼與貪婪指數" in result["summary"]
        assert "72" in result["summary"]
        assert "Greed" in result["summary"]


class TestGetSentimentFailure:
    """Test failure scenarios return error dict without raising."""

    @patch("tools.sentiment.requests.get")
    def test_network_error_returns_error_dict(self, mock_get):
        mock_get.side_effect = ConnectionError("Connection refused")

        result = get_sentiment("測試市場情緒", lookback_days=30)

        assert "error" in result
        assert "ConnectionError" in result["error"]
        assert "source" in result
        assert "content_reference" in result
        assert result["content_reference"] == {}

    @patch("tools.sentiment.requests.get")
    def test_timeout_returns_error_dict(self, mock_get):
        import requests
        mock_get.side_effect = requests.exceptions.Timeout("Request timed out")

        result = get_sentiment("測試市場情緒", lookback_days=30)

        assert "error" in result
        assert "Timeout" in result["error"]
        assert result["content_reference"] == {}

    @patch("tools.sentiment.requests.get")
    def test_http_error_returns_error_dict(self, mock_get):
        import requests
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError("500 Server Error")
        mock_get.return_value = mock_resp

        result = get_sentiment("測試市場情緒", lookback_days=30)

        assert "error" in result
        assert "HTTPError" in result["error"]

    @patch("tools.sentiment.requests.get")
    def test_empty_data_returns_error_dict(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = _MOCK_EMPTY_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = get_sentiment("測試市場情緒", lookback_days=30)

        assert "error" in result
        assert "source" in result
        assert result["content_reference"] == {}

    @patch("tools.sentiment.requests.get")
    def test_invalid_json_returns_error_dict(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.side_effect = ValueError("Invalid JSON")
        mock_get.return_value = mock_resp

        result = get_sentiment("測試市場情緒", lookback_days=30)

        assert "error" in result
        assert result["content_reference"] == {}


class TestGetSentimentNeverRaises:
    """Test that get_sentiment never raises an unhandled exception (Property 12)."""

    @patch("tools.sentiment.requests.get")
    def test_unexpected_exception_caught(self, mock_get):
        mock_get.side_effect = RuntimeError("Unexpected error")

        result = get_sentiment("測試市場情緒", lookback_days=30)

        assert isinstance(result, dict)
        assert "error" in result

    @patch("tools.sentiment.requests.get")
    def test_type_error_caught(self, mock_get):
        mock_get.side_effect = TypeError("bad argument")

        result = get_sentiment("claim", lookback_days=None)

        assert isinstance(result, dict)
        assert "error" in result
