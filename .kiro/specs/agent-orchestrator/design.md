# agent-orchestrator 設計

## 定位
系統唯一的「編排者」,也是唯一同時接觸多個模組的地方。耦合被限制在:工具契約 C1、Evidence API C2、Report 契約 C4、HTTP 契約 C5。

## agent.py
- `build_tool_config()`:為 `TOOL_DISPATCH` 目前註冊的 15 個工具建立 toolSpec；每個 inputSchema 的 required 必含 related_claim(強制 LLM 說明每次取數為了支撐什麼判斷 — 這是證據鏈的關鍵設計)
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


## Pipeline Presentation 設計增補

### 新增元件

- `classify_question_type(symbols, question) -> QuestionTypeResult`：規則優先；回傳 `question_type`、`method`、`matched_rules`。LLM 兜底只接收題目，不得呼叫工具。
- `build_prefetch_plan(question_type, symbols, question, settings) -> list[PrefetchItem]`：純函式，產出可測試的題型×能力矩陣；能力 ID 與工具名稱分離，便於 fallback。
- `run_phase_a_prefetch(run_id, plan) -> PrefetchOutcome`：使用有上限的 thread pool；各 future 有 timeout；錯誤轉為 outcome，不向外拋出。
- `build_phase_b_context(outcome) -> dict`：只保留 summary、content_reference 品質摘要、anomaly_flags、evidence_id 與 missing reason。
- `should_force_convergence(started_at, budget_seconds) -> bool`：剩餘比例 `< 0.20` 時為 true。
- `build_question_type_prompt(question_type, symbols) -> str`：在共同 SYSTEM_PROMPT 後附加題型專屬輸出要求。
- `register_visualization_series(run_context, capability, fetch_result) -> None`：每個 Phase A/B 成功工具在 raw 封存後，依 capability 呼叫 market/intel documented adapter，把已正規化的近 90 日序列寫入 request-scoped registry；完整 raw 不進模型訊息。
- `collect_series(run_context, symbols, question_type) -> dict`：在報告前凍結 registry，依 C7 series key 組裝資料；comparison 只搬運工具已決定性計算的 relative strength/correlation，不在 Handler 重算。

### 執行順序

`parse_request → classify_question_type → build_prefetch_plan → run_phase_a_prefetch → run_agent_loop(Phase B context；每個成功工具同步 register series) → summarize_final_analysis(question_type) → collect_series → report-delivery(build model → render Markdown + build_report_data → validate C7 → export)`。

Phase A 約 90 秒是軟期限，不延長 Lambda 總預算。executor 關閉時不得等待已逾期工作無限完成；每個工具沿用 C1 timeout/retry。成功結果走 `log_evidence`，錯誤、timeout、缺 key 與 fallback 皆走 `log_execution_step`。

### PrefetchOutcome

```python
{
  "question_type": "single_integration",
  "started_at": "...",
  "completed_at": "...",
  "results": [{"capability": "price", "status": "success", "evidence_id": "ev_...", "summary": "..."}],
  "missing": [{"capability": "macro", "status": "timeout", "reason": "..."}],
}
```

Phase A 只保證嘗試題目相關能力，不保證報告引用；Report coverage 由 `results` 與 `missing` 計算資料可用率。comparison 的兩幣工作必須保留 symbol 維度，禁止把單邊成功誤標為雙邊完成。

### 測試

- classifier 規則、LLM fallback 與 execution log。
- plan 的三題型快照測試及無 key 能力標記。
- bounded concurrency、90 秒軟期限、單 future timeout 與其他 future 繼續完成。
- 剩餘預算 20% 邊界、Phase A 全失敗降級及 raw 不進模型上下文。
- 三題型 prompt 必含各自專屬約束且不引入固定報告配額。
