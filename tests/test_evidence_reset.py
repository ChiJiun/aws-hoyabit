"""
Property 4: 容器重複使用不汙染
— 呼叫 reset_stores() 後 evidence_list 與 execution_log 必為空列表。

Validates: Requirements 2.6
"""

import sys
import os

# 確保 lambda 目錄在搜尋路徑中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lambda'))

from hypothesis import given, settings
from hypothesis import strategies as st

from evidence import evidence_list, execution_log, reset_stores


# 策略：產生任意長度的 evidence_list 內容（模擬前次執行殘留）
evidence_entry_strategy = st.fixed_dictionaries({
    "evidence_id": st.text(min_size=1, max_size=36),
    "source": st.text(min_size=1, max_size=100),
    "fetched_at": st.text(min_size=1, max_size=30),
    "content_reference": st.text(min_size=0, max_size=200),
    "related_claim": st.text(min_size=1, max_size=200),
})

execution_log_entry_strategy = st.fixed_dictionaries({
    "timestamp": st.text(min_size=1, max_size=30),
    "tool_name": st.text(min_size=1, max_size=50),
    "status": st.sampled_from(["success", "failure", "timeout"]),
    "elapsed_ms": st.integers(min_value=0, max_value=60000),
})


@given(
    residual_evidence=st.lists(evidence_entry_strategy, min_size=0, max_size=20),
    residual_log=st.lists(execution_log_entry_strategy, min_size=0, max_size=20),
)
@settings(max_examples=200)
def test_reset_stores_clears_all_residual_data(residual_evidence, residual_log):
    """
    **Validates: Requirements 2.6**

    Property 4: 無論 evidence_list 與 execution_log 含有多少前次殘留資料，
    呼叫 reset_stores() 後兩者必定為空列表。
    """
    # Arrange: 模擬容器重複使用，填入殘留資料
    evidence_list.clear()
    execution_log.clear()
    evidence_list.extend(residual_evidence)
    execution_log.extend(residual_log)

    # Act
    reset_stores()

    # Assert: 兩個容器必須為空
    assert evidence_list == [], f"evidence_list should be empty, got {len(evidence_list)} items"
    assert execution_log == [], f"execution_log should be empty, got {len(execution_log)} items"


def test_reset_stores_preserves_list_identity():
    """reset_stores 使用 .clear() 而非重新賦值，確保同一物件參照。"""
    # 取得原始物件 id
    ev_id_before = id(evidence_list)
    log_id_before = id(execution_log)

    evidence_list.append({"dummy": "data"})
    execution_log.append({"dummy": "log"})

    reset_stores()

    # 物件參照不變（其他模組持有的參照仍有效）
    assert id(evidence_list) == ev_id_before
    assert id(execution_log) == log_id_before
    assert evidence_list == []
    assert execution_log == []
