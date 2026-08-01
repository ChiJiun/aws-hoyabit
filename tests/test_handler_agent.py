"""
test_handler_agent.py — handler.py 與 agent.py 的單元測試

使用 mock Bedrock 驗證：
  - Property 1: 有效請求必定被接受
  - Property 2: 無效幣種必定被拒絕
  - Property 3: Agent Loop 必定終止
  - Property 5: 工具分派正確性
  - Property 6: Context 膨脹防護（toolResult 不含 raw）

驗證: 需求 1.2、1.3、1.4、1.5、2.1、2.3、3.2、3.6
"""

import os
import sys
import json
import time
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambda"))

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

import config
import handler
import agent
import evidence


# ═══════════════════════════════════════════════════════════════════════════════
# Property 1: 有效請求必定被接受
# Validates: Requirements 1.2, 1.3
# ═══════════════════════════════════════════════════════════════════════════════

@given(
    symbols=st.lists(
        st.sampled_from(config.SUPPORTED_SYMBOLS), min_size=1, max_size=2
    ),
    question=st.text(min_size=1, max_size=200).filter(lambda s: s.strip()),
)
@settings(max_examples=100)
def test_property_1_valid_request_accepted(symbols, question):
    """Property 1: 任何由 1-2 個支援幣種 + 非空 question 組成的請求必定被接受。"""
    event = {"body": json.dumps({"symbols": symbols, "question": question})}
    result_symbols, result_question = handler.parse_request(event)

    assert len(result_symbols) == len(symbols)
    assert all(s in config.SUPPORTED_SYMBOLS for s in result_symbols)
    assert result_question == question.strip()


# ═══════════════════════════════════════════════════════════════════════════════
# Property 2: 無效幣種必定被拒絕
# Validates: Requirements 1.4
# ═══════════════════════════════════════════════════════════════════════════════

@given(
    bad_symbol=st.text(min_size=1, max_size=10).filter(
        lambda s: s.upper() not in config.SUPPORTED_SYMBOLS
    ),
    question=st.text(min_size=1, max_size=100).filter(lambda s: s.strip()),
)
@settings(max_examples=100)
def test_property_2_invalid_symbol_rejected(bad_symbol, question):
    """Property 2: 不在 SUPPORTED_SYMBOLS 中的代號必定被拒絕。"""
    event = {"body": json.dumps({"symbols": [bad_symbol], "question": question})}

    with pytest.raises(ValueError) as exc_info:
        handler.parse_request(event)

    assert "不支援" in str(exc_info.value)


def test_property_2_empty_question_rejected():
    """Property 2 補充: 空 question 被拒絕。"""
    event = {"body": json.dumps({"symbols": ["BTC"], "question": ""})}

    with pytest.raises(ValueError) as exc_info:
        handler.parse_request(event)

    assert "題目" in str(exc_info.value) or "question" in str(exc_info.value).lower()


def test_property_2_too_many_symbols_rejected():
    """Property 2 補充: 超過 2 個幣種被拒絕。"""
    event = {"body": json.dumps({"symbols": ["BTC", "ETH", "SOL"], "question": "test"})}

    with pytest.raises(ValueError) as exc_info:
        handler.parse_request(event)

    assert "2" in str(exc_info.value)


# ═══════════════════════════════════════════════════════════════════════════════
# Property 3: Agent Loop 必定終止
# Validates: Requirements 2.1, 2.3
# ═══════════════════════════════════════════════════════════════════════════════

@patch("agent.call_bedrock")
def test_property_3_loop_terminates_on_end_turn(mock_bedrock):
    """Property 3: stopReason 為 end_turn 時迴圈正確退出。"""
    evidence.reset_stores()

    # 模擬 Bedrock 回傳 end_turn
    mock_bedrock.return_value = {
        "stopReason": "end_turn",
        "output": {
            "message": {
                "role": "assistant",
                "content": [{"text": "分析完成。"}]
            }
        }
    }

    messages = agent.run_agent_loop("run_test_001", ["BTC"], "測試問題")

    # 迴圈應該在第一輪就結束
    assert mock_bedrock.call_count == 1
    # messages 應包含初始 user 訊息 + assistant 回應
    assert len(messages) >= 2


@patch("agent.call_bedrock")
def test_property_3_loop_terminates_at_max_turns(mock_bedrock):
    """Property 3: 達到 MAX_AGENT_TURNS 時強制退出，不無限迴圈。"""
    evidence.reset_stores()

    # 模擬 Bedrock 每次都回傳 tool_use（永遠不停）
    mock_bedrock.return_value = {
        "stopReason": "tool_use",
        "output": {
            "message": {
                "role": "assistant",
                "content": [{
                    "toolUse": {
                        "toolUseId": "test-id-123",
                        "name": "get_sentiment",
                        "input": {"related_claim": "測試用的 claim 文字"}
                    }
                }]
            }
        }
    }

    # 用小的 MAX_AGENT_TURNS 避免測試耗時
    original_max = config.MAX_AGENT_TURNS
    config.MAX_AGENT_TURNS = 3

    try:
        with patch("agent.dispatch_tool_call") as mock_dispatch:
            mock_dispatch.return_value = {
                "toolResultId": "test-id-123",
                "content": [{"text": json.dumps({"summary": "test", "evidence_id": "ev_123"})}],
                "status": "success",
            }
            messages = agent.run_agent_loop("run_test_002", ["BTC"], "測試問題")
    finally:
        config.MAX_AGENT_TURNS = original_max

    # 應該剛好呼叫 MAX_AGENT_TURNS 次
    assert mock_bedrock.call_count == 3


@patch("agent.call_bedrock")
def test_property_3_loop_terminates_on_time_budget(mock_bedrock):
    """Property 3: 時間預算超出時強制退出。"""
    evidence.reset_stores()

    # 模擬 Bedrock 每次回傳 tool_use，但時間流逝很快
    call_count = [0]

    def slow_bedrock(*args, **kwargs):
        call_count[0] += 1
        # 模擬耗時
        time.sleep(0.1)
        return {
            "stopReason": "tool_use",
            "output": {
                "message": {
                    "role": "assistant",
                    "content": [{
                        "toolUse": {
                            "toolUseId": f"test-id-{call_count[0]}",
                            "name": "get_sentiment",
                            "input": {"related_claim": "時間預算測試用的 claim"}
                        }
                    }]
                }
            }
        }

    mock_bedrock.side_effect = slow_bedrock

    # 設極短的時間預算
    original_budget = config.TIME_BUDGET_SECONDS
    config.TIME_BUDGET_SECONDS = 0.2  # 200ms

    try:
        with patch("agent.dispatch_tool_call") as mock_dispatch:
            mock_dispatch.return_value = {
                "toolResultId": "test-id-1",
                "content": [{"text": json.dumps({"summary": "test", "evidence_id": "ev_1"})}],
                "status": "success",
            }
            messages = agent.run_agent_loop("run_test_003", ["BTC"], "測試問題")
    finally:
        config.TIME_BUDGET_SECONDS = original_budget

    # 應該在很少的輪次內結束（不是跑滿 MAX_AGENT_TURNS）
    assert call_count[0] < config.MAX_AGENT_TURNS


# ═══════════════════════════════════════════════════════════════════════════════
# Property 5: 工具分派正確性
# Validates: Requirements 3.2
# ═══════════════════════════════════════════════════════════════════════════════

def test_property_5_known_tool_dispatches_correctly():
    """Property 5: TOOL_DISPATCH 中已知的工具名能正確分派。"""
    evidence.reset_stores()

    # 驗證所有已註冊的工具都在 TOOL_DISPATCH 中
    expected_tools = [
        "get_price_ohlcv", "search_news", "get_onchain",
        "compute_quant", "get_sentiment", "get_macro"
    ]
    for tool_name in expected_tools:
        assert tool_name in agent.TOOL_DISPATCH, f"{tool_name} not in TOOL_DISPATCH"
        assert callable(agent.TOOL_DISPATCH[tool_name])


def test_property_5_unknown_tool_returns_error():
    """Property 5: 未知的工具名回傳 error，不 crash。"""
    evidence.reset_stores()

    tool_use_block = {
        "toolUseId": "test-unknown-001",
        "name": "nonexistent_tool",
        "input": {"related_claim": "測試未知工具"}
    }

    result = agent.dispatch_tool_call("run_test_004", tool_use_block)

    assert result["status"] == "error"
    assert "Unknown tool" in result["content"][0]["text"] or "error" in result["content"][0]["text"]


@patch("agent.TOOL_DISPATCH", {"get_sentiment": MagicMock(return_value={
    "raw": {"data": [1, 2, 3]},
    "source": "https://api.alternative.me/fng/",
    "content_reference": {"value": 65, "classification": "Greed"},
    "summary": "Fear & Greed Index 目前為 65 (Greed)"
})})
def test_property_5_dispatch_calls_correct_function():
    """Property 5: dispatch_tool_call 呼叫 TOOL_DISPATCH 中對應的函式。"""
    evidence.reset_stores()

    tool_use_block = {
        "toolUseId": "test-dispatch-001",
        "name": "get_sentiment",
        "input": {"related_claim": "需要了解目前市場情緒狀態以判斷風險偏好"}
    }

    result = agent.dispatch_tool_call("run_test_005", tool_use_block)

    assert result["status"] == "success"
    # 確認工具函式被呼叫
    agent.TOOL_DISPATCH["get_sentiment"].assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════════
# Property 6: Context 膨脹防護
# Validates: Requirements 3.6
# ═══════════════════════════════════════════════════════════════════════════════

@patch("agent.TOOL_DISPATCH", {"get_sentiment": MagicMock(return_value={
    "raw": {"very_large_data": "x" * 10000, "nested": {"deep": [1] * 1000}},
    "source": "https://api.alternative.me/fng/",
    "content_reference": {"value": 50, "classification": "Neutral"},
    "summary": "Fear & Greed Index 為 50 (Neutral)"
})})
def test_property_6_tool_result_excludes_raw():
    """Property 6: toolResult 回傳給模型的內容不含 raw 原始資料。"""
    evidence.reset_stores()

    tool_use_block = {
        "toolUseId": "test-raw-001",
        "name": "get_sentiment",
        "input": {"related_claim": "需要市場情緒數據來判斷投資人恐慌程度"}
    }

    result = agent.dispatch_tool_call("run_test_006", tool_use_block)

    assert result["status"] == "success"

    # 解析 toolResult 的內容
    content_text = result["content"][0]["text"]
    content_json = json.loads(content_text)

    # 必須包含 summary 和 evidence_id
    assert "summary" in content_json
    assert "evidence_id" in content_json

    # 不可包含 raw
    assert "raw" not in content_json
    assert "very_large_data" not in content_text
    # 原始 10000 字元的資料不應出現在 toolResult 中
    assert len(content_text) < 500


def test_property_6_build_tool_config_has_related_claim_required():
    """Property 6 補充: build_tool_config 中每個工具的 related_claim 都是 required。"""
    tool_config = agent.build_tool_config()

    for tool in tool_config["tools"]:
        spec = tool["toolSpec"]
        schema = spec["inputSchema"]["json"]
        required_fields = schema.get("required", [])
        assert "related_claim" in required_fields, (
            f"Tool '{spec['name']}' 的 inputSchema 未將 related_claim 列為 required"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 補充: handler CORS 與錯誤回應格式
# ═══════════════════════════════════════════════════════════════════════════════

@patch("agent.run_agent_loop")
@patch("agent.summarize_final_analysis")
def test_handler_returns_cors_on_success(mock_summarize, mock_loop):
    """handler 成功回應必含 CORS 標頭。"""
    evidence.reset_stores()
    mock_loop.return_value = [{"role": "user", "content": [{"text": "test"}]}]
    mock_summarize.return_value = "## 市場判斷\n分析內容\n## 關鍵依據\n依據\n## 信心說明\n說明"

    event = {"body": json.dumps({"symbols": ["BTC"], "question": "測試問題文字"})}
    response = handler.lambda_handler(event, None)

    assert "Access-Control-Allow-Origin" in response["headers"]
    assert response["headers"]["Access-Control-Allow-Origin"] == "*"


def test_handler_returns_cors_on_error():
    """handler 錯誤回應也必含 CORS 標頭。"""
    event = {"body": json.dumps({"symbols": ["DOGE"], "question": "test"})}
    response = handler.lambda_handler(event, None)

    assert response["statusCode"] == 400
    assert "Access-Control-Allow-Origin" in response["headers"]
    assert response["headers"]["Access-Control-Allow-Origin"] == "*"


def test_handler_options_preflight():
    """handler 正確處理 OPTIONS preflight 請求。"""
    event = {
        "requestContext": {"http": {"method": "OPTIONS"}},
        "body": "",
    }
    response = handler.lambda_handler(event, None)

    assert response["statusCode"] == 200
    assert "Access-Control-Allow-Origin" in response["headers"]
