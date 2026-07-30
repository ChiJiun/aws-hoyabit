"""
report.py — 報告渲染

把模型的分析內容套進固定的 Markdown 模板。渲染由程式負責、不交給模型，
這樣可以保證命題要求的三個章節一定存在。
"""


def render_report(run_id, question, analysis_text, evidence_list, missing_sources=None):
    # 功能：產出最終的 Markdown 分析報告。
    # 模板結構（對應命題「分析報告至少需包含」的三項要求）：
    #   1. 結論／市場判斷
    #   2. 關鍵依據        —— 每條附對應的 evidence_id，說明該證據如何支撐判斷
    #   3. 信心說明        —— 判斷信心、已知限制、資料不足之處、可能推翻結論的條件
    #   附錄：資料覆蓋率   —— 成功取得的資料類別 ÷ 原本計畫的資料類別
    #   附錄：完整證據清單
    # 參數 missing_sources：本次執行未能取得的資料類別，會寫進限制段落。
    # 實作：用 f-string 拼接字串即可，不需要額外的模板套件。
    # 回傳：完整的 Markdown 字串
    pass


def build_evidence_table(evidence_list):
    # 功能：把證據清單轉成 Markdown 表格，附加在報告附錄。
    # 欄位：evidence_id、來源、取得時間、對應判斷。
    # 回傳：Markdown 表格字串
    pass


def calculate_coverage(evidence_list):
    # 功能：計算資料覆蓋率，作為報告中信心等級的客觀依據。
    # 實作：統計 evidence_list 中出現了幾種不同的資料類別
    #      （價格、新聞、鏈上、情緒、總經），除以預期的類別總數。
    # 回傳：(覆蓋率百分比, 已取得的類別清單, 缺少的類別清單)
    pass