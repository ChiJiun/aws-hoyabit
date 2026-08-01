# 需求文件

## 簡介

本系統為「2026 雲湧智生：臺灣生成式 AI 應用黑客松」HOYA BIT 命題之參賽作品。系統接受使用者指定的加密貨幣幣種（BTC／ETH／SOL／BNB／XRP）與分析題目，由 AI Agent 自主決定資料蒐集策略，整合多源證據後產出具備可回溯來源的結構化市場分析報告。系統定位為資訊提煉工具，不提供投資建議。

## 詞彙表

- **Agent_Loop**: 系統核心迴圈，負責反覆呼叫 LLM 取得工具呼叫指令並分派執行，直到 LLM 判斷證據充分或達到終止條件
- **Lambda_Function**: 部署於 AWS Lambda 的單一函式，承載整個 Agent 系統的運行
- **Function_URL**: AWS Lambda 提供的 HTTPS 端點，直接觸發 Lambda 函式執行，無 29 秒逾時限制
- **Bedrock**: Amazon Bedrock 服務，提供 Claude 模型推理能力
- **Evidence_Record**: 每筆證據的標準記錄，包含 source、fetched_at、content_reference、related_claim 四個欄位
- **Data_Tool**: Agent 可呼叫的資料蒐集工具，包括價格、新聞、鏈上、情緒、總經、量化指標計算等
- **Report**: 最終輸出的分析報告，包含市場判斷、關鍵依據、信心說明三個章節
- **Baseline_CSV**: 賽方提供的歷史 OHLCV 日線資料，儲存於 S3，截止日為 2026-05-31
- **Run_ID**: 每次執行的唯一識別碼，用於歸檔 S3 路徑與關聯所有產出物
- **Frontend**: S3 靜態網站託管的前端頁面，提供使用者輸入介面與報告顯示
- **Presigned_URL**: S3 產生的有時效性下載連結，讓資料桶無需公開即可提供檔案下載

---

## 需求

### 需求 1：請求接收與驗證

**使用者故事：** 身為使用者，我希望透過網頁介面提交幣種與分析題目，以便系統開始執行分析。

#### 驗收條件

1. WHEN 使用者透過 Frontend 送出 POST 請求，THE Lambda_Function SHALL 透過 Function_URL 接收該請求並開始執行分析流程
2. WHEN 請求中包含 1 個支援的幣種代號與非空的分析題目，THE Lambda_Function SHALL 接受該請求並產生 Run_ID
3. WHEN 請求中包含 2 個支援的幣種代號與非空的分析題目，THE Lambda_Function SHALL 接受該請求作為比較分析題型
4. IF 請求中的幣種代號不在 BTC、ETH、SOL、BNB、XRP 之中，THEN THE Lambda_Function SHALL 回傳包含明確錯誤說明的回應
5. IF 請求中的分析題目為空字串，THEN THE Lambda_Function SHALL 回傳包含明確錯誤說明的回應
6. THE Lambda_Function SHALL 在回應中包含 CORS 標頭，使 Frontend 的跨網域呼叫能正常運作

---

### 需求 2：Agent 主迴圈與執行控制

**使用者故事：** 身為系統營運者，我希望 Agent 迴圈具備明確的終止機制，以確保每次執行在合理時間內完成且不超過 Lambda 逾時限制。

#### 驗收條件

1. THE Agent_Loop SHALL 以最大輪次數（MAX_AGENT_TURNS）與時間預算（TIME_BUDGET_SECONDS）作為終止條件
2. WHILE Agent_Loop 執行中，THE Agent_Loop SHALL 在每輪開始前檢查已耗用時間是否超過時間預算
3. IF Agent_Loop 的已執行輪次達到 MAX_AGENT_TURNS，THEN THE Agent_Loop SHALL 停止呼叫 Data_Tool 並進入報告產出階段
4. IF Agent_Loop 的已耗用時間超過 TIME_BUDGET_SECONDS，THEN THE Agent_Loop SHALL 停止呼叫 Data_Tool 並進入報告產出階段
5. THE Lambda_Function SHALL 設定逾時時間為 15 分鐘，確保 Agent_Loop 有足夠的執行時間
6. WHEN Agent_Loop 開始執行，THE Agent_Loop SHALL 清空前一次執行可能殘留的證據清單與執行紀錄（因 Lambda 容器可能重複使用）

---

### 需求 3：LLM 推理與工具呼叫

**使用者故事：** 身為使用者，我希望 AI Agent 能根據我的問題自主判斷需要哪些資料，而非固定呼叫所有工具。

#### 驗收條件

1. THE Agent_Loop SHALL 透過 Bedrock Converse API 呼叫 Claude 模型進行推理
2. WHEN Bedrock 回應的 stopReason 為 tool_use，THE Agent_Loop SHALL 解析工具呼叫請求並分派至對應的 Data_Tool 執行
3. WHEN Bedrock 回應的 stopReason 為 end_turn，THE Agent_Loop SHALL 結束迴圈並將最終分析內容傳給報告產出階段
4. THE Agent_Loop SHALL 提供系統提示詞（System Prompt），指示模型遵循事實→推論→結論的分析層次
5. THE Agent_Loop SHALL 在系統提示詞中明確禁止模型提供投資建議（買進、賣出、目標價）
6. WHEN 將 Data_Tool 執行結果回傳給模型時，THE Agent_Loop SHALL 僅回傳精簡摘要與 evidence_id，避免完整原始資料導致上下文膨脹

---

### 需求 4：證據記錄與可回溯性

**使用者故事：** 身為評審，我希望每筆證據都能回溯到原始來源與取得時間，以便驗證分析的可信度。

#### 驗收條件

1. THE Evidence_Record SHALL 包含且僅包含以下四個欄位：source、fetched_at、content_reference、related_claim
2. WHEN Data_Tool 執行完成，THE Lambda_Function SHALL 自動產生 source（實際呼叫的 API 網址或來源名稱）、fetched_at（UTC 時間 ISO 8601 格式）、content_reference（引用片段或查詢參數或指標數值）三個欄位
3. THE Agent_Loop SHALL 將 related_claim 列為每個 Data_Tool 的必填參數，由 LLM 在呼叫工具時提供
4. IF related_claim 參數為空或長度不足，THEN THE Lambda_Function SHALL 拒絕記錄該筆證據並回傳錯誤訊息
5. WHEN 每筆 Evidence_Record 產生時，THE Lambda_Function SHALL 賦予唯一的 evidence_id 以供報告引用
6. WHEN Data_Tool 執行完成，THE Lambda_Function SHALL 將原始 API 回應封存至 S3 路徑 runs/{run_id}/raw/{evidence_id}.json

---

### 需求 5：執行紀錄

**使用者故事：** 身為評審，我希望能看到完整的執行過程紀錄，包括失敗的嘗試，以評估系統的資料蒐集能力。

#### 驗收條件

1. WHEN Data_Tool 執行成功，THE Lambda_Function SHALL 記錄一筆執行紀錄，包含時間戳記、工具名稱、執行狀態、耗時毫秒數、對應的 evidence_id
2. WHEN Data_Tool 執行失敗，THE Lambda_Function SHALL 記錄一筆執行紀錄，包含時間戳記、工具名稱、失敗狀態、耗時毫秒數、錯誤說明
3. THE Lambda_Function SHALL 將所有執行紀錄以 JSONL 格式輸出，每行一筆 JSON 物件

---

### 需求 6：價格與 OHLCV 資料工具

**使用者故事：** 身為使用者，我希望系統能取得指定幣種的歷史與即時價格資料，以支撐技術面分析。

#### 驗收條件

1. WHEN Agent 呼叫 get_price_ohlcv 工具並指定幣種與日期範圍，THE Data_Tool SHALL 回傳該幣種在指定期間的日線 OHLCV 資料
2. THE Data_Tool SHALL 優先使用 S3 上的 Baseline_CSV 作為歷史價格資料來源
3. WHEN 請求的結束日期超過 Baseline_CSV 截止日（2026-05-31），THE Data_Tool SHALL 從 Binance 公開 API 補齊缺口資料
4. WHEN 基準資料與即時資料拼接時，THE Data_Tool SHALL 檢查重疊日期的收盤價差異百分比，並記錄校驗結果
5. THE Data_Tool SHALL 使用 CoinGecko API 作為備用價格資料來源
6. IF 外部 API 呼叫失敗，THEN THE Data_Tool SHALL 回傳包含錯誤說明的結果而非拋出未處理的例外

---

### 需求 7：新聞與官方公告工具

**使用者故事：** 身為使用者，我希望系統能蒐集指定幣種的近期新聞與官方公告，以掌握基本面變化。

#### 驗收條件

1. WHEN Agent 呼叫 search_news 工具，THE Data_Tool SHALL 從 Google News RSS 與媒體 RSS 白名單查詢指定幣種的近期新聞(免費來源)
2. THE Data_Tool SHALL 從各專案官方部落格與 GitHub releases 取得一手官方公告
3. WHEN 彙整新聞結果時，THE Data_Tool SHALL 標註來自同一來源家族的重複報導，避免模型誤判為多源共識
4. THE Data_Tool SHALL 在 content_reference 中包含新聞標題、發布時間、原文網址、引用片段
5. IF 外部 API 呼叫失敗，THEN THE Data_Tool SHALL 回傳包含錯誤說明的結果而非拋出未處理的例外

---

### 需求 8：鏈上資料工具

**使用者故事：** 身為使用者，我希望系統能取得指定幣種的鏈上活躍度指標，以評估網路基本面。

#### 驗收條件

1. WHEN Agent 呼叫 get_onchain 工具並指定 BTC，THE Data_Tool SHALL 從 mempool.space 取得鏈上資料
2. WHEN Agent 呼叫 get_onchain 工具並指定 ETH，THE Data_Tool SHALL 從 Etherscan API V2 取得鏈上資料
3. WHEN Agent 呼叫 get_onchain 工具並指定 BNB，THE Data_Tool SHALL 從 Blockscout 取得鏈上資料
4. WHEN Agent 呼叫 get_onchain 工具並指定 SOL，THE Data_Tool SHALL 從 Helius 取得鏈上資料
5. WHEN Agent 呼叫 get_onchain 工具並指定 XRP，THE Data_Tool SHALL 從 XRPL 公開節點取得鏈上資料
6. THE Data_Tool SHALL 在 content_reference 中包含實際呼叫的 API endpoint、查詢參數、資料時間範圍
7. IF 外部 API 呼叫失敗，THEN THE Data_Tool SHALL 回傳包含錯誤說明的結果而非拋出未處理的例外

---

### 需求 9：市場情緒工具

**使用者故事：** 身為使用者，我希望系統能取得市場恐懼與貪婪指數，以評估當前市場情緒狀態。

#### 驗收條件

1. WHEN Agent 呼叫 get_sentiment 工具，THE Data_Tool SHALL 從 alternative.me Fear & Greed Index 取得當前指數值與近期走勢
2. THE Data_Tool SHALL 在 content_reference 中包含 API endpoint、查詢時間範圍、指數數值與分級文字
3. IF 外部 API 呼叫失敗，THEN THE Data_Tool SHALL 回傳包含錯誤說明的結果而非拋出未處理的例外

---

### 需求 10：總體經濟工具

**使用者故事：** 身為使用者，我希望系統能取得總體經濟指標，以評估宏觀環境對加密市場的影響。

#### 驗收條件

1. WHEN Agent 呼叫 get_macro 工具，THE Data_Tool SHALL 從 FRED 取得指定總經指標的近期走勢
2. THE Data_Tool SHALL 支援查詢美元指數（DXY）、10 年期公債殖利率、聯邦基金利率等指標
3. THE Data_Tool SHALL 在 content_reference 中包含 FRED series ID、查詢時間範圍、數值序列摘要
4. IF 外部 API 呼叫失敗，THEN THE Data_Tool SHALL 回傳包含錯誤說明的結果而非拋出未處理的例外

---

### 需求 11：技術指標計算工具

**使用者故事：** 身為使用者，我希望所有數字運算由程式決定性地算出，而非由模型心算，以確保數據正確性。

#### 驗收條件

1. WHEN Agent 呼叫 compute_quant 工具，THE Data_Tool SHALL 使用 pandas 計算指定的技術指標
2. THE Data_Tool SHALL 支援計算 ATR 百分比、布林帶寬、ADX、成交量 Z-score、已實現波動率、相關係數等指標
3. WHEN 計算技術指標時，THE Data_Tool SHALL 同時計算該指標在歷史資料中的百分位排名
4. WHEN 比較分析題型提供兩個幣種時，THE Data_Tool SHALL 支援計算兩幣種報酬率的相關係數
5. THE Data_Tool SHALL 在 content_reference 中包含指標名稱、計算視窗、計算結果數值、百分位排名

---

### 需求 12：分析報告產出

**使用者故事：** 身為使用者，我希望系統產出的報告具備固定結構，且每個結論都有對應的證據引用。

#### 驗收條件

1. THE Report SHALL 包含以下三個章節：市場判斷、關鍵依據、信心說明
2. WHEN 產出報告時，THE Lambda_Function SHALL 在關鍵依據章節中為每條依據附上對應的 evidence_id
3. THE Report SHALL 在信心說明章節中包含已知限制、資料不足之處、可能推翻結論的條件
4. THE Report SHALL 在附錄中包含資料覆蓋率（已取得的資料類別數 ÷ 預期的資料類別總數）
5. THE Report SHALL 以 Markdown 格式輸出
6. THE Report SHALL 遵循事實→推論→結論的三層分析結構

---

### 需求 13：分析內容品質約束

**使用者故事：** 身為使用者，我希望分析內容在資訊不足時承認限制，而非強行給出結論。

#### 驗收條件

1. THE Report SHALL 不包含投資建議語句（買進、賣出、目標價、建議持有等）
2. WHEN 資料來源之間存在矛盾訊號，THE Report SHALL 明確說明矛盾內容與取捨依據
3. WHEN 部分資料來源取得失敗，THE Report SHALL 在信心說明章節中列出缺失的資料類別
4. THE Lambda_Function SHALL 在交付前執行自我檢查，驗證報告中是否出現投資建議語句
5. THE Lambda_Function SHALL 在交付前驗證證據來源類別數是否大於等於 3

---

### 需求 14：收尾報告整理

**使用者故事：** 身為系統設計者，我希望報告結構由程式保證，而非依賴模型在長對話中自行維持格式。

#### 驗收條件

1. WHEN Agent_Loop 結束後，THE Lambda_Function SHALL 執行第二次 Bedrock 呼叫（不提供工具），要求模型依市場判斷、關鍵依據、信心說明三段式結構重新整理分析內容
2. THE Lambda_Function SHALL 使用程式化的 Markdown 模板渲染最終報告，確保三個章節一定存在

---

### 需求 15：交付物匯出與儲存

**使用者故事：** 身為評審，我希望每次執行能產出完整的四項交付物，且能透過連結下載。

#### 驗收條件

1. WHEN 分析完成，THE Lambda_Function SHALL 產出以下交付物：report.md、evidence_list.json、execution_log.jsonl
2. THE Lambda_Function SHALL 將所有交付物上傳至 S3 路徑 runs/{run_id}/ 下
3. THE Lambda_Function SHALL 為 evidence_list.json 與 execution_log.jsonl 產生 Presigned_URL 供下載
4. THE Lambda_Function SHALL 在回應中包含報告 Markdown 原文，供 Frontend 直接顯示

---

### 需求 16：分析題型支援

**使用者故事：** 身為使用者，我希望系統能處理命題規定的三種分析題型。

#### 驗收條件

1. WHEN 使用者提交 1 個幣種與整合類題目，THE Lambda_Function SHALL 執行多源整合分析，整合價格、鏈上、新聞、情緒等多類資料
2. WHEN 使用者提交 1 個幣種與假設驗證類題目，THE Lambda_Function SHALL 蒐集支持與反對該假設的證據，給出判斷與理由
3. WHEN 使用者提交 2 個幣種與比較分析類題目，THE Lambda_Function SHALL 比較兩幣種的市場位置與風險特徵

---

### 需求 17：前端介面

**使用者故事：** 身為使用者，我希望透過簡潔的網頁介面提交分析請求並查看結果。

#### 驗收條件

1. THE Frontend SHALL 提供幣種選擇按鈕，允許選取 1 至 2 個幣種
2. THE Frontend SHALL 提供文字輸入區域供使用者輸入分析題目
3. WHEN 使用者未選擇幣種或未輸入題目即按下送出，THE Frontend SHALL 顯示明確的錯誤提示
4. WHILE 等待後端回應期間，THE Frontend SHALL 顯示執行中狀態，包含經過時間與進度提示文字輪播
5. WHEN 後端回傳分析結果，THE Frontend SHALL 使用 marked.js 將 Markdown 報告渲染為 HTML 顯示
6. THE Frontend SHALL 提供證據清單與執行紀錄的下載連結
7. THE Frontend SHALL 部署於 S3 靜態網站託管

---

### 需求 18：S3 資料儲存

**使用者故事：** 身為系統營運者，我希望所有資料存取集中管理，且資料桶不對外公開。

#### 驗收條件

1. THE Lambda_Function SHALL 從 S3 讀取 Baseline_CSV，路徑為 baseline/{symbol}USDT_daily_ohlcv.csv
2. THE Lambda_Function SHALL 將每次執行的原始 API 回應、交付物皆儲存於 S3 的 runs/{run_id}/ 路徑下
3. THE Lambda_Function SHALL 透過 Presigned_URL 提供檔案下載，資料桶本身不設為公開讀取
4. THE Presigned_URL SHALL 具備有效期限（預設 1 小時）

---

### 需求 19：環境配置與部署

**使用者故事：** 身為開發者，我希望所有環境設定集中管理，且機密資訊不寫入程式碼。

#### 驗收條件

1. THE Lambda_Function SHALL 從環境變數讀取所有 API 金鑰與設定參數，不將機密資訊寫入程式碼
2. THE Lambda_Function SHALL 支援本機開發時從 .env 檔案載入環境變數
3. WHEN 部署至 AWS Lambda 時，THE Lambda_Function SHALL 透過 Lambda Layer 或容器映像方式提供 pandas 與 numpy 套件
4. THE Lambda_Function SHALL 使用 Python 3.12 執行環境

---

### 需求 20：工具回傳格式統一

**使用者故事：** 身為開發者，我希望所有 Data_Tool 的回傳格式一致，以簡化 Agent_Loop 的處理邏輯。

#### 驗收條件

1. THE Data_Tool SHALL 統一回傳包含以下欄位的 dict：raw（原始 API 回應）、source（API 網址或來源名稱）、content_reference（引用片段或指標數值）、summary（給模型看的精簡摘要）
2. IF Data_Tool 執行失敗，THEN THE Data_Tool SHALL 回傳包含 error 欄位的 dict，供 Agent_Loop 記錄缺口並繼續執行
3. THE Data_Tool SHALL 不拋出未處理的例外，確保 Agent_Loop 不會因單一工具失敗而中斷

---

### 需求 21：本機測試

**使用者故事：** 身為開發者，我希望能在本機完整執行分析流程，以便在部署前驗證邏輯正確性。

#### 驗收條件

1. THE Lambda_Function SHALL 提供本機測試進入點，使用寫死的測試輸入執行完整分析流程
2. WHEN 本機執行時，THE Lambda_Function SHALL 將交付物輸出至本地 outputs/ 資料夾而非上傳 S3
3. THE Lambda_Function SHALL 提供整合測試腳本，涵蓋五個幣種與三種分析題型的組合測試
