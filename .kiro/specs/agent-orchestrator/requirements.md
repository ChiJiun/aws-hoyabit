# agent-orchestrator 需求

範圍:lambda/agent.py、lambda/handler.py、tests/test_local_run.py。編號引用主 spec。

## 承接的主 spec 需求
- **R1 請求接收與驗證**(全部):Function URL、1–2 幣種驗證、非空題目、CORS、明確錯誤回應
- **R2 Agent 主迴圈與執行控制**(全部):MAX_AGENT_TURNS + TIME_BUDGET_SECONDS 雙終止條件、15 分鐘 Lambda 逾時、reset_stores
- **R3 LLM 推理與工具呼叫**(全部):Bedrock Converse、tool_use/end_turn 分流、事實→推論→結論 system prompt、禁投資建議、toolResult 只回 summary+evidence_id
- **R14 收尾報告整理**(全部):第二次無工具 Bedrock 呼叫做三段式整理
- **R16 題型支援**(全部):多源整合/假設驗證/比較分析
- **R21 本機測試**(全部):本機進入點 + 5 幣種 × 3 題型整合測試

## 本模組補充驗收條件
1. THE agent SHALL 只透過契約 C1 的統一格式認識工具,新增工具僅需註冊 TOOL_DISPATCH + toolSpec,不改迴圈邏輯
2. WHEN 時間預算剩餘 < 20%,THE agent SHALL 於下一輪 system 提示中要求模型停止蒐集、開始收斂
3. WHEN Bedrock 回傳 ThrottlingException,THE agent SHALL 等待 2 秒重試一次,再失敗則以現有內容收斂
4. WHEN 題目涉及目前/近期/短期/當前,THE agent SHALL 將目前 UTC 日期、價格查詢起訖日與新聞 lookback_days 明確注入模型上下文(R3.7)
