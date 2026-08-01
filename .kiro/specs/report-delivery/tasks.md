# report-delivery 實作計畫

對應主 spec tasks.md 的 10.x、11.x。無外部依賴,可與工具模組完全平行。DoD:pytest 全綠 + 用假 evidence 渲染的樣張讓全隊審過一次(排版即賣相,商業應用性 25%)。

- [ ] 1. report.py:calculate_coverage(R12.4)
- [ ] 2. report.py:build_evidence_table(R12.2)
- [ ] 3. report.py:render_report 三章節模板 + 附錄(R12.1–12.6)
- [ ] 4. export.py:export_evidence_list JSON/CSV(R15.1)
- [ ] 5. export.py:export_execution_log JSONL(R5.3, R15.1)
- [ ] 6. export.py:validate_before_export 五項檢查 + 品質警示降級(R13.1, R13.4, R13.5)
- [ ] 7. 測試:P11/P16/P17/P18 + 孤兒引用案例
- [ ] 8. 產出 outputs/sample_run/ 範例(評審快速檢視格式用)
- [ ] 9. 檢查點:樣張全隊審查(可讀性/可採信性)

## 異常訊號擴充(docs/anomaly-signal-plan.md 第四節)
- [ ] 10. report.py:模板新增「⚡ 異常訊號」章節(市場判斷之後),支援 🔴/🟡 訊號卡 + ⚪ 已檢查無異常清單;無任何輸入時渲染常態聲明
- [ ] 11. validate_before_export:確認異常章節句式無交易建議語彙
