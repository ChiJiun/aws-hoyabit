"""
test_fetch_btc_onchain.py — fetch_btc_onchain 單元測試

使用 unittest.mock 模擬 mempool.space API 回應，驗證：
1. 成功時回傳正確格式（raw/source/content_reference/summary）
2. 部分指標請求正確過濾
3. 異常時回傳 error dict 不拋錯
4. evidence.log_execution_step 被正確呼叫
"""

import sys
import os
from unittest.mock import patch, MagicMock

import pytest

# 將 lambda 目錄加入 path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambda"))

from tools.onchain import fetch_btc_onchain


# --- Mock 資料 ---

MOCK_BLOCKS = [
    {"height": 840000 - i, "tx_count": 2000 + i * 10, "timestamp": 1710000000 - i * 600}
    for i in range(15)
]

MOCK_MEMPOOL = {
    "count": 45000,
    "vsize": 150000000,
    "total_fee": 5000000,
}

MOCK_FEES = {
    "fastestFee": 25,
    "halfHourFee": 20,
    "hourFee": 15,
    "economyFee": 8,
    "minimumFee": 5,
}

MOCK_HASHRATE = {
    "currentHashrate": 600000000000000000000,  # 600 EH/s
    "currentDifficulty": 83000000000000,
    "hashrates": [
        {"timestamp": 1710000000, "avgHashrate": 590000000000000000000},
        {"timestamp": 1710086400, "avgHashrate": 595000000000000000000},
        {"timestamp": 1710172800, "avgHashrate": 600000000000000000000},
    ],
}

MOCK_DIFFICULTY_ADJUSTMENT = {
    "progressPercent": 45.5,
    "difficultyChange": 2.35,
    "estimatedRetargetDate": 1710500000,
    "remainingBlocks": 1100,
    "remainingTime": 660000,
    "previousRetarget": -1.2,
}


def _make_mock_response(json_data, status_code=200):
    """建立模擬的 requests.Response 物件。"""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = json_data
    mock_resp.raise_for_status.return_value = None
    return mock_resp


def _side_effect_all_endpoints(url, **kwargs):
    """根據 URL 回傳對應的模擬回應。"""
    if "/fees/recommended" in url:
        return _make_mock_response(MOCK_FEES)
    elif "/mining/hashrate" in url:
        return _make_mock_response(MOCK_HASHRATE)
    elif "/difficulty-adjustment" in url:
        return _make_mock_response(MOCK_DIFFICULTY_ADJUSTMENT)
    elif url.endswith("/blocks"):
        return _make_mock_response(MOCK_BLOCKS)
    elif url.endswith("/mempool"):
        return _make_mock_response(MOCK_MEMPOOL)
    raise ValueError(f"Unexpected URL: {url}")


class TestFetchBtcOnchainSuccess:
    """成功情境測試。"""

    @patch("tools.onchain.evidence")
    @patch("tools.onchain.requests.get")
    def test_all_metrics_returns_unified_format(self, mock_get, mock_evidence):
        """傳入 None metrics 時取得所有指標，回傳格式正確。"""
        mock_get.side_effect = _side_effect_all_endpoints

        result = fetch_btc_onchain(None, 7)

        assert "raw" in result
        assert "source" in result
        assert "content_reference" in result
        assert "summary" in result
        assert "error" not in result

    @patch("tools.onchain.evidence")
    @patch("tools.onchain.requests.get")
    def test_all_metrics_data_populated(self, mock_get, mock_evidence):
        """所有指標資料都有填充。"""
        mock_get.side_effect = _side_effect_all_endpoints

        result = fetch_btc_onchain(None, 7)
        raw = result["raw"]

        assert "tx_count" in raw
        assert "mempool_size" in raw
        assert "fees" in raw
        assert "hashrate" in raw
        assert "difficulty_adjustment" in raw

    @patch("tools.onchain.evidence")
    @patch("tools.onchain.requests.get")
    def test_tx_count_metric_values(self, mock_get, mock_evidence):
        """tx_count 指標數值正確。"""
        mock_get.side_effect = _side_effect_all_endpoints

        result = fetch_btc_onchain(["tx_count"], 7)
        raw = result["raw"]

        assert "tx_count" in raw
        assert len(raw["tx_count"]["recent_blocks"]) == 10
        assert raw["tx_count"]["total_tx_in_recent_blocks"] > 0
        assert raw["tx_count"]["avg_tx_per_block"] > 0

    @patch("tools.onchain.evidence")
    @patch("tools.onchain.requests.get")
    def test_fees_metric_values(self, mock_get, mock_evidence):
        """fees 指標數值正確。"""
        mock_get.side_effect = _side_effect_all_endpoints

        result = fetch_btc_onchain(["fees"], 7)
        raw = result["raw"]

        assert raw["fees"]["fastest_fee"] == 25
        assert raw["fees"]["half_hour_fee"] == 20
        assert raw["fees"]["hour_fee"] == 15
        assert raw["fees"]["economy_fee"] == 8

    @patch("tools.onchain.evidence")
    @patch("tools.onchain.requests.get")
    def test_mempool_size_values(self, mock_get, mock_evidence):
        """mempool_size 指標數值正確。"""
        mock_get.side_effect = _side_effect_all_endpoints

        result = fetch_btc_onchain(["mempool_size"], 7)
        raw = result["raw"]

        assert raw["mempool_size"]["count"] == 45000
        assert raw["mempool_size"]["vsize"] == 150000000

    @patch("tools.onchain.evidence")
    @patch("tools.onchain.requests.get")
    def test_single_metric_only_fetches_that_endpoint(self, mock_get, mock_evidence):
        """只請求單一指標時，只呼叫對應的 endpoint。"""
        mock_get.side_effect = _side_effect_all_endpoints

        result = fetch_btc_onchain(["fees"], 7)

        # 只呼叫了 fees endpoint
        assert mock_get.call_count == 1
        assert "fees" in mock_get.call_args_list[0][0][0]

    @patch("tools.onchain.evidence")
    @patch("tools.onchain.requests.get")
    def test_string_metric_handled(self, mock_get, mock_evidence):
        """傳入字串（非列表）的 metrics 也能正確處理。"""
        mock_get.side_effect = _side_effect_all_endpoints

        result = fetch_btc_onchain("fees", 7)

        assert "error" not in result
        assert "fees" in result["raw"]

    @patch("tools.onchain.evidence")
    @patch("tools.onchain.requests.get")
    def test_content_reference_has_required_fields(self, mock_get, mock_evidence):
        """content_reference 包含必要欄位。"""
        mock_get.side_effect = _side_effect_all_endpoints

        result = fetch_btc_onchain(["fees"], 7)
        cr = result["content_reference"]

        assert "endpoints_called" in cr
        assert "metrics_retrieved" in cr
        assert "data_time_range" in cr
        assert "fetched_at" in cr
        assert len(cr["endpoints_called"]) > 0

    @patch("tools.onchain.evidence")
    @patch("tools.onchain.requests.get")
    def test_evidence_logged_on_success(self, mock_get, mock_evidence):
        """成功時 evidence.log_execution_step 被呼叫。"""
        mock_get.side_effect = _side_effect_all_endpoints

        fetch_btc_onchain(["fees"], 7)

        mock_evidence.log_execution_step.assert_called_once()
        call_kwargs = mock_evidence.log_execution_step.call_args[1]
        assert call_kwargs["tool_name"] == "fetch_btc_onchain"
        assert call_kwargs["status"] == "success"

    @patch("tools.onchain.evidence")
    @patch("tools.onchain.requests.get")
    def test_hashrate_lookback_period_mapping(self, mock_get, mock_evidence):
        """lookback_days 正確映射到 hashrate 時間區間。"""
        mock_get.side_effect = _side_effect_all_endpoints

        # 7 天 → 1m
        fetch_btc_onchain(["hashrate"], 7)
        url_called = mock_get.call_args_list[0][0][0]
        assert "/1m" in url_called

        mock_get.reset_mock()
        # 60 天 → 3m
        fetch_btc_onchain(["hashrate"], 60)
        url_called = mock_get.call_args_list[0][0][0]
        assert "/3m" in url_called

    @patch("tools.onchain.evidence")
    @patch("tools.onchain.requests.get")
    def test_unsupported_metrics_defaults_to_all(self, mock_get, mock_evidence):
        """傳入不支援的指標名稱時，改為取得所有支援的指標。"""
        mock_get.side_effect = _side_effect_all_endpoints

        result = fetch_btc_onchain(["active_addresses", "unknown_metric"], 7)

        # 不支援的指標 → fallback 取所有
        assert "error" not in result
        assert len(result["raw"]) == 5  # 所有 5 個指標


class TestFetchBtcOnchainFailure:
    """失敗情境測試。"""

    @patch("tools.onchain.evidence")
    @patch("tools.onchain.requests.get")
    def test_network_error_returns_error_dict(self, mock_get, mock_evidence):
        """網路異常時回傳 error dict，不拋出例外。"""
        import requests as req
        mock_get.side_effect = req.ConnectionError("Connection refused")

        result = fetch_btc_onchain(["fees"], 7)

        assert "error" in result
        assert "source" in result
        assert "content_reference" in result
        assert result["content_reference"] == {}
        assert "ConnectionError" in result["error"]

    @patch("tools.onchain.evidence")
    @patch("tools.onchain.requests.get")
    def test_http_error_returns_error_dict(self, mock_get, mock_evidence):
        """HTTP 錯誤碼時回傳 error dict。"""
        import requests as req
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = req.HTTPError("500 Server Error")
        mock_get.return_value = mock_resp

        result = fetch_btc_onchain(["tx_count"], 7)

        assert "error" in result
        assert "HTTPError" in result["error"]

    @patch("tools.onchain.evidence")
    @patch("tools.onchain.requests.get")
    def test_evidence_logged_on_error(self, mock_get, mock_evidence):
        """失敗時 evidence.log_execution_step 記錄錯誤。"""
        import requests as req
        mock_get.side_effect = req.Timeout("Request timed out")

        fetch_btc_onchain(["fees"], 7)

        mock_evidence.log_execution_step.assert_called_once()
        call_kwargs = mock_evidence.log_execution_step.call_args[1]
        assert call_kwargs["tool_name"] == "fetch_btc_onchain"
        assert call_kwargs["status"] == "error"

    @patch("tools.onchain.evidence")
    @patch("tools.onchain.requests.get")
    def test_json_decode_error_returns_error_dict(self, mock_get, mock_evidence):
        """JSON 解析失敗時回傳 error dict。"""
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.side_effect = ValueError("No JSON")
        mock_get.return_value = mock_resp

        result = fetch_btc_onchain(["fees"], 7)

        assert "error" in result
        assert "ValueError" in result["error"]
