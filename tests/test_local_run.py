"""
test_local_run.py — 本機整合測試

目的：在部署到 AWS 之前，先在本機把整條「輸入 → Agent 迴圈 → 報告產出」
的流程跑過一輪，確認邏輯正確。

執行方式：在專案根目錄下跑
    python -m tests.test_local_run

注意：需要設定環境變數（BEDROCK_MODEL_ID 等）或 .env 才能真的呼叫 Bedrock。
若只想驗證流程框架（不實際呼叫外部 API），可搭配 mock 使用。
"""

import sys
import os
import time
import json
import re
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambda"))

import config  # noqa: E402
import handler  # noqa: E402
import evidence  # noqa: E402
import export  # noqa: E402
import report  # noqa: E402


# 命題的三種範例題型，對應到不同的輸入形狀
TEST_CASES = [
    {
        "name": "多源整合－單幣種",
        "symbols": ["SOL"],
        "question": "分析 SOL 過去兩週的市場表現，整合價格走勢、鏈上活躍度、"
                    "主要新聞事件與社群討論熱度，給出整體市場狀態判斷，"
                    "並說明各類資料之間的一致程度。",
    },
    {
        "name": "假設驗證－單幣種",
        "symbols": ["BTC"],
        "question": "市場上有聲音認為 BTC 短期內將維持盤整、缺乏明確方向，"
                    "請蒐集支持與反對此觀點的證據，並說明你最終的判斷與理由。",
    },
    {
        "name": "比較分析－雙幣種",
        "symbols": ["ETH", "SOL"],
        "question": "比較 ETH 與 SOL 在當前宏觀環境下各自的市場位置與風險特徵，"
                    "說明兩者在流動性、市場關注度或風險敞口上的主要差異，"
                    "以及在什麼條件下各自更值得優先關注。",
    },
]


_FIXED_SCORE_PATTERN = re.compile(
    r"(?:資料覆蓋率|覆蓋率|涵蓋率|維度分數|維度得分|coverage(?:\s+score)?|dimension\s+score)"
    r"[^\n\d]{0,20}\d+(?:\.\d+)?\s*(?:/\s*\d+|%)",
    re.IGNORECASE,
)


def find_fixed_score_issues(report_text):
    """只攔截具覆蓋／分數語境的固定比率，不誤判日期、市場比率、URL 或一般百分比。"""
    return [
        f"報告仍含固定覆蓋或分數輸出：{match.group(0)}"
        for match in _FIXED_SCORE_PATTERN.finditer(str(report_text or ""))
    ]


def run_single_case(case):
    """執行單一測試案例，呼叫 handler 內部邏輯並檢查結果。

    檢查項目：
      1. 是否有拋出未處理的例外
      2. report_text 是否非空
      3. evidence_list 涵蓋的來源類別數 >= 3
      4. 報告中無投資建議語句
      5. 整體耗時是否在 TIME_BUDGET_SECONDS 之內

    回傳：dict 包含 name、passed、elapsed_s、evidence_count、
          analyzed_dimensions、cited_evidence_count、
          independent_source_count、failed_attempts、issues
    """
    result = {
        "name": case["name"],
        "passed": False,
        "elapsed_s": 0,
        "evidence_count": 0,
        "analyzed_dimensions": [],
        "cited_evidence_count": 0,
        "independent_source_count": 0,
        "failed_attempts": [],
        "issues": [],
    }

    start = time.time()

    try:
        # 模擬 Lambda event
        test_event = {
            "body": json.dumps({
                "symbols": case["symbols"],
                "question": case["question"],
            })
        }

        # 呼叫 lambda_handler
        response = handler.lambda_handler(test_event, None)
        elapsed = time.time() - start
        result["elapsed_s"] = round(elapsed, 1)

        # 檢查 HTTP 狀態碼
        status_code = response.get("statusCode", 0)
        if status_code != 200:
            body = json.loads(response.get("body", "{}"))
            result["issues"].append(f"HTTP {status_code}: {body.get('error', 'unknown')}")
            return result

        # 解析回應
        body = json.loads(response.get("body", "{}"))

        # 檢查 1：report_text 非空
        report_text = body.get("report_text", "")
        if not report_text:
            result["issues"].append("report_text 為空")
        elif len(report_text) < 100:
            result["issues"].append(f"report_text 過短：{len(report_text)} 字元")

        # 檢查 2：證據筆數
        result["evidence_count"] = len(evidence.evidence_list)
        if result["evidence_count"] == 0:
            result["issues"].append("evidence_list 為空，沒有蒐集到任何證據")

        # 檢查 3：從實際引用與 execution log 衍生多維度執行結果
        analysis_portion = report_text.split("### 完整證據清單", 1)[0]
        metadata = handler.build_report_metadata(
            analysis_portion, evidence.evidence_list, evidence.execution_log
        )
        analysis_summary = report.build_analysis_summary(
            evidence.evidence_list, metadata
        )
        result["analyzed_dimensions"] = analysis_summary["analyzed_dimensions"]
        result["cited_evidence_count"] = analysis_summary["cited_evidence_count"]
        result["independent_source_count"] = analysis_summary["independent_source_count"]
        result["failed_attempts"] = analysis_summary["failed_attempts"]

        # 品質閘門：必須有有效引用，且實際引用至少涵蓋兩個分析維度。
        if result["cited_evidence_count"] == 0:
            result["issues"].append("引用證據筆數為 0，報告沒有有效引用")
        if len(result["analyzed_dimensions"]) < 2:
            result["issues"].append(
                f"實際分析維度不足：{len(result['analyzed_dimensions'])} 個，至少需要 2 個"
            )

        # C2 Evidence Record 欄位契約保持不變
        expected_evidence_fields = {
            "evidence_id", "source", "fetched_at", "content_reference", "related_claim"
        }
        for record in evidence.evidence_list:
            if not isinstance(record, dict) or set(record) != expected_evidence_fields:
                result["issues"].append("Evidence Record 欄位不符合 C2 契約")
                break

        # C5 回應保留既有欄位，不暴露內部 report metadata
        required_response_fields = {
            "report_text", "evidence_download_url", "log_download_url", "run_id"
        }
        if not required_response_fields.issubset(body):
            result["issues"].append("HTTP 回應缺少 C5 必要欄位")
        leaked_metadata = {
            "analyzed_dimensions", "cited_evidence_count",
            "independent_source_count", "failed_attempts",
        }.intersection(body)
        if leaked_metadata:
            result["issues"].append("HTTP 回應不應暴露 report metadata")

        # 報告須呈現摘要、逐維明細、實際計數與已知失敗
        if "### 多維度分析摘要" not in report_text:
            result["issues"].append("報告缺少多維度分析摘要")
        for dimension in result["analyzed_dimensions"]:
            if dimension not in report_text:
                result["issues"].append(f"報告未呈現分析維度：{dimension}")
        if f"引用證據筆數**：{result['cited_evidence_count']}" not in report_text:
            result["issues"].append("報告引用證據筆數與 metadata 不一致")
        if f"獨立來源數**：{result['independent_source_count']}" not in report_text:
            result["issues"].append("報告獨立來源數與 metadata 不一致")
        for failure in result["failed_attempts"]:
            failure_label = failure.get("dimension") or failure.get("capability_id")
            if failure_label not in report_text or failure.get("status") not in report_text:
                result["issues"].append(f"報告未呈現失敗嘗試：{failure_label}")

        result["issues"].extend(find_fixed_score_issues(report_text))

        # 檢查 4：來源類別 >= 3 僅保留為獨立 export pass/fail 政策
        passed_export, export_issues = export.validate_before_export(
            evidence.evidence_list, report_text
        )
        for issue in export_issues:
            if "投資建議" in issue or "來源類別數不足" in issue:
                result["issues"].append(issue)

        # 檢查 5：耗時
        if elapsed > config.TIME_BUDGET_SECONDS:
            result["issues"].append(
                f"耗時 {elapsed:.0f}s 超過預算 {config.TIME_BUDGET_SECONDS}s"
            )

        # 判斷通過與否
        result["passed"] = len(result["issues"]) == 0

    except Exception as e:
        elapsed = time.time() - start
        result["elapsed_s"] = round(elapsed, 1)
        result["issues"].append(f"未處理例外：{type(e).__name__}: {str(e)}")
        traceback.print_exc()

    return result


def print_summary(results):
    """印出實際多維度、證據／來源計數及已知失敗的本機總表。"""
    print("\n" + "=" * 100)
    print("整合測試總表")
    print("=" * 100)
    print(
        f"{'案例名稱':<20} {'結果':<8} {'耗時':<8} "
        f"{'蒐集證據':<8} {'引用證據':<8} {'獨立來源':<8} {'問題'}"
    )
    print("-" * 100)

    total = len(results)
    passed = 0

    for result in results:
        status = "PASS" if result["passed"] else "FAIL"
        if result["passed"]:
            passed += 1
        issues = "; ".join(result["issues"][:2]) if result["issues"] else ""
        print(
            f"{result['name']:<20} {status:<8} {str(result['elapsed_s']) + 's':<8} "
            f"{result['evidence_count']:<8} {result['cited_evidence_count']:<8} "
            f"{result['independent_source_count']:<8} {issues}"
        )
        dimensions = result["analyzed_dimensions"]
        print(f"  分析維度：{', '.join(dimensions) if dimensions else '無有效引用'}")
        failures = result["failed_attempts"]
        if failures:
            failure_text = "; ".join(
                f"{item.get('dimension') or item.get('capability_id')} "
                f"({item.get('status')}: {item.get('reason')})"
                for item in failures
            )
        else:
            failure_text = "無"
        print(f"  失敗嘗試：{failure_text}")

    print("-" * 100)
    print(f"結果：{passed}/{total} 通過")

    if passed == total:
        print("所有案例通過！")
    else:
        print("\n未通過案例的詳細問題：")
        for result in results:
            if not result["passed"]:
                print(f"\n  [{result['name']}]")
                for issue in result["issues"]:
                    print(f"    - {issue}")

    print("=" * 100)
    return passed == total


def _sample_multidimensional_run():
    records = [
        {
            "evidence_id": "ev_price",
            "source": "https://api.binance.com/api/v3/klines",
            "fetched_at": "2026-08-01T00:00:00Z",
            "content_reference": {"pair": "BTCUSDT", "range": "30d"},
            "related_claim": "檢驗近期價格方向",
        },
        {
            "evidence_id": "ev_sentiment",
            "source": "https://api.alternative.me/fng/",
            "fetched_at": "2026-08-01T00:00:01Z",
            "content_reference": {"current_index": 42},
            "related_claim": "檢驗市場情緒是否一致",
        },
        {
            "evidence_id": "ev_macro",
            "source": "https://api.stlouisfed.org/fred/series/observations",
            "fetched_at": "2026-08-01T00:00:02Z",
            "content_reference": {"series_id": "DGS10"},
            "related_claim": "檢驗宏觀利率壓力",
        },
        {
            "evidence_id": "ev_unused",
            "source": "https://coindesk.com/markets",
            "fetched_at": "2026-08-01T00:00:03Z",
            "content_reference": {"title": "未引用新聞"},
            "related_claim": "蒐集但未採用的新聞背景",
        },
    ]
    execution_log = [
        {"tool_name": "get_price_ohlcv", "status": "success", "evidence_id": "ev_price", "note": None},
        {"tool_name": "get_sentiment", "status": "success", "evidence_id": "ev_sentiment", "note": None},
        {"tool_name": "get_macro", "status": "success", "evidence_id": "ev_macro", "note": None},
        {"tool_name": "search_news", "status": "success", "evidence_id": "ev_unused", "note": None},
        {"tool_name": "get_onchain", "status": "timeout", "evidence_id": None, "note": "上游逾時"},
    ]
    analysis = (
        "## 市場判斷\n事實：價格 [ev_price]、情緒 [ev_sentiment] 與總體經濟 [ev_macro]。"
        "\n推論：三個維度呈現不同程度壓力。\n結論：信心中等。"
        "\n## 關鍵依據\n[ev_price] [ev_sentiment] [ev_macro]"
        "\n## 信心說明\n鏈上資料取得逾時，限制交叉驗證。"
    )
    metadata = handler.build_report_metadata(analysis, records, execution_log)
    report_text = report.render_report(
        "run_offline", "BTC 多維度測試", analysis, records, coverage=metadata
    )
    return records, execution_log, analysis, report_text


def test_run_single_case_exposes_actual_multidimensional_results(monkeypatch):
    """離線驗證 Lambda 路徑的 C2/C5、report metadata 與 export 政策隔離。"""
    records, execution_log, _, report_text = _sample_multidimensional_run()
    evidence.evidence_list[:] = records
    evidence.execution_log[:] = execution_log

    response_body = {
        "report_text": report_text,
        "evidence_download_url": "https://example.invalid/evidence",
        "log_download_url": "https://example.invalid/log",
        "run_id": "run_offline",
    }
    monkeypatch.setattr(
        handler,
        "lambda_handler",
        lambda event, context: {"statusCode": 200, "body": json.dumps(response_body)},
    )

    try:
        result = run_single_case({
            "name": "離線多維測試",
            "symbols": ["BTC"],
            "question": "比較價格、情緒與宏觀訊號",
        })
    finally:
        evidence.reset_stores()

    assert result["passed"], result["issues"]
    assert result["evidence_count"] == 4
    assert result["analyzed_dimensions"] == ["價格", "情緒", "總體經濟"]
    assert result["cited_evidence_count"] == 3
    assert result["independent_source_count"] == 3
    assert result["failed_attempts"] == [{
        "dimension": "鏈上",
        "capability_id": "get_onchain",
        "status": "timeout",
        "reason": "上游逾時",
    }]
    assert "categories" not in result


def _run_offline_report_case(monkeypatch, records, execution_log, report_text):
    evidence.evidence_list[:] = records
    evidence.execution_log[:] = execution_log
    response_body = {
        "report_text": report_text,
        "evidence_download_url": "https://example.invalid/evidence",
        "log_download_url": "https://example.invalid/log",
        "run_id": "run_quality",
    }
    monkeypatch.setattr(
        handler,
        "lambda_handler",
        lambda event, context: {"statusCode": 200, "body": json.dumps(response_body)},
    )
    try:
        return run_single_case({
            "name": "品質閘門測試",
            "symbols": ["BTC"],
            "question": "驗證報告品質",
        })
    finally:
        evidence.reset_stores()


def test_run_single_case_rejects_zero_cited_evidence(monkeypatch):
    """即使蒐集到證據，報告未實際引用任何一筆也不得通過。"""
    records, execution_log, _, _ = _sample_multidimensional_run()
    report_text = report.render_report(
        "run_zero", "零引用測試", "沒有引用證據的分析", records, coverage={}
    )
    result = _run_offline_report_case(
        monkeypatch, records, execution_log, report_text
    )
    assert result["passed"] is False
    assert result["cited_evidence_count"] == 0
    assert any("引用證據筆數為 0" in issue for issue in result["issues"])


def test_run_single_case_rejects_only_one_analyzed_dimension(monkeypatch):
    """有效引用若只落在單一實際維度，仍不得通過多維度品質檢查。"""
    records, execution_log, _, _ = _sample_multidimensional_run()
    analysis = (
        "## 市場判斷\n價格事實 [ev_price]。\n"
        "## 關鍵依據\n[ev_price]\n## 信心說明\n僅有價格維度。"
    )
    metadata = handler.build_report_metadata(analysis, records, execution_log)
    report_text = report.render_report(
        "run_one_dimension", "單維測試", analysis, records, coverage=metadata
    )
    result = _run_offline_report_case(
        monkeypatch, records, execution_log, report_text
    )
    assert result["passed"] is False
    assert result["cited_evidence_count"] == 1
    assert result["analyzed_dimensions"] == ["價格"]
    assert any("實際分析維度不足：1 個" in issue for issue in result["issues"])


def test_fixed_score_check_allows_legitimate_ratios_dates_urls_and_analysis_percentages():
    legitimate = (
        "市場成交比為 3/5；日期 2026/3/5；來源 https://example.com/3/5；"
        "分析指出波動率為 68%。"
    )
    assert find_fixed_score_issues(legitimate) == []
    issues = find_fixed_score_issues("資料覆蓋率：4/5")
    assert len(issues) == 1
    assert "資料覆蓋率：4/5" in issues[0]


def test_handler_main_writes_offline_multidimensional_report(monkeypatch, tmp_path, capsys):
    """本機 main 路徑也使用 execution log 衍生 metadata，不呼叫網路。"""
    records, execution_log, analysis, _ = _sample_multidimensional_run()

    def fake_loop(run_id, symbols, question):
        evidence.evidence_list[:] = records
        evidence.execution_log[:] = execution_log
        return [{"role": "assistant", "content": [{"text": analysis}]}]

    monkeypatch.setattr(handler, "__file__", str(tmp_path / "lambda" / "handler.py"))
    monkeypatch.setattr(handler.config, "load_local_env", lambda: None)
    monkeypatch.setattr(handler.agent, "run_agent_loop", fake_loop)
    monkeypatch.setattr(handler.agent, "summarize_final_analysis", lambda messages: analysis)

    try:
        handler.main()
        generated_report = (tmp_path / "outputs" / "report.md").read_text(encoding="utf-8")
        console = capsys.readouterr().out
    finally:
        evidence.reset_stores()

    assert "### 多維度分析摘要" in generated_report
    assert "引用證據筆數**：3" in generated_report
    assert "獨立來源數**：3" in generated_report
    assert "鏈上" in generated_report and "timeout" in generated_report
    assert "實際分析維度：價格, 情緒, 總體經濟" in console
    assert "引用證據筆數：3" in console
    assert "獨立來源數：3" in console
    assert "失敗嘗試：鏈上 (timeout: 上游逾時)" in console


def test_print_summary_shows_dimension_names_counts_and_failures(capsys):
    results = [{
        "name": "摘要案例",
        "passed": True,
        "elapsed_s": 1.2,
        "evidence_count": 4,
        "analyzed_dimensions": ["價格", "情緒"],
        "cited_evidence_count": 3,
        "independent_source_count": 2,
        "failed_attempts": [{
            "dimension": "鏈上", "capability_id": "get_onchain",
            "status": "timeout", "reason": "上游逾時",
        }],
        "issues": [],
    }]

    assert print_summary(results) is True
    output = capsys.readouterr().out
    assert "分析維度：價格, 情緒" in output
    assert "引用證據" in output and "獨立來源" in output
    assert "失敗嘗試：鏈上 (timeout: 上游逾時)" in output
    assert "資料覆蓋率" not in output
    assert "類別" not in output
    assert "%" not in output


def main():
    """依序執行 TEST_CASES 裡的每個案例，最後印出總表。"""
    # 載入本機環境變數
    config.load_local_env()

    # 檢查必要環境變數
    missing = config.check_required_env()
    if missing:
        print(f"[WARN] 缺少環境變數：{', '.join(missing)}")
        print("[WARN] 部分功能可能無法正常運作")
        print()

    print("=" * 80)
    print("加密市場分析 AI Agent — 整合測試")
    print(f"測試案例數：{len(TEST_CASES)}")
    print(f"時間預算：{config.TIME_BUDGET_SECONDS}s / 案例")
    print("=" * 80)

    results = []
    for i, case in enumerate(TEST_CASES, 1):
        print(f"\n[{i}/{len(TEST_CASES)}] 執行：{case['name']}")
        print(f"  幣種：{case['symbols']}")
        print(f"  題目：{case['question'][:50]}...")
        print()

        result = run_single_case(case)
        results.append(result)

        status = "✅" if result["passed"] else "❌"
        print(f"  {status} 完成 ({result['elapsed_s']}s, {result['evidence_count']} 筆證據)")
        if result["issues"]:
            for issue in result["issues"][:3]:
                print(f"    ⚠ {issue}")

    # 印出總表
    all_passed = print_summary(results)

    # 回傳退出碼（CI 用）
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
