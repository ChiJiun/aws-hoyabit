# intel-data-tools 設計

## 定位
質性資訊來源(新聞/鏈上/情緒/總經)。四個檔案完全獨立,**可由不同人平行開發**,彼此不 import。
依賴:僅 config(金鑰)。回傳一律契約 C1。

## news.py
- `search_news(symbol, lookback_days, related_claim)`
- CryptoPanic(currencies 參數)+ fetch_official_announcements(依幣種分派:bitcoin.org / blog.ethereum.org / solana.com / bnbchain.org / ripple.com + GitHub releases)
- 同源標註:以 domain 分組,同組多篇標 same_family=true

## onchain.py
- `get_onchain(symbol, metrics, related_claim)`;match/case 按幣種分派
- BTC: mempool.space(免鑰)|ETH: Etherscan V2(鑰)|BNB: Blockscout(免鑰)|SOL: Helius(鑰)|XRP: XRPL JSON-RPC(免鑰)
- ETH/BNB 解析邏輯共用(fetch_evm_onchain)

## sentiment.py
- `get_sentiment(lookback_days, related_claim)`;alternative.me API,回傳當前值+分級文字+近 N 天走勢

## macro.py
- `get_macro(series_ids, related_claim)`;FRED API;附 fetch_upcoming_events(FOMC/CPI 日程)

## 共通實作規範
- requests timeout=10、最多 1 次重試;任何失敗 → `{"error": ...}`(P12)
- content_reference 必可回溯:endpoint + 查詢參數 + 時間範圍(評審抽查項目)
- summary 精簡(防 context 膨脹,契約 C1)

## 測試重點
P5 幣種分派正確|P12 永不拋錯(五鏈 × 失敗情境)|同源標註|content_reference 完整性
