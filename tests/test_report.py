"""
test_report.py — report.py 的多維度摘要、證據表與渲染測試
"""

import os
import re
import sys

from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambda"))

import report as report_module
from report import (
    ANALYSIS_DIMENSIONS,
    TOOL_DIMENSIONS,
    build_analysis_summary,
    build_evidence_table,
    canonicalize_source,
    classify_dimension,
    render_report,
)


def make_evidence(evidence_id, source, content_reference=None, claim="測試判斷"):
    return {
        "evidence_id": evidence_id,
        "source": source,
        "fetched_at": "2026-07-30T14:15:30Z",
        "content_reference": content_reference or {},
        "related_claim": claim,
    }


# **Validates: Requirements 12.5**
@given(
    tool_name=st.sampled_from(sorted(TOOL_DIMENSIONS)),
    source=st.text(max_size=80),
    content_reference=st.dictionaries(
        st.sampled_from(["metric", "data_type", "provider"]),
        st.text(max_size=30),
        max_size=3,
    ),
)
@settings(max_examples=80)
def test_property_17_tool_classification_is_deterministic_and_complete(
    tool_name, source, content_reference
):
    """Property 17: 工具名稱為最強訊號，結果固定且一定屬於 13 維。"""
    first = classify_dimension(tool_name, source, content_reference)
    second = classify_dimension(tool_name, source, content_reference)
    assert first == second == TOOL_DIMENSIONS[tool_name]
    assert first in ANALYSIS_DIMENSIONS


def test_all_implemented_tool_mappings():
    """15 個已實作工具均映射到指定顯示維度。"""
    expected = {
        "get_price_ohlcv": "價格",
        "compute_quant": "技術指標",
        "get_orderbook_depth": "市場結構與流動性",
        "get_market_dominance": "市場結構與流動性",
        "get_derivatives": "衍生品",
        "get_onchain": "鏈上",
        "get_sentiment": "情緒",
        "get_prediction_market": "預測市場",
        "search_news": "新聞與公告",
        "get_macro": "總體經濟",
        "get_defi_data": "DeFi",
        "get_dev_activity": "開發活躍度",
        "get_coin_metrics": "機構資料",
        "get_cftc_cot": "機構資料",
        "get_sec_filings": "監管資料",
    }
    assert TOOL_DIMENSIONS == expected
    assert set(ANALYSIS_DIMENSIONS) == set(expected.values())


def test_structured_and_source_fallbacks_cover_all_dimensions():
    """沒有 execution log 時，結構化內容與來源仍能決定性分類 13 維。"""
    cases = {
        "價格": ("", {"data_type": "OHLCV"}),
        "技術指標": ("", {"metric": "ATR percentile"}),
        "市場結構與流動性": ("", {"metric": "order book depth"}),
        "衍生品": ("", {"metric": "funding open interest"}),
        "鏈上": ("https://mempool.space/api/blocks", {}),
        "情緒": ("https://api.alternative.me/fng/", {}),
        "預測市場": ("https://polymarket.com/market/test", {}),
        "新聞與公告": ("https://coindesk.com/markets", {}),
        "總體經濟": ("https://fred.stlouisfed.org/series/DXY", {}),
        "DeFi": ("https://api.defillama.com/tvl", {}),
        "開發活躍度": ("https://github.com/org/repo/releases", {}),
        "機構資料": ("Coin Metrics", {"metric": "MVRV"}),
        "監管資料": ("https://www.sec.gov/edgar/search", {}),
    }
    for expected, (source, reference) in cases.items():
        assert classify_dimension(None, source, reference) == expected


def test_capability_priority_is_fixed_for_compound_match():
    """複合命中時 capability 優先於結構與來源。"""
    result = classify_dimension(
        "regulation.filing",
        "https://github.com/org/repo",
        {"metric": "funding rate and TVL"},
    )
    assert result == "監管資料"


def test_unknown_tool_gracefully_uses_fallback():
    """未知工具不拋錯，仍依來源分類到合法維度。"""
    assert classify_dimension("mystery_tool", "https://api.defillama.com/tvl", {}) == "DeFi"
    assert classify_dimension("mystery_tool", "", {}) in ANALYSIS_DIMENSIONS


def test_canonical_source_counting_url_hosts_and_aliases():
    """同 host 不同 endpoint 與 www. 只算一次，非 URL alias 也決定性正規化。"""
    assert canonicalize_source("https://www.API.Binance.com/a") == "api.binance.com"
    assert canonicalize_source("https://api.binance.com/b") == "api.binance.com"
    assert canonicalize_source("Binance API") == canonicalize_source("binance") == "binance"
    assert canonicalize_source("Coin Metrics") == canonicalize_source("coinmetrics")


# **Validates: Requirements 12.5, 12.6, 12.7, 13.6, 13.9**
@given(duplicate_count=st.integers(min_value=1, max_value=8))
@settings(max_examples=30)
def test_property_18_duplicate_ids_uncited_evidence_and_sources_are_faithful(duplicate_count):
    """Property 18: 只計引用 ID，重複 ID 與同 host endpoint 不膨脹計數。"""
    cited = make_evidence("ev_price", "https://www.api.binance.com/v3/klines")
    duplicate = make_evidence("ev_price", "https://api.binance.com/v3/ticker")
    uncited = make_evidence("ev_news", "https://coindesk.com/news")
    evidence_list = [cited] + [duplicate] * duplicate_count + [uncited]
    metadata = {
        "analyzed_evidence_ids": ["ev_price", "ev_price", "missing"],
        "evidence_capabilities": {"ev_price": "get_price_ohlcv"},
    }
    summary = build_analysis_summary(evidence_list, metadata)
    assert summary["cited_evidence_count"] == 1
    assert summary["independent_source_count"] == 1
    assert summary["analyzed_dimensions"] == ["價格"]
    assert "ev_news" not in str(summary["dimension_details"])


def test_summary_mixed_success_failures_and_relevant_omissions():
    evidence_list = [
        make_evidence("ev_quant", "local_pandas", {"metric": "ATR"}),
        make_evidence("ev_sentiment", "Fear and Greed Index"),
    ]
    metadata = {
        "analyzed_evidence_ids": ["ev_quant"],
        "evidence_capabilities": {
            "ev_quant": "compute_quant",
            "ev_sentiment": "get_sentiment",
        },
        "attempted_capabilities": [
            {"capability_id": "get_derivatives", "status": "timeout", "reason": "上游逾時"},
            {"capability_id": "get_onchain", "status": "unavailable", "reason": "無可用金鑰"},
            {"capability_id": "get_macro", "status": "error", "reason": "服務錯誤"},
            {"capability_id": "get_sentiment", "status": "success", "reason": ""},
            {"capability_id": "unknown_tool", "status": "error", "reason": "unknown tool"},
        ],
        "relevant_omissions": [
            {"dimension": "監管資料", "reason": "題目相關但無資料", "confidence_impact": "中"}
        ],
    }
    summary = build_analysis_summary(evidence_list, metadata)
    assert summary["analyzed_dimensions"] == ["技術指標"]
    assert {item["status"] for item in summary["failed_attempts"]} == {
        "timeout", "unavailable", "error"
    }
    assert all(item["dimension"] in ANALYSIS_DIMENSIONS for item in summary["failed_attempts"])
    assert "unknown_tool" not in str(summary["failed_attempts"])
    assert summary["relevant_omissions"][0]["dimension"] == "監管資料"


def test_analysis_without_valid_ids_does_not_claim_collected_evidence():
    evidence_list = [make_evidence("ev_unused", "https://coindesk.com/news")]
    result = render_report(
        "run_no_citation", "BTC 新聞", "分析沒有引用任何有效 ID", evidence_list
    )
    assert "引用證據筆數**：0" in result
    assert "實際分析維度**：（未引用有效證據，無法判定）" in result
    assert "**[ev_unused]**" not in result
    assert "ev_unused" in result  # 完整證據表仍須保留


def test_render_report_uses_only_cited_evidence_and_canonical_sources():
    evidence_list = [
        make_evidence("ev_a", "https://www.api.binance.com/v3/klines"),
        make_evidence("ev_b", "https://api.binance.com/v3/ticker"),
        make_evidence("ev_c", "https://coindesk.com/news"),
    ]
    analysis = (
        "## 市場判斷\n事實：價格資料 [ev_a] 與 [ev_b]。\n"
        "## 關鍵依據\n[ev_a]、[ev_b]\n"
        "## 信心說明\n信心中等。"
    )
    metadata = {
        "analyzed_evidence_ids": ["ev_a", "ev_b"],
        "evidence_capabilities": {"ev_a": "get_price_ohlcv", "ev_b": "get_price_ohlcv"},
    }
    result = render_report("run_sources", "價格題", analysis, evidence_list, coverage=metadata)
    assert "引用證據筆數**：2" in result
    assert "獨立來源數**：1" in result
    assert "實際分析維度**：價格" in result
    assert "api.binance.com" in result


def test_failed_attempts_and_execution_limits_are_separate_and_deduplicated():
    metadata = {
        "analyzed_evidence_ids": [],
        "attempted_capabilities": [
            {"capability_id": "get_derivatives", "status": "timeout", "reason": "10 秒逾時"},
            {"capability_id": "get_derivatives", "status": "timeout", "reason": "10  秒逾時"},
            {"capability_id": "mystery_tool", "status": "error", "reason": "unknown tool"},
        ],
        "execution_limitations": [
            {"source": "agent_loop", "status": "timeout", "reason": "時間預算耗盡"},
            {"source": "agent_loop", "status": "timeout", "reason": "時間預算耗盡"},
        ],
        "relevant_omissions": [
            {"dimension": "鏈上", "reason": "本題需要但未取得", "confidence_impact": "降低基本面判斷信心"}
        ],
    }
    summary = build_analysis_summary([], metadata)
    assert len(summary["failed_attempts"]) == 1
    assert len(summary["execution_limitations"]) == 1

    result = render_report("run_fail", "測試", "內容", [], coverage=metadata)
    assert "### 多維度分析摘要" in result
    assert "衍生品" in result and "timeout" in result and "10 秒逾時" in result
    assert "mystery_tool" not in result
    assert "#### 執行限制" in result and "時間預算耗盡" in result
    assert "鏈上" in result and "降低基本面判斷信心" in result
    confidence = result.split("## 信心說明", 1)[1].split("## 附錄", 1)[0]
    assert "衍生品" in confidence
    assert "**執行限制**" in confidence
    assert "鏈上" in confidence
    assert "價格" not in confidence


def test_legacy_missing_sources_adds_only_supplied_omissions():
    result = render_report(
        "run_legacy", "監管題", "內容", [], missing_sources=["監管資料"]
    )
    assert "監管資料" in result
    assert "價格取得失敗" not in result
    assert "鏈上取得失敗" not in result


def test_report_guarantees_sections_full_table_and_no_fixed_scores():
    evidence_list = [make_evidence("ev_one", "https://coindesk.com/news")]
    metadata = {
        "analyzed_evidence_ids": ["ev_one"],
        "evidence_capabilities": {"ev_one": "search_news"},
    }
    result = render_report(
        "run_sections", "新聞題", "事實 [ev_one] → 推論 → 結論", evidence_list,
        coverage=metadata,
    )
    assert "## 市場判斷" in result
    assert "## 關鍵依據" in result
    assert "## 信心說明" in result
    assert "### 完整證據清單" in result
    assert "| evidence_id | 來源 |" in result
    forbidden = ["/5 類別", "資料覆蓋率", "覆蓋率**", "維度分數"]
    for text in forbidden:
        assert text not in result
    assert not re.search(
        r"(?:資料覆蓋率|覆蓋率|維度分數)[^\n\d]{0,20}\d+(?:\.\d+)?\s*(?:/\s*\d+|%)",
        result,
    )


def test_render_report_fallback_guarantees_required_sections_when_helper_raises(monkeypatch):
    """內部渲染 helper 失敗時仍回傳完整四段 fallback，不依賴網路情境。"""
    def fail_rendering(*args, **kwargs):
        raise RuntimeError("forced rendering failure")

    monkeypatch.setattr(report_module, "_parse_analysis_sections", fail_rendering)
    result = render_report("run_fallback", "測試", "內容", [], coverage={})
    assert "## 市場判斷" in result
    assert "## 關鍵依據" in result
    assert "## 信心說明" in result
    assert "### 多維度分析摘要" in result
    assert "報告渲染時發生錯誤" in result


def test_build_evidence_table_normal_escape_and_missing_fields():
    evidence = [
        make_evidence("ev_pipe", "source|with|pipes", claim="claim|pipe"),
        {"evidence_id": "ev_partial"},
        {},
    ]
    result = build_evidence_table(evidence)
    lines = result.split("\n")
    assert len(lines) == 5
    assert "source\\|with\\|pipes" in result
    assert "claim\\|pipe" in result
    assert "ev_partial" in result


def test_build_evidence_table_empty_inputs():
    assert build_evidence_table([]) == ""
    assert build_evidence_table(None) == ""
