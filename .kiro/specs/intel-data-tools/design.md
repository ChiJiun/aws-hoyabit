# intel-data-tools 設計

## 定位
質性資訊來源(新聞/鏈上/情緒/總經)。四個檔案完全獨立,**可由不同人平行開發**,彼此不 import。
依賴:僅 config(金鑰)。回傳一律契約 C1。

## news.py
- `search_news(symbol, lookback_days, related_claim)`
- Google News RSS(q="<幣種名> crypto",when:7d)+ 媒體 RSS 白名單 + fetch_official_announcements(依幣種分派:bitcoin.org / blog.ethereum.org / solana.com / bnbchain.org / ripple.com + GitHub releases)
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


## Pipeline Presentation 設計增補

### 統一 series envelope

非價格工具在 raw 中可選提供：

```python
"series": {
  "funding": {"points": [[timestamp, value]], "unit": "%/8h", "provider": "Hyperliquid"},
  "open_interest": {"points": [[timestamp, value]], "unit": "USD"},
  "stablecoin_supply": {"points": [[date, value]], "unit": "USD", "scope": "chain"},
  "events": [{"date": "2026-08-18", "event": "FOMC", "source_url": "..."}],
}
```

共用 adapter 負責 UTC 正規化、排序、去重、finite 過濾、近 90 日裁切與 metadata；provider collector 只負責抓取。Funding 不同 interval 必須先以原單位保留，不在 adapter 靜默年化。OI 不同交易所不可相加，comparison 必須保留 provider 維度。

歷史 endpoint 與 snapshot endpoint 分開 try/except：歷史失敗時回 `status=success/partial`、snapshot 與 `quality.reliability.partial_failures`，讓 Agent/Report 顯示序列缺口而非遺失整筆證據。Event items 必須有 human URL 或明確 technical source，watchlist 只搬運未來或題目窗口內事件。

測試以 provider fixtures 驗證 envelope、單位、排序、90 日裁切、歷史失敗/snapshot 成功、跨交易所不可比與缺 API key 降級。
