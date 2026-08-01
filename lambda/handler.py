"""
handler.py — 進入點

lambda_handler 是部署到 AWS 後的進入點；main 是本機測試用的進入點。
兩者邏輯幾乎相同，差別只在輸入來源（event 參數 vs 寫死的測試值）
與輸出位置（S3 vs 本地檔案）。

介面契約（不可更動）：
  請求：{"symbols": ["BTC"] 或 ["BTC","ETH"], "question": "..."}
  回應：{"report_text": "...", "evidence_download_url": "...",
         "log_download_url": "...", "run_id": "..."}
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


# ---- CORS 標頭 ----
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
    body = event.get("body", "{}")
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except json.JSONDecodeError:
            raise ValueError("請求 body 不是有效的 JSON 格式")

    symbols = body.get("symbols", [])
    if isinstance(symbols, str):
        symbols = [symbols]

    if not symbols:
        raise ValueError("必須提供至少一個幣種（symbols 欄位）")

    if len(symbols) > 2:
        raise ValueError(f"最多允許 2 個幣種，收到 {len(symbols)} 個：{symbols}")

    for s in symbols:
        if s.upper() not in config.SUPPORTED_SYMBOLS:
            raise ValueError(
                f"不支援的幣種：{s}。支援的幣種為：{', '.join(config.SUPPORTED_SYMBOLS)}"
            )

    symbols = [s.upper() for s in symbols]

    question = body.get("question", "").strip()
    if not question:
        raise ValueError("必須提供分析題目（question 欄位）")

    return symbols, question


def generate_run_id():
    """產生本次執行的唯一識別碼。格式：run_YYYYMMDD_HHMMSS（UTC）。"""
    now = datetime.now(timezone.utc)
    return now.strftime("run_%Y%m%d_%H%M%S")


def lambda_handler(event, context):
    """AWS Lambda 的進入點。回傳含 CORS 標頭的 JSON 回應。"""
    # 處理 CORS preflight
    http_method = event.get("requestContext", {}).get("http", {}).get("method", "")
    if http_method == "OPTIONS":
        return {"statusCode": 200, "body": ""}

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

        # 4. 執行多階段 Agent 流程（回傳 ReportModel dict）
        report_model = agent.run_agent_loop(run_id, symbols, question)

        # 5. 交付前自我檢查（使用 ReportModel 的文字內容）
        report_text_for_check = json.dumps(report_model, ensure_ascii=False)
        passed, issues = export.validate_before_export(
            evidence.evidence_list, report_text_for_check
        )

        # 6. 用決定性 Renderer 渲染 Markdown 報告
        coverage_pct, got_categories, missing_categories = report.calculate_coverage(
            evidence.evidence_list
        )
        report_text = report.render_report(
            run_id, question, report_model,
            evidence.evidence_list, missing_sources=missing_categories
        )

        # 7. 匯出三份交付物並上傳 S3
        storage.save_output_file(run_id, "report.md", report_text)

        evidence_json = export.export_evidence_list(evidence.evidence_list)
        storage.save_output_file(run_id, "evidence_list.json", evidence_json)

        log_jsonl = export.export_execution_log(evidence.execution_log)
        storage.save_output_file(run_id, "execution_log.jsonl", log_jsonl)

        # 8. 產生下載連結
        evidence_url = storage.generate_download_link(run_id, "evidence_list.json")
        log_url = storage.generate_download_link(run_id, "execution_log.jsonl")

        # 9. 組裝回應（維持前端契約不變）
        response_body = {
            "report_text": report_text,
            "evidence_download_url": evidence_url,
            "log_download_url": log_url,
            "run_id": run_id,
        }

        if not passed:
            response_body["validation_warnings"] = issues

        return {
            "statusCode": 200,
            "body": json.dumps(response_body, ensure_ascii=False),
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps(
                {"error": f"Internal server error: {type(e).__name__}: {str(e)}"},
                ensure_ascii=False,
            ),
        }


def main():
    """本機測試專用進入點。流程與 lambda_handler 相同，輸出寫到本地。"""
    # 載入本機環境變數
    config.load_local_env()

    # 確保輸出目錄存在
    output_dir = Path(__file__).resolve().parent.parent / "outputs"
    output_dir.mkdir(exist_ok=True)

    # 測試案例
    test_event = {
        "body": json.dumps({
            "symbols": ["BTC"],
            "question": "綜合價格走勢、鏈上活躍度與市場情緒，分析 BTC 目前的市場狀態與短期可能方向。"
        })
    }

    print("=" * 60)
    print("本機測試模式（多階段架構）")
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

    # 4. 多階段 Agent 流程
    print("[INFO] 開始多階段 Agent 流程...")
    print(f"  [Planner] 分析題目...")
    report_model = agent.run_agent_loop(run_id, symbols, question)
    print(f"[INFO] Agent 流程完成，共 {len(evidence.evidence_list)} 筆證據")

    # 5. 自我檢查
    report_text_for_check = json.dumps(report_model, ensure_ascii=False)
    passed, issues = export.validate_before_export(
        evidence.evidence_list, report_text_for_check
    )
    if not passed:
        print(f"[WARN] 自我檢查未全數通過：{issues}")
    else:
        print("[INFO] 自我檢查全數通過")

    # 6. 渲染報告
    coverage_pct, got_categories, missing_categories = report.calculate_coverage(
        evidence.evidence_list
    )
    report_text = report.render_report(
        run_id, question, report_model,
        evidence.evidence_list, missing_sources=missing_categories
    )

    # 7. 寫入本地檔案（含 run_id 子目錄）
    run_dir = output_dir / run_id
    run_dir.mkdir(exist_ok=True)

    report_path = run_dir / "report.md"
    report_path.write_text(report_text, encoding="utf-8")
    print(f"[INFO] 報告已寫入：{report_path}")

    evidence_json = export.export_evidence_list(evidence.evidence_list)
    evidence_path = run_dir / "evidence_list.json"
    evidence_path.write_text(evidence_json, encoding="utf-8")
    print(f"[INFO] 證據清單已寫入：{evidence_path}")

    log_jsonl = export.export_execution_log(evidence.execution_log)
    log_path = run_dir / "execution_log.jsonl"
    log_path.write_text(log_jsonl, encoding="utf-8")
    print(f"[INFO] 執行紀錄已寫入：{log_path}")

    # 8. 同時寫到 outputs/ 根目錄（相容舊測試）
    (output_dir / "report.md").write_text(report_text, encoding="utf-8")
    (output_dir / "evidence_list.json").write_text(evidence_json, encoding="utf-8")
    (output_dir / "execution_log.jsonl").write_text(log_jsonl, encoding="utf-8")

    # 9. 印出摘要
    print("\n" + "=" * 60)
    print("執行摘要")
    print(f"  證據筆數：{len(evidence.evidence_list)}")
    print(f"  執行步驟：{len(evidence.execution_log)}")
    print(f"  資料覆蓋率：{coverage_pct:.0f}%（{', '.join(got_categories)}）")
    if missing_categories:
        print(f"  缺少類別：{', '.join(missing_categories)}")
    print(f"  市場狀態：{report_model.get('market_state', {}).get('regime', 'N/A')}")
    print(f"  信心程度：{report_model.get('market_state', {}).get('confidence', 'N/A')}")
    print("=" * 60)

    # 10. 印出 handler 回傳格式（供驗證前端契約）
    response_body = {
        "report_text": report_text,
        "evidence_download_url": "(local mode - no S3)",
        "log_download_url": "(local mode - no S3)",
        "run_id": run_id,
    }
    print("\n[DEBUG] Handler response JSON (前端契約格式):")
    print(json.dumps(response_body, ensure_ascii=False, indent=2)[:500] + "...")


if __name__ == "__main__":
    main()
