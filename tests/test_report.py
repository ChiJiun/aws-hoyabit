"""
test_report.py — report.py 的單元測試

測試 calculate_coverage、build_evidence_table、render_report 函式的正確性。
"""

import sys
import os

# 將 lambda 目錄加入 sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambda"))

from report import calculate_coverage, build_evidence_table, render_report


def test_empty_evidence_list():
    """空證據清單應回傳 0% 覆蓋率，五類全部缺少"""
    pct, obtained, missing = calculate_coverage([])
    assert pct == 0.0
    assert obtained == []
    assert len(missing) == 5
    assert set(missing) == {"價格", "新聞", "鏈上", "情緒", "總經"}


def test_none_evidence_list():
    """None 輸入應等同空清單"""
    pct, obtained, missing = calculate_coverage(None)
    assert pct == 0.0
    assert obtained == []
    assert len(missing) == 5


def test_single_category_price():
    """僅有價格類別，應回傳 20% 覆蓋率"""
    evidence = [
        {"source": "https://api.binance.com/api/v3/klines?symbol=BTCUSDT", "fetched_at": "2025-01-01T00:00:00Z",
         "content_reference": {}, "related_claim": "測試用"},
    ]
    pct, obtained, missing = calculate_coverage(evidence)
    assert pct == 20.0
    assert "價格" in obtained
    assert "價格" not in missing
    assert len(missing) == 4


def test_all_five_categories():
    """五類全齊，應回傳 100% 覆蓋率"""
    evidence = [
        {"source": "https://api.binance.com/api/v3/klines", "related_claim": "價格資料"},
        {"source": "https://cryptopanic.com/api/v1/posts", "related_claim": "新聞資料"},
        {"source": "https://mempool.space/api/blocks", "related_claim": "鏈上資料"},
        {"source": "https://alternative.me/crypto/fear-and-greed-index", "related_claim": "情緒資料"},
        {"source": "https://api.stlouisfed.org/fred/series", "related_claim": "總經資料"},
    ]
    pct, obtained, missing = calculate_coverage(evidence)
    assert pct == 100.0
    assert len(obtained) == 5
    assert missing == []


def test_three_categories():
    """三類覆蓋，應回傳 60%"""
    evidence = [
        {"source": "https://api.binance.com/ohlcv", "related_claim": "價格"},
        {"source": "https://cryptopanic.com/news", "related_claim": "新聞"},
        {"source": "https://api.stlouisfed.org/fred", "related_claim": "總經"},
    ]
    pct, obtained, missing = calculate_coverage(evidence)
    assert pct == 60.0
    assert len(obtained) == 3
    assert len(missing) == 2
    assert "鏈上" in missing
    assert "情緒" in missing


def test_duplicate_sources_same_category():
    """同一類別有多筆證據，不應重複計算"""
    evidence = [
        {"source": "https://api.binance.com/klines?symbol=BTCUSDT", "related_claim": "BTC 價格"},
        {"source": "https://api.coingecko.com/v3/coins/bitcoin", "related_claim": "BTC 備用價格"},
        {"source": "https://api.binance.com/klines?symbol=ETHUSDT", "related_claim": "ETH 價格"},
    ]
    pct, obtained, missing = calculate_coverage(evidence)
    assert pct == 20.0
    assert obtained == ["價格"]


def test_quant_not_counted():
    """quant 不屬於五類預期類別，不應被計入覆蓋率"""
    evidence = [
        {"source": "quant_indicator_local_computation", "related_claim": "技術指標"},
    ]
    pct, obtained, missing = calculate_coverage(evidence)
    assert pct == 0.0
    assert len(missing) == 5


def test_missing_source_field():
    """證據記錄缺少 source 欄位時不應拋錯"""
    evidence = [
        {"related_claim": "缺少來源"},
        {"source": "", "related_claim": "空來源"},
    ]
    pct, obtained, missing = calculate_coverage(evidence)
    assert pct == 0.0
    assert len(missing) == 5


def test_onchain_various_sources():
    """不同鏈上來源都能被正確歸類為鏈上"""
    sources = [
        "https://mempool.space/api/blocks",
        "https://api.etherscan.io/v2/api",
        "https://blockscout.com/xdai/mainnet",
        "https://api.helius.xyz/v0/addresses",
        "https://s1.ripple.com:51234 xrpl",
    ]
    for src in sources:
        evidence = [{"source": src, "related_claim": "鏈上測試"}]
        pct, obtained, missing = calculate_coverage(evidence)
        assert "鏈上" in obtained, f"來源 '{src}' 未被歸類為鏈上"


# ============ build_evidence_table 測試 ============


def test_build_evidence_table_normal():
    """正常證據清單應產出正確的 Markdown 表格"""
    evidence = [
        {
            "evidence_id": "ev_a1b2c3",
            "source": "https://api.binance.com/api/v3/klines",
            "fetched_at": "2026-07-30T14:15:30Z",
            "related_claim": "需要日線資料計算波動率",
        },
        {
            "evidence_id": "ev_d4e5f6",
            "source": "https://cryptopanic.com/api/v1/posts",
            "fetched_at": "2026-07-30T14:16:00Z",
            "related_claim": "蒐集近期新聞情緒",
        },
    ]
    result = build_evidence_table(evidence)
    lines = result.split("\n")
    # 應有表頭 + 分隔線 + 2 筆資料 = 4 行
    assert len(lines) == 4
    # 表頭欄位
    assert "evidence_id" in lines[0]
    assert "來源" in lines[0]
    assert "取得時間" in lines[0]
    assert "對應判斷" in lines[0]
    # 資料列包含正確內容
    assert "ev_a1b2c3" in lines[2]
    assert "ev_d4e5f6" in lines[3]
    assert "需要日線資料計算波動率" in lines[2]


def test_build_evidence_table_empty():
    """空清單應回傳空字串"""
    result = build_evidence_table([])
    assert result == ""


def test_build_evidence_table_none():
    """None 輸入應回傳空字串"""
    result = build_evidence_table(None)
    assert result == ""


def test_build_evidence_table_pipe_escape():
    """欄位中的 | 字元應被跳脫，避免破壞 Markdown 表格"""
    evidence = [
        {
            "evidence_id": "ev_pipe",
            "source": "source|with|pipes",
            "fetched_at": "2026-01-01T00:00:00Z",
            "related_claim": "claim|pipe",
        },
    ]
    result = build_evidence_table(evidence)
    # related_claim 中的 | 應被跳脫；技術 API 來源不直接顯示在報告中
    assert "source|with|pipes" not in result
    assert "claim\\|pipe" in result


def test_build_evidence_table_missing_fields():
    """證據記錄缺少部分欄位時不應拋錯，缺少的欄位以空字串呈現"""
    evidence = [
        {"evidence_id": "ev_partial"},
        {},
    ]
    result = build_evidence_table(evidence)
    lines = result.split("\n")
    # 表頭 + 分隔 + 2 筆 = 4 行
    assert len(lines) == 4
    assert "ev_partial" in lines[2]


# ============ render_report 測試 ============


def test_render_report_three_sections_guaranteed():
    """Property 16: 不論 analysis_text 內容為何，輸出必包含三個章節標題"""
    result = render_report("run_001", "BTC 走勢分析", "這是一段隨意文字", [])
    assert "## 市場判斷" in result
    assert "## 關鍵依據" in result
    assert "## 信心說明" in result


def test_render_report_with_structured_analysis():
    """當 analysis_text 包含三段標記時，正確分離到各章節"""
    analysis = (
        "## 市場判斷\nBTC 短期看多\n\n"
        "## 關鍵依據\n日線連三紅\n\n"
        "## 信心說明\n信心中等，鏈上資料不足\n"
    )
    result = render_report("run_002", "BTC 分析", analysis, [])
    assert "BTC 短期看多" in result
    assert "日線連三紅" in result
    assert "信心中等" in result


def test_render_report_evidence_ids_in_report():
    """需求 12.2: 關鍵依據章節中為每條依據附上 evidence_id"""
    evidence = [
        {"evidence_id": "ev_abc123", "source": "binance", "fetched_at": "2026-01-01T00:00:00Z",
         "related_claim": "價格突破"},
        {"evidence_id": "ev_def456", "source": "cryptopanic", "fetched_at": "2026-01-01T00:00:00Z",
         "related_claim": "利多消息"},
    ]
    result = render_report("run_003", "BTC 走勢", "分析文字", evidence)
    assert "ev_abc123" in result
    assert "ev_def456" in result


def test_render_report_missing_sources_limitation():
    """需求 12.3 + missing_sources: 當有缺失資料類別時應寫入限制段落"""
    result = render_report(
        "run_004", "ETH 分析", "分析文字", [],
        missing_sources=["鏈上", "情緒"]
    )
    assert "鏈上" in result
    assert "情緒" in result
    assert "資料不足" in result or "資料缺失" in result


def test_render_report_coverage_in_appendix():
    """需求 12.4: 附錄中包含資料覆蓋率"""
    evidence = [
        {"source": "https://api.binance.com/klines", "related_claim": "價格"},
        {"source": "https://cryptopanic.com/posts", "related_claim": "新聞"},
    ]
    result = render_report("run_005", "分析", "文字", evidence)
    assert "覆蓋率" in result
    assert "40.0%" in result


def test_render_report_markdown_format():
    """需求 12.5: 輸出為 Markdown 格式（含標題符號 #）"""
    result = render_report("run_006", "測試", "內容", [])
    assert result.startswith("#")
    assert "---" in result


def test_render_report_empty_inputs():
    """空的 analysis_text 和 evidence_list 不應拋錯"""
    result = render_report("run_007", "空測試", "", [], None)
    assert "## 市場判斷" in result
    assert "## 關鍵依據" in result
    assert "## 信心說明" in result


def test_render_report_no_exception_on_bad_input():
    """無論輸入多離譜都不應拋出未處理的例外"""
    # None 輸入
    result = render_report("run_008", "test", None, None, None)
    assert "## 市場判斷" in result
    assert "## 關鍵依據" in result
    assert "## 信心說明" in result


if __name__ == "__main__":
    test_empty_evidence_list()
    test_none_evidence_list()
    test_single_category_price()
    test_all_five_categories()
    test_three_categories()
    test_duplicate_sources_same_category()
    test_quant_not_counted()
    test_missing_source_field()
    test_onchain_various_sources()
    test_build_evidence_table_normal()
    test_build_evidence_table_empty()
    test_build_evidence_table_none()
    test_build_evidence_table_pipe_escape()
    test_build_evidence_table_missing_fields()
    test_render_report_three_sections_guaranteed()
    test_render_report_with_structured_analysis()
    test_render_report_evidence_ids_in_report()
    test_render_report_missing_sources_limitation()
    test_render_report_coverage_in_appendix()
    test_render_report_markdown_format()
    test_render_report_empty_inputs()
    test_render_report_no_exception_on_bad_input()
    print("All tests passed!")
