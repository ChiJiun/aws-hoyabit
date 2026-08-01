---
inclusion: always
---

# Hoyabit 加密市場分析 AI Agent — Steering Rules

## 專案概要

本專案為「2026 雲湧智生：臺灣生成式 AI 應用黑客松」HOYA BIT 命題參賽作品。系統接收加密貨幣幣種（BTC／ETH／SOL／BNB／XRP）與分析題目，由 AI Agent 自主蒐集多源資料後產出具可回溯證據的結構化市場分析報告。系統為資訊提煉工具，不提供投資建議。

## 技術棧

- 語言：Python 3.12
- 雲端：AWS Lambda (Function URL, 無 API Gateway)、Amazon Bedrock (Claude)、Amazon S3
- 套件：boto3、requests、pandas、numpy、python-dotenv（僅本機開發）
- 前端：單頁 HTML + vanilla JS（marked.js 渲染 Markdown）
- 部署：Lambda zip 打包（scripts/package_lambda.sh）

## 專案結構

```
lambda/                    # 部署到 Lambda 的程式碼（進入點）
├── config.py              # 環境變數與常數集中管理
├── handler.py             # Lambda 進入點 + 本機測試 main()
├── agent.py               # Agent 主迴圈與 Bedrock 呼叫
├── evidence.py            # 四欄位證據記錄
├── report.py              # 報告渲染（保證三章節）
├── export.py              # 交付物匯出 + 自我檢查
├── storage.py             # S3 讀寫 / 本機 fallback
└── tools/                 # 六個資料蒐集工具
    ├── price.py           # OHLCV 價格（基準 CSV + Binance/CoinGecko）
    ├── news.py            # 新聞（CryptoPanic + 官方 RSS/GitHub）
    ├── onchain.py         # 鏈上資料（依幣種分派五種來源）
    ├── quant.py           # 技術指標計算（純本地，無外部 API）
    ├── sentiment.py       # 情緒指數（alternative.me Fear & Greed）
    └── macro.py           # 總經指標（FRED + 排程事件）
frontend/index.html        # 靜態前端
tests/test_local_run.py    # 端到端整合測試
scripts/                   # 部署腳本
```

## 核心設計原則

### 1. 環境變數集中於 config.py
所有 `os.environ` 呼叫只能出現在 `lambda/config.py`，其他模組一律 `from config import X`。新增環境變數時務必同步更新 `.env.example`。

### 2. 工具統一回傳格式
所有 `tools/` 模組的公開函式必須回傳以下結構的 dict：
```python
{
    "raw": ...,               # 原始 API 回應（封存到 S3）
    "source": "...",          # 實際呼叫的 API 網址或來源名稱
    "content_reference": {},  # 引用片段／查詢參數／指標數值／資料區間
    "summary": "..."          # 給模型看的精簡摘要
}
```
失敗時回傳 `{"error": "說明文字", ...}`，永遠不要讓未處理的例外從工具函式逸出。

### 3. related_claim 為所有工具的必填參數
每次工具呼叫都要帶 `related_claim`（由 LLM 填寫），說明這筆資料要用來檢驗什麼判斷。`evidence.log_evidence()` 會拒絕空的 related_claim。

### 4. 四欄位證據記錄
每筆 Evidence Record 必含：
- `source` — 程式自動填（來自 fetch_result）
- `fetched_at` — 程式自動填（ISO 8601 UTC）
- `content_reference` — 程式自動填
- `related_claim` — LLM 提供（必填、不可為空）

### 5. Agent 迴圈必定終止
`run_agent_loop` 受 `MAX_AGENT_TURNS`（預設 8）與 `TIME_BUDGET_SECONDS`（預設 600）雙重限制。超出任一條件必須強制跳出，不可無限迴圈。

### 6. Context 膨脹防護
`dispatch_tool_call` 回傳給模型的 toolResult 只含 `summary` + `evidence_id`，不含完整 `raw` 資料。

### 7. 報告三章節保證
由 `report.render_report()` 的 f-string 模板保證輸出一定包含：
1. 市場判斷
2. 關鍵依據（每條附 evidence_id）
3. 信心說明（含已知限制、資料不足、可能推翻結論的條件）

### 8. 不提供投資建議
系統 prompt 與 `validate_before_export()` 雙重防線：禁止出現「買進」「賣出」「目標價」「建議持有」等語句。

## 編碼慣例

### Python 風格
- 檔案開頭用三引號 docstring 說明模組用途與設計原因
- 函式用 `# 功能：` `# 步驟：` `# 回傳：` 格式的行內註解
- 繁體中文註解（配合團隊語言）
- 不使用 type hints（現有 codebase 風格）
- 變數名用英文、snake_case；常數用 UPPER_SNAKE_CASE
- import 順序：標準庫 → 第三方 → 本地模組

### 錯誤處理
- 工具函式：捕獲所有例外，回傳 error dict
- Agent 迴圈：超時/超輪次時 graceful 退出
- handler.py：外層 try/except 捕獲一切，回傳 500 + CORS 標頭

### 測試
- 測試檔案放在 `tests/` 目錄
- 使用 `python -m tests.test_local_run` 執行
- 遵循 tasks_exeOrderInstruction.md 中的區塊檢查方式

## 外部 API 來源與金鑰

| 來源 | 用途 | 金鑰 |
|------|------|------|
| Binance 公開 API | 即時 OHLCV 補齊 | 不需要 |
| CoinGecko | 備用價格來源 | COINGECKO_API_KEY |
| CryptoPanic | 新聞 | CRYPTOPANIC_API_KEY |
| mempool.space | BTC 鏈上 | 不需要 |
| Etherscan API V2 | ETH 鏈上 | ETHERSCAN_API_KEY |
| Blockscout | BNB 鏈上 | 不需要 |
| Helius | SOL 鏈上 | HELIUS_API_KEY |
| XRPL 公開節點 | XRP 鏈上 | 不需要 |
| alternative.me | 市場情緒 | 不需要 |
| FRED | 總體經濟 | FRED_API_KEY |

## 業務常數

- 支援幣種：`["BTC", "ETH", "SOL", "BNB", "XRP"]`
- 基準資料截止日：`2026-05-31`
- 請求最多允許 2 個幣種（比較分析題型）
- 三種題型：多源整合（1 幣種）、假設驗證（1 幣種）、比較分析（2 幣種）

## 交付物

每次執行在 S3 `runs/{run_id}/` 下產出：
1. `report.md` — Markdown 分析報告
2. `evidence_list.json` — 證據清單（四欄位）
3. `execution_log.jsonl` — 執行紀錄（每行一筆 JSON）
4. `raw/{evidence_id}.json` — 原始 API 回應封存

## 開發流程

### 執行順序
依照 tasks_exeOrderInstruction.md 的七區塊進行：
- 區塊 A：地基（config、evidence、storage）— 無外部依賴
- 區塊 B：六個工具 — 互不依賴，可平行開發
- 區塊 C：Agent 核心 — 依賴區塊 A + 至少 quant/price 完成
- 區塊 D：報告與匯出 — 可與區塊 C 平行
- 區塊 E：Lambda 整合 — 依賴 C + D
- 區塊 F：前端 — 完全獨立
- 區塊 G：部署（最後）

### Git 慣例
- 每個區塊完成後做一次 commit
- Commit 訊息格式：`完成區塊 X：模組名稱`
- 區塊開始前先 commit 當前狀態作為還原點

### 本機測試
```bash
# 啟動虛擬環境
.venv\Scripts\activate

# 執行主程式（本機模式寫入 outputs/）
python lambda/handler.py

# 執行整合測試
python -m tests.test_local_run
```

## 重要提醒

1. **quant.py 所有數字由程式計算**：絕對不可讓 LLM 心算技術指標，這是 Demo 時最容易被評審驗證出錯的地方
2. **onchain.py 五條鏈都要測**：唯一有分支邏輯的工具，容易漏掉某個分支
3. **幣種上限驗證**：parse_request 必須攔截超過 2 個幣種的請求
4. **Lambda 容器重複使用**：每次執行開始必須 `evidence.reset_stores()`
5. **不用 API Gateway**：使用 Function URL 避免 29 秒逾時限制
6. **pandas/numpy 部署**：需用 Lambda Layer 或容器映像
7. **前端 API_URL**：部署後需替換 `index.html` 中的 Function URL 常數
