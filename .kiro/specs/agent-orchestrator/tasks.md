# agent-orchestrator 實作計畫

對應主 spec tasks.md 的 9.x、14.x、16.x。**依賴:core-infrastructure 凍結 + 各工具至少有 stub。**DoD:本機整合測試 3 案例通過 + 部署後 Function URL 實測一輪 + 15 分鐘時限演練。

- [x] 1. agent.py:SYSTEM_PROMPT(三層推理/禁投資建議/evidence_id 引用紀律)(R3.4, R3.5)
- [x] 2. agent.py:build_tool_config,related_claim 全部 required(R3.1, R4.3)
- [x] 3. agent.py:call_bedrock 含 Throttling 重試(R3.1)
- [x] 4. agent.py:dispatch_tool_call(計時/記錄/summary+evidence_id)(R3.2, R3.6, R5)
- [x] 5. agent.py:run_agent_loop(雙終止條件 + 收斂指令注入)(R2.1–2.4, R3.3)
- [x] 6. agent.py:summarize_final_analysis 三段式收尾(R14.1)
- [x] 7. handler.py:parse_request + generate_run_id(R1.2–1.5)
- [x] 8. handler.py:lambda_handler 全流程串接 + CORS + 外層錯誤處理(R1.1, R1.6, R2.5, R15)
- [x] 9. handler.py:本機測試進入點(R21.1, R21.2)
- [x] 10. tests/test_local_run.py:5 幣種 × 3 題型組合 + 總表輸出(R21.3)
- [x] 11. 單元測試:P1/P2/P3/P5/P6(mock Bedrock)
- [ ] 12. 檢查點:計時演練 — 完整執行需 < 12 分鐘(留 3 分鐘緩衝)

## 異常訊號擴充(docs/anomaly-signal-plan.md 表 B、C)
- [ ] 13. SYSTEM_PROMPT:加入跨源背離檢查清單 B1–B6,要求逐項回答 有/無/資料不足,判定必引用兩側 evidence_id
- [ ] 14. SYSTEM_PROMPT:訊號分級規則(🔴/🟡/⚪)與「異常訊號 ≠ 交易建議」措辭紀律

## 管線與呈現規劃增補(docs/pipeline-presentation-plan.md)
- [ ] 15. 題型判別:規則優先(2 幣=comparison;含「認為/觀點/驗證」類詞=hypothesis;其餘 single),LLM 兜底,結果入 execution_log
- [ ] 16. Phase A 保底預抓:依題型×幣種矩陣並行抓必備組(ThreadPool);約 90 秒軟期限到達時取消尚未開始的 futures、將未完成項目記為 timeout/cancelled 後立即進 Agent 迴圈,executor 不得 block 等待
- [ ] 17. 題型專屬 prompt 模板(single 五維度/hypothesis 三欄證據/comparison 量化對比)


- [ ] 18. Phase B 補洞控制:注入 Phase A 摘要/缺口,每輪檢查剩餘預算,<20% 拒絕新工具並記 convergence log
- [ ] 19. 兩階段測試:三題型 plan snapshot、bounded concurrency、90 秒軟期限、單工具失敗隔離、全失敗低信心降級
- [ ] 20. Series bridge:Phase A/B 成功結果封存 raw 後依 capability 寫入 request-scoped registry,報告前 collect_series 傳入 build_report_data,finally 清空；測試 raw 不進 LLM context
