# core-infrastructure 需求

範圍:lambda/config.py、lambda/evidence.py、lambda/storage.py。
需求編號引用主 spec(crypto-market-agent/requirements.md)。

## 承接的主 spec 需求
- **R4 證據記錄與可回溯性**(全部):四欄位 Evidence Record、related_claim 必填驗證、evidence_id 唯一、原始回應封存 S3
- **R5 執行紀錄**(全部):成功與失敗都記錄,JSONL 輸出
- **R2.6**:reset_stores 清除容器殘留狀態
- **R18 S3 資料儲存**(全部):baseline 讀取、runs/{run_id}/ 歸檔、presigned URL(預設 1 小時)
- **R19 環境配置**(全部):環境變數集中管理、.env 本機載入、機密不入碼

## 本模組補充驗收條件
1. WHEN 其他模組 import 本模組,THE 模組 SHALL 不觸發任何網路呼叫(import 副作用為零)
2. WHEN 本機執行(無 S3 環境),THE storage SHALL 自動 fallback 至 data/baseline/ 與 outputs/,呼叫端無需改碼
3. THE config SHALL 為所有必要環境變數提供缺漏檢查,啟動時一次性列出缺少的變數名
