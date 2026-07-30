"""
handler.py — 進入點

lambda_handler 是部署到 AWS 後的進入點；main 是本機測試用的進入點。
兩者邏輯幾乎相同，差別只在輸入來源（event 參數 vs 寫死的測試值）
與輸出位置（S3 vs 本地檔案）。
"""

import agent
import evidence
import report
import export
import storage


def parse_request(event):
    # 功能：從 Lambda 的 event 參數取出使用者輸入。
    # 取出：symbols（1 或 2 個幣種，比較分析題型會有 2 個）、question（題目全文）
    # 驗證：幣種是否在 SUPPORTED_SYMBOLS 內；question 是否非空。
    # 回傳：(symbols, question)，驗證失敗則拋出錯誤
    pass


def generate_run_id():
    # 功能：產生本次執行的唯一識別碼，用來歸檔 S3 路徑與關聯證據。
    # 實作：用 UTC 時間戳記組成，例如 run_20260730_141530。
    # 回傳：run_id 字串
    pass


def lambda_handler(event, context):
    # 功能：AWS Lambda 的進入點，串起整條流程。
    # 流程：
    #   1. evidence.reset_stores()        清空上一次執行的殘留資料
    #   2. parse_request(event)           取出並驗證使用者輸入
    #   3. generate_run_id()              產生本次 run_id
    #   4. agent.run_agent_loop()         執行 Agent 主迴圈，蒐集證據
    #   5. agent.summarize_final_analysis()  收尾整理成三段式結構
    #   6. export.validate_before_export()   交付前自我檢查
    #   7. report.render_report()         渲染 Markdown 報告
    #   8. export_* + storage.save_output_file()  三份交付物上傳 S3
    #   9. storage.generate_download_link()      產生下載連結
    # 回傳給前端的內容：
    #   {
    #     "report_text": 報告 Markdown 原文（前端直接顯示，不需下載）,
    #     "evidence_download_url": 證據清單的 presigned URL,
    #     "log_download_url": 執行紀錄的 presigned URL,
    #     "run_id": run_id
    #   }
    # 注意：需回傳 CORS 標頭，否則前端跨網域呼叫會被瀏覽器擋下。
    pass


def main():
    # 功能：本機測試專用進入點，不會部署到 Lambda。
    # 流程與 lambda_handler 相同，差別在於：
    #   - 幣種與題目直接寫死在這裡（方便反覆測試）
    #   - 輸出寫到本地的 outputs/ 資料夾，不上傳 S3
    # 建議在此把五個幣種與三種題型都各測一次，特別是比較分析
    #   （需傳入兩個幣種，輸入形狀與其他題型不同，容易漏測）。
    pass


if __name__ == "__main__":
    main()