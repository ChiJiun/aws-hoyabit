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

## Pipeline Presentation 補充需求

1. THE Orchestrator SHALL 將每次請求正規化為 `single_integration`、`hypothesis` 或 `comparison`；兩幣種請求 SHALL 決定為 comparison，單幣種規則無法判定時才允許 LLM 兜底，並將結果與判定方法寫入 execution log。
2. BEFORE Agent_Loop，THE Orchestrator SHALL 依題型、幣種與可用設定建立可檢視的 Phase A `prefetch_plan`，每個項目包含 capability、tool、symbols、reason、required/optional 與 timeout。
3. THE Phase A common plan SHALL 覆蓋價格/quant、衍生品、情緒、近期新聞、對應鏈上與核心總經；single/hypothesis/comparison 的額外項目 SHALL 遵循 pipeline plan 的題型矩陣。缺少 API key 的能力 SHALL 標記 unavailable，而非阻斷整批。
4. WHEN 執行 Phase A，THE Orchestrator SHALL 使用 bounded concurrency、約 90 秒軟期限與單工具失敗隔離；每個成功/失敗/timeout SHALL 寫 execution log，成功結果 SHALL 透過既有 Evidence API 記錄。
5. THE Orchestrator SHALL 將 Phase A 精簡摘要、anomaly flags、缺口與 evidence_id 注入 Phase B，不將 raw payload 注入模型上下文。
6. DURING Phase B，THE Agent SHALL 依題目語意與 Phase A 缺口自主選擇追查，並受 MAX_AGENT_TURNS、TIME_BUDGET_SECONDS 與可設定補洞輪次上限約束。
7. WHEN 剩餘總時間預算低於 20%，THE Orchestrator SHALL 停止接受新的補洞工具呼叫並進入 summarize；此狀態 SHALL 寫 execution log。
8. THE Phase A plan SHALL NOT 成為固定報告分母、來源配額或強迫引用清單；只有題目相關且品質可用的結果可進入推理。
9. THE 題型 prompt SHALL 要求：single 產出題目相關維度狀態與整體一致性；hypothesis 將證據分類為支持/反對/中性；comparison 在相同維度量化比較並產出相關係數、相對強弱與條件式關注說明。
10. WHEN Phase A 全部失敗，THE Orchestrator SHALL 仍允許 Phase B 在剩餘預算內嘗試相關 fallback，最終以低信心/資料不足收斂，不得拋出未處理例外。

11. WHEN 任一 Phase A 或 Phase B 工具成功回傳 documented series，THE Orchestrator SHALL 在 raw 封存後將正規化近 90 日序列寫入 request-scoped series registry，且只把 summary/evidence_id 傳給 LLM；報告階段 SHALL 將 registry 傳入 build_report_data，請求結束時 SHALL 清空 registry。
