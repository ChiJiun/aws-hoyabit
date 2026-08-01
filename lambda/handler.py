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


def _normalize_execution_status(status):
    # 功能：將 execution log 的失敗狀態正規化，供穩定去重與報告顯示。
    normalized = str(status or "").strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in ("failed", "failure"):
        return "error"
    if normalized == "maxturns":
        return "max_turns"
    return normalized


def _normalize_execution_reason(reason):
    # 功能：移除原因文字多餘空白，避免同一失敗因格式差異重複出現。
    return " ".join(str(reason or "未提供原因").split()) or "未提供原因"


def build_report_metadata(analysis_text, evidence_list, execution_log):
    # 功能：從實際引用證據與 execution log 建立報告 metadata。
    # 步驟：解析有效引用、映射成功工具，並分離資料失敗與 Agent 執行限制。
    # 回傳：可透過 C4 coverage 相容參數傳入 report.py 的 dict。
    evidence_list = evidence_list if isinstance(evidence_list, list) else []
    execution_log = execution_log if isinstance(execution_log, list) else []
    analyzed_ids = report.extract_cited_evidence_ids(analysis_text, evidence_list)
    existing_ids = {
        str(record.get("evidence_id"))
        for record in evidence_list
        if isinstance(record, dict) and record.get("evidence_id")
    }

    evidence_capabilities = {}
    attempted_capabilities = []
    execution_limitations = []
    seen_failures = set()
    seen_limitations = set()
    failed_dimensions = set()
    for step in execution_log:
        if not isinstance(step, dict):
            continue
        tool_name = str(step.get("tool_name") or "").strip()
        status = _normalize_execution_status(step.get("status"))
        reason = _normalize_execution_reason(step.get("note"))
        evidence_id = str(step.get("evidence_id") or "").strip()
        if status == "success" and evidence_id in existing_ids and tool_name:
            evidence_capabilities[evidence_id] = tool_name
            continue

        dedup_key = (tool_name.lower(), status, reason)
        if tool_name == "agent_loop" and status in {"timeout", "max_turns", "error"}:
            if dedup_key not in seen_limitations:
                seen_limitations.add(dedup_key)
                execution_limitations.append({
                    "source": "agent_loop",
                    "status": status,
                    "reason": reason,
                })
            continue

        if tool_name not in report.TOOL_DIMENSIONS or status not in report.FAILED_STATUSES:
            continue
        if dedup_key in seen_failures:
            continue
        seen_failures.add(dedup_key)
        attempted_capabilities.append({
            "capability_id": tool_name,
            "status": status,
            "reason": reason,
        })
        failed_dimensions.add(report.TOOL_DIMENSIONS[tool_name])

    relevant_omissions = []
    omission_markers = ("省略", "未取得", "無法取得", "資料不足", "缺少")
    for raw_line in str(analysis_text or "").splitlines():
        line = raw_line.strip(" -*#\t")
        if not line or not any(marker in line for marker in omission_markers):
            continue
        for dimension in report.ANALYSIS_DIMENSIONS:
            if dimension in line and dimension not in failed_dimensions:
                relevant_omissions.append({
                    "dimension": dimension,
                    "reason": line,
                    "confidence_impact": "限制該維度對結論的交叉驗證能力",
                })
                break

    metadata = {
        "analyzed_evidence_ids": analyzed_ids,
        "evidence_capabilities": evidence_capabilities,
        "attempted_capabilities": attempted_capabilities,
        "relevant_omissions": relevant_omissions,
    }
    if execution_limitations:
        metadata["execution_limitations"] = execution_limitations
    return metadata


def build_report_quality_warnings(summary):
    # 功能：檢查報告是否具備最低可用引用與實際多維分析，不產生固定分母顯示。
    warnings = []
    if summary.get("cited_evidence_count", 0) == 0:
        warnings.append("報告未引用任何有效證據（cited_evidence_count == 0）")
    dimension_count = len(summary.get("analyzed_dimensions", []))
    if dimension_count < 2:
        warnings.append(f"報告實際分析維度不足：{dimension_count} 個，至少需要 2 個")
    return warnings


def lambda_handler(event, context):
    """AWS Lambda 的進入點，串起整條流程。

    回傳含 CORS 標頭的 JSON 回應。
    """
    # 處理 CORS preflight
    http_method = event.get("requestContext", {}).get("http", {}).get("method", "")
    if http_method == "OPTIONS":
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
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
                "headers": CORS_HEADERS,
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

        # 7. 由實際引用與執行紀錄建立 metadata，再渲染 Markdown 報告
        report_metadata = build_report_metadata(
            analysis_text, evidence.evidence_list, evidence.execution_log
        )
        report_summary = report.build_analysis_summary(
            evidence.evidence_list, report_metadata
        )
        validation_warnings = list(issues)
        validation_warnings.extend(build_report_quality_warnings(report_summary))
        validation_warnings = list(dict.fromkeys(validation_warnings))
        report_text = report.render_report(
            run_id, question, analysis_text,
            evidence.evidence_list, coverage=report_metadata
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

        # 若匯出或報告品質檢查未通過，沿用既有警告欄位但維持 200 與 C5 必要欄位
        if validation_warnings:
            response_body["validation_warnings"] = validation_warnings

        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps(response_body, ensure_ascii=False),
        }

    except Exception as e:
        # 外層兜底：捕獲所有未預期錯誤，回傳 500 + CORS
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
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

    # 7. 由實際引用與執行紀錄建立 metadata，再渲染報告
    report_metadata = build_report_metadata(
        analysis_text, evidence.evidence_list, evidence.execution_log
    )
    report_summary = report.build_analysis_summary(
        evidence.evidence_list, report_metadata
    )
    report_text = report.render_report(
        run_id, question, analysis_text,
        evidence.evidence_list, coverage=report_metadata
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
    print(f"  蒐集證據筆數：{len(evidence.evidence_list)}")
    print(f"  引用證據筆數：{report_summary['cited_evidence_count']}")
    print(f"  執行步驟：{len(evidence.execution_log)}")
    dimensions = report_summary["analyzed_dimensions"]
    print(f"  實際分析維度：{', '.join(dimensions) if dimensions else '無有效引用'}")
    print(f"  獨立來源數：{report_summary['independent_source_count']}")
    failures = report_summary["failed_attempts"]
    if failures:
        failure_text = "; ".join(
            f"{item.get('dimension') or item.get('capability_id')} ({item.get('status')}: {item.get('reason')})"
            for item in failures
        )
        print(f"  失敗嘗試：{failure_text}")
    print("=" * 60)


if __name__ == "__main__":
    main()
