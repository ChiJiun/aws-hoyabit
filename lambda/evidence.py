"""
evidence.py — 四欄位證據記錄

命題明文要求每筆證據需可回溯，且主辦方會抽查。這裡的設計原則是
「不讓 LLM 負責記錄」：source、fetched_at、content_reference 由程式自動產生，
LLM 唯一要提供的是 related_claim，並且列為工具的必填參數。
"""

import uuid
from datetime import datetime, timezone

import storage

# 執行期間累積證據與日誌的容器。每次執行開始時由 reset_stores() 清空。
evidence_list = []
execution_log = []

# related_claim 最小長度（強制 LLM 提供有意義的說明）
_MIN_CLAIM_LENGTH = 5


def reset_stores():
    """清空證據清單與執行紀錄，在每次新的執行開始時呼叫。

    Lambda 容器可能被重複使用，殘留上一次的資料會污染結果。
    使用 .clear() 保持同一 list 物件參照，避免其他模組持有舊參照時不同步。
    """
    global evidence_list, execution_log
    evidence_list.clear()
    execution_log.clear()


def log_evidence(run_id, tool_name, related_claim, fetch_result):
    """把一次工具呼叫的結果轉成一筆標準證據記錄，存進 evidence_list。

    驗證 related_claim 非空且長度足夠，不足則回傳錯誤不寫入。
    自動產生 evidence_id（UUID）、source、fetched_at（ISO 8601 UTC）、content_reference。
    呼叫 storage.save_raw_payload() 封存原始回應。
    回傳 evidence_id 字串。
    """
    # 驗證 related_claim 非空且長度足夠
    if not related_claim or not related_claim.strip():
        return "ERROR: related_claim 不可為空"
    if len(related_claim.strip()) < _MIN_CLAIM_LENGTH:
        return "ERROR: related_claim 長度不足，至少需要 5 個字元"

    # 工具執行失敗時不記錄證據（只有成功的工具呼叫才產生證據）
    if "error" in fetch_result:
        return "ERROR: 工具執行失敗，不記錄證據"

    # 自動產生欄位
    evidence_id = f"ev_{uuid.uuid4().hex[:8]}"
    source = fetch_result.get("source", "")
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    content_reference = fetch_result.get("content_reference", {})

    # 封存原始回應到 S3
    storage.save_raw_payload(run_id, evidence_id, fetch_result.get("raw", {}))

    # 組裝證據記錄並加入 evidence_list
    record = {
        "evidence_id": evidence_id,
        "source": source,
        "fetched_at": fetched_at,
        "content_reference": content_reference,
        "related_claim": related_claim,
    }
    evidence_list.append(record)

    return evidence_id


def log_execution_step(tool_name, status, elapsed_ms, evidence_id=None, note=None):
    """記錄一筆執行紀錄，存進 execution_log。

    無論工具呼叫成功或失敗都會記錄。一份看得到「嘗試過、失敗了、記錄了缺口」的日誌，
    比只有成功紀錄的日誌更可信。
    """
    record = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tool_name": tool_name,
        "status": status,
        "elapsed_ms": elapsed_ms,
        "evidence_id": evidence_id,
        "note": note,
    }
    execution_log.append(record)