# 工具能力與資料品質矩陣

## 一、文件目的

本文件是「資料工具與品質負責人」交付物，記錄：

- 每個工具的能力、來源、時效、單位與相容性。
- C1 v1.0 遷移狀態。
- timeout、rate limit、fallback 與失敗行為。
- 公開來源 live smoke 結果。
- 主動交易者第一個 BTC 垂直切片的可用範圍。

共同格式見 [tool-result-contract.md](./tool-result-contract.md)，產品用途見 [active-trader-information-product.md](./active-trader-information-product.md)，異常門檻見 [anomaly-signal-plan.md](./anomaly-signal-plan.md)。

## 二、工具能力矩陣

| 能力／入口 | 模組 | 主來源 | 備援 | 時間粒度／Freshness | 單位 | C1 v1.0 | 異常 | 主要限制 |
|---|---|---|---|---|---|---|---|---|
| 日線 OHLCV `get_price_ohlcv` | price | baseline + Binance Spot | CoinGecko | 1d；最多 3 日 | USD、base asset volume | ✅ | A5 | CoinGecko 日內點位聚合 OHLC 與交易所原生日 K 可比性有限 |
| 技術指標 `compute_quant` | quant | 本地 pandas | 無 | 跟隨價格；最多 3 日 | %、index、z-score、correlation | ✅ | A1–A4 | 價格失敗即無法計算；相關係數需相同視窗 |
| Order book `get_orderbook_depth` | price | Binance Spot | 無 | snapshot；60 秒 | USD、base asset depth | ✅ | — | 單一交易所快照不代表全市場流動性 |
| 市場市佔 `get_market_dominance` | price | CoinGecko | 無 | snapshot；1 日 | %、USD | ✅ | — | 聚合供應商口徑，不等同交易所資金流 |
| Funding／OI `get_derivatives` | derivatives | Hyperliquid | Binance Futures | snapshot；5 分鐘 | rate/8h、USD／contracts | ✅ | 供 Agent 做跨源背離 | OI 與比率只代表所選交易所；跨所不可直接等值比較 |
| 期權 DVOL／OI | derivatives | Deribit | 無 | snapshot；5 分鐘 | %、contracts、ratio | ✅ | 供 Agent 比對 realized vol | 僅 BTC／ETH；DVOL 與現貨實現波動口徑不同 |
| 新聞／官方事件 `search_news` | news | Google News + 媒體 + 官方 + GitHub | 任一成功來源降級 | event；題目 lookback，最長 14 日 | articles、UTC | ✅ | A7、A8 | 通稿轉載不可視為獨立來源；缺發布時間即排除 |
| 鏈上 `get_onchain` | onchain | 依鏈分派 | 無統一 fallback | 依 provider | 各鏈原生單位 | 舊 C1，待遷移 | A9 待完成 | 不同鏈時間窗／計數口徑不可直接比較絕對值 |
| 情緒 `get_sentiment` | sentiment | alternative.me | 無 | 日；建議 1 日 | index 0–100 | 舊 C1，待遷移 | A6 待完成 | 市場總體指標，非單一幣種情緒 |
| 總經 `get_macro` | macro | FRED | 無 | 日／低頻發布；建議 3 日並註明頻率 | 依序列 | 舊 C1，待遷移 | A10 待完成 | 需 API key；週末／假日及發布延遲不能誤判 stale |
| 預測市場 | prediction | Polymarket | keyword → crypto tag | snapshot | probability | 部分自有 retry，待 C1 遷移 | — | 市場流動性與題目匹配度需揭露 |
| DeFi／穩定幣 | defi | DefiLlama | 部分結果可降級 | 日／snapshot | USD | 舊 C1，待遷移 | — | 鏈與幣種映射不一定一對一 |
| 開發活動 | defi | GitHub | 無 | event／週期統計 | commits/releases | 舊 C1，待遷移 | — | 開發活躍不等同短期價格催化 |
| CFTC／SEC／Coin Metrics | institutional | 各官方／社群 API | 部分 metric fallback | 週／event／日 | 依來源 | 舊 C1，待遷移 | — | CFTC 僅 BTC；資料發布頻率低；不可當即時訊號 |

## 三、公開來源 Live Smoke

### 測試方式

- 時間：2026-08-01 UTC（本機執行）。
- 每來源 3 次低頻、序列化請求；timeout 10 秒。
- 只送固定 BTC／公開 endpoint 查詢，未讀取或傳送任何本機 API key。
- `observed error rate` 只是 3 次樣本，不是 SLA，也不能取代賽前長時間監控。

| 來源 | 成功／樣本 | 觀察錯誤率 | p50 | max | 可見額度／header | 結果 |
|---|---:|---:|---:|---:|---|---|
| Binance Spot | 3/3 | 0% | 205 ms | 319 ms | `x-mbx-used-weight-1m=3` | 通過 |
| CoinGecko | 3/3 | 0% | 418 ms | 461 ms | 本次未回傳 rate-limit header | 通過 |
| Hyperliquid | 3/3 | 0% | 341 ms | 356 ms | 本次未回傳 rate-limit header | 通過 |
| Binance Futures | 3/3 | 0% | 208 ms | 276 ms | `x-mbx-used-weight-1m=3` | 通過 |
| Deribit | 3/3 | 0% | 440 ms | 484 ms | 本次未回傳 rate-limit header | 通過 |
| Google News RSS | 3/3 | 0% | 350 ms | 514 ms | 本次未回傳 rate-limit header | 通過 |
| GitHub Releases（未驗證） | 3/3 | 0% | 318 ms | 473 ms | limit 60，測試後 remaining 54 | 通過 |
| mempool.space | 3/3 | 0% | 354 ms | 457 ms | 本次未回傳 rate-limit header | 通過 |
| alternative.me | 3/3 | 0% | 821 ms | 900 ms | 本次未回傳 rate-limit header | 通過，為本次最慢來源 |
| DefiLlama | 3/3 | 0% | 251 ms | 423 ms | 本次未回傳 rate-limit header | 通過 |

### 未執行的金鑰來源

| 來源 | 原因 | 部署前動作 |
|---|---|---|
| FRED | 需 API key；本次不讀取或傳送本機秘密 | 在正式 Lambda 環境以最小序列 query 驗證，記錄延遲與錯誤碼 |
| Etherscan | 需 API key | 依 ETH 測試案例驗證額度與 V2 endpoint |
| Helius | 需 API key | 依 SOL 測試案例驗證 RPC 額度 |
| 其他付費／選用來源 | 非 BTC MVP 必要能力 | 只有完成授權、成本與 fallback 評估後才啟用 |

## 四、Timeout、Rate Limit 與錯誤分類

### 共用政策

- 預設 timeout 15 秒；舊 collector 明確傳入 30 秒時保留 30 秒。
- 最多 2 次嘗試。
- 只重試 timeout、connection error、429、500、502、503、504。
- `Retry-After` 最多等待 2 秒，避免單一來源吃掉整體 15 分鐘預算。
- 400、401、403、404 及資料驗證錯誤不重試。
- `price`、`derivatives`、`news` 已透過 `RetryingRequestsFacade` 套用政策。
- 重試測試完全使用 mock，不對外製造 429／5xx。

### 錯誤類型與處理

| 類型 | 是否重試 | 是否 fallback | C1 結果 |
|---|---|---|---|
| Timeout／ConnectionError | 是，最多一次 | 有備援能力時使用 | fallback 成功為 success/partial；否則 error |
| HTTP 429 | 是，遵循受限 Retry-After | 有備援能力時使用 | 同上，reliability.rate_limited=true |
| HTTP 5xx | 是，最多一次 | 有備援能力時使用 | 同上 |
| HTTP 4xx（429 除外） | 否 | 只有明確資料源備援才使用 | error 或 fallback 結果 |
| JSON／XML 格式錯誤 | 否 | 新聞可跳過單一 feed | partial 或 error |
| 資料過期 | 否 | 價格可嘗試即時備援 | stale 或拒絕冒充目前資料 |
| 單位／視窗不可比 | 否 | 不替換資料 | success/partial + comparability 限制 |
| 原始資料封存失敗 | 不重試於 Evidence 層 | 不丟失 Evidence record | archive_status=failed + Execution Log |

## 五、Fallback 與失敗案例

### 價格

1. 先讀 baseline。
2. 查詢超過 baseline 截止日時呼叫 Binance Spot。
3. Binance 失敗或空資料時改用 CoinGecko。
4. 兩者都失敗時回 error，禁止只用舊 baseline 冒充目前價格。
5. 最新資料距查詢結束日超過 3 日時標示 stale／拒絕目前性宣稱。

### 衍生品

1. `source=hyperliquid` 先取得 Hyperliquid funding／OI。
2. 主來源 error 時，自動以相容 metrics 呼叫 Binance Futures。
3. fallback 成功後 provider 必須是 Binance Futures，並保存 `primary_source_error`。
4. 兩者都失敗才回 error；errors 保留在 reliability。
5. 不把 Hyperliquid OI 與 Binance OI 當成同一母體直接比較。

### 新聞與事件

1. Google News、三個媒體 RSS、官方 RSS、GitHub release 獨立取得。
2. 單一 feed 失敗不終止整體流程。
3. 只保留有可解析時間且在 lookback 內的項目。
4. Google News 失敗但其他來源成功時標記 fallback／partial。
5. 以 domain family 與標題相似度標記通稿重複。
6. 所有來源都沒有可驗證資料時回 error，不產生虛構事件摘要。

## 六、資料相容性說明

| 情境 | 可否直接比較 | 規則 |
|---|---|---|
| Binance 與 CoinGecko 日線 | 有限 | 比較方向可用；OHLC 聚合與 volume 口徑需揭露 |
| Hyperliquid 與 Binance funding | 有限 | 必須先統一 funding 週期（本工具顯示 8h） |
| 不同交易所 OI | 不可直接加總或排名 | 合約面值、標的與市場覆蓋不同 |
| Order book 深度與成交量 | 不可互相替代 | 一者是快照流動性，一者是期間成交 |
| ETH 區塊交易數與 SOL 分鐘交易數 | 不可直接比較 | 需相同時間窗與明確定義後才可比較變化率 |
| 新聞文章數 | 有限 | 必須去除同源通稿，來源數不等於獨立證據數 |
| DVOL 與 realized volatility | 可比較差值但非同一指標 | 需標示一者隱含、一者歷史實現及各自視窗 |
| 低頻總經序列與即時市場快照 | 有限 | 資料發布頻率需納入 freshness 解釋 |

## 七、BTC 第一垂直切片完成狀態

| 資料鏈 | 必要能力 | 狀態 | 測試 |
|---|---|---|---|
| 價格／技術 | OHLCV、拼接、freshness、A1–A5 | 完成 | price/quant 既有測試 + `test_btc_vertical_slice_quality.py` |
| 衍生品／流動性 | funding、OI、order book、fallback | 完成 | fallback 成功／雙失敗／C1 metadata |
| 事件催化 | 多來源新聞、官方事件、A7/A8 | 完成 | 密度與重大事件、全來源失敗 graceful error |
| Evidence | 完整 ID、quality、raw envelope、SHA-256 | 完成 | `test_evidence_traceability.py` |
| Reliability | timeout、429/5xx、有限重試 | 完成於三類 HTTP 工具 | `test_tool_quality.py` |

## 八、後續遷移優先序

1. `onchain.py`：補齊 as_of、window、unit、provider、endpoint、freshness、comparability，實作 A9。
2. `sentiment.py`：補 A6 及 1 日 freshness。
3. `macro.py`：處理低頻發布日曆，避免週末誤判 stale，實作 A10。
4. `prediction.py`、`defi.py`、`institutional.py`：統一改用共用 reliability 與 C1 metadata。
5. 建立定時 canary 或賽前 smoke，累積足夠樣本後再報告實際錯誤率與 p95；目前三次樣本只能證明當下可達。
