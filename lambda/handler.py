"""
handler.py — 進入點

lambda_handler 是部署到 AWS 後的進入點；main 是本機測試用的進入點。
兩者邏輯幾乎相同，差別只在輸入來源（event 參數 vs 寫死的測試值）
與輸出位置（S3 vs 本地檔案）。
"""

import json
import sys
import os
from datetime import datetime, timezone
from pathlib import Path

import config
import agent
import evidence
import report
import export
import storage


# ---- CORS 標頭（所有回應都需要帶，否則前端跨域呼叫被瀏覽器擋下） ----
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}


def parse_request(event):
    """從 Lambda 的 event 參數取出並驗證使用者輸入。

    回傳：(symbols, question) tuple。
    驗證失敗時拋出 ValueError 附帶明確的錯誤說明。
    """
    # 取出 body（可能是字串或已解析的 dict）
    body = event.get("body", "{}")
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except json.JSONDecodeError:
            raise ValueError("請求 body 不是有效的 JSON 格式")

    # 取出 symbols
    symbols = body.get("symbols", [])
    if isinstance(symbols, str):
        symbols = [symbols]

    if not symbols:
        raise ValueError("必須提供至少一個幣種（symbols 欄位）")

    if len(symbols) > 2:
        raise ValueError(f"最多允許 2 個幣種，收到 {len(symbols)} 個：{symbols}")

    # 驗證每個幣種是否在支援清單中
    for s in symbols:
        if s.upper() not in config.SUPPORTED_SYMBOLS:
            raise ValueError(
                f"不支援的幣種：{s}。支援的幣種為：{', '.join(config.SUPPORTED_SYMBOLS)}"
            )

    # 正規化為大寫
    symbols = [s.upper() for s in symbols]

    # 取出 question
    question = body.get("question", "").strip()
    if not question:
        raise ValueError("必須提供分析題目（question 欄位）")

    return symbols, question


def generate_run_id():
    """產生本次執行的唯一識別碼。

    格式：run_YYYYMMDD_HHMMSS（UTC 時間）。
    用來歸檔 S3 路徑與關聯證據。
    """
    now = datetime.now(timezone.utc)
    return now.strftime("run_%Y%m%d_%H%M%S")


def lambda_handler(event, context):
    """AWS Lambda 的進入點，串起整條流程。

    回傳含 CORS 標頭的 JSON 回應。
    """
    # 處理 CORS preflight
    http_method = event.get("requestContext", {}).get("http", {}).get("method", "")
    if http_method == "OPTIONS":
        return {
            "statusCode": 200,
            "body": "",
        }

    try:
        # 1. 清空上一次執行的殘留資料
        evidence.reset_stores()

        # 2. 解析並驗證使用者輸入
        try:
            symbols, question = parse_request(event)
        except ValueError as e:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": str(e)}, ensure_ascii=False),
            }

        # 3. 產生本次 run_id
        run_id = generate_run_id()

        # 4. 執行 Agent 主迴圈，蒐集證據
        messages = agent.run_agent_loop(run_id, symbols, question)

        # 5. 收尾整理成三段式結構
        analysis_text = agent.summarize_final_analysis(messages)

        # 6. 交付前自我檢查
        passed, issues = export.validate_before_export(
            evidence.evidence_list, analysis_text
        )

        # 7. 渲染 Markdown 報告
        coverage_pct, got_categories, missing_categories = report.calculate_coverage(
            evidence.evidence_list
        )
        report_text = report.render_report(
            run_id, question, analysis_text,
            evidence.evidence_list, missing_sources=missing_categories
        )

        # 8. 匯出三份交付物並上傳 S3
        # 8a. 報告
        storage.save_output_file(run_id, "report.md", report_text)

        # 8b. 證據清單
        evidence_json = export.export_evidence_list(evidence.evidence_list)
        storage.save_output_file(run_id, "evidence_list.json", evidence_json)

        # 8c. 執行紀錄
        log_jsonl = export.export_execution_log(evidence.execution_log)
        storage.save_output_file(run_id, "execution_log.jsonl", log_jsonl)

        # 9. 產生下載連結
        evidence_url = storage.generate_download_link(run_id, "evidence_list.json")
        log_url = storage.generate_download_link(run_id, "execution_log.jsonl")

        # 組裝回應
        response_body = {
            "report_text": report_text,
            "evidence_download_url": evidence_url,
            "log_download_url": log_url,
            "run_id": run_id,
        }

        # 若自我檢查未全數通過，附帶警告
        if not passed:
            response_body["validation_warnings"] = issues

        return {
            "statusCode": 200,
            "body": json.dumps(response_body, ensure_ascii=False),
        }

    except Exception as e:
        # 外層兜底：捕獲所有未預期錯誤，回傳 500 + CORS
        return {
            "statusCode": 500,
            "body": json.dumps(
                {"error": f"Internal server error: {type(e).__name__}: {str(e)}"},
                ensure_ascii=False,
            ),
        }


def main():
    """本機測試專用進入點，不會部署到 Lambda。

    流程與 lambda_handler 相同，差別在於：
    - 幣種與題目直接寫死在這裡（方便反覆測試）
    - 輸出寫到本地的 outputs/ 資料夾，不上傳 S3
    """
    # 載入本機環境變數
    config.load_local_env()

    # 確保輸出目錄存在
    output_dir = Path(__file__).resolve().parent.parent / "outputs"
    output_dir.mkdir(exist_ok=True)

    # 測試案例：單一幣種多源整合
    test_event = {
        "body": json.dumps({
            "symbols": ["BTC"],
            "question": "綜合價格走勢、鏈上活躍度與市場情緒，分析 BTC 目前的市場狀態與短期可能方向。"
        })
    }

    print("=" * 60)
    print("本機測試模式")
    print(f"測試輸入：{test_event['body']}")
    print("=" * 60)

    # 1. 清空
    evidence.reset_stores()

    # 2. 解析
    try:
        symbols, question = parse_request(test_event)
    except ValueError as e:
        print(f"[ERROR] 輸入驗證失敗：{e}")
        sys.exit(1)

    # 3. run_id
    run_id = generate_run_id()
    print(f"[INFO] Run ID: {run_id}")

    # 4. Agent 主迴圈
    print("[INFO] 開始 Agent 主迴圈...")
    messages = agent.run_agent_loop(run_id, symbols, question)
    print(f"[INFO] Agent 迴圈完成，共 {len(messages)} 則訊息")

    # 5. 摘要
    print("[INFO] 產生最終分析摘要...")
    analysis_text = agent.summarize_final_analysis(messages)

    # 6. 自我檢查
    passed, issues = export.validate_before_export(
        evidence.evidence_list, analysis_text
    )
    if not passed:
        print(f"[WARN] 自我檢查未全數通過：{issues}")
    else:
        print("[INFO] 自我檢查全數通過")

    # 7. 渲染報告
    coverage_pct, got_categories, missing_categories = report.calculate_coverage(
        evidence.evidence_list
    )
    report_text = report.render_report(
        run_id, question, analysis_text,
        evidence.evidence_list, missing_sources=missing_categories
    )

    # 8. 寫入本地檔案
    report_path = output_dir / "report.md"
    report_path.write_text(report_text, encoding="utf-8")
    print(f"[INFO] 報告已寫入：{report_path}")

    evidence_json = export.export_evidence_list(evidence.evidence_list)
    evidence_path = output_dir / "evidence_list.json"
    evidence_path.write_text(evidence_json, encoding="utf-8")
    print(f"[INFO] 證據清單已寫入：{evidence_path}")

    log_jsonl = export.export_execution_log(evidence.execution_log)
    log_path = output_dir / "execution_log.jsonl"
    log_path.write_text(log_jsonl, encoding="utf-8")
    print(f"[INFO] 執行紀錄已寫入：{log_path}")

    # 9. 印出摘要
    print("\n" + "=" * 60)
    print("執行摘要")
    print(f"  證據筆數：{len(evidence.evidence_list)}")
    print(f"  執行步驟：{len(evidence.execution_log)}")
    print(f"  資料覆蓋率：{coverage_pct:.0f}%（{', '.join(got_categories)}）")
    if missing_categories:
        print(f"  缺少類別：{', '.join(missing_categories)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
