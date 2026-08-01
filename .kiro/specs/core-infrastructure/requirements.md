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


## Pipeline Presentation 補充需求

1. THE Core_Infrastructure SHALL 提供無網路副作用的 C7 schema module，集中定義 schema version、required fields、question type、stance、dimension state 與 signal level enums。
2. THE C7 validator SHALL 接受任意 Python value 並回傳結構化 validation errors；一般資料錯誤不得拋出未處理例外。
3. THE validator SHALL 檢查必要欄位、型別、enum、confidence 0–1、題型與 symbols 數量、hypothesis/comparison 條件欄位、evidence_id 外鍵及 series 日期/數值/排序。
4. THE validator SHALL 將未知額外欄位視為向前相容，不得因 extension fields 拒絕整份 C7，除非欄位覆蓋既有語意。
5. THE coverage validator SHALL 允許 pct 為 null 或 0–100，並要求 got/missing 為可追蹤 capability 清單；validator 不得推導固定維度分數。
6. WHEN validator 回報失敗，THE caller SHALL 能安全選擇 Markdown fallback；schema module 本身不得 import report、handler 或 frontend 邏輯以避免循環依賴。
