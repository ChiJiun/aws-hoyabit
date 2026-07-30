# 加密市場分析 AI Agent

2026 雲湧智生：臺灣生成式 AI 應用黑客松競賽｜命題單位：HOYA BIT（禾亞數位科技）

一套針對指定加密貨幣與指定題目，自動蒐集多源資料、產出具備證據支撐與可回溯來源的市場分析報告的 AI Agent 系統。

---

## 系統做什麼

使用者輸入一個幣種（BTC / ETH / SOL / BNB / XRP）與一道分析題目，系統會：

1. 由 LLM 理解題目意圖，自行判斷需要哪些類別的資料
2. 呼叫多個資料工具（價格、新聞、鏈上、情緒），逐一取得證據
3. 每筆證據自動記錄四項可回溯欄位（來源、取得時間、引用內容、對應判斷）
4. 將分析拆為「事實 → 推論 → 結論」三個層次
5. 對資料不足或訊號矛盾之處明確說明限制，不強行給出結論
6. 產出四項交付物：分析報告、證據清單、執行紀錄、原始碼

系統定位為資訊提煉工具，不提供投資建議。

---

## 系統架構

```
┌───────────────────────────────┐
│         使用者瀏覽器             │
└───────────────┬───────────────┘
                │ ① 開啟網址，載入頁面
                ▼
┌───────────────────────────────┐
│   S3 靜態網站（前端 bucket）      │
│   frontend/index.html           │
└───────────────┬───────────────┘
                │ ② 送出幣種與題目（fetch POST）
                ▼
┌───────────────────────────────┐
│   Lambda Function URL           │
│   單一 Lambda ＝ Agent 主迴圈    │
└─────┬───────────────────┬───────┘
      │ ③ 推理             │ ④ 讀寫檔案
      ▼                     ▼
┌───────────────┐   ┌───────────────────────┐
│ Amazon Bedrock │   │ Amazon S3（資料 bucket）│
│ Claude 推理     │   │ ・賽方基準 OHLCV CSV    │
└───────────────┘   │ ・原始 API 回應封存      │
      │              │ ・報告／證據清單／日誌    │
      │              └───────────────────────┘
      │ ⑤ 依 Agent 判斷呼叫外部資料 API
      ▼
┌───────────────────────────────┐
│  外部資料來源（見下方清單）       │
└───────────────────────────────┘

⑥ 執行完畢 → 回傳報告內文與下載連結給前端顯示
```

刻意採單一 Lambda 設計，不使用 API Gateway（避免 29 秒逾時限制）與 Step Functions（流程為單一線性路徑，無需狀態機）。

---

## 專案結構

```
crypto-market-agent/
├── README.md                  本檔案
├── requirements.txt           Python 套件清單
├── .gitignore                 排除機密與建置產物
├── .env.example               環境變數範例（不含真實金鑰）
│
├── lambda/                    部署到 AWS Lambda 的程式碼
│   ├── config.py              環境變數與常數集中管理
│   ├── handler.py             Lambda 進入點
│   ├── agent.py               Agent 主迴圈與工具規格
│   ├── evidence.py            四欄位證據記錄
│   ├── report.py              報告渲染
│   ├── export.py              交付物匯出
│   ├── storage.py             S3 讀寫與下載連結
│   └── tools/                 Agent 可呼叫的資料工具
│       ├── price.py           價格與 OHLCV
│       ├── news.py            新聞與官方公告
│       ├── onchain.py         鏈上資料（依幣種分派）
│       ├── quant.py           技術指標計算
│       ├── sentiment.py       市場情緒指數
│       └── macro.py           總體經濟指標
│
├── frontend/
│   └── index.html             輸入介面與報告顯示（上傳到前端 bucket）
│
├── data/baseline/             賽方基準 CSV（本機測試用）
└── outputs/sample_run/        範例輸出，供評審快速檢視格式
```

---

## 環境需求

- Python 3.12
- AWS 帳號，且已於 Bedrock「Model access」頁面開通所需模型
- AWS CLI 已完成 `aws configure`

---

## 本機執行

```bash
# 1. 建立虛擬環境並安裝套件
python -m venv .venv
source .venv/bin/activate        # Windows 使用 .venv\Scripts\activate
pip install -r requirements.txt

# 2. 設定環境變數
cp .env.example .env
# 編輯 .env，填入真實的 API 金鑰與 bucket 名稱

# 3. 將賽方提供的 CSV 放進 data/baseline/

# 4. 執行
python lambda/handler.py
```

本機執行會直接把報告、證據清單、執行紀錄輸出到 `outputs/` 資料夾。

---

## AWS 部署

### 一次性資源建立

1. 建立資料 bucket，上傳基準 CSV 至 `baseline/` 路徑
2. 建立前端 bucket，開啟 Static website hosting，設定公開讀取
3. 建立 Lambda 專用 IAM Role，附加以下權限：
   - `bedrock:InvokeModel`
   - `s3:GetObject`、`s3:PutObject`（限定於資料 bucket）
   - Lambda 基本執行權限（CloudWatch Logs）
4. 建立 Lambda function，套用上述 Role，開啟 Function URL 並設定 CORS
5. 於 Lambda 環境變數填入 `.env.example` 所列的各項變數

pandas 與 numpy 不在 Lambda 內建環境中，需以 Lambda Layer 或容器映像方式提供。

### 部署程式碼

```bash
# 打包 lambda 資料夾
cd lambda
pip install -r ../requirements.txt -t .
zip -r ../function.zip .
cd ..

# 更新 Lambda
aws lambda update-function-code \
  --function-name crypto-market-agent \
  --zip-file fileb://function.zip
```

### 部署前端與資料

```bash
aws s3 cp frontend/index.html s3://你的前端bucket/index.html
aws s3 sync data/baseline/ s3://你的資料bucket/baseline/
```

---

## 交付物

系統每次執行會於 S3 產生以下四項，對應命題要求：

| 交付物 | 檔案 | 內容 |
|---|---|---|
| 分析報告 | `report.md` | 市場判斷、關鍵依據、信心說明（含已知限制） |
| 證據清單 | `evidence_list.json` | 每筆證據含 source、fetched_at、content_reference、related_claim |
| 執行紀錄 | `execution_log.jsonl` | 時間戳記、工具呼叫、資料取得紀錄、流程摘要 |
| 原始碼與配置 | 本 repo | 完整程式碼、設定檔與執行說明 |

---

## 資料來源

| 類別 | 來源 | 需要金鑰 |
|---|---|---|
| 基準價格 | 賽方提供 OHLCV CSV | — |
| 即時價格 | CoinGecko、Binance 公開 API | CoinGecko 需要 |
| 新聞與公告 | CryptoPanic、各專案官方部落格與 GitHub releases | CryptoPanic 需要 |
| 鏈上 BTC | mempool.space | 不需要 |
| 鏈上 ETH | Etherscan API V2 | 需要 |
| 鏈上 BNB | Blockscout | 不需要 |
| 鏈上 SOL | Helius | 需要 |
| 鏈上 XRP | XRPL 公開節點 | 不需要 |
| 市場情緒 | alternative.me Fear & Greed Index | 不需要 |
| 總體經濟 | FRED | 需要 |

付費或商業資料來源若有使用，會於報告與證據清單中揭露，且不作為唯一關鍵依據。

---

## 安全性

- API 金鑰一律透過環境變數讀取，未寫入程式碼
- `.env` 已由 `.gitignore` 排除
- 資料 bucket 不對外公開，交付物透過 S3 presigned URL 提供下載