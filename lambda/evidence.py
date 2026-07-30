"""
evidence.py — 四欄位證據記錄

命題明文要求每筆證據需可回溯，且主辦方會抽查。這裡的設計原則是
「不讓 LLM 負責記錄」：source、fetched_at、content_reference 由程式自動產生，
LLM 唯一要提供的是 related_claim，並且列為工具的必填參數。
"""

# 執行期間累積證據與日誌的容器。每次執行開始時由 reset_stores() 清空。
evidence_list = []
execution_log = []


def reset_stores():
    # 功能：清空證據清單與執行紀錄，在每次新的執行開始時呼叫。
    # 需要這個是因為 Lambda 容器可能被重複使用，殘留上一次的資料會污染結果。
    pass


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
    pass


def log_execution_step(tool_name, status, elapsed_ms, evidence_id=None, note=None):
    # 功能：記錄一筆執行紀錄，存進 execution_log。
    # 欄位：時間戳記、步驟名稱、工具名稱、執行狀態、耗時、對應的 evidence_id、備註。
    # 注意：失敗的呼叫也要記錄。一份看得到「嘗試過、失敗了、記錄了缺口」的日誌，
    #      比只有成功紀錄的日誌更可信。
    pass