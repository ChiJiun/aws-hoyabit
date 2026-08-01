# market-data-tools 實作計畫

對應主 spec tasks.md 的 2.x、3.x。DoD:pytest 全綠 + 五幣種本機實測一輪 + 回傳完全符合契約 C1。

- [ ] 1. quant.py:calc_percentile_rank(共用轉換,先做)(R11.3)
- [ ] 2. quant.py:calc_atr_pct / calc_bollinger_bandwidth / calc_adx / volume_zscore / realized_vol(R11.1, R11.2)
- [ ] 3. quant.py:calc_correlation 雙幣種(R11.4)
- [ ] 4. quant.py:compute_quant 主函式,統一 C1 格式 + error dict(R11.5, R20)
- [ ] 5. price.py:fetch_recent_from_exchange(Binance 日線)(R6.3)
- [ ] 6. price.py:check_data_seam 接縫校驗(R6.4)
- [ ] 7. price.py:get_price_ohlcv 主函式(baseline→補齊→拼接→篩選;CoinGecko 備援)(R6.1–6.6, R20)
- [ ] 8. 測試:P12/P14/P15 + 接縫警告 + 五幣種煙霧測試
- [ ] 9. 檢查點:與 agent-orchestrator 對齊 toolSpec 參數命名

## 異常訊號擴充(docs/anomaly-signal-plan.md 表 A1–A5)
- [ ] 10. quant.py:detect_price_anomalies(量能 Z-score、帶寬壓縮/爆發、ATR 極端、ADX 極端、報酬率極端),門檻讀 config.ANOMALY_THRESHOLDS,結果放入回傳的 anomaly_flags
- [ ] 11. 測試:各門檻邊界案例 + 無異常時 anomaly_flags 為空列表
