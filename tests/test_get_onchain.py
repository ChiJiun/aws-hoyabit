"""
Unit tests for get_onchain dispatcher function.

Tests verify:
- Correct dispatch to each symbol's fetch function
- Unsupported symbol returns error dict
- Top-level exception safety (never throws)
- Case-insensitive symbol handling
"""

import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambda"))

from tools.onchain import get_onchain


# --- Mock return values ---
_SUCCESS_RESULT = {
    "raw": {"tx_count": {"total": 100}},
    "source": "https://example.com",
    "content_reference": {"endpoints_called": ["https://example.com/api"]},
    "summary": "Test summary",
}

_ERROR_RESULT = {
    "error": "[test] Something went wrong",
    "source": "https://example.com",
    "content_reference": {},
}


class TestGetOnchainDispatch:
    """Test that get_onchain dispatches to correct fetch functions."""

    @patch("tools.onchain.fetch_btc_onchain")
    def test_dispatch_btc(self, mock_fetch):
        mock_fetch.return_value = _SUCCESS_RESULT
        result = get_onchain("BTC", ["tx_count"], 7, "claim")
        mock_fetch.assert_called_once_with(["tx_count"], 7)
        assert result == _SUCCESS_RESULT

    @patch("tools.onchain.fetch_evm_onchain")
    def test_dispatch_eth(self, mock_fetch):
        mock_fetch.return_value = _SUCCESS_RESULT
        result = get_onchain("ETH", ["gas_price"], 14, "claim")
        mock_fetch.assert_called_once_with("ethereum", ["gas_price"], 14)
        assert result == _SUCCESS_RESULT

    @patch("tools.onchain.fetch_evm_onchain")
    def test_dispatch_bnb(self, mock_fetch):
        mock_fetch.return_value = _SUCCESS_RESULT
        result = get_onchain("BNB", ["supply"], 30, "claim")
        mock_fetch.assert_called_once_with("bsc", ["supply"], 30)
        assert result == _SUCCESS_RESULT

    @patch("tools.onchain.fetch_sol_onchain")
    def test_dispatch_sol(self, mock_fetch):
        mock_fetch.return_value = _SUCCESS_RESULT
        result = get_onchain("SOL", ["tps"], 7, "claim")
        mock_fetch.assert_called_once_with(["tps"], 7)
        assert result == _SUCCESS_RESULT

    @patch("tools.onchain.fetch_xrp_onchain")
    def test_dispatch_xrp(self, mock_fetch):
        mock_fetch.return_value = _SUCCESS_RESULT
        result = get_onchain("XRP", ["fee"], 7, "claim")
        mock_fetch.assert_called_once_with(["fee"], 7)
        assert result == _SUCCESS_RESULT


class TestGetOnchainCaseInsensitive:
    """Test that symbol matching is case-insensitive."""

    @patch("tools.onchain.fetch_btc_onchain")
    def test_lowercase_btc(self, mock_fetch):
        mock_fetch.return_value = _SUCCESS_RESULT
        result = get_onchain("btc", ["tx_count"], 7, "claim")
        mock_fetch.assert_called_once()
        assert result == _SUCCESS_RESULT

    @patch("tools.onchain.fetch_sol_onchain")
    def test_mixed_case_sol(self, mock_fetch):
        mock_fetch.return_value = _SUCCESS_RESULT
        result = get_onchain("Sol", ["tps"], 7, "claim")
        mock_fetch.assert_called_once()
        assert result == _SUCCESS_RESULT


class TestGetOnchainUnsupportedSymbol:
    """Test unsupported symbols return error dict."""

    def test_unsupported_symbol(self):
        result = get_onchain("DOGE", ["tx_count"], 7, "claim")
        assert "error" in result
        assert "DOGE" in result["error"]
        assert result["source"] == ""
        assert result["content_reference"] == {}

    def test_empty_symbol(self):
        result = get_onchain("", ["tx_count"], 7, "claim")
        assert "error" in result
        assert result["content_reference"] == {}

    def test_none_symbol(self):
        """None symbol should be caught by top-level try/except."""
        result = get_onchain(None, ["tx_count"], 7, "claim")
        assert "error" in result
        assert result["content_reference"] == {}


class TestGetOnchainExceptionSafety:
    """Test that get_onchain never raises an unhandled exception."""

    @patch("tools.onchain.fetch_btc_onchain")
    def test_fetch_raises_exception(self, mock_fetch):
        """Even if a fetch function raises, get_onchain returns error dict."""
        mock_fetch.side_effect = RuntimeError("Network timeout")
        result = get_onchain("BTC", ["tx_count"], 7, "claim")
        assert "error" in result
        assert "RuntimeError" in result["error"]
        assert "Network timeout" in result["error"]
        assert result["source"] == ""
        assert result["content_reference"] == {}

    @patch("tools.onchain.fetch_evm_onchain")
    def test_fetch_raises_unexpected_error(self, mock_fetch):
        """Unexpected errors are caught by top-level except."""
        mock_fetch.side_effect = TypeError("unexpected None")
        result = get_onchain("ETH", None, 7, "claim")
        assert "error" in result
        assert "TypeError" in result["error"]


class TestGetOnchainReturnFormat:
    """Test that return format matches the unified specification."""

    @patch("tools.onchain.fetch_btc_onchain")
    def test_success_format_has_required_keys(self, mock_fetch):
        mock_fetch.return_value = _SUCCESS_RESULT
        result = get_onchain("BTC", ["tx_count"], 7, "claim")
        assert "raw" in result
        assert "source" in result
        assert "content_reference" in result
        assert "summary" in result

    @patch("tools.onchain.fetch_btc_onchain")
    def test_error_from_fetch_has_required_keys(self, mock_fetch):
        mock_fetch.return_value = _ERROR_RESULT
        result = get_onchain("BTC", ["tx_count"], 7, "claim")
        assert "error" in result
        assert "source" in result
        assert "content_reference" in result
