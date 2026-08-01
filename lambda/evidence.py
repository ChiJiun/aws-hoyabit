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


def reset_stores():
    """清空證據清單與執行紀錄，在每次新的執行開始時呼叫。

    需要這個是因為 Lambda 容器可能被重複使用，殘留上一次的資料會污染結果。
    使用 .clear() 而非重新賦值，確保所有已持有參照的地方都能看到清空效果。
    """
    global evidence_list, execution_log
    evidence_list.clear()
    execution_log.clear()


def log_evidence(run_id, tool_name, related_claim, fetch_result):
    # 功能：把一次工具呼叫的結果轉成一筆標準證據記錄，存進 evidence_list。
    # 檢查：related_claim 若為空或過短，直接回傳錯誤，不寫入
    #      （這是強制 LLM 說明取數目的的關卡）。
    # 自動產生的欄位：
    #   evidence_id       —— 唯一識別碼
    #   source            —— 從 fetch_result 取實際呼叫的 API 網址
    #   fetched_at        —— 目前 UTC 時間（ISO 8601）
    #   content_reference —— 從 fetch_result 取引用片段／查詢參數／指標數值
    # 由 LLM 提供的欄位：
    #   related_claim     —— 這筆資料要支持或檢驗哪個判斷
    # 同時呼叫 storage.save_raw_payload() 把原始回應封存到 S3。
    # 回傳：evidence_id 字串

    # 驗證 related_claim：空值、None、或去空白後長度 < 5 一律拒絕
    if not related_claim or len(related_claim.strip()) < 5:
        return {"error": "related_claim is empty or too short"}

    # 自動產生欄位
    evidence_id = str(uuid.uuid4())
    source = fetch_result.get("source", "unknown")
    fetched_at = datetime.now(timezone.utc).isoformat()
    content_reference = fetch_result.get("content_reference", {})

    # 組建證據記錄
    record = {
        "evidence_id": evidence_id,
        "source": source,
        "fetched_at": fetched_at,
        "content_reference": content_reference,
        "related_claim": related_claim,
    }

    # 封存原始回應到 S3
    storage.save_raw_payload(run_id, evidence_id, fetch_result.get("raw", {}))

    # 新增至全域證據清單
    evidence_list.append(record)

    return evidence_id


def log_execution_step(tool_name, status, elapsed_ms, evidence_id=None, note=None):
    """記錄一筆執行紀錄，存進 execution_log。

    無論工具呼叫成功或失敗都會記錄。一份看得到「嘗試過、失敗了、記錄了缺口」
    的日誌，比只有成功紀錄的日誌更可信。

    Args:
        tool_name: 呼叫的工具名稱（如 "get_price_ohlcv"）
        status: 執行狀態（如 "success" 或 "error"）
        elapsed_ms: 執行耗時（毫秒）
        evidence_id: 對應的證據 ID（失敗時可為 None）
        note: 備註說明（可為 None）
    """
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tool_name": tool_name,
        "status": status,
        "elapsed_ms": elapsed_ms,
        "evidence_id": evidence_id,
        "note": note,
    }
    execution_log.append(record)