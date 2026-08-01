# core-infrastructure 實作計畫

對應主 spec tasks.md 的 1.x 與 12.x。完成定義(DoD):pytest 全綠 + 介面與 contracts.md C2/C3/C6 完全一致 + 通知全隊介面凍結。

- [x] 1. config.py:Settings 集中管理 + load_local_env + check_required_env(R19.1, R19.2)
- [x] 2. evidence.py:reset_stores(R2.6)
- [x] 3. evidence.py:log_evidence 四欄位 + related_claim 驗證 + UUID + raw 封存(R4.1–4.6)
- [x] 4. evidence.py:log_execution_step 成功/失敗皆記錄(R5.1, R5.2)
- [x] 5. storage.py:read_baseline_csv 含本機 fallback(R18.1)
- [x] 6. storage.py:save_raw_payload / save_output_file(R4.6, R18.2)
- [x] 7. storage.py:generate_download_link presigned 1hr(R18.3, R18.4)
- [x] 8. 測試:屬性測試 P4/P7/P8/P9/P10(tests/test_evidence.py + test_config.py)
- [x] 9. 檢查點:介面凍結,contracts.md C2/C3/C6 一致確認完成

## 異常訊號擴充
- [x] 10. config.py:ANOMALY_THRESHOLDS 集中管理(docs/anomaly-signal-plan.md 表 A 的門檻,賽前可調)

## 管線與呈現規劃增補
- [ ] 11. C7 report_data schema 欄位常數與齊備性驗證函式(供 report/handler 共用)


- [ ] 12. 新增 report_schema.py:必要欄位/enum/題型條件/evidence 外鍵/series/coverage 驗證,回傳結構化 errors 且 import 零副作用
- [ ] 13. C7 validator 測試:invalid fixtures、未知 extension、輸入不變性、never-raises property 與 90 日日期邊界
