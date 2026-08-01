# 需求文件：資料工具增強

## 簡介

本功能擴充現有 `lambda/tools/` 的資料蒐集工具，依照 `docs/data-source-catalog.md` 所規劃的訊號價值層級，新增衍生品與槓桿數據（Tier 1）、預測市場（Tier 2）、市場結構深化（Tier 3）、DeFi 與開發活躍度（Tier 4）、以及新聞來源升級（Tier 5）。所有新增工具遵循契約 C1 回傳格式，並在 `agent.py` 中註冊供 Agent 自主呼叫。

## 詞彙表

- **Derivatives_Tool**: 衍生品資料蒐集工具，負責取得資金費率、未平倉量、清算、隱含波動率等衍生品市場數據
- **Hyperliquid_API**: Hyperliquid DEX 的公開 REST API，提供永續合約資金費率、OI、標記價格、清算資料（完全免鑰）
- **Binance_Futures_API**: Binance 合約公開 API，提供資金費率、OI、大戶多空比、吃單多空比（免鑰）
- **Deribit_API**: Deribit 公開 API，提供 DVOL 隱含波動率指數、期權 OI、Put/Call 比率（免鑰，僅 BTC/ETH）
- **Polymarket_API**: Polymarket 的 Gamma/CLOB 公開 API，提供加密相關事件市場價格與成交量（免鑰）
- **DefiLlama_API**: DefiLlama 公開 API，提供 TVL、穩定幣供給量、鏈間資金流（免鑰）
- **Order_Book_Depth**: Binance Spot 盤口深度快照，用於計算 ±2% 價位的流動性（買賣掛單量）
- **Market_Dominance**: 特定幣種市值佔加密市場總市值的百分比，反映資金輪動趨勢
- **Funding_Rate**: 永續合約資金費率，正值表示多方付費給空方（多頭擁擠），負值反之
- **Open_Interest**: 未平倉合約量，反映市場槓桿規模
- **DVOL**: Deribit 隱含波動率指數，類似 VIX，衡量選擇權市場對未來波動的定價
- **Google_News_RSS**: Google News 提供的關鍵字 RSS 聚合服務，可依 query 取得多家媒體新聞（免鑰）
- **Media_RSS**: CoinDesk、The Block、Cointelegraph 等一手媒體的 RSS feed（免鑰）

---

## 需求

### 需求 1：Hyperliquid 衍生品資料

**使用者故事：** 身為主動交易者，我希望系統能取得 Hyperliquid 的資金費率、未平倉量與清算資料，以識別槓桿過度堆積或去槓桿完成等關鍵訊號。

#### 驗收條件

1. WHEN Agent 呼叫 get_derivatives 工具並指定 symbol 與 source 為 "hyperliquid"，THE Derivatives_Tool SHALL 從 Hyperliquid_API 取得該幣種的即時資金費率、未平倉量（OI）、標記價格
2. WHEN Agent 呼叫 get_derivatives 工具並指定 metrics 包含 "liquidations"，THE Derivatives_Tool SHALL 從 Hyperliquid_API 取得近期清算事件資料
3. THE Derivatives_Tool SHALL 在 content_reference 中包含 API endpoint、查詢參數、資料時間戳、資金費率數值、OI 數值
4. THE Derivatives_Tool SHALL 在 summary 中以「數值 + 方向含義」格式呈現資金費率（例如「資金費率 0.08%/8h，多頭付費，表示多方擁擠」）
5. IF Hyperliquid_API 呼叫失敗或逾時，THEN THE Derivatives_Tool SHALL 回傳包含錯誤說明的 error dict 而非拋出未處理的例外
6. THE Derivatives_Tool SHALL 設定 HTTP 請求逾時為 30 秒

---

### 需求 2：Binance Futures 衍生品資料

**使用者故事：** 身為主動交易者，我希望系統能取得 Binance Futures 的資金費率、OI、大戶多空比與吃單比，以交叉驗證 Hyperliquid 資料並取得散戶行為訊號。

#### 驗收條件

1. WHEN Agent 呼叫 get_derivatives 工具並指定 source 為 "binance_futures"，THE Derivatives_Tool SHALL 從 Binance_Futures_API 取得該幣種的資金費率與未平倉量
2. WHEN Agent 呼叫 get_derivatives 工具並指定 metrics 包含 "long_short_ratio"，THE Derivatives_Tool SHALL 從 Binance_Futures_API 取得大戶持倉多空比（topTraderLongShortRatio）
3. WHEN Agent 呼叫 get_derivatives 工具並指定 metrics 包含 "taker_buy_sell_ratio"，THE Derivatives_Tool SHALL 從 Binance_Futures_API 取得吃單買賣比（takerBuySellVol）
4. THE Derivatives_Tool SHALL 在 content_reference 中包含 API endpoint、symbol、period、各項數值
5. IF Binance_Futures_API 呼叫失敗或逾時，THEN THE Derivatives_Tool SHALL 回傳包含錯誤說明的 error dict 而非拋出未處理的例外
6. THE Derivatives_Tool SHALL 設定 HTTP 請求逾時為 30 秒

---

### 需求 3：Deribit 選擇權與隱含波動率資料

**使用者故事：** 身為主動交易者，我希望系統能取得 Deribit 的 DVOL 隱含波動率、期權 OI 與 Put/Call 比率，以評估市場對未來波動的定價與避險情緒。

#### 驗收條件

1. WHEN Agent 呼叫 get_derivatives 工具並指定 source 為 "deribit" 且 symbol 為 BTC 或 ETH，THE Derivatives_Tool SHALL 從 Deribit_API 取得 DVOL 隱含波動率指數
2. WHEN Agent 呼叫 get_derivatives 工具並指定 metrics 包含 "options_oi"，THE Derivatives_Tool SHALL 從 Deribit_API 取得期權未平倉量與 Put/Call OI 比率
3. IF Agent 呼叫 get_derivatives 並指定 source 為 "deribit" 且 symbol 不是 BTC 或 ETH，THEN THE Derivatives_Tool SHALL 回傳 error dict 說明 Deribit 僅支援 BTC 與 ETH
4. THE Derivatives_Tool SHALL 在 content_reference 中包含 DVOL 數值、期權 OI、Put/Call 比率、資料時間戳
5. IF Deribit_API 呼叫失敗或逾時，THEN THE Derivatives_Tool SHALL 回傳包含錯誤說明的 error dict 而非拋出未處理的例外

---

### 需求 4：Polymarket 預測市場資料

**使用者故事：** 身為主動交易者，我希望系統能取得 Polymarket 上加密相關事件市場的價格與成交量，以捕捉「現貨市場尚未反映的預期」這類高價值訊號。

#### 驗收條件

1. WHEN Agent 呼叫 get_prediction_market 工具並指定搜尋關鍵字，THE Polymarket_API SHALL 被用於查詢加密相關事件市場
2. THE Data_Tool SHALL 回傳匹配事件的市場名稱、目前價格（機率）、成交量、7 日價格變化
3. THE Data_Tool SHALL 在 summary 中以「事件名稱 + 市場定價機率 + 變化方向」格式呈現結果
4. THE Data_Tool SHALL 在 content_reference 中包含 API endpoint、查詢關鍵字、各事件的市場 ID、價格、成交量
5. IF Polymarket_API 呼叫失敗或逾時，THEN THE Data_Tool SHALL 回傳包含錯誤說明的 error dict 而非拋出未處理的例外
6. THE Data_Tool SHALL 設定 HTTP 請求逾時為 30 秒

---

### 需求 5：Binance Spot 盤口深度快照

**使用者故事：** 身為主動交易者，我希望系統能取得 Binance Spot 的盤口深度快照，以評估 ±2% 價位的流動性（滑價成本），判斷市場微結構是否支撐大額交易。

#### 驗收條件

1. WHEN Agent 呼叫 get_orderbook_depth 工具並指定 symbol，THE Data_Tool SHALL 從 Binance Spot API 的 /api/v3/depth endpoint 取得盤口快照
2. THE Data_Tool SHALL 計算目前最佳買賣價 ±2% 範圍內的累積掛單量（bid_depth_2pct、ask_depth_2pct）
3. THE Data_Tool SHALL 在 summary 中以「買方 ±2% 深度 X BTC / 賣方 ±2% 深度 Y BTC」格式呈現結果
4. THE Data_Tool SHALL 在 content_reference 中包含 API endpoint、symbol、best_bid、best_ask、bid_depth_2pct、ask_depth_2pct、snapshot_timestamp
5. IF Binance Spot API 呼叫失敗或逾時，THEN THE Data_Tool SHALL 回傳包含錯誤說明的 error dict 而非拋出未處理的例外
6. THE Data_Tool SHALL 設定 HTTP 請求逾時為 30 秒，且 depth limit 參數設為 1000

---

### 需求 6：CoinGecko 市值佔比資料

**使用者故事：** 身為主動交易者，我希望系統能取得 BTC 及各幣種的市值佔比（dominance）資料，以偵測資金輪動趨勢。

#### 驗收條件

1. WHEN Agent 呼叫 get_market_dominance 工具，THE Data_Tool SHALL 從 CoinGecko /global endpoint 取得各主要幣種的市值佔比百分比
2. THE Data_Tool SHALL 回傳至少包含 BTC 與 ETH 的 dominance 百分比數值
3. THE Data_Tool SHALL 在 summary 中以「BTC dominance X%, ETH dominance Y%」格式呈現結果
4. THE Data_Tool SHALL 在 content_reference 中包含 API endpoint、各幣種 dominance 百分比、total_market_cap、資料時間戳
5. IF CoinGecko API 呼叫失敗或逾時，THEN THE Data_Tool SHALL 回傳包含錯誤說明的 error dict 而非拋出未處理的例外

---

### 需求 7：DefiLlama TVL 與穩定幣供給資料

**使用者故事：** 身為主動交易者，我希望系統能取得 DeFi TVL 與穩定幣供給量變化，以偵測場外資金流入或流出加密生態的訊號。

#### 驗收條件

1. WHEN Agent 呼叫 get_defi_data 工具並指定 metrics 包含 "tvl"，THE Data_Tool SHALL 從 DefiLlama_API 取得指定鏈或全市場的 TVL 數據
2. WHEN Agent 呼叫 get_defi_data 工具並指定 metrics 包含 "stablecoin_supply"，THE Data_Tool SHALL 從 DefiLlama_API 的 stablecoins endpoint 取得穩定幣總供給量與近期變化
3. THE Data_Tool SHALL 在 summary 中以「全市場 TVL $X B, 穩定幣供給 $Y B（近 7 日變化 +Z%）」格式呈現結果
4. THE Data_Tool SHALL 在 content_reference 中包含 API endpoint、TVL 數值、穩定幣供給數值、各鏈 TVL breakdown（若適用）、資料時間戳
5. IF DefiLlama_API 呼叫失敗或逾時，THEN THE Data_Tool SHALL 回傳包含錯誤說明的 error dict 而非拋出未處理的例外
6. THE Data_Tool SHALL 設定 HTTP 請求逾時為 30 秒

---

### 需求 8：GitHub 開發活躍度資料

**使用者故事：** 身為主動交易者，我希望系統能取得各幣種專案的 GitHub 開發活躍度（commit 頻率、release 頻率），以評估基本面健康度與開發動能。

#### 驗收條件

1. WHEN Agent 呼叫 get_dev_activity 工具並指定 symbol，THE Data_Tool SHALL 從 GitHub API 取得對應專案 repository 的近期 commit 頻率與 contributor 活躍度
2. THE Data_Tool SHALL 使用預設的 symbol-to-repo 映射表（BTC→bitcoin/bitcoin、ETH→ethereum/go-ethereum、SOL→solana-labs/solana、BNB→bnb-chain/bsc、XRP→XRPLF/rippled）
3. THE Data_Tool SHALL 在 summary 中以「近 4 週 commit 數、近期 release 標題與日期」格式呈現結果
4. THE Data_Tool SHALL 在 content_reference 中包含 API endpoint、repo 名稱、commit_count_4w、latest_release_tag、latest_release_date
5. IF GitHub API 呼叫失敗或逾時，THEN THE Data_Tool SHALL 回傳包含錯誤說明的 error dict 而非拋出未處理的例外
6. THE Data_Tool SHALL 設定 HTTP 請求逾時為 30 秒，且不需要 API token（公開 repo 的 unauthenticated 限制為 60 次/小時，足夠本專案使用量）

---

### 需求 9：Google News RSS 與媒體 RSS 新聞來源升級

**使用者故事：** 身為主動交易者，我希望系統使用完全免費的新聞來源（Google News RSS + CoinDesk/The Block/Cointelegraph RSS），取代需要 API 金鑰的 CryptoPanic，確保零成本且不受 rate limit 限制。

#### 驗收條件

1. WHEN Agent 呼叫 search_news 工具，THE Data_Tool SHALL 從 Google_News_RSS 取得指定幣種關鍵字的新聞聚合結果
2. THE Data_Tool SHALL 從 Media_RSS 白名單（CoinDesk、The Block、Cointelegraph）取得一手媒體新聞
3. THE Data_Tool SHALL 保留既有的官方部落格 RSS 與 GitHub releases 抓取邏輯
4. WHEN 彙整新聞結果時，THE Data_Tool SHALL 標註每則新聞的來源管道（google_news、media_rss、official_rss、github_release）
5. THE Data_Tool SHALL 移除對 CryptoPanic API 的依賴，改為 Google News RSS 作為主要新聞聚合來源
6. IF Google News RSS 或任何 Media RSS feed 取得失敗，THEN THE Data_Tool SHALL 略過該來源並繼續處理其他來源，回傳已成功取得的結果
7. THE Data_Tool SHALL 在 content_reference 中保持既有結構：新聞標題、發布時間、原文網址、引用片段

---

### 需求 10：Agent 工具註冊與分派

**使用者故事：** 身為開發者，我希望所有新增工具都在 agent.py 的 TOOL_DISPATCH 與 build_tool_config() 中正確註冊，使 Agent 能自主決定何時呼叫這些工具。

#### 驗收條件

1. WHEN 新工具函式實作完成，THE Agent_Loop SHALL 在 TOOL_DISPATCH dict 中新增對應的 name-to-function 映射
2. THE Agent_Loop SHALL 在 build_tool_config() 中為每個新工具提供 toolSpec，包含 name、description、inputSchema
3. THE inputSchema SHALL 將 related_claim 列為每個新工具的 required 參數
4. THE toolSpec description SHALL 明確說明該工具能產出什麼訊號，使 LLM 能判斷何時該呼叫
5. WHEN 新工具在 agent.py 中註冊，THE config.py SHALL 新增對應的環境變數讀取（若該工具需要 API 金鑰）

---

### 需求 11：工具回傳格式與錯誤處理一致性

**使用者故事：** 身為開發者，我希望所有新增工具嚴格遵循契約 C1 回傳格式，確保 Agent_Loop 的 dispatch_tool_call 能一致地處理成功與失敗情境。

#### 驗收條件

1. THE Data_Tool SHALL 統一回傳包含 raw、source、content_reference、summary 四個欄位的 dict
2. IF Data_Tool 執行失敗，THEN THE Data_Tool SHALL 回傳包含 error 欄位的 dict
3. THE Data_Tool SHALL 以最外層 try/except 捕獲所有例外，確保絕不向呼叫端拋出未處理的例外
4. THE Data_Tool SHALL 將 summary 控制在約 500 tokens 以內，避免模型 context 膨脹
5. THE Data_Tool SHALL 使用 evidence.log_execution_step() 記錄每次執行的工具名稱、狀態、耗時毫秒數
6. THE Data_Tool SHALL 不 import 其他 tools 模組的函式（tools 之間不得互相依賴）

---

### 需求 12：效能與降級設計

**使用者故事：** 身為系統營運者，我希望所有新增工具的總執行時間在可控範圍內，且單一來源失敗不影響整體分析流程。

#### 驗收條件

1. THE Data_Tool SHALL 設定每個 HTTP 請求的逾時為 30 秒
2. WHILE 多個外部 API 來源需要查詢時，THE Agent_Loop SHALL 依序呼叫各工具（由 LLM 決定順序），單一工具失敗不中斷迴圈
3. IF 某個資料來源持續不可用，THEN THE Data_Tool SHALL 在 error dict 中提供足夠資訊讓 Agent 決定是否嘗試替代來源
4. THE Data_Tool SHALL 在 content_reference 中記錄實際請求耗時（elapsed_ms），供效能監控使用
5. WHEN Derivatives_Tool 的 Hyperliquid 來源失敗，THE Derivatives_Tool SHALL 建議 Agent 改用 Binance Futures 作為替代（透過 error dict 的提示訊息）

---

### 需求 13：模組邊界與依賴規則

**使用者故事：** 身為開發者，我希望新增的工具檔案遵循既有的模組邊界規則，確保低耦合與可平行開發。

#### 驗收條件

1. THE Derivatives_Tool SHALL 作為新檔案 `lambda/tools/derivatives.py` 實作，不修改既有工具檔案的核心邏輯
2. THE Polymarket 工具 SHALL 作為新檔案 `lambda/tools/prediction.py` 實作
3. THE DefiLlama 與 GitHub 工具 SHALL 作為新檔案 `lambda/tools/defi.py` 實作
4. THE 盤口深度與市值佔比工具 SHALL 在既有 `lambda/tools/price.py` 中新增函式
5. THE 新聞來源升級 SHALL 在既有 `lambda/tools/news.py` 中修改實作
6. THE 所有新增工具 SHALL 僅 import config 與 evidence 模組，不得 import 其他 tools 模組
7. THE `lambda/tools/__init__.py` SHALL 更新以 export 新增的工具模組

