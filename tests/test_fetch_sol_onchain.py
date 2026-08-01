"""Unit tests for fetch_sol_onchain function."""
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambda"))

from tools.onchain import fetch_sol_onchain


def _mock_rpc_response(result):
    """Create a mock response object for a successful JSON-RPC call."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"jsonrpc": "2.0", "id": 1, "result": result}
    return mock_resp


def _mock_rpc_responses(results_by_method):
    """Create a side_effect function that returns different results per RPC method."""
    def side_effect(url, json=None, timeout=None, headers=None):
        method = json.get("method") if json else ""
        result = results_by_method.get(method, {})
        return _mock_rpc_response(result)
    return side_effect


# --- Sample RPC responses ---
_PERFORMANCE_SAMPLES = [
    {"numTransactions": 5000, "numSlots": 10, "samplePeriodSecs": 60, "slot": 100}
    for _ in range(10)
]

_EPOCH_INFO = {
    "absoluteSlot": 250000000,
    "blockHeight": 230000000,
    "epoch": 580,
    "slotIndex": 200000,
    "slotsInEpoch": 432000,
    "transactionCount": 999999999,
}

_VOTE_ACCOUNTS = {
    "current": [
        {"activatedStake": 1000000000000, "votePubkey": "val1"},
        {"activatedStake": 2000000000000, "votePubkey": "val2"},
    ],
    "delinquent": [
        {"activatedStake": 500000000000, "votePubkey": "val3"},
    ],
}

_SUPPLY = {
    "value": {
        "total": 570000000000000000,
        "circulating": 430000000000000000,
        "nonCirculating": 140000000000000000,
        "nonCirculatingAccounts": [],
    }
}

_ALL_METHODS = {
    "getRecentPerformanceSamples": _PERFORMANCE_SAMPLES,
    "getEpochInfo": _EPOCH_INFO,
    "getVoteAccounts": _VOTE_ACCOUNTS,
    "getSupply": _SUPPLY,
}


@patch("tools.onchain.evidence")
@patch("tools.onchain.requests.post")
@patch("config.HELIUS_API_KEY", "test-api-key-123")
def test_success_all_metrics(mock_post, mock_evidence):
    """With all metrics requested, should return raw data for all supported metrics."""
    mock_post.side_effect = _mock_rpc_responses(_ALL_METHODS)

    result = fetch_sol_onchain(None, 7)

    assert "error" not in result
    assert "raw" in result
    assert "source" in result
    assert "content_reference" in result
    assert "summary" in result

    raw = result["raw"]
    assert "tps" in raw
    assert "tx_count" in raw
    assert "epoch_info" in raw
    assert "slot_height" in raw
    assert "active_validators" in raw
    assert "supply" in raw

    # Verify TPS calculation
    assert raw["tps"]["avg_tps"] > 0
    assert raw["tps"]["total_transactions"] == 50000  # 5000 * 10

    # Verify epoch info
    assert raw["epoch_info"]["epoch"] == 580
    assert raw["epoch_info"]["absolute_slot"] == 250000000

    # Verify validators
    assert raw["active_validators"]["active_count"] == 2
    assert raw["active_validators"]["delinquent_count"] == 1

    # Verify supply
    assert raw["supply"]["total_sol"] > 0
    assert raw["supply"]["circulating_sol"] > 0

    # Verify evidence was logged
    mock_evidence.log_execution_step.assert_called_once()
    call_kwargs = mock_evidence.log_execution_step.call_args[1]
    assert call_kwargs["tool_name"] == "fetch_sol_onchain"
    assert call_kwargs["status"] == "success"


@patch("tools.onchain.evidence")
@patch("tools.onchain.requests.post")
@patch("config.HELIUS_API_KEY", "test-api-key-123")
def test_specific_metrics_only(mock_post, mock_evidence):
    """When specific metrics are requested, only those should be fetched."""
    mock_post.side_effect = _mock_rpc_responses(_ALL_METHODS)

    result = fetch_sol_onchain(["tps", "supply"], 14)

    assert "error" not in result
    raw = result["raw"]
    assert "tps" in raw
    assert "supply" in raw
    # epoch_info and active_validators should NOT be fetched
    assert "active_validators" not in raw
    assert "epoch_info" not in raw


@patch("tools.onchain.evidence")
@patch("config.HELIUS_API_KEY", "")
def test_missing_api_key(mock_evidence):
    """Should return error dict when HELIUS_API_KEY is not configured."""
    result = fetch_sol_onchain(None, 7)

    assert "error" in result
    assert "HELIUS_API_KEY" in result["error"]
    assert result["source"] == "https://mainnet.helius-rpc.com (Helius Solana RPC)"
    assert result["content_reference"] == {}

    mock_evidence.log_execution_step.assert_called_once()
    call_kwargs = mock_evidence.log_execution_step.call_args[1]
    assert call_kwargs["status"] == "error"


@patch("tools.onchain.evidence")
@patch("config.HELIUS_API_KEY", None)
def test_none_api_key(mock_evidence):
    """Should return error dict when HELIUS_API_KEY is None."""
    result = fetch_sol_onchain(["tps"], 7)

    assert "error" in result
    assert "HELIUS_API_KEY" in result["error"]


@patch("tools.onchain.evidence")
@patch("tools.onchain.requests.post")
@patch("config.HELIUS_API_KEY", "test-api-key-123")
def test_network_error_returns_error_dict(mock_post, mock_evidence):
    """Network errors should be caught and returned as error dict (Property 12: never throw)."""
    mock_post.side_effect = Exception("Connection timeout")

    result = fetch_sol_onchain(["tps"], 7)

    assert "error" in result
    assert "Connection timeout" in result["error"]
    assert result["source"] == "https://mainnet.helius-rpc.com (Helius Solana RPC)"
    assert result["content_reference"] == {}

    mock_evidence.log_execution_step.assert_called_once()
    call_kwargs = mock_evidence.log_execution_step.call_args[1]
    assert call_kwargs["status"] == "error"


@patch("tools.onchain.evidence")
@patch("tools.onchain.requests.post")
@patch("config.HELIUS_API_KEY", "test-api-key-123")
def test_string_metric_handled(mock_post, mock_evidence):
    """A single metric passed as string should be handled correctly."""
    mock_post.side_effect = _mock_rpc_responses(_ALL_METHODS)

    result = fetch_sol_onchain("supply", 7)

    assert "error" not in result
    assert "supply" in result["raw"]


@patch("tools.onchain.evidence")
@patch("tools.onchain.requests.post")
@patch("config.HELIUS_API_KEY", "test-api-key-123")
def test_unsupported_metrics_fallback_to_all(mock_post, mock_evidence):
    """If all requested metrics are unsupported, fallback to fetching all."""
    mock_post.side_effect = _mock_rpc_responses(_ALL_METHODS)

    result = fetch_sol_onchain(["unknown_metric", "bad_metric"], 7)

    assert "error" not in result
    raw = result["raw"]
    # Should have fetched all supported metrics
    assert len(raw) >= 1


@patch("tools.onchain.evidence")
@patch("tools.onchain.requests.post")
@patch("config.HELIUS_API_KEY", "test-api-key-123")
def test_content_reference_structure(mock_post, mock_evidence):
    """content_reference should contain expected fields."""
    mock_post.side_effect = _mock_rpc_responses(_ALL_METHODS)

    result = fetch_sol_onchain(["epoch_info"], 30)

    cr = result["content_reference"]
    assert "endpoints_called" in cr
    assert "metrics_retrieved" in cr
    assert "data_time_range" in cr
    assert "rpc_base" in cr
    assert "fetched_at" in cr
    assert cr["data_time_range"] == "lookback_days=30"
    assert cr["rpc_base"] == "https://mainnet.helius-rpc.com"
