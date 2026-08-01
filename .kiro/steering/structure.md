---
inclusion: always
---

# 專案結構與模組邊界(分工依據)

## 六個模組(各自對應 .kiro/specs/ 下一個 spec,可平行開發)

| 模組 spec | 擁有的檔案 | 職責 | 依賴 |
|---|---|---|---|
| core-infrastructure | lambda/config.py、evidence.py、storage.py | 設定、證據記錄、執行紀錄、S3 讀寫 | (無,最底層) |
| market-data-tools | lambda/tools/price.py、quant.py | OHLCV 取得拼接、技術指標計算 | core |
| intel-data-tools | lambda/tools/news.py、onchain.py、sentiment.py、macro.py | 新聞/鏈上/情緒/總經 | core |
| agent-orchestrator | lambda/agent.py、handler.py、tests/test_local_run.py | Bedrock 迴圈、工具分派、請求驗證、整合 | core + tools(僅透過工具契約) |
| report-delivery | lambda/report.py、export.py | 報告渲染、交付物匯出、品質驗證 | core |
| frontend-ui | frontend/index.html | 輸入介面、進度顯示、報告渲染 | (僅依賴 handler 的 HTTP 回應契約) |

## 耦合規則(強制)
1. 模組之間**只能**透過 steering/contracts.md 定義的契約互動;改契約 = 全隊同意 + 更新該文件
2. tools/* 彼此不得互相 import;tools 只能 import config、storage,不得 import agent/report/export
3. report.py、export.py 不得呼叫外部 API,只消費 evidence_list 與分析文字
4. frontend 只認 handler 的 JSON 回應格式,不知道後端內部結構
5. 跨模組需求變更:先改 .kiro/specs/crypto-market-agent(主 spec),再同步到子 spec

## Spec 導覽
- `.kiro/specs/crypto-market-agent/`:主 spec,21 條需求的唯一編號來源,勿刪
- 子 spec 的 requirements 一律引用主 spec 編號(如 R6.3),不自行發明新編號
