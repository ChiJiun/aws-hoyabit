"""Debug scenario C - inspect Sub-agent ResearchResult extraction."""
import sys, json, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lambda"))

import config
config.load_local_env()
import agent, evidence

# Monkey-patch _extract_research_result to print what it sees
original_extract = agent._extract_research_result

def debug_extract(messages, role, dimensions):
    print(f"\n  [DEBUG _extract_research_result] role={role}")
    # Check last few assistant messages
    count = 0
    for msg in reversed(messages):
        if msg.get("role") == "assistant" and count < 3:
            content_blocks = msg.get("content", [])
            has_text = any("text" in b for b in content_blocks)
            has_tooluse = any("toolUse" in b for b in content_blocks)
            print(f"    msg: has_text={has_text}, has_toolUse={has_tooluse}")
            if has_text:
                for b in content_blocks:
                    if "text" in b:
                        text_preview = b["text"][:300]
                        print(f"    text preview: {text_preview}")
                        # Try JSON extraction
                        result = agent._extract_json_from_response(content_blocks)
                        print(f"    json extracted: {result is not None}")
                        if result:
                            print(f"    json keys: {list(result.keys())[:10]}")
                        break
            count += 1
    
    result = original_extract(messages, role, dimensions)
    print(f"  [DEBUG] result facts={len(result.get('facts',[]))}, signals={len(result.get('signals',[]))}")
    print(f"  [DEBUG] result summary: {result.get('summary','')[:100]}")
    return result

agent._extract_research_result = debug_extract

evidence.reset_stores()
from datetime import datetime, timezone
run_id = f"debug_{datetime.now(timezone.utc).strftime('%H%M%S')}"

print("Running scenario C with debug extraction...")
report_model = agent.run_agent_loop(run_id, ["ETH", "SOL"], "比較 ETH 與 SOL 的資金關注度差異")

print(f"\n=== Final ===")
print(f"Evidence: {len(evidence.evidence_list)}")
ms = report_model.get("market_state", {})
print(f"regime: {ms.get('regime')}")
print(f"confidence: {ms.get('confidence')}")
