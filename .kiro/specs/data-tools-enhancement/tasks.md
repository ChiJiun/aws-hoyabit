# Implementation Plan: 資料工具增強 (data-tools-enhancement)

## Overview

依照 `docs/data-source-catalog.md` 的訊號價值層級排序實作，最高價值（必做）的工具先做，確保即使時間不夠，已完成的部分就是投資報酬率最高的增強。所有新工具遵循 Contract C1 回傳格式，使用統一的錯誤處理與 30 秒 timeout 模式。

實作語言：Python 3.12（與既有 codebase 一致）

## Tasks

- [x] 1. Hyperliquid 衍生品資料（Tier 1 必做 — 最高訊號價值）
  - [x] 1.1 建立 `lambda/tools/derivatives.py` 骨架與 Hyperliquid fetcher
    - 建立 `derivatives.py` 新檔案，實作 `get_derivatives()` 公開函式與 `_fetch_hyperliquid()` 內部函式
    - `get_derivatives` 接受 `symbol, source, metrics, related_claim` 參數，內部依 `source` 分派
    - Hyperliquid API：POST `https://api.hyperliquid.xyz/info` body `{"type": "metaAndAssetCtxs"}`
    - 從回傳的 assetCtxs 陣列中依 symbol 過濾取得 funding、openInterest、markPx
    - 回傳 Contract C1 格式，content_reference 含 funding_rate、open_interest_usd、mark_price、fetched_at、elapsed_ms
    - summary 格式：「資金費率 X%/8h，多頭付費/空頭付費/中性，OI $Y」
    - 失敗時回傳 error dict 附 `fallback_suggestion: "binance_futures"`
    - HTTP timeout 30 秒，User-Agent: HoyabitAgent/1.0
    - 僅 import config 與 evidence，不得 import 其他 tools 模組
    - _Requirements: 1.1, 1.3, 1.4, 1.5, 1.6, 11.1, 11.2, 11.3, 11.5, 11.6, 12.1, 12.5, 13.1_

  - [ ]* 1.2 Write property tests for Hyperliquid derivatives
    - **Property 1: Tools never raise exceptions** — 注入隨機 Exception 到 mock requests.post，驗證函式回傳 dict 不拋錯
    - **Property 2: Successful responses conform to Contract C1** — mock 有效 API 回應，驗證回傳含 raw/source/content_reference/summary
    - **Property 10: Funding rate summary includes value and direction** — 生成隨機 funding rate 數值，驗證 summary 含數值+方向
    - **Validates: Requirements 1.1, 1.3, 1.4, 1.5, 11.1, 11.3**

- [x] 2. Binance Futures 衍生品資料（Tier 1 必做 — 交叉驗證 + 散戶指標）
  - [x] 2.1 實作 `_fetch_binance_futures()` 內部函式
    - 在 `derivatives.py` 中新增 Binance Futures fetcher
    - 資金費率：GET `/fapi/v1/premiumIndex?symbol={symbol}USDT`
    - OI：GET `/fapi/v1/openInterest?symbol={symbol}USDT`
    - 大戶多空比：GET `/futures/data/topLongShortPositionRatio?symbol={symbol}USDT&period=5m&limit=1`
    - 吃單買賣比：GET `/futures/data/takerlongshortRatio?symbol={symbol}USDT&period=5m&limit=1`
    - 依 metrics 參數決定呼叫哪些 endpoint（funding_rate, open_interest, long_short_ratio, taker_buy_sell_ratio）
    - 回傳 Contract C1 格式，content_reference 含各項指標數值、elapsed_ms、fetched_at
    - 失敗回傳 error dict，HTTP timeout 30 秒
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 11.1, 11.2, 11.3, 12.1_

  - [ ]* 2.2 Write unit tests for Binance Futures fetcher
    - Mock API 回應測試 long_short_ratio 欄位正確解析
    - Mock API 回應測試 taker_buy_sell_ratio 欄位正確解析
    - 測試 timeout 與連線錯誤時回傳 error dict
    - _Requirements: 2.1, 2.2, 2.3, 2.5_

- [x] 3. Google News RSS + 媒體 RSS 新聞升級（Tier 1 必做 — 免費替換 CryptoPanic）
  - [x] 3.1 重構 `lambda/tools/news.py`：移除 CryptoPanic，改用 Google News RSS + 媒體 RSS
    - 移除對 `CRYPTOPANIC_API_KEY` 的 import 與依賴
    - 新增 Google News RSS 來源：URL 模板 `https://news.google.com/rss/search?q={query}+crypto&hl=en&gl=US&ceid=US:en`
    - 新增 `_MEDIA_RSS_FEEDS` 白名單：CoinDesk、The Block、Cointelegraph RSS URLs
    - 新增 `_SYMBOL_SEARCH_TERMS` 映射：BTC→bitcoin, ETH→ethereum 等
    - 保留既有的 `_OFFICIAL_SOURCES`、`_parse_rss_entries`、`_fetch_rss_feed`、`_fetch_github_releases` 邏輯
    - `search_news()` 內部改為：Google News RSS → 媒體 RSS → 官方 RSS + GitHub releases
    - 每則新聞加上 `channel` 欄位：`"google_news"` | `"media_rss"` | `"official_rss"` | `"github_release"`
    - 每個 RSS feed 獨立 try/except，單一 feed 失敗 skip 繼續處理
    - 回傳結果按 published_at 排序，保留重複偵測邏輯
    - 靜態驗證：檔案中不含 "CRYPTOPANIC" 或 "cryptopanic" 字串
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 11.1, 11.3, 12.1, 12.2, 13.5_

  - [ ]* 3.2 Write property tests for news upgrade
    - **Property 7: News items always have a valid channel annotation** — 生成隨機 RSS XML，驗證每則新聞含 channel 欄位且值在白名單中
    - **Property 8: RSS feed failures don't prevent partial results** — 隨機選擇 feed 子集拋出例外，驗證仍回傳成功結果
    - **Validates: Requirements 9.4, 9.6, 12.2**

- [x] 4. Polymarket 預測市場（Tier 2 強烈建議 — 創意度亮點）
  - [x] 4.1 建立 `lambda/tools/prediction.py` 實作 `get_prediction_market()`
    - 建立 `prediction.py` 新檔案
    - `get_prediction_market(keywords, related_claim)` 公開函式
    - Gamma API 搜尋：GET `https://gamma-api.polymarket.com/events?tag=crypto&active=true&closed=false&limit=10` 或 keyword search
    - 從結果中提取：title、outcomePrices（解析 JSON string）、volume、liquidity
    - 嘗試從 CLOB API 取得 7 日價格變化（失敗時略過）
    - summary 格式：「事件名稱 + 市場定價機率 + 變化方向」
    - content_reference 含 events 陣列（market_id, title, outcome_price, volume_usd, price_change_7d）
    - Contract C1 格式，失敗回傳 error dict，timeout 30 秒
    - 僅 import config 與 evidence
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 11.1, 11.2, 11.3, 12.1, 13.2_

  - [ ]* 4.2 Write unit tests for Polymarket prediction tool
    - Mock Gamma API 回應測試事件解析
    - 測試 outcomePrices JSON string 解析正確
    - 測試 API 失敗回傳 error dict
    - _Requirements: 4.1, 4.2, 4.5_

- [x] 5. Checkpoint — 核心高價值工具驗證
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Deribit 選擇權與隱含波動率（Tier 2 強烈建議 — BTC/ETH 限定）
  - [x] 6.1 實作 `_fetch_deribit()` 內部函式
    - 在 `derivatives.py` 中新增 Deribit fetcher
    - 進入分派前先驗證 symbol 必須為 BTC 或 ETH，否則直接回傳 error dict
    - DVOL：GET `/public/get_volatility_index_data?currency={currency}&start_timestamp={ms}&end_timestamp={ms}&resolution=3600`
    - 期權 OI + Put/Call 比率：GET `/public/get_book_summary_by_currency?currency={currency}&kind=option`，遍歷所有 instrument 分類 P/C 加總 OI
    - content_reference 含 dvol 數值、options_oi、put_call_ratio、fetched_at、elapsed_ms
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 11.1, 11.3, 12.1_

  - [ ]* 6.2 Write property test for Deribit symbol validation
    - **Property 5: Deribit rejects unsupported symbols** — 生成隨機非 BTC/ETH symbol，驗證回傳 error dict
    - **Validates: Requirements 3.3**

- [x] 7. DefiLlama TVL 與穩定幣供給（Tier 2 強烈建議）
  - [x] 7.1 建立 `lambda/tools/defi.py` 實作 `get_defi_data()`
    - 建立 `defi.py` 新檔案
    - `get_defi_data(metrics, chain, related_claim)` 公開函式
    - TVL：GET `https://api.llama.fi/v2/chains`（全市場各鏈 TVL）
    - 穩定幣供給：GET `https://stablecoins.llama.fi/stablecoins?includePrices=true`
    - 計算 7 日供給變化百分比（需取歷史數據對比）
    - summary 格式：「全市場 TVL $X B, 穩定幣供給 $Y B（近 7 日變化 +Z%）」
    - content_reference 含 total_tvl_usd、chain_tvl_breakdown、stablecoin_total_supply_usd、stablecoin_7d_change_pct
    - Contract C1 格式，部分失敗時回傳已取得的部分結果
    - timeout 30 秒，僅 import config 與 evidence
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 11.1, 11.3, 12.1, 13.3_

  - [ ]* 7.2 Write unit tests for DefiLlama data tool
    - Mock TVL 與 stablecoin API 回應測試正確解析
    - 測試 chain 參數過濾邏輯
    - 測試 API 失敗回傳 error dict
    - _Requirements: 7.1, 7.2, 7.5_

- [x] 8. Binance Spot 盤口深度快照（Tier 2 強烈建議 — 流動性訊號）
  - [x] 8.1 在 `lambda/tools/price.py` 新增 `get_orderbook_depth()`
    - GET `https://api.binance.com/api/v3/depth?symbol={symbol}USDT&limit=1000`
    - 計算 best_bid、best_ask
    - bid_depth_2pct = sum(qty for bids where price >= best_bid * 0.98)
    - ask_depth_2pct = sum(qty for asks where price <= best_ask * 1.02)
    - summary 格式：「買方 ±2% 深度 X BTC / 賣方 ±2% 深度 Y BTC」
    - content_reference 含 best_bid、best_ask、bid_depth_2pct、ask_depth_2pct、snapshot_timestamp、elapsed_ms
    - Contract C1 格式，失敗回傳 error dict，timeout 30 秒，limit=1000
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 11.1, 11.3, 12.1, 13.4_

  - [ ]* 8.2 Write property test for orderbook depth calculation
    - **Property 6: Orderbook depth calculation correctness** — 生成隨機 [price, qty] 對的 orderbook，驗證計算結果正確
    - **Validates: Requirements 5.2**

- [x] 9. Checkpoint — Tier 2 工具驗證
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. GitHub 開發活躍度（Tier 3 有餘裕）
  - [x] 10.1 在 `lambda/tools/defi.py` 新增 `get_dev_activity()`
    - `get_dev_activity(symbol, related_claim)` 公開函式
    - `_SYMBOL_TO_REPO` 映射表：BTC→bitcoin/bitcoin, ETH→ethereum/go-ethereum 等
    - commit 頻率：GET `/repos/{owner}/{repo}/stats/commit_activity`，取最後 4 週加總
    - 最新 release：GET `/repos/{owner}/{repo}/releases/latest`
    - summary 格式：「近 4 週 commit 數 N、最新 release: tag (日期)」
    - content_reference 含 repo、commit_count_4w、latest_release_tag、latest_release_date、elapsed_ms
    - timeout 30 秒，免鑰（unauthenticated 60 次/小時）
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 11.1, 11.3, 12.1, 13.3_

  - [ ]* 10.2 Write unit tests for GitHub dev activity
    - Mock commit_activity 與 releases API 回應
    - 測試 4 週 commit 加總正確
    - 測試 symbol 不在映射表時的錯誤處理
    - _Requirements: 8.1, 8.2, 8.5_

- [x] 11. CoinGecko 市值佔比（Tier 3 有餘裕）
  - [x] 11.1 在 `lambda/tools/price.py` 新增 `get_market_dominance()`
    - GET `https://api.coingecko.com/api/v3/global`，帶 `x-cg-demo-api-key` header（若有設定）
    - 提取 `data.market_cap_percentage`（btc, eth 等百分比）
    - 提取 `data.total_market_cap.usd`
    - summary 格式：「BTC dominance X%, ETH dominance Y%」
    - content_reference 含各幣種 dominance、total_market_cap、fetched_at、elapsed_ms
    - 若 COINGECKO_API_KEY 未設定，回傳 error dict
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 11.1, 11.3, 12.1, 13.4_

  - [ ]* 11.2 Write unit tests for market dominance
    - Mock CoinGecko global API 回應測試百分比提取
    - 測試 API key 未設定時回傳 error dict
    - _Requirements: 6.1, 6.2, 6.5_

- [x] 12. config.py 環境變數與 __init__.py 更新
  - [x] 12.1 更新 `lambda/config.py` 新增環境變數預留
    - 新增 CMC_API_KEY、COINGLASS_API_KEY、REDDIT_CLIENT_ID、REDDIT_CLIENT_SECRET、SOSOVALUE_API_KEY、DUNE_API_KEY 的 os.environ.get
    - 移除 CRYPTOPANIC_API_KEY（已不再使用）
    - 更新 `load_local_env()` 的 global 宣告
    - _Requirements: 10.5, 13.5_

  - [x] 12.2 更新 `lambda/tools/__init__.py` 匯出新模組
    - 在 __init__.py 中新增對 derivatives、prediction、defi 的說明（docstring 更新）
    - _Requirements: 13.7_

- [x] 13. Agent 工具註冊與 TOOL_DISPATCH 擴充
  - [x] 13.1 更新 `lambda/agent.py` 的 TOOL_DISPATCH 與 build_tool_config()
    - 在檔案頂部新增 `from tools import derivatives, prediction, defi`
    - TOOL_DISPATCH 新增 6 個工具映射：get_derivatives, get_prediction_market, get_defi_data, get_dev_activity, get_orderbook_depth, get_market_dominance
    - build_tool_config() 新增 6 個 toolSpec（description 含訊號價值說明）
    - 每個 toolSpec 的 inputSchema.required 都必須包含 related_claim
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 11.1_

  - [ ]* 13.2 Write property test for tool registration completeness
    - **Property 9: All tool inputSchemas require related_claim** — 遍歷 build_tool_config() 回傳，驗證每個 toolSpec 的 required 含 related_claim
    - 驗證 TOOL_DISPATCH 含全部 12 個工具名稱且值為 callable
    - **Validates: Requirements 10.3**

- [x] 14. Final checkpoint — 全工具整合驗證
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- 實作順序依 `docs/data-source-catalog.md` 的訊號價值層級：Tier 1（必做）→ Tier 2（強烈建議）→ Tier 3（有餘裕）
- 所有新工具共用統一的錯誤處理模式：最外層 try/except，回傳 error dict，記錄 elapsed_ms
- 本次所有工具完全免鑰（Hyperliquid、Binance Futures、Deribit、Polymarket、DefiLlama、GitHub、Google News RSS）
- config.py 新增的環境變數是為未來 Tier 擴充預留
- Property tests 使用 pytest + hypothesis，每個 test 至少 100 次迭代
- Checkpoints ensure incremental validation

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "3.1", "4.1"] },
    { "id": 1, "tasks": ["1.2", "2.1", "3.2", "4.2"] },
    { "id": 2, "tasks": ["2.2", "6.1", "7.1", "8.1"] },
    { "id": 3, "tasks": ["6.2", "7.2", "8.2", "10.1", "11.1"] },
    { "id": 4, "tasks": ["10.2", "11.2", "12.1", "12.2"] },
    { "id": 5, "tasks": ["13.1"] },
    { "id": 6, "tasks": ["13.2"] }
  ]
}
```
