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
4. IF 即時價格來源無法補齊至查詢結束日附近,THE price 工具 SHALL 回傳 error dict,不得以 baseline 資料冒充目前資料(R6.7)
5. THE price 與 quant 工具 SHALL 在 content_reference 與 summary 明示實際資料區間及 as_of 日期

## Pipeline Presentation 補充需求

1. WHEN price 成功取得日線資料，THE tool SHALL 在 raw 保留最多近 90 日、UTC 日期升冪且去重的 `[date, close]` 序列，並在 content_reference 標示 series 名稱、實際範圍、單位與 pair。
2. WHEN comparison 題型提供兩幣種資料，THE quant tool SHALL 以共同日期及相同 quote/unit 決定性計算相關係數與相對強弱（A close / B close）序列；不足兩個共同點 SHALL 回傳可追蹤缺口，不得補造數值。
3. THE series SHALL 僅包含 finite numeric values；零分母、缺值、重複日期與不同時區 SHALL 在工具層處理並留下 comparability note。
4. THE C1 summary SHALL 僅摘要最新值、變化與時間範圍，不得把完整 90 日 series 放入 LLM summary；完整序列只供 Evidence/Report C7。
5. WHEN Binance 與 CoinGecko fallback 的 candle 定義不同，THE relative-strength builder SHALL 拒絕無法比較的混合序列或明確標記 `comparability=limited`，不得宣稱精確優勢。
