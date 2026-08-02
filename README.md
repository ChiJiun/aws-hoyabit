# 加密市場分析 AI Agent

**2026 雲湧智生：臺灣生成式 AI 應用黑客松競賽**｜命題單位：HOYA BIT（禾亞數位科技）
命題主題：加密市場分析 AI Agent — 多源資訊的信任提煉

輸入一個或兩個幣種與一道分析題目，Agent 自主蒐集多源資料、交叉比對訊號，產出每條判斷都能回溯到來源的結構化市場分析報告。

> 本系統為**資訊提煉工具，不提供投資建議**、進出場時機或目標價。

---

## 目錄

- [核心設計](#核心設計)
- [系統架構](#系統架構)
- [快速開始（本機）](#快速開始本機)
- [AWS 部署](#aws-部署)
- [交付物](#交付物)
- [資料來源](#資料來源)
- [測試](#測試)
- [專案結構](#專案結構)
- [環境變數](#環境變數)
- [設計取捨](#設計取捨)

---

## 核心設計

### 兩階段蒐集：決定性預抓 + Agent 補洞

單純讓 LLM 自由呼叫工具，會遇到兩個問題：慢，以及每次抓的資料不一樣（Demo 不可重現）。所以蒐集拆成兩段：

**Phase A — 決定性預抓**（約 90 秒，bounded concurrency）
依題型與幣種建立固定計畫，8 個 worker 並行抓取。單一來源 timeout 或 rate limit 不會取消其他工作。若題目提到監管／升級／流動性／機構持倉／估值等特定情境，會額外追加對應來源。

**Phase B — Agent 迴圈**
把 Phase A 的摘要（不含原始資料，避免 context 膨脹）餵給模型，由它決定還要補什麼。每輪檢查剩餘時間預算，低於 20% 時停止新增蒐集並強制收斂。

### 題型判別

三種題型走不同的分析與呈現路徑：

| 題型 | 觸發條件 | 產出重點 |
|---|---|---|
| 多源整合 | 預設 | 跨維度整合，標示各來源一致程度 |
| 假設驗證 | 檢驗某個說法的關鍵詞，或是非問句配方向性主張 | 支持／反對／中性／資料不足四類證據 + 判定理由 |
| 比較分析 | 兩個幣種 | 相同口徑逐維度比較，程式計算相關係數 |

判別採三層：高精準關鍵詞 → 疑問詞配主張詞 → 語意不明才由 LLM 兜底。實測 19 種常見問法全數正確，且都由規則命中，不增加延遲。LLM 兜底失敗一律安全退回多源整合，不會讓分類成為整次執行的失敗點。

### 異常訊號是主要價值

不只描述現狀，主動標出偏離常態之處：

- 指標處於歷史極端百分位（如成交量 Z-score 落在第 0.3 百分位）
- 跨來源訊號背離（價格下跌但鏈上活躍度上升）
- 量價異常、情緒與價格脫鉤

同時列出「已檢查且正常」的項目，證明異常是全面掃描後的結果，而非挑選出來的。

所有數值運算都由工具以 pandas 決定性計算，LLM 不做任何心算。

### 可回溯的證據

每筆證據固定四欄位，對應命題的抽查要求：

| 欄位 | 內容 |
|---|---|
| `source` | 來源名稱或 API URL |
| `fetched_at` | 取得時間（UTC ISO 8601） |
| `content_reference` | 查詢參數、資料區間、指標數值、引用片段 |
| `related_claim` | 這筆資料用來檢驗什麼判斷（工具呼叫時強制填寫） |

原始 API 回應完整封存在 `runs/{run_id}/raw/{evidence_id}.json`，前端證據區可逐筆展開查驗，也提供人類可讀的查證連結。

### 三層推理

報告明確區分 **事實**（有 evidence_id 支撐的數字或事件）→ **推論**（由事實推導的邏輯）→ **結論**（綜合判斷，標示信心程度）。資料不足或訊號矛盾時明說限制，並列出什麼情況會推翻結論。

---

## 系統架構

```
┌─────────────────────────────────────────────┐
│                 使用者瀏覽器                    │
└──────────────────────┬──────────────────────┘
                       │ ① 載入頁面
                       ▼
┌─────────────────────────────────────────────┐
│      S3 靜態網站（前端 bucket）                  │
│      frontend/index.html（單檔，無建置步驟）      │
└──────────────────────┬──────────────────────┘
                       │ ② POST {symbols, question}
                       ▼
┌─────────────────────────────────────────────┐
│      Lambda Function URL                     │
│      單一 Lambda = 完整 Agent 流程             │
│                                              │
│   Phase A 並行預抓 ──▶ Phase B Agent 迴圈       │
│         │                     │               │
│         └──── 證據記錄 ────────┘               │
│                     │                        │
│              報告渲染 + C7 結構化資料           │
└────┬─────────────────────────┬───────────────┘
     │ ③ 推理與工具呼叫           │ ④ 讀寫
     ▼                          ▼
┌──────────────┐   ┌──────────────────────────┐
│Amazon Bedrock│   │  Amazon S3（資料 bucket）  │
│  Claude      │   │  ・基準 OHLCV CSV          │
└──────────────┘   │  ・原始 API 回應封存        │
     │             │  ・四項交付物               │
     │             └──────────────────────────┘
     │ ⑤ 15 個資料工具
     ▼
┌─────────────────────────────────────────────┐
│  外部資料來源（價格／鏈上／衍生品／新聞／情緒／   │
│  總經／DeFi／機構／監管／預測市場）              │
└─────────────────────────────────────────────┘

⑥ 回傳報告內文、結構化資料與 presigned 下載連結
```

單一 Lambda + Function URL，不使用 API Gateway（避開 29 秒逾時限制）、不使用 Step Functions（流程為線性路徑）、不使用資料庫（每次執行以 `run_id` 隔離）。

---

## 快速開始（本機）

### 需求

- Python 3.12
- Node.js（僅前端測試需要，非必要）
- AWS 帳號，且已在 Bedrock **Model access** 開通 Claude
- AWS 憑證（`aws configure` 或環境變數）

### 步驟

```bash
# 1. 虛擬環境與套件
python -m venv .venv
.venv\Scripts\activate          # macOS / Linux: source .venv/bin/activate
pip install -r requirements.txt

# 2. 環境變數
copy .env.example .env          # macOS / Linux: cp .env.example .env
# 編輯 .env，至少填入 BEDROCK_MODEL_ID 與 AWS 憑證

# 3. 基準資料
# 把賽方提供的 CSV 放進 data/baseline/
# 檔名格式：{SYMBOL}_daily_ohlcv.csv，例如 BTC_daily_ohlcv.csv

# 4a. 執行單次分析（結果寫入 outputs/）
python lambda/handler.py

# 4b. 或啟動含前端的本機 Demo
python local_server.py
# 瀏覽器開啟 http://localhost:8080
```

`local_server.py` 同時提供前端靜態檔案與 `/api` 端點，模擬 Lambda Function URL 的行為，並把本機檔案路徑改寫成可下載的 HTTP URL。

> **AWS 臨時憑證會過期。** 若 `.env` 內含 `AWS_SESSION_TOKEN`，該組憑證通常 1–12 小時後失效，症狀是報告的「市場判斷」為空且出現 `ExpiredTokenException`。Demo 前重新取得一組即可。

---

## AWS 部署

### 一、建立資源（一次性）

```bash
# 資料 bucket（不公開）
aws s3 mb s3://你的資料bucket

# 前端 bucket（靜態網站）
aws s3 mb s3://你的前端bucket
aws s3 website s3://你的前端bucket --index-document index.html
```

Lambda 執行角色需要的權限：

- `bedrock:InvokeModel`
- `s3:GetObject`、`s3:PutObject`（限定資料 bucket）
- `AWSLambdaBasicExecutionRole`（CloudWatch Logs）

建立 Lambda function：

- Runtime：Python 3.12
- Handler：`handler.lambda_handler`
- Timeout：**900 秒**（15 分鐘，命題時限）
- Memory：建議 1024 MB 以上（pandas 運算）
- 開啟 **Function URL**，Auth type 選 `NONE`，並設定 CORS
- 環境變數：依 `.env.example` 逐項填入

> **pandas 與 numpy 不在 Lambda 內建環境。** 兩者體積較大，zip 部署可能超過 250 MB 解壓限制。超過時改用 Lambda Layer 或容器映像。

### 二、上傳基準資料

```bash
./scripts/upload_baseline.sh 你的資料bucket
```

### 三、部署程式碼

```bash
./scripts/package_lambda.sh

aws lambda update-function-code \
  --function-name crypto-market-agent \
  --zip-file fileb://function.zip
```

### 四、部署前端

```bash
# 把前端的 API_URL 換成實際的 Function URL
./scripts/set_api_url.sh https://你的id.lambda-url.us-west-2.on.aws/

aws s3 cp frontend/index.html s3://你的前端bucket/index.html
```

前端在 `localhost` 執行時會自動指向 `/api`，部署後才需要替換為 Function URL。

---

## 交付物

每次執行在 S3 `runs/{run_id}/` 下產生：

| 交付物 | 檔案 | 內容 |
|---|---|---|
| 分析報告 | `report.md` | 市場判斷、關鍵依據（附 evidence_id）、信心說明（含已知限制、矛盾訊號取捨、推翻條件） |
| 證據清單 | `evidence_list.json` | 每筆含 source、fetched_at、content_reference、related_claim |
| 執行紀錄 | `execution_log.jsonl` | 每行一筆 JSON：時間戳、工具名稱、狀態、耗時、失敗原因 |
| 結構化資料 | `report_data.json` | 供前端視覺化的結構化版本（判斷／維度／訊號／覆蓋率／時間序列） |
| 原始回應封存 | `raw/{evidence_id}.json` | 完整 API 回應，供抽查比對 |
| 原始碼與配置 | 本 repo | 程式碼、設定檔與本文件 |

報告與結構化資料來自同一份分析，結論、信心、訊號與引用保持一致。結構化資料組裝失敗時，前端自動降級為純 Markdown 渲染，不影響其他交付物。

---

## 資料來源

15 個工具，覆蓋 10 個資料類別。命題要求證據來源類別 ≥ 3，實測單次執行通常涵蓋 7–9 類。

| 類別 | 工具 | 來源 | 金鑰 |
|---|---|---|---|
| 基準價格 | `get_price_ohlcv` | 賽方 OHLCV CSV | — |
| 即時價格 | `get_price_ohlcv` | Binance 公開 API、CoinGecko（備援） | CoinGecko 選用 |
| 技術指標 | `compute_quant` | 本地 pandas 計算，無外部呼叫 | — |
| 新聞與公告 | `search_news` | Google News RSS、CoinDesk、Cointelegraph、The Block、各鏈官方部落格、GitHub releases | 免鑰 |
| 鏈上 BTC | `get_onchain` | mempool.space | 免鑰 |
| 鏈上 ETH | `get_onchain` | Etherscan API V2 | 需要 |
| 鏈上 BNB | `get_onchain` | BscScan（Blockscout 相容） | 免鑰 |
| 鏈上 SOL | `get_onchain` | Helius | 需要 |
| 鏈上 XRP | `get_onchain` | XRPL 公開節點（xrplcluster、s1.ripple） | 免鑰 |
| 衍生品 | `get_derivatives` | Hyperliquid、Binance Futures、Deribit | 免鑰 |
| 盤口深度 | `get_orderbook_depth` | Binance Spot | 免鑰 |
| 市場情緒 | `get_sentiment` | alternative.me Fear & Greed | 免鑰 |
| 總體經濟 | `get_macro` | FRED（DXY、DGS10、DFF）+ 排程事件 | 需要 |
| DeFi 資金流 | `get_defi_data` | DefiLlama、stablecoins.llama.fi | 免鑰 |
| 開發活躍度 | `get_dev_activity` | GitHub API | 免鑰 |
| 市值佔比 | `get_market_dominance` | CoinGecko | 選用 |
| 機構持倉 | `get_cftc_cot` | CFTC Public Reporting（僅 BTC） | 免鑰 |
| 監管文件 | `get_sec_filings` | SEC EDGAR full-text search | 免鑰 |
| 機構級指標 | `get_coin_metrics` | Coin Metrics Community API | 免鑰 |
| 預測市場 | `get_prediction_market` | Polymarket Gamma API | 免鑰 |

所有外部呼叫都設定 timeout、失敗回傳 error dict，不讓未處理例外中斷執行。付費來源若有使用會在報告與證據清單揭露，且不作為唯一關鍵依據。

---

## 測試

```bash
# 後端（39 個測試檔案）
python -m pytest tests/ -q

# 端到端整合測試（三種題型，需要 AWS 憑證）
python -m tests.test_local_run

# 前端
node frontend/tests/structure_check.mjs   # HTML 結構與元素唯一性
node frontend/tests/smoke_c7.mjs          # 渲染邏輯，含注入防護與無障礙
node frontend/tests/render_live.mjs       # 以 outputs/ 的真實執行結果驗證渲染
```

前端測試在 Node 的最小 DOM sandbox 中實際執行 `index.html` 的渲染函式，涵蓋 HTML 逸出、題型路由、資料缺失降級、百分位邊界、無障礙屬性與響應式斷點。

離線檢視前端：直接用瀏覽器開啟 `frontend/index.html`（`file://` 協定），會載入 `frontend/fixtures/` 的範例資料，無需啟動後端。

---

## 專案結構

```
aws-hoyabit/
├── README.md
├── requirements.txt
├── .env.example                 環境變數範例（不含真實金鑰）
├── local_server.py              本機 Demo 伺服器（前端 + /api）
│
├── lambda/                      部署到 Lambda 的程式碼
│   ├── handler.py               進入點（lambda_handler + 本機 main）
│   ├── config.py                環境變數與常數集中管理
│   ├── agent.py                 題型判別、Phase A/B、工具分派
│   ├── evidence.py              四欄位證據記錄與執行紀錄
│   ├── report.py                Markdown 報告渲染
│   ├── report_schema.py         結構化報告資料組裝與驗證
│   ├── export.py                交付物匯出與品質檢查
│   ├── storage.py               S3 讀寫與 presigned URL
│   └── tools/                   15 個資料工具
│       ├── price.py             OHLCV 取得與拼接
│       ├── quant.py             技術指標（純本地計算）
│       ├── news.py              新聞、官方公告、GitHub releases
│       ├── onchain.py           鏈上資料（五條鏈分派）
│       ├── derivatives.py       資金費率、OI、多空比、DVOL
│       ├── sentiment.py         恐懼貪婪指數
│       ├── macro.py             FRED 總經指標
│       ├── defi.py              TVL、穩定幣供給、開發活躍度
│       ├── institutional.py     CFTC、SEC、Coin Metrics
│       ├── prediction.py        Polymarket 預測市場
│       ├── quality.py           資料新鮮度與可比性判定
│       └── series_utils.py      時間序列處理
│
├── frontend/
│   ├── index.html               單檔前端（無建置步驟）
│   ├── fixtures/                離線示範用的範例資料
│   └── tests/                   前端測試
│
├── scripts/
│   ├── package_lambda.sh        打包 function.zip
│   ├── upload_baseline.sh       上傳基準 CSV 至 S3
│   └── set_api_url.sh           替換前端的 Function URL
│
├── tests/                       後端測試
├── data/baseline/               賽方基準 CSV
└── outputs/                     本機執行輸出
```

---

## 環境變數

設定方式：本機開發複製 `.env.example` 為 `.env` 並填入真實值；AWS Lambda 則在控制台的「環境變數」區塊逐項填入。所有 `os.environ` 讀取集中在 `config.py`，其他模組一律 `from config import X`。

### 必填（系統無法啟動）

| 變數 | 範例值 | 說明 |
|---|---|---|
| `BEDROCK_MODEL_ID` | `us.anthropic.claude-sonnet-4-20250514-v1:0` | Bedrock 模型完整 ID。必須包含 `us.` 前綴，且 region 需已開通該模型的存取權限。錯誤時會得到 `ValidationException: The provided model identifier is invalid` |
| `DATA_BUCKET` | `crypto-agent-data-teamname` | S3 資料 bucket 名稱，用於讀取基準 CSV 與寫入執行產物。**本機測試留空**即自動切換為本地 `outputs/` 目錄 |

### AWS 憑證

| 變數 | 說明 |
|---|---|
| `AWS_REGION` | 預設 `us-west-2`。必須與 Bedrock 模型開通的 region 一致 |
| `AWS_ACCESS_KEY_ID` | IAM 長期金鑰或臨時憑證的 Access Key |
| `AWS_SECRET_ACCESS_KEY` | 對應的 Secret Key |
| `AWS_SESSION_TOKEN` | **僅臨時憑證需要**（SSO / assume-role / Workshop）。長期 IAM User 不需要填這一行。臨時憑證通常 1–12 小時過期，症狀是 `ExpiredTokenException` |

> Lambda 上不需要填 AWS 憑證 — 它透過 IAM Role 自動取得。這四個變數只有本機開發時才需要。

### 執行參數

| 變數 | 預設 | 說明 |
|---|---|---|
| `MAX_AGENT_TURNS` | `15` | Phase B Agent 迴圈最大輪數。與時間預算雙重約束，任一觸及即停止並收斂 |
| `TIME_BUDGET_SECONDS` | `600` | 整次執行的時間預算（秒）。命題限 15 分鐘，建議設 600 留緩衝 |
| `TOOL_HTTP_TIMEOUT_SECONDS` | `15` | 單次外部 API 呼叫的 timeout（秒） |
| `TOOL_HTTP_MAX_ATTEMPTS` | `2` | 單次工具呼叫最大嘗試次數（含重試） |
| `TOOL_HTTP_BACKOFF_SECONDS` | `0.25` | 重試間隔（秒） |

### 資料源金鑰（全部選用）

缺少時對應工具會 graceful fail，錯誤記入 `execution_log.jsonl` 並在報告的覆蓋率與信心說明中標註。不會導致整次執行失敗。

| 變數 | 用途 | 免費額度 | 影響的工具 |
|---|---|---|---|
| `COINGECKO_API_KEY` | CoinGecko Demo API | 免費申請，日限 10K calls | `get_price_ohlcv`（備援路徑）、`get_market_dominance` |
| `ETHERSCAN_API_KEY` | Etherscan V2 API | 免費申請，5 calls/s | `get_onchain`（ETH 鏈上） |
| `HELIUS_API_KEY` | Helius RPC | 免費申請，有日限 | `get_onchain`（SOL 鏈上） |
| `FRED_API_KEY` | 聖路易聯儲 FRED | 免費申請，無實質限制 | `get_macro`（DXY、DGS10、DFF） |
| `SOSOVALUE_API_KEY` | SoSoValue ETF 數據 | 需申請 | `get_etf_flow`（BTC/ETH ETF 資金流） |
| `CMC_API_KEY` | CoinMarketCap | 免費 Basic 方案 | 預留，目前未使用 |
| `COINGLASS_API_KEY` | CoinGlass 衍生品 | 需付費 | 預留，目前改用免費的 Hyperliquid |
| `REDDIT_CLIENT_ID` | Reddit OAuth | 免費申請 | 預留，目前未使用 |
| `REDDIT_CLIENT_SECRET` | Reddit OAuth | 免費申請 | 預留，目前未使用 |
| `DUNE_API_KEY` | Dune Analytics | 免費方案有限 | 預留，目前未使用 |

### 免鑰來源（不需要環境變數，程式碼直接呼叫）

| 來源 | 用途 |
|---|---|
| Binance Spot API | 即時 OHLCV（主力價格來源） |
| Hyperliquid API | 資金費率、OI、清算（衍生品主力，替代被封鎖的 Binance Futures） |
| Deribit API | DVOL、期權 OI、Put/Call（BTC/ETH） |
| Polymarket Gamma API | 預測市場事件定價（創意度亮點） |
| alternative.me | Fear & Greed 恐懼貪婪指數 |
| mempool.space | BTC 鏈上交易量 |
| BscScan (Blockscout) | BNB 鏈上 |
| XRPL 公開節點 | XRP 鏈上 |
| DefiLlama | TVL、穩定幣供給 |
| Google News + 媒體 RSS | 新聞聚合（CoinDesk、Cointelegraph、The Block） |
| 官方部落格 + GitHub RSS | 一手公告 |
| SEC EDGAR | 監管文件全文搜尋 |
| CFTC COT 報告 | 機構期貨淨部位（僅 BTC，每週） |
| Coin Metrics Community | MVRV、活躍地址等機構級指標 |
| GitHub API | 開發活躍度（commit 數、最新 release） |

### 已知的雲端環境限制

| 問題 | 原因 | 影響 | 替代方案 |
|---|---|---|---|
| Binance Futures 回 HTTP 451 | Binance 封鎖 AWS/GCP 雲端 IP 段 | 缺少 Binance 的多空比 | Hyperliquid 提供同等指標 |
| Binance Orderbook 回 HTTP 451 | 同上 | 缺少盤口深度 | 目前無替代，記為覆蓋缺口 |
| 臨時憑證過期 | Session Token 壽命有限 | Bedrock 呼叫失敗 | Demo 前重新取得憑證 |

### `.env` 最小可執行範例

```env
# 最少需要這些才能在本機跑出完整報告
AWS_REGION=us-west-2
AWS_ACCESS_KEY_ID=ASIA...
AWS_SECRET_ACCESS_KEY=...
BEDROCK_MODEL_ID=us.anthropic.claude-sonnet-4-20250514-v1:0

# 本機測試留空，產出寫到 outputs/
DATA_BUCKET=

# 有這四把鑰就能覆蓋大部分資料源
ETHERSCAN_API_KEY=...
HELIUS_API_KEY=...
FRED_API_KEY=...
COINGECKO_API_KEY=...
```

---

## 設計取捨

**為什麼不用 API Gateway** — Function URL 沒有 29 秒逾時限制，而完整分析需要數十秒到數分鐘。

**為什麼不用 Step Functions** — 流程是單一線性路徑，狀態機只增加部署複雜度與失敗面。

**為什麼 Agent 迴圈必定終止** — 受 `MAX_AGENT_TURNS` 與 `TIME_BUDGET_SECONDS` 雙重約束，超出任一條件即停止工具呼叫，以現有證據強制收斂並在信心說明標註缺口。命題只給一次正式執行機會，穩定完成優先於功能豐富。

**為什麼給模型的 toolResult 只有摘要** — 原始資料封存到 S3，只把 summary + evidence_id 回傳給模型，避免 context 膨脹拖慢推理或觸及上限。

**為什麼數值一律由工具計算** — LLM 心算技術指標是 Demo 時最容易被驗證出錯的環節。`compute_quant` 以 pandas 計算並附歷史百分位，模型只負責解讀。

**為什麼前端只讀結構化資料** — 前端不從 Markdown 抽數字、不重算指標，確保畫面與報告不會出現不一致的數值。
