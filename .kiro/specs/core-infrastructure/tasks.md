# core-infrastructure 實作計畫

對應主 spec tasks.md 的 1.x 與 12.x。完成定義(DoD):pytest 全綠 + 介面與 contracts.md C2/C3/C6 完全一致 + 通知全隊介面凍結。

- [ ] 1. config.py:Settings 集中管理 + load_local_env + missing_vars(R19.1, R19.2)
- [ ] 2. evidence.py:reset_stores(R2.6)
- [ ] 3. evidence.py:log_evidence 四欄位 + related_claim 驗證 + UUID + raw 封存(R4.1–4.6)
- [ ] 4. evidence.py:log_execution_step 成功/失敗皆記錄(R5.1, R5.2)
- [ ] 5. storage.py:read_baseline_csv 含本機 fallback(R18.1)
- [ ] 6. storage.py:save_raw_payload / save_output_file(R4.6, R18.2)
- [ ] 7. storage.py:generate_download_link presigned 1hr(R18.3, R18.4)
- [ ] 8. 測試:屬性測試 P4/P7/P8/P9/P10(tests/test_evidence.py、test_storage.py)
- [ ] 9. 檢查點:介面凍結公告,更新 contracts.md 若有偏差(需全隊同意)
