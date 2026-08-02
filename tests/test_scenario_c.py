"""
test_scenario_c.py — 情境 C 比較分析重複測試（3 次）

專門測試雙幣種比較分析情境，觀察 Synthesis 的穩定性。
"""

import sys
import json
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lambda"))

import config
config.load_local_env()

import agent
import evidence
import report
import export


def run_comparison_test(run_number):
    """執行一次情境 C 測試。"""
    print(f"\n{'='*70}")
    print(f"情境 C 第 {run_number} 次：雙幣種比較分析")
    print(f"幣種：['ETH', 'SOL']")
    print(f"問題：比較 ETH 與 SOL 的資金關注度差異")
    print(f"{'='*70}")

    evidence.reset_stores()

    from datetime import datetime, timezone
    run_id = f"test_c{run_number}_{datetime.now(timezone.utc).strftime('%H%M%S')}"

    start = time.time()
    try:
        report_model = agent.run_agent_loop(run_id, ["ETH", "SOL"], "比較 ETH 與 SOL 的資金關注度差異")
    except Exception as e:
        print(f"[FATAL ERROR] {type(e).__name__}: {e}")
        return None
    elapsed = time.time() - start

    # 渲染報告
    coverage_pct, got_cats, missing_cats = report.calculate_coverage(evidence.evidence_list)
    report_text = report.render_report(
        run_id, "比較 ETH 與 SOL 的資金關注度差異", report_model,
        evidence.evidence_list, missing_sources=missing_cats
    )

    # Handler 回傳格式
    handler_response = {
        "report_text": report_text,
        "evidence_download_url": "(test mode)",
        "log_download_url": "(test mode)",
        "run_id": run_id,
    }

    # 結果摘要
    print(f"\n--- 耗時：{elapsed:.1f}s ---")
    print(f"--- 證據筆數：{len(evidence.evidence_list)} ---")
    print(f"--- 覆蓋率：{coverage_pct:.0f}% ({', '.join(got_cats)}) ---")
    if missing_cats:
        print(f"--- 缺少：{', '.join(missing_cats)} ---")

    # ReportModel 關鍵資訊
    ms = report_model.get("market_state", {})
    print(f"\n--- ReportModel ---")
    print(f"  regime: {ms.get('regime', 'N/A')}")
    print(f"  confidence: {ms.get('confidence', 'N/A')}")
    print(f"  key_findings 數量: {len(report_model.get('key_findings', []))}")
    print(f"  supporting_signals 數量: {len(report_model.get('supporting_signals', []))}")
    print(f"  contradicting_signals 數量: {len(report_model.get('contradicting_signals', []))}")
    print(f"  limitations 數量: {len(report_model.get('limitations', []))}")
    print(f"  evidence_ids 數量: {len(report_model.get('evidence_ids', []))}")

    # 檢查 correlation 是否被計算
    has_correlation = False
    for rec in evidence.evidence_list:
        cr = rec.get("content_reference", {})
        if isinstance(cr, dict):
            features = cr.get("features_computed", [])
            if "correlation" in str(features).lower() or "compare" in str(cr).lower():
                has_correlation = True
                break
        if "correlation" in str(rec.get("related_claim", "")).lower():
            has_correlation = True
            break
    print(f"  correlation 計算: {'✅' if has_correlation else '❌'}")

    # 檢查兩幣種對等性
    eth_evidence = [r for r in evidence.evidence_list if "ETH" in str(r.get("source", "")) or "ETH" in str(r.get("related_claim", ""))]
    sol_evidence = [r for r in evidence.evidence_list if "SOL" in str(r.get("source", "")) or "SOL" in str(r.get("related_claim", ""))]
    print(f"  ETH 相關證據: {len(eth_evidence)} 筆")
    print(f"  SOL 相關證據: {len(sol_evidence)} 筆")
    balance_ratio = min(len(eth_evidence), len(sol_evidence)) / max(len(eth_evidence), len(sol_evidence)) if max(len(eth_evidence), len(sol_evidence)) > 0 else 0
    print(f"  對等比例: {balance_ratio:.2f} (1.0=完全對等)")

    # 使用的工具
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

    # 驗證
    print(f"\n--- 驗證 ---")
    has_judgment = "## 市場判斷" in report_text
    has_evidence_sec = "## 關鍵依據" in report_text
    has_confidence = "## 信心說明" in report_text
    print(f"  三章節齊備：{'✅' if (has_judgment and has_evidence_sec and has_confidence) else '❌'}")

    forbidden = ["買進", "賣出", "目標價", "建議持有"]
    found_forbidden = [p for p in forbidden if p in report_text]
    print(f"  無投資建議：{'✅' if not found_forbidden else '❌ ' + str(found_forbidden)}")

    conf = ms.get("confidence", "")
    print(f"  confidence 合法值：{'✅' if conf in ('low','medium','high') else '❌ got: '+conf}")

    # Synthesis 是否成功（非降級模式）
    is_degraded = "降級" in ms.get("regime", "") or "失敗" in ms.get("regime", "")
    print(f"  Synthesis 正常產出：{'❌ (降級模式)' if is_degraded else '✅'}")

    # 印出報告前 800 字
    print(f"\n--- 報告摘要（前 800 字）---")
    print(report_text[:800])

    # 印出 ReportModel JSON
    print(f"\n--- ReportModel JSON ---")
    print(json.dumps(report_model, ensure_ascii=False, indent=2)[:2500])

    return {
        "elapsed": elapsed,
        "evidence_count": len(evidence.evidence_list),
        "coverage_pct": coverage_pct,
        "is_degraded": is_degraded,
        "has_correlation": has_correlation,
        "eth_evidence": len(eth_evidence),
        "sol_evidence": len(sol_evidence),
        "confidence": conf,
    }


if __name__ == "__main__":
    print("=" * 70)
    print("情境 C 比較分析壓力測試（3 次）")
    print(f"MAX_SUB_AGENT_TURNS = {config.MAX_SUB_AGENT_TURNS}")
    print(f"TIME_BUDGET_SECONDS = {config.TIME_BUDGET_SECONDS}")
    print("=" * 70)

    results = []
    for i in range(1, 4):
        r = run_comparison_test(i)
        results.append(r)
        if i < 3:
            print("\n[等待 5 秒避免 throttling...]")
            time.sleep(5)

    # 總結
    print(f"\n\n{'='*70}")
    print("三次測試總結")
    print(f"{'='*70}")
    for i, r in enumerate(results, 1):
        if r:
            status = "✅ 正常" if not r["is_degraded"] else "❌ 降級"
            print(f"  第 {i} 次: {status} | "
                  f"證據 {r['evidence_count']} | "
                  f"覆蓋 {r['coverage_pct']:.0f}% | "
                  f"correlation {'✅' if r['has_correlation'] else '❌'} | "
                  f"ETH/SOL={r['eth_evidence']}/{r['sol_evidence']} | "
                  f"信心={r['confidence']} | "
                  f"耗時 {r['elapsed']:.0f}s")
        else:
            print(f"  第 {i} 次: ❌ 執行失敗")
