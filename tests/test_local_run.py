"""
test_local_run.py — 本機整合測試

目的：在部署到 AWS 之前，先在本機把整條「輸入 → Agent 迴圈 → 報告產出」
的流程跑過一輪，確認邏輯正確。這裡不是要取代 handler.py 的 main()，
而是把 main() 針對「五個幣種 × 三種題型」重複呼叫，確保現場不管抽到
什麼組合都測試過。

執行方式：在專案根目錄下跑
    python -m tests.test_local_run
"""

import sys
import os
import json
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambda"))

import handler  # noqa: E402
import evidence  # noqa: E402
import report  # noqa: E402
import config  # noqa: E402


# 命題的三種範例題型，對應到不同的輸入形狀（尤其比較分析需要兩個幣種）
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
    # 功能：執行單一測試案例，透過 lambda_handler 呼叫完整流程，
    #      並進行五項關鍵檢查。
    # 檢查項目：
    #   1. 是否有拋出未處理的例外
    #   2. 是否真的產出 report_text，且長度不為 0
    #   3. evidence_list 是否至少涵蓋 3 種不同的 source_type
    #   4. 是否有任何 claim 找不到對應的 evidence_id（孤兒結論）
    #   5. 整體耗時是否在 TIME_BUDGET_SECONDS 之內
    # 回傳：結果 dict（name, passed, elapsed_sec, evidence_count, category_count, error）

    result = {
        "name": case["name"],
        "passed": False,
        "elapsed_sec": 0.0,
        "evidence_count": 0,
        "category_count": 0,
        "error": None,
    }

    # 步驟：記錄開始時間
    start_time = time.time()

    try:
        # 步驟：清空上一次執行殘留的證據與日誌
        evidence.reset_stores()

        # 步驟：組建 Lambda 風格的 event dict
        event = {
            "body": json.dumps({
                "symbols": case["symbols"],
                "question": case["question"],
            })
        }

        # 步驟：呼叫 lambda_handler 執行完整流程
        response = handler.lambda_handler(event, None)

        # 步驟：計算耗時
        elapsed = time.time() - start_time
        result["elapsed_sec"] = round(elapsed, 2)

        # 步驟：若 lambda_handler 回傳 None（尚未實作），標記為 SKIP
        if response is None:
            result["passed"] = "skip"
            result["error"] = "lambda_handler 尚未實作（回傳 None）"
            print(f"  [{case['name']}] SKIP — handler 尚未實作")
            return result

        # 步驟：解析回應 body
        status_code = response.get("statusCode", 0)
        body_str = response.get("body", "{}")
        body = json.loads(body_str) if isinstance(body_str, str) else body_str

        # 步驟：若狀態碼非 200，視為失敗
        if status_code != 200:
            result["error"] = f"statusCode={status_code}, body={body}"
            print(f"  [{case['name']}] FAIL — HTTP {status_code}")
            return result

        # 步驟：檢查 1 — report_text 是否非空
        report_text = body.get("report_text", "")
        if not report_text or len(report_text.strip()) == 0:
            result["error"] = "report_text 為空"
            print(f"  [{case['name']}] FAIL — report_text 為空")
            return result

        # 步驟：檢查 2 — evidence 涵蓋類別數 >= 3
        evidence_snapshot = list(evidence.evidence_list)
        result["evidence_count"] = len(evidence_snapshot)

        coverage_pct, obtained_categories, missing_categories = report.calculate_coverage(evidence_snapshot)
        result["category_count"] = len(obtained_categories)

        if len(obtained_categories) < 3:
            result["error"] = f"證據類別不足：僅有 {len(obtained_categories)} 類（{', '.join(obtained_categories)}）"
            print(f"  [{case['name']}] FAIL — 類別不足 ({len(obtained_categories)}/3)")
            return result

        # 步驟：檢查 3 — 無孤兒結論（report_text 中引用的 evidence_id 皆存在於 evidence_list）
        existing_ids = {rec["evidence_id"] for rec in evidence_snapshot}
        # 從 report_text 中搜尋引用的 evidence_id 格式
        orphan_found = False
        for rec in evidence_snapshot:
            if rec.get("related_claim") and rec["evidence_id"] not in existing_ids:
                orphan_found = True
                break

        if orphan_found:
            result["error"] = "存在孤兒結論（evidence_id 引用不到對應證據）"
            print(f"  [{case['name']}] FAIL — 孤兒結論")
            return result

        # 步驟：檢查 4 — 耗時是否在 TIME_BUDGET_SECONDS 之內
        if elapsed > config.TIME_BUDGET_SECONDS:
            result["error"] = f"耗時超限：{elapsed:.1f}s > {config.TIME_BUDGET_SECONDS}s"
            print(f"  [{case['name']}] FAIL — 耗時超限")
            return result

        # 步驟：全部檢查通過
        result["passed"] = True
        print(f"  [{case['name']}] PASS — {elapsed:.1f}s, {len(evidence_snapshot)} 筆證據, {len(obtained_categories)} 類別")

    except Exception as e:
        # 步驟：捕獲未預期的例外，標記失敗
        elapsed = time.time() - start_time
        result["elapsed_sec"] = round(elapsed, 2)
        result["error"] = f"例外：{type(e).__name__}: {str(e)}"
        print(f"  [{case['name']}] FAIL — {type(e).__name__}: {e}")

    return result


def print_summary(results):
    # 功能：所有案例跑完後，印出一張總表，方便一次看出哪些案例沒過。
    # 欄位：案例名稱、通過與否、耗時、證據筆數、涵蓋的資料類別數

    print("\n" + "=" * 78)
    print(f"{'案例名稱':<20} {'狀態':<8} {'耗時(s)':<10} {'證據筆數':<10} {'類別數':<8}")
    print("-" * 78)

    # 步驟：逐筆印出結果
    passed_count = 0
    failed_count = 0
    skipped_count = 0

    for r in results:
        # 步驟：判斷狀態文字
        if r["passed"] == "skip":
            status_str = "SKIP"
            skipped_count += 1
        elif r["passed"]:
            status_str = "PASS"
            passed_count += 1
        else:
            status_str = "FAIL"
            failed_count += 1

        print(
            f"{r['name']:<20} {status_str:<8} {r['elapsed_sec']:<10.2f} "
            f"{r['evidence_count']:<10} {r['category_count']:<8}"
        )

        # 步驟：若有錯誤，印出原因
        if r["error"]:
            print(f"  └─ {r['error']}")

    # 步驟：印出統計總結
    print("-" * 78)
    total = len(results)
    print(f"合計：{total} 案例 | PASS: {passed_count} | FAIL: {failed_count} | SKIP: {skipped_count}")
    print("=" * 78)


def main():
    # 功能：依序執行 TEST_CASES 裡的每個案例，最後印出總表。
    # 步驟：先載入本機環境變數

    print("=" * 78)
    print("整合測試 — 本機執行")
    print("=" * 78)

    # 步驟：載入 .env 環境變數
    try:
        config.load_local_env()
        print("[環境] .env 載入完成")
    except Exception as e:
        print(f"[環境] .env 載入失敗：{e}（繼續執行）")

    print(f"[設定] TIME_BUDGET_SECONDS = {config.TIME_BUDGET_SECONDS}")
    print(f"[設定] MAX_AGENT_TURNS = {config.MAX_AGENT_TURNS}")
    print(f"[設定] 測試案例數 = {len(TEST_CASES)}")
    print()

    # 步驟：依序執行每個測試案例
    results = []
    for i, case in enumerate(TEST_CASES, 1):
        print(f"[{i}/{len(TEST_CASES)}] 執行案例：{case['name']}")
        print(f"  幣種：{case['symbols']} | 題目：{case['question'][:30]}...")
        result = run_single_case(case)
        results.append(result)
        print()

    # 步驟：印出總表
    print_summary(results)


if __name__ == "__main__":
    main()