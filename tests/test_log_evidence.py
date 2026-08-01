"""
Tests for evidence.log_evidence function.

Property 7: 證據記錄欄位完整性
Property 8: 空 related_claim 被拒絕
Property 9: Evidence ID 唯一性

Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 4.6
"""

import sys
import os

# 確保 lambda 目錄在搜尋路徑中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lambda'))

from unittest.mock import patch
from datetime import datetime

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from evidence import evidence_list, execution_log, reset_stores, log_evidence


# --- Strategies ---

valid_claim_strategy = st.text(min_size=5, max_size=200).filter(lambda s: len(s.strip()) >= 5)

valid_fetch_result_strategy = st.fixed_dictionaries({
    "raw": st.dictionaries(st.text(min_size=1, max_size=20), st.text(min_size=0, max_size=50), max_size=5),
    "source": st.text(min_size=1, max_size=200),
    "content_reference": st.dictionaries(st.text(min_size=1, max_size=20), st.text(min_size=0, max_size=50), max_size=5),
    "summary": st.text(min_size=1, max_size=100),
})

run_id_strategy = st.from_regex(r"run_[0-9]{8}_[0-9]{6}", fullmatch=True)
tool_name_strategy = st.sampled_from([
    "get_price_ohlcv", "search_news", "get_onchain",
    "compute_quant", "get_sentiment", "get_macro",
])


# --- Property 7: 證據記錄欄位完整性 ---

@given(
    run_id=run_id_strategy,
    tool_name=tool_name_strategy,
    related_claim=valid_claim_strategy,
    fetch_result=valid_fetch_result_strategy,
)
@settings(max_examples=200)
def test_evidence_record_has_exactly_five_fields(run_id, tool_name, related_claim, fetch_result):
    """
    **Validates: Requirements 4.1, 4.2**

    Property 7: log_evidence 產生的記錄包含正確五欄位
    (evidence_id, source, fetched_at, content_reference, related_claim)
    """
    reset_stores()

    with patch("storage.save_raw_payload", return_value="s3://bucket/path"):
        result = log_evidence(run_id, tool_name, related_claim, fetch_result)

    # 回傳值為 evidence_id 字串（以 ev_ 開頭）
    assert result.startswith("ev_"), f"Expected evidence_id starting with 'ev_', got: {result}"

    # evidence_list 新增一筆
    assert len(evidence_list) == 1

    record = evidence_list[0]

    # 必須恰好包含這五個欄位
    expected_fields = {"evidence_id", "source", "fetched_at", "content_reference", "related_claim"}
    assert set(record.keys()) == expected_fields, f"Fields mismatch: {set(record.keys())} != {expected_fields}"

    # evidence_id 與回傳值一致
    assert record["evidence_id"] == result

    # source 來自 fetch_result
    assert record["source"] == fetch_result["source"]

    # fetched_at 為 ISO 8601 UTC 格式
    fetched_at = record["fetched_at"]
    assert fetched_at.endswith("Z")
    # 確認可以解析
    datetime.strptime(fetched_at, "%Y-%m-%dT%H:%M:%SZ")

    # content_reference 來自 fetch_result
    assert record["content_reference"] == fetch_result["content_reference"]

    # related_claim 為 LLM 提供的原始值
    assert record["related_claim"] == related_claim


# --- Property 8: 空 related_claim 被拒絕 ---

@given(
    run_id=run_id_strategy,
    tool_name=tool_name_strategy,
    fetch_result=valid_fetch_result_strategy,
    claim=st.one_of(
        st.just(""),
        st.just("   "),
        st.just("\t\n"),
        st.text(max_size=4).filter(lambda s: len(s.strip()) < 5),
    ),
)
@settings(max_examples=200)
def test_empty_or_short_related_claim_rejected(run_id, tool_name, fetch_result, claim):
    """
    **Validates: Requirements 4.4**

    Property 8: 空白或過短的 related_claim 不增加 evidence_list 長度。
    """
    reset_stores()
    initial_length = len(evidence_list)

    with patch("storage.save_raw_payload", return_value="s3://bucket/path"):
        result = log_evidence(run_id, tool_name, claim, fetch_result)

    # 回傳 ERROR 字串
    assert result.startswith("ERROR:"), f"Expected error string, got: {result}"

    # evidence_list 長度不變
    assert len(evidence_list) == initial_length


# --- Property 9: Evidence ID 唯一性 ---

@given(
    run_id=run_id_strategy,
    tool_names=st.lists(tool_name_strategy, min_size=2, max_size=10),
    claims=st.lists(valid_claim_strategy, min_size=2, max_size=10),
    fetch_results=st.lists(valid_fetch_result_strategy, min_size=2, max_size=10),
)
@settings(max_examples=100)
def test_evidence_ids_are_unique(run_id, tool_names, claims, fetch_results):
    """
    **Validates: Requirements 4.5**

    Property 9: 同次執行中所有 evidence_id 互不相同。
    """
    reset_stores()

    # 取最小長度以對齊
    n = min(len(tool_names), len(claims), len(fetch_results))
    assume(n >= 2)

    ids = []
    with patch("storage.save_raw_payload", return_value="s3://bucket/path"):
        for i in range(n):
            eid = log_evidence(run_id, tool_names[i], claims[i], fetch_results[i])
            if not eid.startswith("ERROR:"):
                ids.append(eid)

    # 所有 evidence_id 互不相同
    assert len(ids) == len(set(ids)), f"Duplicate evidence_ids found: {ids}"


# --- Unit Tests ---

def test_log_evidence_none_claim_rejected():
    """None related_claim 被拒絕。"""
    reset_stores()
    with patch("storage.save_raw_payload", return_value="s3://bucket/path"):
        result = log_evidence("run_20260730_141530", "get_price_ohlcv", None, {
            "raw": {}, "source": "https://api.example.com", "content_reference": {}, "summary": "test"
        })
    assert result.startswith("ERROR:")
    assert len(evidence_list) == 0


def test_log_evidence_error_in_fetch_result_rejected():
    """fetch_result 含 error 欄位時不記錄證據。"""
    reset_stores()
    fetch_result = {
        "error": "API rate limit exceeded",
        "source": "https://api.example.com",
        "content_reference": {},
    }
    with patch("storage.save_raw_payload", return_value="s3://bucket/path"):
        result = log_evidence("run_20260730_141530", "get_price_ohlcv", "要驗證最近的價格走勢", fetch_result)
    assert result.startswith("ERROR:")
    assert len(evidence_list) == 0


def test_log_evidence_calls_save_raw_payload():
    """確認 storage.save_raw_payload 被正確呼叫。"""
    reset_stores()
    raw_data = {"prices": [100, 200, 300]}
    fetch_result = {
        "raw": raw_data,
        "source": "https://api.binance.com/api/v3/klines",
        "content_reference": {"pair": "BTCUSDT"},
        "summary": "BTC 日線",
    }
    with patch("storage.save_raw_payload", return_value="s3://bucket/path") as mock_save:
        eid = log_evidence("run_20260730_141530", "get_price_ohlcv", "需要近期價格資料做波動率分析", fetch_result)

    assert not eid.startswith("ERROR:")
    mock_save.assert_called_once_with("run_20260730_141530", eid, raw_data)


def test_log_evidence_successful_basic():
    """基本成功案例。"""
    reset_stores()
    fetch_result = {
        "raw": {"data": "example"},
        "source": "https://api.binance.com/api/v3/klines?symbol=SOLUSDT&interval=1d",
        "content_reference": {"pair": "SOLUSDT", "range": "2026-06-01~2026-07-30", "rows": 60},
        "summary": "SOL 日線 60 筆",
    }
    with patch("storage.save_raw_payload", return_value="s3://bucket/path"):
        eid = log_evidence("run_20260730_141530", "get_price_ohlcv", "需要最近兩個月的日線資料來計算波動率指標", fetch_result)

    assert eid.startswith("ev_")
    assert len(evidence_list) == 1
    record = evidence_list[0]
    assert record["evidence_id"] == eid
    assert record["source"] == fetch_result["source"]
    assert record["content_reference"] == fetch_result["content_reference"]
    assert record["related_claim"] == "需要最近兩個月的日線資料來計算波動率指標"
