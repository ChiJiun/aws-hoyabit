# intel-data-tools 實作計畫

對應主 spec tasks.md 的 4.x–7.x。四個檔案可四人平行。DoD:各工具獨立煙霧測試通過 + mock 失敗情境回 error dict + C1 契約檢查通過。

- [ ] 1. sentiment.py:get_sentiment(最簡單,先做熟悉契約)(R9)
- [ ] 2. macro.py:get_macro + fetch_upcoming_events(R10)
- [ ] 3. news.py:CryptoPanic 查詢(R7.1)
- [ ] 4. news.py:官方公告(五幣種來源分派)+ 同源標註(R7.2, R7.3)
- [ ] 5. onchain.py:fetch_btc(mempool.space)+ fetch_evm(Etherscan V2/Blockscout 共用)(R8.1–8.3)
- [ ] 6. onchain.py:fetch_sol(Helius)+ fetch_xrp(XRPL)(R8.4, R8.5)
- [ ] 7. onchain.py:get_onchain 分派主函式(R8.6, R8.7)
- [ ] 8. 測試:P5/P12 + mock 各 API 失敗 + content_reference 欄位齊備
- [ ] 9. 檢查點:四工具 summary 長度抽查(context 預算)
