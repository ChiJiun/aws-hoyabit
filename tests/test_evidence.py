"""
test_evidence.py — evidence.py 屬性測試 (Property-Based Testing)

使用 Hypothesis 框架驗證 evidence.py 的核心正確性屬性。
驗證: 需求 2.6、4.1、4.2、4.4、4.5、5.1、5.2
"""

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambda"))

from hypothesis import given, settings, assume
from hypothesis import strategies as st

import evidence


# ─── Strategies ───────────────────────────────────────────────────────────────

# 有效的 related_claim：去空白後長度 >= 5
valid_related_claim = st.text(min_size=5, max_size=200).filter(
    lambda s: len(s.strip()) >= 5
)

# 無效的 related_claim：空字串、純空白、或去空白後長度 < 5
invalid_related_claim = st.one_of(
    st.just(""),
    st.text(alphabet=" \t\n\r", min_size=0, max_size=50),
    st.text(min_size=1, max_size=10).filter(lambda s: len(s.strip()) < 5),
)

# fetch_result 策略
fetch_result_strategy = st.fixed_dictionaries({
    "source": st.text(min_size=1, max_size=100),
    "content_reference": st.fixed_dictionaries({
        "key": st.text(min_size=1, max_size=50),
    }),
    "raw": st.fixed_dictionaries({
        "data": st.text(min_size=0, max_size=100),
    }),
})

# 工具名稱策略
tool_name_strategy = st.sampled_from([
    "get_price_ohlcv", "search_news", "get_onchain",
    "compute_quant", "get_sentiment", "get_macro",
])

# 執行狀態策略
status_strategy = st.sampled_from(["success", "error"])

# elapsed_ms 策略
elapsed_ms_strategy = st.integers(min_value=0, max_value=30000)

# run_id 策略
run_id_strategy = st.from_regex(r"run_[0-9]{8}_[0-9]{6}", fullmatch=True)


# ─── Property 4: 容器重複使用不汙染 ─────────────────────────────────────────
# Validates: Requirements 2.6

@given(
    n_evidence=st.integers(min_value=0, max_value=20),
    n_logs=st.integers(min_value=0, max_value=20),
)
@settings(max_examples=100)
def test_property_4_reset_stores_clears_all(n_evidence, n_logs):
    """Property 4: reset_stores 後 evidence_list 與 execution_log 為空。

    For any initial state of evidence_list and execution_log (containing
    leftover data from previous run), after calling reset_stores(), both
    must be empty lists.

    **Validates: Requirements 2.6**
    """
    # 模擬殘留資料
    evidence.evidence_list.clear()
    evidence.execution_log.clear()

    for i in range(n_evidence):
        evidence.evidence_list.append({"evidence_id": f"fake_{i}"})
    for i in range(n_logs):
        evidence.execution_log.append({"tool_name": f"tool_{i}"})

    # 呼叫 reset_stores
    evidence.reset_stores()

    # 驗證清空
    assert evidence.evidence_list == []
    assert evidence.execution_log == []
    assert len(evidence.evidence_list) == 0
    assert len(evidence.execution_log) == 0


# ─── Property 7: 證據記錄欄位完整性 ──────────────────────────────────────────
# Validates: Requirements 4.1, 4.2

@given(
    run_id=run_id_strategy,
    tool_name=tool_name_strategy,
    related_claim=valid_related_claim,
    fetch_result=fetch_result_strategy,
)
@settings(max_examples=100)
@patch("storage.save_raw_payload")
def test_property_7_evidence_record_fields(mock_save, run_id, tool_name, related_claim, fetch_result):
    """Property 7: log_evidence 產生的記錄包含正確五欄位。

    For any successful tool execution result, log_evidence() produces a record
    containing exactly these five fields: evidence_id, source, fetched_at,
    content_reference, related_claim. source and fetched_at are auto-generated.

    **Validates: Requirements 4.1, 4.2**
    """
    evidence.reset_stores()

    result = evidence.log_evidence(run_id, tool_name, related_claim, fetch_result)

    # 確認回傳的是 evidence_id 字串（非錯誤 dict）
    assert isinstance(result, str)
    assert len(result) > 0

    # 取得剛記錄的證據
    assert len(evidence.evidence_list) == 1
    record = evidence.evidence_list[0]

    # 驗證命題五個必要欄位與 C1 追溯欄位存在
    expected_fields = {"evidence_id", "source", "fetched_at", "content_reference", "related_claim"}
    assert expected_fields <= set(record.keys())
    assert {
        "schema_version", "tool_name", "data_quality", "anomaly_flags",
        "raw_payload_path", "raw_payload_sha256", "archive_status",
    } <= set(record.keys())

    # 驗證 evidence_id 與回傳值一致
    assert record["evidence_id"] == result

    # 驗證 source 來自 fetch_result（自動產生，非 LLM 提供）
    assert record["source"] == fetch_result.get("source", "unknown")

    # 驗證 fetched_at 是 ISO 8601 格式的時間字串（自動產生）
    assert "T" in record["fetched_at"]
    assert record["fetched_at"].endswith("+00:00") or record["fetched_at"].endswith("Z")

    # 驗證 related_claim 正確傳入
    assert record["related_claim"] == related_claim


# ─── Property 8: 空 related_claim 被拒絕 ─────────────────────────────────────
# Validates: Requirements 4.4

@given(
    run_id=run_id_strategy,
    tool_name=tool_name_strategy,
    related_claim=invalid_related_claim,
    fetch_result=fetch_result_strategy,
)
@settings(max_examples=100)
@patch("storage.save_raw_payload")
def test_property_8_empty_claim_rejected(mock_save, run_id, tool_name, related_claim, fetch_result):
    """Property 8: 空白 related_claim 不增加 evidence_list 長度。

    For any empty string or whitespace-only related_claim (or string with
    stripped length < 5), log_evidence() must reject it and evidence_list
    length must not increase.

    **Validates: Requirements 4.4**
    """
    evidence.reset_stores()

    length_before = len(evidence.evidence_list)
    result = evidence.log_evidence(run_id, tool_name, related_claim, fetch_result)

    # 確認回傳錯誤 dict
    assert isinstance(result, dict)
    assert "error" in result

    # 確認 evidence_list 長度沒有增加
    assert len(evidence.evidence_list) == length_before

    # 確認 storage.save_raw_payload 沒有被呼叫
    mock_save.assert_not_called()


# ─── Property 9: Evidence ID 唯一性 ──────────────────────────────────────────
# Validates: Requirements 4.5

@given(
    run_id=run_id_strategy,
    tool_names=st.lists(tool_name_strategy, min_size=2, max_size=20),
    related_claims=st.lists(valid_related_claim, min_size=2, max_size=20),
    fetch_results=st.lists(fetch_result_strategy, min_size=2, max_size=20),
)
@settings(max_examples=100)
@patch("storage.save_raw_payload")
def test_property_9_evidence_id_unique(mock_save, run_id, tool_names, related_claims, fetch_results):
    """Property 9: 同次執行中所有 evidence_id 互不相同。

    For any sequence of multiple log_evidence calls in the same execution,
    all evidence_ids must be unique.

    **Validates: Requirements 4.5**
    """
    evidence.reset_stores()

    # 取最小長度確保對齊
    n = min(len(tool_names), len(related_claims), len(fetch_results))
    assume(n >= 2)

    evidence_ids = []
    for i in range(n):
        eid = evidence.log_evidence(run_id, tool_names[i], related_claims[i], fetch_results[i])
        assert isinstance(eid, str)
        evidence_ids.append(eid)

    # 所有 evidence_id 互不相同
    assert len(evidence_ids) == len(set(evidence_ids))


# ─── Property 10: 執行紀錄完整性 ─────────────────────────────────────────────
# Validates: Requirements 5.1, 5.2

@given(
    tool_name=tool_name_strategy,
    status=status_strategy,
    elapsed_ms=elapsed_ms_strategy,
    evidence_id=st.one_of(st.none(), st.uuids().map(str)),
    note=st.one_of(st.none(), st.text(min_size=0, max_size=100)),
)
@settings(max_examples=100)
def test_property_10_execution_log_completeness(tool_name, status, elapsed_ms, evidence_id, note):
    """Property 10: log_execution_step 新增一筆包含必要欄位的記錄。

    For any Data Tool execution (success or failure), log_execution_step()
    adds one record to execution_log containing timestamp, tool_name,
    status, elapsed_ms fields.

    **Validates: Requirements 5.1, 5.2**
    """
    evidence.reset_stores()

    length_before = len(evidence.execution_log)
    evidence.log_execution_step(tool_name, status, elapsed_ms, evidence_id=evidence_id, note=note)

    # 確認新增了一筆
    assert len(evidence.execution_log) == length_before + 1

    record = evidence.execution_log[-1]

    # 驗證必要欄位存在
    assert "timestamp" in record
    assert "tool_name" in record
    assert "status" in record
    assert "elapsed_ms" in record

    # 驗證欄位值正確
    assert record["tool_name"] == tool_name
    assert record["status"] == status
    assert record["elapsed_ms"] == elapsed_ms

    # 驗證 timestamp 是 ISO 8601 格式
    assert "T" in record["timestamp"]

    # 驗證可選欄位
    assert record["evidence_id"] == evidence_id
    assert record["note"] == note
