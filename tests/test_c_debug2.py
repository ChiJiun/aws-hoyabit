"""Debug: check if forced convergence call throws exception."""
import sys, json, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lambda"))

import config
config.load_local_env()
import agent, evidence

evidence.reset_stores()
from datetime import datetime, timezone
run_id = f"dbg2_{datetime.now(timezone.utc).strftime('%H%M%S')}"

report_model = agent.run_agent_loop(run_id, ["ETH", "SOL"], "比較 ETH 與 SOL 的資金關注度差異")

# Check execution log for forced convergence errors
print("=== Execution Log (sub_agent entries) ===")
for log in evidence.execution_log:
    if "sub_agent" in log.get("tool_name", "") or "convergence" in str(log.get("note", "")):
        print(json.dumps(log, ensure_ascii=False))
