---
inclusion: always
---

# 技術棧與規範

## 架構(刻意極簡,勿擅自加服務)
- 單一 AWS Lambda(Python 3.12)+ Function URL(免 API Gateway 29 秒限制)
- Amazon Bedrock Converse API(Claude)做推理與工具呼叫;自建 Agent 迴圈,不引入額外 Agent framework
- S3:資料 bucket(baseline CSV、runs/{run_id}/ 產出物,不公開,presigned URL 下載)+ 前端 bucket(靜態網站)
- 前端:單檔 frontend/index.html,marked.js 渲染報告
- 不使用 API Gateway、Step Functions、資料庫 — 若認為需要,先與團隊討論,不要直接加

## 程式規範
- 依賴以 requirements.txt 管理;pandas/numpy 需 Lambda Layer 或容器映像
- 所有機密只從環境變數讀取(本機 .env,已 gitignore);絕不寫死金鑰
- 所有外部 API 呼叫:timeout 必設、失敗回傳 error dict、**絕不拋出未處理例外**(Property 12)
- 工具回傳統一契約(見 steering/contracts.md),違反視同破壞他人模組
- 時間一律 UTC ISO 8601;每次執行以 run_id 隔離
- 給模型的 toolResult 只含 summary + evidence_id,raw 封存 S3,防 context 膨脹

## 時間預算(總限 15 分鐘)
Agent 迴圈受 MAX_AGENT_TURNS 與 TIME_BUDGET_SECONDS 雙重約束;超時即停止工具呼叫、以現有證據強制收斂出報告,並於信心說明標註缺口。

## 資料來源(金鑰需求見 README)
價格:賽方 baseline CSV(至 2026-05-31)+ Binance 補即時 + CoinGecko 備援
新聞:Google News RSS + 媒體 RSS(CoinDesk/Cointelegraph/The Block)+ 官方部落格/GitHub releases(全免費)|鏈上:mempool.space / Etherscan V2 / Blockscout / Helius / XRPL
情緒:alternative.me Fear & Greed|總經:FRED
