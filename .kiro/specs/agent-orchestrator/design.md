# agent-orchestrator 設計

## 定位
系統唯一的「編排者」,也是唯一同時接觸多個模組的地方。耦合被限制在:工具契約 C1、Evidence API C2、Report 契約 C4、HTTP 契約 C5。

## agent.py
- `build_tool_config()`:六個 toolSpec(get_price_ohlcv、compute_quant、search_news、get_onchain、get_sentiment、get_macro),每個 inputSchema 的 required 必含 related_claim(強制 LLM 說明每次取數為了支撐什麼判斷 — 這是證據鏈的關鍵設計)
- `call_bedrock(messages, tool_config=None)`:converse();Throttling 重試 1 次;逾時/驗證錯誤明確上拋
- `dispatch_tool_call(block, run_id)`:TOOL_DISPATCH dict 分派 → 計時 → log_evidence + log_execution_step → toolResult 僅 {summary, evidence_id}
- `run_agent_loop(symbols, question, run_id) -> analysis_text`:迴圈上限 MAX_AGENT_TURNS;每輪前檢查時間預算;剩餘 <20% 注入收斂指令;end_turn 跳出
- `summarize_final_analysis(analysis_text, evidence_list)`:第二次呼叫,無工具,強制三段式輸出(R14)
- SYSTEM_PROMPT:事實→推論→結論紀律、禁投資建議語句、矛盾訊號須明寫、引用 evidence_id

## handler.py
- `parse_request`:symbols ⊂ {BTC,ETH,SOL,BNB,XRP} 且 1–2 個、question 非空;錯誤回 400 + 說明 + CORS
- `lambda_handler` 流程:reset_stores → parse → run_id(run_YYYYMMDD_HHMMSS)→ config.missing_vars 自檢 → run_agent_loop → summarize → report-delivery(validate → render → export)→ storage 上傳 → 回應(契約 C5)
- 外層 try/except:任何未預期錯誤 → 500 + CORS + 可讀訊息
- `if __name__ == "__main__"`:本機進入點,產出寫 outputs/(R21)

## 測試重點
P1 有效請求必受理|P2 無效幣種必拒|P3 迴圈必終止|P5 分派正確|P6 toolResult 不含 raw|整合:5 幣種 × 3 題型
