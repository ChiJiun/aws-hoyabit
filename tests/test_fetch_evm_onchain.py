"""
test_fetch_evm_onchain.py — fetch_evm_onchain 單元測試

使用 unittest.mock 模擬 Etherscan/Blockscout API 回應，驗證：
1. ETH (Etherscan V2) 成功時回傳正確格式
2. BNB (Blockscout) 成功時回傳正確格式
3. 缺少 API key 時回傳 error dict
4. 異常時回傳 error dict 不拋錯
5. 兩鏈共用解析邏輯
6. evidence.log_execution_step 被正確呼叫
"""

import sys
import os
from unittest.mock import patch, MagicMock

import pytest

# 將 lambda 目錄加入 path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambda"))

from tools.onchain import fetch_evm_onchain


# --- Mock 資料 ---

MOCK_BLOCK_NUMBER_RESPONSE = {"result": "0x13B6E7"}  # 1291495 in decimal
MOCK_TX_COUNT_RESPONSE = {"result": "0xC8"}  # 200 in decimal
MOCK_GAS_PRICE_RESPONSE = {"result": "0x3B9ACA00"}  # 1 Gwei in wei
MOCK_ETH_SUPPLY_RESPONSE = {"result": "120000000000000000000000000"}  # 120M ETH
MOCK_BNB_SUPPLY_RESPONSE = {"result": "150000000000000000000000000"}  # 150M BNB


def _make_mock_response(json_data, status_code=200):
    """建立模擬的 requests.Response 物件。"""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = json_data
    mock_resp.raise_for_status.return_value = None
    return mock_resp


def _side_effect_etherscan(url, **kwargs):
    """根據查詢參數回傳對應的模擬回應（ETH Etherscan）。"""
    params = kwargs.get("params", {})
    action = params.get("action", "")

    if action == "eth_blockNumber":
        return _make_mock_response(MOCK_BLOCK_NUMBER_RESPONSE)
    elif action == "eth_getBlockTransactionCountByNumber":
        return _make_mock_response(MOCK_TX_COUNT_RESPONSE)
    elif action == "eth_gasPrice":
        return _make_mock_response(MOCK_GAS_PRICE_RESPONSE)
    elif action == "ethsupply":
        return _make_mock_response(MOCK_ETH_SUPPLY_RESPONSE)
    elif action == "bnbsupply":
        return _make_mock_response(MOCK_BNB_SUPPLY_RESPONSE)

    # Default: return block number for any unknown action
    return _make_mock_response(MOCK_BLOCK_NUMBER_RESPONSE)


class TestFetchEvmOnchainEthSuccess:
    """ETH (Etherscan V2) 成功情境測試。"""

    @patch("tools.onchain.evidence")
    @patch("tools.onchain.requests.get")
    @patch("config.ETHERSCAN_API_KEY", "test-api-key-123")
    def test_all_metrics_returns_unified_format(self, mock_get, mock_evidence):
        """傳入 None metrics 時取得所有指標，回傳格式正確。"""
        mock_get.side_effect = _side_effect_etherscan

        result = fetch_evm_onchain("ethereum", None, 7)

        assert "raw" in result
        assert "source" in result
        assert "content_reference" in result
        assert "summary" in result
        assert "error" not in result

    @patch("tools.onchain.evidence")
    @patch("tools.onchain.requests.get")
    @patch("config.ETHERSCAN_API_KEY", "test-api-key-123")
    def test_all_metrics_data_populated(self, mock_get, mock_evidence):
        """所有指標資料都有填充。"""
        mock_get.side_effect = _side_effect_etherscan

        result = fetch_evm_onchain("ethereum", None, 7)
        raw = result["raw"]

        assert "tx_count" in raw
        assert "gas_price" in raw
        assert "supply" in raw
        assert "block_count" in raw

    @patch("tools.onchain.evidence")
    @patch("tools.onchain.requests.get")
    @patch("config.ETHERSCAN_API_KEY", "test-api-key-123")
    def test_tx_count_metric_values(self, mock_get, mock_evidence):
        """tx_count 指標數值正確。"""
        mock_get.side_effect = _side_effect_etherscan

        result = fetch_evm_onchain("ethereum", ["tx_count"], 7)
        raw = result["raw"]

        assert "tx_count" in raw
        assert len(raw["tx_count"]["recent_blocks"]) == 5
        assert raw["tx_count"]["total_tx_in_recent_blocks"] == 1000  # 200 * 5
        assert raw["tx_count"]["avg_tx_per_block"] == 200.0

    @patch("tools.onchain.evidence")
    @patch("tools.onchain.requests.get")
    @patch("config.ETHERSCAN_API_KEY", "test-api-key-123")
    def test_gas_price_values(self, mock_get, mock_evidence):
        """gas_price 指標數值正確。"""
        mock_get.side_effect = _side_effect_etherscan

        result = fetch_evm_onchain("ethereum", ["gas_price"], 7)
        raw = result["raw"]

        assert raw["gas_price"]["gas_price_wei"] == 1000000000  # 1 Gwei
        assert raw["gas_price"]["gas_price_gwei"] == 1.0

    @patch("tools.onchain.evidence")
    @patch("tools.onchain.requests.get")
    @patch("config.ETHERSCAN_API_KEY", "test-api-key-123")
    def test_supply_values(self, mock_get, mock_evidence):
        """supply 指標數值正確。"""
        mock_get.side_effect = _side_effect_etherscan

        result = fetch_evm_onchain("ethereum", ["supply"], 7)
        raw = result["raw"]

        assert raw["supply"]["total_supply"] == 120000000.0
        assert raw["supply"]["unit"] == "ETH"

    @patch("tools.onchain.evidence")
    @patch("tools.onchain.requests.get")
    @patch("config.ETHERSCAN_API_KEY", "test-api-key-123")
    def test_eth_supply_alias_normalized(self, mock_get, mock_evidence):
        """eth_supply 別名正確正規化為 supply。"""
        mock_get.side_effect = _side_effect_etherscan

        result = fetch_evm_onchain("ethereum", ["eth_supply"], 7)
        raw = result["raw"]

        assert "supply" in raw

    @patch("tools.onchain.evidence")
    @patch("tools.onchain.requests.get")
    @patch("config.ETHERSCAN_API_KEY", "test-api-key-123")
    def test_content_reference_has_required_fields(self, mock_get, mock_evidence):
        """content_reference 包含必要欄位。"""
        mock_get.side_effect = _side_effect_etherscan

        result = fetch_evm_onchain("ethereum", ["gas_price"], 7)
        cr = result["content_reference"]

        assert "endpoints_called" in cr
        assert "query_params" in cr
        assert "metrics_retrieved" in cr
        assert "data_time_range" in cr
        assert "chain" in cr
        assert "fetched_at" in cr
        assert cr["chain"] == "ethereum"
        assert len(cr["endpoints_called"]) > 0

    @patch("tools.onchain.evidence")
    @patch("tools.onchain.requests.get")
    @patch("config.ETHERSCAN_API_KEY", "test-api-key-123")
    def test_evidence_logged_on_success(self, mock_get, mock_evidence):
        """成功時 evidence.log_execution_step 被呼叫。"""
        mock_get.side_effect = _side_effect_etherscan

        fetch_evm_onchain("ethereum", ["gas_price"], 7)

        mock_evidence.log_execution_step.assert_called_once()
        call_kwargs = mock_evidence.log_execution_step.call_args[1]
        assert call_kwargs["tool_name"] == "fetch_evm_onchain"
        assert call_kwargs["status"] == "success"

    @patch("tools.onchain.evidence")
    @patch("tools.onchain.requests.get")
    @patch("config.ETHERSCAN_API_KEY", "test-api-key-123")
    def test_string_metric_handled(self, mock_get, mock_evidence):
        """傳入字串（非列表）的 metrics 也能正確處理。"""
        mock_get.side_effect = _side_effect_etherscan

        result = fetch_evm_onchain("ethereum", "gas_price", 7)

        assert "error" not in result
        assert "gas_price" in result["raw"]

    @patch("tools.onchain.evidence")
    @patch("tools.onchain.requests.get")
    @patch("config.ETHERSCAN_API_KEY", "test-api-key-123")
    def test_source_contains_etherscan(self, mock_get, mock_evidence):
        """source 欄位包含 Etherscan 資訊。"""
        mock_get.side_effect = _side_effect_etherscan

        result = fetch_evm_onchain("ethereum", ["gas_price"], 7)

        assert "Etherscan" in result["source"]


class TestFetchEvmOnchainBnbSuccess:
    """BNB (Blockscout/BscScan) 成功情境測試。"""

    @patch("tools.onchain.evidence")
    @patch("tools.onchain.requests.get")
    def test_bnb_returns_unified_format(self, mock_get, mock_evidence):
        """BNB 不需要 API key 即可取得資料。"""
        mock_get.side_effect = _side_effect_etherscan

        result = fetch_evm_onchain("bsc", None, 7)

        assert "raw" in result
        assert "source" in result
        assert "content_reference" in result
        assert "summary" in result
        assert "error" not in result

    @patch("tools.onchain.evidence")
    @patch("tools.onchain.requests.get")
    def test_bnb_supply_uses_bnbsupply_action(self, mock_get, mock_evidence):
        """BNB chain 使用 bnbsupply action。"""
        mock_get.side_effect = _side_effect_etherscan

        result = fetch_evm_onchain("bsc", ["supply"], 7)
        raw = result["raw"]

        assert raw["supply"]["unit"] == "BNB"

    @patch("tools.onchain.evidence")
    @patch("tools.onchain.requests.get")
    def test_bnb_supply_alias_normalized(self, mock_get, mock_evidence):
        """bnb_supply 別名正確正規化為 supply。"""
        mock_get.side_effect = _side_effect_etherscan

        result = fetch_evm_onchain("bsc", ["bnb_supply"], 7)
        raw = result["raw"]

        assert "supply" in raw

    @patch("tools.onchain.evidence")
    @patch("tools.onchain.requests.get")
    def test_bnb_no_apikey_in_params(self, mock_get, mock_evidence):
        """BNB chain 不在 API 請求中附帶 apikey 參數。"""
        mock_get.side_effect = _side_effect_etherscan

        fetch_evm_onchain("bsc", ["gas_price"], 7)

        # 檢查呼叫參數中不含 apikey
        for call in mock_get.call_args_list:
            params = call[1].get("params", {})
            assert "apikey" not in params

    @patch("tools.onchain.evidence")
    @patch("tools.onchain.requests.get")
    def test_bnb_block_count_values(self, mock_get, mock_evidence):
        """BNB 區塊時間為 3 秒，每日約 28800 區塊。"""
        mock_get.side_effect = _side_effect_etherscan

        result = fetch_evm_onchain("bsc", ["block_count"], 7)
        raw = result["raw"]

        assert raw["block_count"]["estimated_daily_blocks"] == 28800
        assert raw["block_count"]["avg_block_time_seconds"] == 3

    @patch("tools.onchain.evidence")
    @patch("tools.onchain.requests.get")
    def test_bnb_content_reference_chain(self, mock_get, mock_evidence):
        """content_reference 的 chain 欄位為 bsc。"""
        mock_get.side_effect = _side_effect_etherscan

        result = fetch_evm_onchain("bsc", ["gas_price"], 7)

        assert result["content_reference"]["chain"] == "bsc"


class TestFetchEvmOnchainFailure:
    """失敗情境測試。"""

    @patch("tools.onchain.evidence")
    @patch("config.ETHERSCAN_API_KEY", None)
    def test_missing_api_key_returns_error_dict(self, mock_evidence):
        """ETH 缺少 API key 時回傳 error dict。"""
        result = fetch_evm_onchain("ethereum", ["gas_price"], 7)

        assert "error" in result
        assert "ETHERSCAN_API_KEY" in result["error"]
        assert "source" in result
        assert "content_reference" in result
        assert result["content_reference"] == {}

    @patch("tools.onchain.evidence")
    @patch("config.ETHERSCAN_API_KEY", "")
    def test_empty_api_key_returns_error_dict(self, mock_evidence):
        """ETH API key 為空字串時回傳 error dict。"""
        result = fetch_evm_onchain("ethereum", ["gas_price"], 7)

        assert "error" in result
        assert "ETHERSCAN_API_KEY" in result["error"]

    @patch("tools.onchain.evidence")
    @patch("tools.onchain.requests.get")
    @patch("config.ETHERSCAN_API_KEY", "test-api-key-123")
    def test_network_error_returns_error_dict(self, mock_get, mock_evidence):
        """網路異常時回傳 error dict，不拋出例外。"""
        import requests as req
        mock_get.side_effect = req.ConnectionError("Connection refused")

        result = fetch_evm_onchain("ethereum", ["gas_price"], 7)

        assert "error" in result
        assert "source" in result
        assert "content_reference" in result
        assert result["content_reference"] == {}
        assert "ConnectionError" in result["error"]

    @patch("tools.onchain.evidence")
    @patch("tools.onchain.requests.get")
    @patch("config.ETHERSCAN_API_KEY", "test-api-key-123")
    def test_timeout_error_returns_error_dict(self, mock_get, mock_evidence):
        """逾時時回傳 error dict。"""
        import requests as req
        mock_get.side_effect = req.Timeout("Request timed out")

        result = fetch_evm_onchain("ethereum", ["gas_price"], 7)

        assert "error" in result
        assert "Timeout" in result["error"]

    @patch("tools.onchain.evidence")
    @patch("tools.onchain.requests.get")
    @patch("config.ETHERSCAN_API_KEY", "test-api-key-123")
    def test_http_error_returns_error_dict(self, mock_get, mock_evidence):
        """HTTP 錯誤碼時回傳 error dict。"""
        import requests as req
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = req.HTTPError("500 Server Error")
        mock_get.return_value = mock_resp

        result = fetch_evm_onchain("ethereum", ["tx_count"], 7)

        assert "error" in result
        assert "HTTPError" in result["error"]

    @patch("tools.onchain.evidence")
    @patch("tools.onchain.requests.get")
    @patch("config.ETHERSCAN_API_KEY", "test-api-key-123")
    def test_evidence_logged_on_error(self, mock_get, mock_evidence):
        """失敗時 evidence.log_execution_step 記錄錯誤。"""
        import requests as req
        mock_get.side_effect = req.Timeout("Request timed out")

        fetch_evm_onchain("ethereum", ["gas_price"], 7)

        mock_evidence.log_execution_step.assert_called_once()
        call_kwargs = mock_evidence.log_execution_step.call_args[1]
        assert call_kwargs["tool_name"] == "fetch_evm_onchain"
        assert call_kwargs["status"] == "error"

    @patch("tools.onchain.evidence")
    def test_unsupported_chain_returns_error(self, mock_evidence):
        """不支援的 chain 參數回傳 error dict。"""
        result = fetch_evm_onchain("polygon", ["gas_price"], 7)

        assert "error" in result
        assert "Unsupported chain" in result["error"]

    @patch("tools.onchain.evidence")
    @patch("tools.onchain.requests.get")
    def test_bnb_network_error_returns_error_dict(self, mock_get, mock_evidence):
        """BNB 網路錯誤也回傳 error dict。"""
        import requests as req
        mock_get.side_effect = req.ConnectionError("Connection refused")

        result = fetch_evm_onchain("bsc", ["gas_price"], 7)

        assert "error" in result
        assert "ConnectionError" in result["error"]

    @patch("tools.onchain.evidence")
    @patch("tools.onchain.requests.get")
    @patch("config.ETHERSCAN_API_KEY", "test-api-key-123")
    def test_unsupported_metrics_defaults_to_all(self, mock_get, mock_evidence):
        """傳入不支援的指標名稱時，改為取得所有支援的指標。"""
        mock_get.side_effect = _side_effect_etherscan

        result = fetch_evm_onchain("ethereum", ["unknown_metric"], 7)

        assert "error" not in result
        assert len(result["raw"]) == 4  # 所有 4 個指標
