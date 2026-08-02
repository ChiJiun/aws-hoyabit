"""Quick scenario C only test."""
import sys, json, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lambda"))

import config
config.load_local_env()
import agent, evidence, report

evidence.reset_stores()

from datetime import datetime, timezone
run_id = f"test_c_{datetime.now(timezone.utc).strftime('%H%M%S')}"

print(f"Running scenario C: ETH vs SOL comparison")
print(f"MAX_SUB_AGENT_TURNS = {config.MAX_SUB_AGENT_TURNS}")
start = time.time()
report_model = agent.run_agent_loop(run_id, ["ETH", "SOL"], "比較 ETH 與 SOL 的資金關注度差異")
elapsed = time.time() - start

coverage_pct, got_cats, missing_cats = report.calculate_coverage(evidence.evidence_list)
report_text = report.render_report(run_id, "比較 ETH 與 SOL 的資金關注度差異", report_model, evidence.evidence_list, missing_sources=missing_cats)

ms = report_model.get("market_state", {})
is_degraded = "降級" in ms.get("regime", "") or "失敗" in ms.get("regime", "")

print(f"\n{'='*60}")
print(f"耗時: {elapsed:.1f}s")
print(f"證據: {len(evidence.evidence_list)} 筆")
print(f"覆蓋率: {coverage_pct:.0f}% ({', '.join(got_cats)})")
print(f"regime: {ms.get('regime', 'N/A')}")
print(f"confidence: {ms.get('confidence', 'N/A')}")
print(f"key_findings: {len(report_model.get('key_findings', []))}")
print(f"Synthesis 正常: {'❌ 降級' if is_degraded else '✅'}")
print(f"三章節: {'✅' if all(x in report_text for x in ['## 市場判斷','## 關鍵依據','## 信心說明']) else '❌'}")

# 工具使用
tools_used = set()
for log in evidence.execution_log:
    tn = log.get("tool_name", "")
    if tn not in ("planner","validator","synthesis","agent_pipeline") and not tn.startswith("sub_agent"):
        if log.get("status") in ("success","error"):
            tools_used.add(tn)
print(f"核心: {sorted(tools_used & set(agent.CORE_TOOLS))}")
print(f"進階: {sorted(tools_used & set(agent.ADVANCED_TOOLS))}")

# correlation check
has_corr = any("correlation" in str(r.get("related_claim","")).lower() or "相關" in str(r.get("related_claim","")) for r in evidence.evidence_list)
print(f"correlation: {'✅' if has_corr else '❌'}")

print(f"\n--- ReportModel (前 2000 字) ---")
print(json.dumps(report_model, ensure_ascii=False, indent=2)[:2000])

print(f"\n--- 報告 (前 1200 字) ---")
print(report_text[:1200])
