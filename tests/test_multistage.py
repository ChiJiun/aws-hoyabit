"""
test_multistage.py — 多階段架構端到端測試

測試 4 種情境：
  a. 單一幣種、簡單題目（核心層工具）
  b. 單一幣種、需要進階資料（進階層工具）
  c. 雙幣種比較分析（correlation）
  d. 模擬工具失敗（降級機制）
"""

import sys
import json
import time
from pathlib import Path

# 設定 import 路徑
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lambda"))

import config
config.load_local_env()

import agent
import evidence
import report
import export


def run_scenario(label, symbols, question, mock_failure=False):
    """執行一個測試情境並印出結果。"""
    print(f"\n{'='*70}")
    print(f"情境：{label}")
    print(f"幣種：{symbols}")
    print(f"問題：{question}")
    if mock_failure:
        print("⚠️  模擬工具失敗模式")
    print(f"{'='*70}")

    # 清空
    evidence.reset_stores()

    # 如果要模擬失敗，暫時替換某個工具
    original_func = None
    if mock_failure:
        original_func = agent.TOOL_DISPATCH.get("get_onchain")
        def failing_tool(**kwargs):
            raise ConnectionError("Simulated network failure for testing")
        agent.TOOL_DISPATCH["get_onchain"] = failing_tool

    # 產生 run_id
    from datetime import datetime, timezone
    run_id = f"test_{datetime.now(timezone.utc).strftime('%H%M%S')}"

    start = time.time()
    try:
        # 執行多階段流程
        report_model = agent.run_agent_loop(run_id, symbols, question)
    except Exception as e:
        print(f"[FATAL ERROR] {type(e).__name__}: {e}")
        report_model = None
    elapsed = time.time() - start

    # 恢復工具
    if mock_failure and original_func:
        agent.TOOL_DISPATCH["get_onchain"] = original_func

    if report_model is None:
        print("[FAIL] run_agent_loop 回傳 None")
        return None

    # 渲染報告
    coverage_pct, got_cats, missing_cats = report.calculate_coverage(evidence.evidence_list)
    report_text = report.render_report(
        run_id, question, report_model,
        evidence.evidence_list, missing_sources=missing_cats
    )

    # 組裝 handler 回傳格式
    handler_response = {
        "report_text": report_text,
        "evidence_download_url": "(test mode - no S3)",
        "log_download_url": "(test mode - no S3)",
        "run_id": run_id,
    }

    # 印出結果
    print(f"\n--- 耗時：{elapsed:.1f}s ---")
    print(f"--- 證據筆數：{len(evidence.evidence_list)} ---")
    print(f"--- 覆蓋率：{coverage_pct:.0f}% ({', '.join(got_cats)}) ---")
    if missing_cats:
        print(f"--- 缺少：{', '.join(missing_cats)} ---")

    print(f"\n--- ReportModel JSON（前 2000 字）---")
    model_json = json.dumps(report_model, ensure_ascii=False, indent=2)
    print(model_json[:2000])
    if len(model_json) > 2000:
        print("... (truncated)")

    print(f"\n--- 報告 Markdown（前 1500 字）---")
    print(report_text[:1500])
    if len(report_text) > 1500:
        print("... (truncated)")

    print(f"\n--- Handler 回傳 JSON 結構（前端契約驗證）---")
    # 只印 key 結構，不印完整 report_text
    contract_check = {
        "report_text": f"(string, {len(report_text)} chars)",
        "evidence_download_url": handler_response["evidence_download_url"],
        "log_download_url": handler_response["log_download_url"],
        "run_id": handler_response["run_id"],
    }
    print(json.dumps(contract_check, ensure_ascii=False, indent=2))

    # 驗證項目
    print(f"\n--- 驗證 ---")
    # 確認三章節存在
    has_judgment = "## 市場判斷" in report_text
    has_evidence = "## 關鍵依據" in report_text
    has_confidence = "## 信心說明" in report_text
    print(f"  三章節齊備：{'✅' if (has_judgment and has_evidence and has_confidence) else '❌'}")
    print(f"    市場判斷：{'✅' if has_judgment else '❌'}")
    print(f"    關鍵依據：{'✅' if has_evidence else '❌'}")
    print(f"    信心說明：{'✅' if has_confidence else '❌'}")

    # 檢查投資建議
    forbidden = ["買進", "賣出", "目標價", "建議持有"]
    found_forbidden = [p for p in forbidden if p in report_text]
    print(f"  無投資建議：{'✅' if not found_forbidden else '❌ ' + str(found_forbidden)}")

    # 確認 confidence 是合法值
    conf = report_model.get("market_state", {}).get("confidence", "")
    print(f"  confidence 合法值：{'✅' if conf in ('low','medium','high') else '❌ got: '+conf}")

    # 印出使用的工具（從 execution_log）
    tools_used = set()
    for log in evidence.execution_log:
        tn = log.get("tool_name", "")
        if tn not in ("planner", "validator", "synthesis", "agent_pipeline") and not tn.startswith("sub_agent"):
            if log.get("status") in ("success", "error"):
                tools_used.add(tn)
    core_used = tools_used & set(agent.CORE_TOOLS)
    advanced_used = tools_used & set(agent.ADVANCED_TOOLS)
    print(f"  核心層工具：{sorted(core_used)}")
    print(f"  進階層工具：{sorted(advanced_used)}")

    return {
        "report_model": report_model,
        "report_text": report_text,
        "handler_response": handler_response,
        "tools_used": tools_used,
        "evidence_count": len(evidence.evidence_list),
    }


if __name__ == "__main__":
    print("多階段架構端到端測試")
    print(f"TIME_BUDGET_SECONDS = {config.TIME_BUDGET_SECONDS}")
    print(f"MAX_SUB_AGENTS = {config.MAX_SUB_AGENTS}")

    results = {}

    # 情境 a：單一幣種、簡單題目
    results["a"] = run_scenario(
        "a. 單一幣種 + 簡單題目（應只用核心層工具）",
        ["BTC"],
        "BTC 最近幾週的趨勢如何"
    )

    # 情境 b：單一幣種、需要進階資料
    results["b"] = run_scenario(
        "b. 單一幣種 + 進階題目（應選用 get_derivatives）",
        ["BTC"],
        "BTC 目前槓桿多空是否過度擁擠"
    )

    # 情境 c：雙幣種比較分析
    results["c"] = run_scenario(
        "c. 雙幣種比較分析（應有 correlation + 對等研究深度）",
        ["ETH", "SOL"],
        "比較 ETH 與 SOL 的資金關注度差異"
    )

    # 情境 d：模擬工具失敗
    results["d"] = run_scenario(
        "d. 模擬工具失敗（get_onchain 強制拋例外）",
        ["BTC"],
        "分析 BTC 鏈上活躍度與價格的關係",
        mock_failure=True
    )

    # 最終摘要
    print(f"\n\n{'='*70}")
    print("全部測試完成摘要")
    print(f"{'='*70}")
    for key, r in results.items():
        if r:
            print(f"  情境 {key}: 證據 {r['evidence_count']} 筆, "
                  f"核心工具 {len(r['tools_used'] & set(agent.CORE_TOOLS))}, "
                  f"進階工具 {len(r['tools_used'] & set(agent.ADVANCED_TOOLS))}")
        else:
            print(f"  情境 {key}: ❌ 失敗")
