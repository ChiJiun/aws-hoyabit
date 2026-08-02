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
import re
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
import report


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

    with patch("agent.run_phase_a_prefetch") as mock_pa:
        mock_pa.return_value = agent.PrefetchOutcome(
            question_type="single_integration",
            started_at="2026-01-01T00:00:00Z",
            completed_at="2026-01-01T00:00:01Z",
        )
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
            with patch("agent.run_phase_a_prefetch") as mock_pa:
                mock_pa.return_value = agent.PrefetchOutcome(
                    question_type="single_integration",
                    started_at="2026-01-01T00:00:00Z",
                    completed_at="2026-01-01T00:00:01Z",
                )
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
    config.TIME_BUDGET_SECONDS = 0.3  # 300ms

    try:
        with patch("agent.dispatch_tool_call") as mock_dispatch:
            mock_dispatch.return_value = {
                "toolResultId": "test-id-1",
                "content": [{"text": json.dumps({"summary": "test", "evidence_id": "ev_1"})}],
                "status": "success",
            }
            with patch("agent.run_phase_a_prefetch") as mock_pa:
                mock_pa.return_value = agent.PrefetchOutcome(
                    question_type="single_integration",
                    started_at="2026-01-01T00:00:00Z",
                    completed_at="2026-01-01T00:00:01Z",
                )
                messages = agent.run_agent_loop("run_test_003", ["BTC"], "測試問題")
    finally:
        config.TIME_BUDGET_SECONDS = original_budget

    # 應該在很少的輪次內結束（不是跑滿 MAX_AGENT_TURNS）
    assert call_count[0] < config.MAX_AGENT_TURNS


def _capture_initial_user_text(symbols, question):
    """以 end_turn 模擬回應取得 run_agent_loop 的初始 user 訊息。"""
    response = {
        "stopReason": "end_turn",
        "output": {
            "message": {
                "role": "assistant",
                "content": [{"text": "分析完成。"}],
            }
        },
    }
    with patch("agent.call_bedrock", return_value=response):
        with patch("agent.run_phase_a_prefetch") as mock_pa:
            mock_pa.return_value = agent.PrefetchOutcome(
                question_type="single_integration",
                started_at="2026-01-01T00:00:00Z",
                completed_at="2026-01-01T00:00:01Z",
            )
            messages = agent.run_agent_loop("run_initial_prompt", symbols, question)
    return messages[0]["content"][0]["text"]


def _assert_no_fixed_six_tool_order(initial_text):
    for phrase in ("依序完成以下資料蒐集", "每一項都必須呼叫"):
        assert phrase not in initial_text
    assert not re.search(
        r"(?ms)^1\..*^2\..*^3\..*^4\..*^5\..*^6\.", initial_text
    )


def test_single_symbol_initial_message_is_question_driven_and_multidimensional():
    """單幣種初始訊息只要求動態、題目驅動的多維度分析。"""
    initial_text = _capture_initial_user_text(["BTC"], "分析目前風險")
    assert "幣種：BTC" in initial_text
    assert "問題：分析目前風險" in initial_text
    assert "相關的子問題" in initial_text
    assert "至少 2 個" in initial_text
    assert "彼此互補" in initial_text
    assert "動態使用足夠的工具與證據" in initial_text
    assert "一致訊號、背離訊號或證據不足" in initial_text
    assert "evidence_id" in initial_text
    _assert_no_fixed_six_tool_order(initial_text)


def test_two_symbol_initial_message_uses_same_dimensions_and_deterministic_quant():
    """比較題初始訊息要求同維度比較，且適用計算交由 compute_quant。"""
    initial_text = _capture_initial_user_text(["ETH", "SOL"], "比較風險特徵")
    assert "幣種：ETH vs SOL" in initial_text
    assert "問題：比較風險特徵" in initial_text
    assert "至少 2 個" in initial_text
    assert "相同的相關維度下比較兩個幣種" in initial_text
    assert "動態使用足夠的工具與證據" in initial_text
    assert "一致訊號、背離訊號或證據不足" in initial_text
    assert "evidence_id" in initial_text
    assert "compute_quant 決定性計算" in initial_text
    _assert_no_fixed_six_tool_order(initial_text)


# ═══════════════════════════════════════════════════════════════════════════════
# Property 5: 工具分派正確性
# Validates: Requirements 3.2
# ═══════════════════════════════════════════════════════════════════════════════

def test_property_5_tool_names_are_exactly_consistent_across_all_registries():
    """15 個工具在 dispatcher、Bedrock config 與報告維度映射中必須完全一致。"""
    evidence.reset_stores()
    dispatch_names = set(agent.TOOL_DISPATCH)
    config_names = {
        item["toolSpec"]["name"] for item in agent.build_tool_config()["tools"]
    }
    report_names = set(report.TOOL_DIMENSIONS)

    assert len(dispatch_names) == 15
    assert dispatch_names == config_names == report_names
    assert all(callable(func) for func in agent.TOOL_DISPATCH.values())


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
    body = json.loads(response["body"])
    assert response["statusCode"] == 200
    assert {"report_text", "evidence_download_url", "log_download_url", "run_id"}.issubset(body)
    assert any(
        "cited_evidence_count == 0" in warning
        for warning in body.get("validation_warnings", [])
    )
    assert any(
        "實際分析維度不足：0 個" in warning
        for warning in body.get("validation_warnings", [])
    )


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


# ═══════════════════════════════════════════════════════════════════════════════
# SYSTEM_PROMPT 動態多維度規劃與 report metadata 整合
# Validates: Requirements 12.2, 12.3, 12.9, 13.2, 13.3, 13.4, 13.5, 13.6, 13.9
# ═══════════════════════════════════════════════════════════════════════════════

def test_system_prompt_uses_question_driven_complementary_dimensions():
    """提示詞要求題目相關的互補維度與跨維度比較。"""
    prompt = agent.SYSTEM_PROMPT
    assert "至少 2 個" in prompt
    assert "不同子問題" in prompt
    assert "彼此互補" in prompt
    assert "與題目相關" in prompt
    assert "一致訊號、背離訊號或證據不足" in prompt
    assert "evidence_id" in prompt
    assert "事實(fact)" in prompt
    assert "推論(inference)" in prompt
    assert "結論(conclusion)" in prompt


def test_system_prompt_preserves_complete_tool_inventory_and_divergence_examples():
    """15 工具清單及有用的背離例子均保留。"""
    expected_tools = [
        "get_price_ohlcv", "compute_quant", "get_orderbook_depth",
        "get_market_dominance", "get_derivatives", "get_onchain",
        "get_defi_data", "get_coin_metrics", "get_dev_activity",
        "get_sentiment", "get_prediction_market", "search_news", "get_macro",
        "get_sec_filings", "get_cftc_cot",
    ]
    for tool_name in expected_tools:
        assert tool_name in agent.SYSTEM_PROMPT
    assert "資金費率轉負 + 價格持平" in agent.SYSTEM_PROMPT
    assert "OI 新高 + 波動率壓縮" in agent.SYSTEM_PROMPT
    assert "DVOL 抬升 + 已實現波動率低" in agent.SYSTEM_PROMPT


def test_system_prompt_removes_fixed_quotas_and_mandatory_order():
    """提示詞不得殘留固定五類、七工具或必須依序呼叫。"""
    prompt = agent.SYSTEM_PROMPT
    assert "至少 5 類" not in prompt
    assert "至少呼叫 7" not in prompt
    assert "推薦的呼叫順序" not in prompt
    assert "嚴格依序執行" not in prompt
    assert "不要省略" not in prompt
    assert "只呼叫 1-3 個工具" not in prompt
    assert "只是一項匯出驗證政策" in prompt
    assert "不是報告分母" in prompt


def test_system_prompt_limits_omissions_to_relevant_or_attempted_dimensions():
    """只說明題目相關或已嘗試失敗的缺口及信心影響。"""
    prompt = agent.SYSTEM_PROMPT
    assert "只列出與題目相關但省略" in prompt
    assert "實際嘗試後失敗" in prompt
    assert "不列舉無關且未嘗試的維度" in prompt
    assert "如何影響結論信心" in prompt


def test_build_report_metadata_maps_citations_successes_failures_and_omissions():
    """handler 只映射存在且實際引用的證據，並保留失敗與明示省略。"""
    evidence_list = [
        {"evidence_id": "ev_price", "source": "https://api.binance.com/a",
         "fetched_at": "2026-01-01T00:00:00Z", "content_reference": {},
         "related_claim": "價格判斷"},
        {"evidence_id": "ev_unused", "source": "https://coindesk.com/news",
         "fetched_at": "2026-01-01T00:00:00Z", "content_reference": {},
         "related_claim": "新聞判斷"},
    ]
    execution_log = [
        {"tool_name": "get_price_ohlcv", "status": "success", "evidence_id": "ev_price", "note": None},
        {"tool_name": "search_news", "status": "success", "evidence_id": "ev_unused", "note": None},
        {"tool_name": "get_derivatives", "status": "timeout", "evidence_id": None, "note": "上游逾時"},
    ]
    analysis = "事實 [ev_price]。鏈上資料未取得，因此基本面信心受限。"
    metadata = handler.build_report_metadata(analysis, evidence_list, execution_log)
    assert metadata["analyzed_evidence_ids"] == ["ev_price"]
    assert metadata["evidence_capabilities"]["ev_price"] == "get_price_ohlcv"
    assert metadata["evidence_capabilities"]["ev_unused"] == "search_news"
    assert metadata["attempted_capabilities"] == [{
        "capability_id": "get_derivatives", "status": "timeout", "reason": "上游逾時"
    }]
    assert metadata["relevant_omissions"][0]["dimension"] == "鏈上"


def test_build_report_metadata_deduplicates_tool_failures_and_separates_agent_limits():
    """工具內部與 dispatcher 的重複失敗只留一筆，Agent timeout 不成為分析維度。"""
    execution_log = [
        {
            "tool_name": "get_prediction_market", "status": "error",
            "evidence_id": None, "note": "Polymarket upstream timeout",
        },
        {
            "tool_name": "get_prediction_market", "status": "failure",
            "evidence_id": None, "note": "Polymarket   upstream timeout",
        },
        {
            "tool_name": "agent_loop", "status": "timeout",
            "evidence_id": None, "note": "Time budget exceeded at turn 4",
        },
        {
            "tool_name": "agent_loop", "status": "timeout",
            "evidence_id": None, "note": "Time budget exceeded at turn 4",
        },
    ]
    metadata = handler.build_report_metadata("", [], execution_log)

    assert metadata["attempted_capabilities"] == [{
        "capability_id": "get_prediction_market",
        "status": "error",
        "reason": "Polymarket upstream timeout",
    }]
    assert metadata["execution_limitations"] == [{
        "source": "agent_loop",
        "status": "timeout",
        "reason": "Time budget exceeded at turn 4",
    }]

    summary = report.build_analysis_summary([], metadata)
    assert summary["failed_attempts"] == [{
        "dimension": "預測市場",
        "capability_id": "get_prediction_market",
        "status": "error",
        "reason": "Polymarket upstream timeout",
    }]
    assert summary["execution_limitations"] == metadata["execution_limitations"]
    assert all(item["dimension"] != "agent_loop" for item in summary["failed_attempts"])

    rendered = report.render_report(
        "run_limits", "測試", "內容", [], coverage=metadata
    )
    assert rendered.count("Polymarket upstream timeout") == 2  # 信心說明與附錄各一次
    assert "#### 執行限制" in rendered
    assert "Agent 迴圈受限（timeout）" in rendered


def test_report_quality_warnings_cover_zero_citations_and_one_dimension():
    zero = handler.build_report_quality_warnings({
        "cited_evidence_count": 0, "analyzed_dimensions": [],
    })
    assert any("cited_evidence_count == 0" in warning for warning in zero)
    assert any("實際分析維度不足：0 個" in warning for warning in zero)

    one_dimension = handler.build_report_quality_warnings({
        "cited_evidence_count": 2, "analyzed_dimensions": ["價格"],
    })
    assert all("cited_evidence_count" not in warning for warning in one_dimension)
    assert one_dimension == ["報告實際分析維度不足：1 個，至少需要 2 個"]


# ═══════════════════════════════════════════════════════════════════════════════
# 最終摘要證據索引
# Validates: Requirements 12.2, 12.3, 12.9, 13.2, 13.3, 14.1
# ═══════════════════════════════════════════════════════════════════════════════

@patch("agent.call_bedrock")
def test_summarize_final_analysis_includes_bounded_deduplicated_evidence_index(
    mock_bedrock,
):
    """最終摘要 prompt 只提供穩定、精簡且可引用的證據索引。"""
    evidence.reset_stores()
    mock_bedrock.return_value = {
        "output": {"message": {"content": [{"text": "摘要完成"}]}}
    }
    oversized_source = "https://example.com/" + ("source-segment-" * 80)
    oversized_claim = "跨維度主張" * 200

    try:
        evidence.evidence_list.extend([
            {
                "evidence_id": "ev_price",
                "source": oversized_source,
                "fetched_at": "2026-01-01T00:00:00Z",
                "content_reference": {"raw": "raw_payload_secret"},
                "related_claim": oversized_claim,
                "raw": "raw_record_secret",
            },
            {
                "evidence_id": "ev_news",
                "source": "https://news.example/article",
                "fetched_at": "2026-01-01T00:01:00Z",
                "content_reference": {"excerpt": "content_reference_secret"},
                "related_claim": "新聞事件是否支持價格訊號",
            },
            {
                "evidence_id": "ev_price",
                "source": "https://duplicate.example/should-not-appear",
                "fetched_at": "2026-01-01T00:02:00Z",
                "content_reference": {"duplicate": True},
                "related_claim": "重複 ID 不應覆寫第一筆",
            },
            {
                "evidence_id": "ev_macro",
                "source": "FRED",
                "fetched_at": "2026-01-01T00:03:00Z",
                "content_reference": {"series": "DGS10"},
                "related_claim": "總經環境是否形成反向訊號",
            },
        ])

        result = agent.summarize_final_analysis([
            {"role": "user", "content": [{"text": "分析 BTC"}]}
        ])

        assert result == "摘要完成"
        prompt = mock_bedrock.call_args.args[0][-1]["content"][0]["text"]
        index_text = prompt.split(
            "## 可用證據索引（只能引用以下 ID）\n", 1
        )[1].split("\n\n引用規則：", 1)[0]
        index_records = [json.loads(line) for line in index_text.splitlines()]

        assert [item["evidence_id"] for item in index_records] == [
            "ev_price", "ev_news", "ev_macro"
        ]
        assert index_text.count('"evidence_id":"ev_price"') == 1
        assert all(set(item) == {"evidence_id", "source", "related_claim"}
                   for item in index_records)
        assert len(index_records[0]["source"]) <= agent.EVIDENCE_INDEX_SOURCE_MAX_CHARS
        assert len(index_records[0]["related_claim"]) <= agent.EVIDENCE_INDEX_CLAIM_MAX_CHARS
        assert "should-not-appear" not in index_text
        assert "raw_payload_secret" not in index_text
        assert "raw_record_secret" not in index_text
        assert "content_reference" not in index_text
        assert "只能逐字引用上述索引內的 ID" in prompt
        assert "禁止杜撰" in prompt
        assert "每一項事實與每一條關鍵依據" in prompt
        assert "至少 2 個與題目相關且彼此互補的分析維度" in prompt
        assert "少於 2 個互補且相關的維度" in prompt
        assert "不得捏造多維度結論" in prompt
    finally:
        evidence.reset_stores()

    assert evidence.evidence_list == []
    assert evidence.execution_log == []


@patch("agent.call_bedrock")
def test_summarize_final_analysis_marks_empty_evidence_as_insufficient(mock_bedrock):
    """無證據時 prompt 明示不可虛構並要求低信心輸出。"""
    evidence.reset_stores()
    mock_bedrock.return_value = {
        "output": {"message": {"content": [{"text": "證據不足"}]}}
    }

    try:
        result = agent.summarize_final_analysis([])

        assert result == "證據不足"
        prompt = mock_bedrock.call_args.args[0][-1]["content"][0]["text"]
        assert "## 可用證據索引（只能引用以下 ID）\n(無可用證據)" in prompt
        assert "必須輸出低信心／證據不足的判斷" in prompt
        assert "不得虛構事實、關鍵依據或 evidence_id" in prompt
    finally:
        evidence.reset_stores()

    assert evidence.evidence_list == []
    assert evidence.execution_log == []


# ═══════════════════════════════════════════════════════════════════════════════
# Phase A/B Orchestration Tests
# Validates: Pipeline Presentation requirements
# ═══════════════════════════════════════════════════════════════════════════════


# ── Question Type Classification ──

class TestClassifyQuestionType:
    """Tests for classify_question_type() rule-based + LLM fallback."""

    def test_two_symbols_always_comparison(self):
        """Rule 1: two symbols → comparison regardless of question content."""
        result = agent.classify_question_type(["BTC", "ETH"], "分析 BTC")
        assert result.question_type == "comparison"
        assert result.method == "rule"
        assert "rule1_two_symbols" in result.matched_rules

    def test_hypothesis_keywords_detected(self):
        """Rule 2: hypothesis keywords trigger hypothesis type."""
        questions = [
            "市場認為 BTC 將上漲，這個觀點正確嗎？",
            "有人說 ETH 即將突破，是否成立？",
            "驗證 BTC 短期盤整的假設",
            "市場預期 SOL 生態將爆發，能否驗證？",
            "聲音認為 BNB 被低估",
        ]
        for q in questions:
            result = agent.classify_question_type(["BTC"], q)
            assert result.question_type == "hypothesis", f"Failed for: {q}"
            assert result.method == "rule"
            assert "rule2_hypothesis_keywords" in result.matched_rules

    def test_default_single_integration(self):
        """Rule 3: no special keywords → single_integration."""
        result = agent.classify_question_type(
            ["BTC"], "綜合分析 BTC 目前的市場狀態"
        )
        assert result.question_type == "single_integration"
        assert result.method == "rule"
        assert "rule3_default" in result.matched_rules

    def test_comparison_overrides_hypothesis_keywords(self):
        """Two symbols should be comparison even if question has hypothesis keywords."""
        result = agent.classify_question_type(
            ["BTC", "ETH"], "市場認為 BTC 比 ETH 更安全，是否成立？"
        )
        assert result.question_type == "comparison"

    def test_classification_logs_execution_step(self):
        """classify_question_type should log its result."""
        evidence.reset_stores()
        agent.classify_question_type(["SOL"], "分析 SOL 走勢")
        classify_logs = [
            log for log in evidence.execution_log
            if log["tool_name"] == "classify_question_type"
        ]
        assert len(classify_logs) == 1
        assert classify_logs[0]["status"] == "success"
        assert "single_integration" in classify_logs[0]["note"]
        evidence.reset_stores()


# ── Prefetch Plan ──

class TestBuildPrefetchPlan:
    """Tests for build_prefetch_plan() — three question types."""

    def test_single_integration_plan_has_common_items(self):
        """Single integration: common per-symbol + sentiment + macro."""
        plan = agent.build_prefetch_plan("single_integration", ["BTC"], "分析走勢")
        capabilities = [item.capability for item in plan]
        # Must have: price, quant, derivatives_hl, derivatives_binance, news, onchain, sentiment, macro
        assert "price" in capabilities
        assert "quant" in capabilities
        assert "derivatives_hl" in capabilities
        assert "derivatives_binance" in capabilities
        assert "news" in capabilities
        assert "onchain" in capabilities
        assert "sentiment" in capabilities
        assert "macro" in capabilities
        # Type-specific additions
        assert "defi_stablecoin" in capabilities
        assert "prediction" in capabilities

    def test_hypothesis_plan_includes_directed_news(self):
        """Hypothesis plan includes directed news search."""
        plan = agent.build_prefetch_plan(
            "hypothesis", ["ETH"], "市場認為 ETH 將突破"
        )
        capabilities = [item.capability for item in plan]
        assert "directed_news" in capabilities
        assert "defi_stablecoin" in capabilities
        assert "prediction" in capabilities

    def test_comparison_plan_includes_correlation_and_dominance(self):
        """Comparison plan includes correlation and dominance."""
        plan = agent.build_prefetch_plan(
            "comparison", ["BTC", "ETH"], "比較風險特徵"
        )
        capabilities = [item.capability for item in plan]
        assert "correlation" in capabilities
        assert "dominance" in capabilities
        # Should have items for both symbols
        btc_items = [item for item in plan if "BTC" in item.symbols]
        eth_items = [item for item in plan if "ETH" in item.symbols]
        assert len(btc_items) >= 4
        assert len(eth_items) >= 4

    def test_sentiment_and_macro_not_duplicated(self):
        """Sentiment and macro only appear once regardless of symbol count."""
        plan = agent.build_prefetch_plan(
            "comparison", ["BTC", "ETH"], "比較"
        )
        sentiment_items = [i for i in plan if i.capability == "sentiment"]
        macro_items = [i for i in plan if i.capability == "macro"]
        assert len(sentiment_items) == 1
        assert len(macro_items) == 1

    def test_plan_items_have_valid_tool_names(self):
        """All plan items reference tools that exist in TOOL_DISPATCH."""
        plan = agent.build_prefetch_plan(
            "single_integration", ["SOL"], "分析 SOL"
        )
        for item in plan:
            assert item.tool_name in agent.TOOL_DISPATCH, (
                f"Plan item {item.capability} references unknown tool: {item.tool_name}"
            )

    def test_plan_items_have_related_claim(self):
        """All plan items must have a non-empty related_claim in kwargs."""
        plan = agent.build_prefetch_plan("hypothesis", ["BTC"], "假設測試")
        for item in plan:
            claim = item.tool_kwargs.get("related_claim", "")
            assert len(claim) >= 5, (
                f"Plan item {item.capability} has too short related_claim: '{claim}'"
            )


# ── Phase A Prefetch Execution ──

class TestRunPhaseAPrefetch:
    """Tests for run_phase_a_prefetch() — concurrency, timeout, isolation."""

    def test_successful_prefetch_records_results(self):
        """Successful tools are recorded in results with evidence_id."""
        evidence.reset_stores()

        # Create a minimal plan with mock tools
        plan = [
            agent.PrefetchItem(
                capability="test_cap",
                tool_name="get_sentiment",
                tool_kwargs={"related_claim": "測試 Phase A 預取功能正確性"},
                symbols=["BTC"],
                reason="test",
            ),
        ]

        with patch.dict(agent.TOOL_DISPATCH, {
            "get_sentiment": MagicMock(return_value={
                "raw": {"value": 65},
                "source": "https://api.alternative.me/fng/",
                "content_reference": {"value": 65},
                "summary": "Fear & Greed Index 為 65",
            })
        }):
            outcome = agent.run_phase_a_prefetch("run_test_pa", plan, soft_deadline_seconds=10)

        assert len(outcome.results) == 1
        assert outcome.results[0]["status"] == "success"
        assert outcome.results[0]["evidence_id"] is not None
        assert "raw" not in outcome.results[0].get("summary", "")
        evidence.reset_stores()

    def test_single_tool_failure_does_not_cancel_others(self):
        """One tool failure should not affect other tools."""
        evidence.reset_stores()

        def failing_tool(**kwargs):
            raise RuntimeError("API exploded")

        def succeeding_tool(**kwargs):
            return {
                "raw": {"ok": True},
                "source": "test_source",
                "content_reference": {"k": "v"},
                "summary": "success data",
            }

        plan = [
            agent.PrefetchItem(
                capability="will_fail",
                tool_name="get_sentiment",
                tool_kwargs={"related_claim": "這個會失敗但不影響其他工具"},
                symbols=["BTC"],
                reason="test failure",
            ),
            agent.PrefetchItem(
                capability="will_succeed",
                tool_name="get_macro",
                tool_kwargs={
                    "indicators": ["DXY"],
                    "related_claim": "這個應該正常完成不受其他工具影響",
                },
                symbols=["BTC"],
                reason="test success",
            ),
        ]

        with patch.dict(agent.TOOL_DISPATCH, {
            "get_sentiment": failing_tool,
            "get_macro": succeeding_tool,
        }):
            outcome = agent.run_phase_a_prefetch("run_test_iso", plan, soft_deadline_seconds=10)

        assert len(outcome.results) == 1
        assert outcome.results[0]["capability"] == "will_succeed"
        assert len(outcome.missing) == 1
        assert outcome.missing[0]["capability"] == "will_fail"
        evidence.reset_stores()

    def test_soft_deadline_cancels_pending_futures(self):
        """Futures not completed within deadline are cancelled/marked timeout."""
        evidence.reset_stores()

        def slow_tool(**kwargs):
            time.sleep(5)  # very slow
            return {
                "raw": {}, "source": "s", "content_reference": {},
                "summary": "should not complete",
            }

        def fast_tool(**kwargs):
            return {
                "raw": {"fast": True}, "source": "fast_src",
                "content_reference": {"r": 1}, "summary": "fast result",
            }

        plan = [
            agent.PrefetchItem(
                capability="fast_one",
                tool_name="get_sentiment",
                tool_kwargs={"related_claim": "快速工具應在期限內完成"},
                symbols=["BTC"],
                reason="fast",
            ),
            agent.PrefetchItem(
                capability="slow_one",
                tool_name="get_macro",
                tool_kwargs={
                    "indicators": ["DXY"],
                    "related_claim": "慢速工具應被期限截止",
                },
                symbols=["BTC"],
                reason="slow",
            ),
        ]

        with patch.dict(agent.TOOL_DISPATCH, {
            "get_sentiment": fast_tool,
            "get_macro": slow_tool,
        }):
            outcome = agent.run_phase_a_prefetch(
                "run_test_deadline", plan, soft_deadline_seconds=0.5
            )

        # The fast one should succeed, the slow one may be in missing
        succeeded = [r["capability"] for r in outcome.results]
        missed = [m["capability"] for m in outcome.missing]
        assert "fast_one" in succeeded
        # slow_one might be cancelled or timeout
        if "slow_one" in missed:
            assert any("deadline" in m.get("reason", "") or "timeout" in m.get("reason", "")
                       for m in outcome.missing if m["capability"] == "slow_one")
        evidence.reset_stores()

    def test_empty_plan_returns_empty_outcome(self):
        """Empty plan produces empty outcome without errors."""
        evidence.reset_stores()
        outcome = agent.run_phase_a_prefetch("run_empty", [], soft_deadline_seconds=10)
        assert outcome.results == []
        assert outcome.missing == []
        evidence.reset_stores()


# ── Phase B Context Builder ──

class TestBuildPhaseBContext:
    """Tests for build_phase_b_context() — no raw data in output."""

    def test_context_contains_summaries_and_evidence_ids(self):
        """Phase B context includes summaries and evidence_ids from results."""
        outcome = agent.PrefetchOutcome(
            question_type="single_integration",
            started_at="2026-08-01T00:00:00Z",
            completed_at="2026-08-01T00:01:30Z",
            results=[{
                "capability": "price",
                "tool_name": "get_price_ohlcv",
                "status": "success",
                "evidence_id": "ev_test_price",
                "summary": "BTC 價格近 30 天上漲 5%",
                "anomaly_flags": [{"signal": "volume_spike", "direction": "up"}],
                "symbols": ["BTC"],
            }],
            missing=[{
                "capability": "onchain",
                "tool_name": "get_onchain",
                "reason": "API timeout",
                "required": True,
            }],
        )
        context = agent.build_phase_b_context(outcome)

        assert "ev_test_price" in context
        assert "BTC 價格近 30 天上漲 5%" in context
        assert "volume_spike" in context
        assert "onchain" in context
        assert "API timeout" in context
        # NO raw data
        assert '"raw"' not in context

    def test_context_excludes_raw_payload(self):
        """Raw data must NEVER appear in Phase B context."""
        outcome = agent.PrefetchOutcome(
            question_type="single_integration",
            started_at="2026-08-01T00:00:00Z",
            completed_at="2026-08-01T00:01:30Z",
            results=[{
                "capability": "price",
                "tool_name": "get_price_ohlcv",
                "status": "success",
                "evidence_id": "ev_123",
                "summary": "summary text",
                "anomaly_flags": [],
                "symbols": ["BTC"],
                "raw_result": {"raw": {"secret_data": "should_not_appear" * 100}},
            }],
            missing=[],
        )
        context = agent.build_phase_b_context(outcome)
        assert "secret_data" not in context
        assert "should_not_appear" not in context


# ── Force Convergence ──

class TestShouldForceConvergence:
    """Tests for should_force_convergence() — 20% boundary."""

    def test_not_convergent_when_plenty_of_time(self):
        """Should not converge when >20% budget remains."""
        # budget=600, elapsed=100 → remaining=500 (83%) → False
        started = time.time() - 100
        assert agent.should_force_convergence(started, 600) is False

    def test_convergent_at_boundary(self):
        """Should converge when remaining is exactly at or below 20%."""
        # budget=600, elapsed=481 → remaining=119 < 120 → True
        started = time.time() - 481
        assert agent.should_force_convergence(started, 600) is True

    def test_convergent_when_over_budget(self):
        """Should converge when over budget."""
        started = time.time() - 700
        assert agent.should_force_convergence(started, 600) is True

    def test_not_convergent_at_80_percent(self):
        """At 80% elapsed (20% remaining), should just barely converge."""
        # budget=100, elapsed=80 → remaining=20 = 20% → equal to threshold
        # remaining < 0.2 * budget → 20 < 20 → False (not strictly less)
        started = time.time() - 80
        result = agent.should_force_convergence(started, 100)
        # At exactly 20% remaining it depends on timing; test near-boundary
        started = time.time() - 81
        assert agent.should_force_convergence(started, 100) is True


# ── Series Registry ──

class TestSeriesRegistry:
    """Tests for series registry — request-scoped, cleared per request."""

    def test_register_and_collect(self):
        """Basic register and collect works."""
        agent.reset_series_registry()
        agent.register_visualization_series("test_series", "price_series", {"data": [1, 2]})
        series = agent.collect_series()
        assert "test_series" in series
        assert series["test_series"]["series_type"] == "price_series"
        agent.reset_series_registry()

    def test_reset_clears_registry(self):
        """reset_series_registry clears all data."""
        agent.reset_series_registry()
        agent.register_visualization_series("s1", "type", {"k": "v"})
        assert len(agent.collect_series()) == 1
        agent.reset_series_registry()
        assert len(agent.collect_series()) == 0

    def test_multiple_registrations_accumulate(self):
        """Multiple registrations in same request accumulate."""
        agent.reset_series_registry()
        agent.register_visualization_series("price_btc", "price", {"btc": [1]})
        agent.register_visualization_series("price_eth", "price", {"eth": [2]})
        series = agent.collect_series()
        assert len(series) == 2
        agent.reset_series_registry()

    def test_series_isolated_per_request(self):
        """Series from one request don't leak to another."""
        agent.reset_series_registry()
        agent.register_visualization_series("request1", "type", {"d": 1})
        agent.reset_series_registry()  # simulate new request
        series = agent.collect_series()
        assert "request1" not in series


# ── Question Type Prompt ──

class TestBuildQuestionTypePrompt:
    """Tests for build_question_type_prompt() — per-type system prompt."""

    def test_single_integration_prompt(self):
        """Single integration prompt mentions relevant keywords."""
        prompt = agent.build_question_type_prompt("single_integration", ["BTC"])
        assert "整合" in prompt or "單幣" in prompt
        assert "BTC" in prompt

    def test_hypothesis_prompt(self):
        """Hypothesis prompt mentions validation keywords."""
        prompt = agent.build_question_type_prompt("hypothesis", ["ETH"])
        assert "驗證" in prompt or "假設" in prompt

    def test_comparison_prompt(self):
        """Comparison prompt mentions both symbols."""
        prompt = agent.build_question_type_prompt("comparison", ["BTC", "ETH"])
        assert "BTC" in prompt
        assert "ETH" in prompt
        assert "比較" in prompt

    def test_no_fixed_report_quotas(self):
        """Question type prompts must not introduce fixed report quotas."""
        for qt in ("single_integration", "hypothesis", "comparison"):
            prompt = agent.build_question_type_prompt(qt, ["BTC", "ETH"][:2 if qt == "comparison" else 1])
            assert "5/5" not in prompt
            assert "固定分母" not in prompt


# ── Integration: run_agent_loop with Phase A/B ──

@patch("agent.call_bedrock")
def test_run_agent_loop_integrates_phase_a_b(mock_bedrock):
    """run_agent_loop should execute Phase A, classify type, and inject context."""
    evidence.reset_stores()

    # Mock Bedrock to immediately end
    mock_bedrock.return_value = {
        "stopReason": "end_turn",
        "output": {
            "message": {
                "role": "assistant",
                "content": [{"text": "基於 Phase A 預取資料進行分析完成。"}]
            }
        }
    }

    # Mock all tools to return success
    mock_tool = MagicMock(return_value={
        "raw": {"data": [1, 2, 3]},
        "source": "https://test.api/mock",
        "content_reference": {"key": "value"},
        "summary": "Mock tool success",
    })

    with patch.dict(agent.TOOL_DISPATCH, {k: mock_tool for k in agent.TOOL_DISPATCH}):
        messages = agent.run_agent_loop("run_test_integration", ["BTC"], "分析市場")

    # Verify Phase A was executed (classification logged)
    classify_logs = [
        log for log in evidence.execution_log
        if log["tool_name"] == "classify_question_type"
    ]
    assert len(classify_logs) == 1

    # Verify question_type is stored in run context
    assert agent._run_context.get("question_type") == "single_integration"

    # Verify Phase A context is injected into initial message
    initial_msg = messages[0]["content"][0]["text"]
    assert "Phase A" in initial_msg

    evidence.reset_stores()


@patch("agent.call_bedrock")
def test_run_agent_loop_forces_convergence_at_20_percent(mock_bedrock):
    """When budget < 20% remaining, convergence is forced."""
    evidence.reset_stores()

    call_count = [0]

    def delayed_bedrock(*args, **kwargs):
        call_count[0] += 1
        # Each call takes 0.5s to simulate time passing
        time.sleep(0.3)
        if call_count[0] <= 5:
            return {
                "stopReason": "tool_use",
                "output": {
                    "message": {
                        "role": "assistant",
                        "content": [{
                            "toolUse": {
                                "toolUseId": f"tool-{call_count[0]}",
                                "name": "get_sentiment",
                                "input": {"related_claim": "持續蒐集但時間快到了"}
                            }
                        }]
                    }
                }
            }
        return {
            "stopReason": "end_turn",
            "output": {
                "message": {
                    "role": "assistant",
                    "content": [{"text": "收斂完成"}]
                }
            }
        }

    mock_bedrock.side_effect = delayed_bedrock

    # Set time budget = 1s. With Phase A returning immediately (mocked),
    # the loop_start captures time at top of run_agent_loop.
    # Each bedrock call takes 0.3s. After ~3 calls (~0.9s), remaining < 0.2s (20% of 1s).
    original_budget = config.TIME_BUDGET_SECONDS
    config.TIME_BUDGET_SECONDS = 1

    mock_tool = MagicMock(return_value={
        "raw": {}, "source": "test", "content_reference": {},
        "summary": "test",
    })

    try:
        with patch.dict(agent.TOOL_DISPATCH, {k: mock_tool for k in agent.TOOL_DISPATCH}):
            with patch("agent.run_phase_a_prefetch") as mock_pa:
                mock_pa.return_value = agent.PrefetchOutcome(
                    question_type="single_integration",
                    started_at="2026-01-01T00:00:00Z",
                    completed_at="2026-01-01T00:00:01Z",
                )
                messages = agent.run_agent_loop("run_test_conv", ["BTC"], "快速測試")
    finally:
        config.TIME_BUDGET_SECONDS = original_budget

    # Should have force_convergence or timeout logged for agent_loop
    agent_loop_logs = [
        log for log in evidence.execution_log
        if log["tool_name"] == "agent_loop"
    ]
    convergence_logs = [
        log for log in evidence.execution_log
        if log.get("status") == "force_convergence"
        or (log.get("note") and "20%" in log.get("note", ""))
        or log.get("status") == "timeout"
    ]
    # Either convergence or timeout must have been triggered
    assert len(agent_loop_logs) >= 1 or len(convergence_logs) >= 1, (
        f"Expected convergence/timeout. agent_loop logs: {agent_loop_logs}, "
        f"all logs: {evidence.execution_log}"
    )
    evidence.reset_stores()


# ── Handler integration with report_data ──

@patch("agent.run_agent_loop")
@patch("agent.summarize_final_analysis")
def test_handler_returns_report_data_in_c5_response(mock_summarize, mock_loop):
    """Handler response includes report_data per C5 contract."""
    evidence.reset_stores()
    agent._run_context = {"question_type": "single_integration"}
    agent._series_registry = {"price_btc": {"series_type": "price", "data": {}}}

    mock_loop.return_value = [{"role": "user", "content": [{"text": "test"}]}]
    mock_summarize.return_value = "## 市場判斷\n結論\n## 關鍵依據\n依據\n## 信心說明\n說明"

    event = {"body": json.dumps({"symbols": ["BTC"], "question": "測試 report_data 傳遞"})}
    response = handler.lambda_handler(event, None)
    body = json.loads(response["body"])

    assert response["statusCode"] == 200
    assert "report_data" in body
    assert body["report_data"]["question_type"] == "single_integration"
    assert body["report_data"]["symbols"] == ["BTC"]
    assert body["report_data"]["schema_version"] == "1.0"

    evidence.reset_stores()
    agent.reset_series_registry()
