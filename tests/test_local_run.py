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


def run_single_case(case):
    """執行單一測試案例，呼叫 handler 內部邏輯並檢查結果。

    檢查項目：
      1. 是否有拋出未處理的例外
      2. report_text 是否非空
      3. evidence_list 涵蓋的來源類別數 >= 3
      4. 報告中無投資建議語句
      5. 整體耗時是否在 TIME_BUDGET_SECONDS 之內

    回傳：dict 包含 name、passed、elapsed_s、evidence_count、
          categories、issues
    """
    result = {
        "name": case["name"],
        "passed": False,
        "elapsed_s": 0,
        "evidence_count": 0,
        "categories": [],
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

        # 檢查 3：來源類別數 >= 3
        coverage_pct, got_categories, missing_categories = report.calculate_coverage(
            evidence.evidence_list
        )
        result["categories"] = got_categories
        if len(got_categories) < 3:
            result["issues"].append(
                f"來源類別不足：僅 {len(got_categories)} 類（{', '.join(got_categories)}），需 >= 3"
            )

        # 檢查 4：無投資建議語句
        passed_export, export_issues = export.validate_before_export(
            evidence.evidence_list, report_text
        )
        for issue in export_issues:
            if "投資建議" in issue:
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
    """所有案例跑完後，印出總表。

    欄位：案例名稱、通過與否、耗時、證據筆數、涵蓋的資料類別數、問題
    """
    print("\n" + "=" * 80)
    print("整合測試總表")
    print("=" * 80)
    print(f"{'案例名稱':<20} {'結果':<6} {'耗時':<8} {'證據':<6} {'類別':<6} {'問題'}")
    print("-" * 80)

    total = len(results)
    passed = 0

    for r in results:
        status = "✅ PASS" if r["passed"] else "❌ FAIL"
        if r["passed"]:
            passed += 1
        elapsed = f"{r['elapsed_s']}s"
        evidence_count = str(r["evidence_count"])
        categories = str(len(r["categories"]))
        issues = "; ".join(r["issues"][:2]) if r["issues"] else ""

        print(f"{r['name']:<20} {status:<6} {elapsed:<8} {evidence_count:<6} {categories:<6} {issues}")

    print("-" * 80)
    print(f"結果：{passed}/{total} 通過")

    if passed == total:
        print("🎉 所有案例通過！")
    else:
        print("\n未通過案例的詳細問題：")
        for r in results:
            if not r["passed"]:
                print(f"\n  [{r['name']}]")
                for issue in r["issues"]:
                    print(f"    - {issue}")

    print("=" * 80)
    return passed == total


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
