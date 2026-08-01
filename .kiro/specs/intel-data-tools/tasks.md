# intel-data-tools 實作計畫

對應主 spec tasks.md 的 4.x–7.x。四個檔案可四人平行。DoD:各工具獨立煙霧測試通過 + mock 失敗情境回 error dict + C1 契約檢查通過。

- [x] 1. sentiment.py:get_sentiment(最簡單,先做熟悉契約)(R9)
- [x] 2. macro.py:get_macro + fetch_upcoming_events(R10)
- [x] 3. news.py:Google News RSS + 媒體 RSS 白名單查詢(R7.1,免費來源替代 CryptoPanic)
- [x] 4. news.py:官方公告(五幣種來源分派)+ 同源標註(R7.2, R7.3)
- [x] 5. onchain.py:fetch_btc(mempool.space)+ fetch_evm(Etherscan V2/Blockscout 共用)(R8.1–8.3)
- [x] 6. onchain.py:fetch_sol(Helius)+ fetch_xrp(XRPL)(R8.4, R8.5)
- [x] 7. onchain.py:get_onchain 分派主函式(R8.6, R8.7)
- [x] 8. 測試:P5/P12 + mock 各 API 失敗 + content_reference 欄位齊備
- [x] 9. 檢查點:四工具 summary 長度抽查(context 預算)

## 異常訊號擴充(docs/anomaly-signal-plan.md 表 A6–A10)
- [x] 10. sentiment.py:F&G 極端值/7 日急變 flag(A6)
- [x] 11. news.py:新聞密度突增(A7)+ 重大官方事件關鍵字(A8)
- [x] 12. onchain.py:活躍度偏離 30 日均 ±30%(A9)
- [x] 13. macro.py:DXY/殖利率 20 日變化極端(A10)
- [ ] 14. 測試:各 flag 觸發與不觸發案例

## 衍生品與市場共識擴充(docs/data-source-catalog.md Tier 1–2)
- [ ] 15. tools/derivatives.py:get_derivatives(symbol)— Hyperliquid 資金費率/OI(主)+ Binance Futures(備援)+ Coinglass 清算/多空比(有鑰時);flag:費率極端、OI 急變、大規模清算
- [ ] 16. tools/prediction.py:get_prediction_markets(symbol)— Polymarket Gamma API 相關事件市場機率與 7 日變化
- [ ] 17. DefiLlama 穩定幣供給/TVL 併入 onchain.py 或獨立小函式
- [ ] 18. agent-orchestrator 同步:兩個新工具註冊 toolSpec + TOOL_DISPATCH(通知該模組負責人)


## Pipeline Presentation Series
- [ ] 19. 非價格 series envelope:funding/OI、stablecoin supply/TVL、events/watchlist 統一 points + unit/provider/scope metadata
- [ ] 20. 部分成功降級:歷史 series 失敗時保留 snapshot,quality 記 partial failure/series_unavailable
- [ ] 21. Series fixtures:排序/去重/finite/90 日裁切、跨交易所不可比、缺 key、事件日期與 human URL
