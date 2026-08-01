# market-data-tools 需求

範圍:lambda/tools/price.py、lambda/tools/quant.py。編號引用主 spec。

## 承接的主 spec 需求
- **R6 價格與 OHLCV**(全部):baseline CSV 優先、超過 2026-05-31 用 Binance 補、接縫校驗、CoinGecko 備援、失敗回 error dict
- **R11 技術指標計算**(全部):pandas 決定性計算 ATR%、布林帶寬、ADX、成交量 Z-score、已實現波動率、相關係數;每指標附歷史百分位;比較題支援雙幣種相關係數
- **R20 工具回傳格式統一**(全部):契約 C1

## 本模組補充驗收條件
1. WHEN baseline 與即時資料重疊日收盤價差 > 1%,THE price 工具 SHALL 於 content_reference 標註校驗警告
2. THE quant 工具 SHALL 只接受 DataFrame 輸入或內部呼叫 price 取數,不得自行呼叫外部 API 以外的來源
3. WHEN 資料筆數不足以計算指定 window,THE quant 工具 SHALL 回傳 error dict 說明所需最小筆數
