"""
export.py — 交付物匯出

把執行期間累積的證據與日誌，轉成命題要求的檔案格式。
"""


def export_evidence_list(evidence_list, as_csv=False):
    # 功能：把證據清單轉成可繳交的檔案內容。
    # 格式：預設 JSON（每筆含 source、fetched_at、content_reference、related_claim）；
    #      as_csv=True 時輸出 CSV 格式。
    # 回傳：字串（可直接交給 storage.save_output_file 上傳）
    pass


def export_execution_log(execution_log):
    # 功能：把執行紀錄轉成 JSONL 格式（每行一筆 JSON）。
    # 內容：時間戳記、工具呼叫、資料取得紀錄、分析流程摘要。
    # 回傳：字串
    pass


def validate_before_export(evidence_list, analysis_text):
    # 功能：交付前的自我檢查，把命題的評分觀察點寫成程式化驗證。
    # 檢查項目：
    #   1. 每筆證據的四個必填欄位是否齊備
    #   2. 資料來源類別數是否 >= 3（命題會看「來源類型是否多樣」）
    #   3. 是否有付費來源被當成唯一依據
    #   4. 報告中是否出現投資建議語句（買進／賣出／目標價）
    # 回傳：(是否全數通過, 未通過項目的清單)
    #      未通過不阻止輸出，而是把警示寫進報告的限制段落。
    pass