# report-delivery 需求

範圍:lambda/report.py、lambda/export.py。編號引用主 spec。

## 承接的主 spec 需求
- **R12 分析報告產出**(全部):三章節模板保證、evidence_id 引用、已知限制、資料覆蓋率附錄、Markdown、三層結構
- **R13 分析內容品質約束**(全部):禁投資建議語句、矛盾訊號說明、缺失來源列舉、交付前自我檢查、來源類別 ≥ 3
- **R15 交付物匯出與儲存**(全部):report.md / evidence_list.json / execution_log.jsonl、S3 歸檔、presigned URL、回應含報告原文

## 本模組補充驗收條件
1. THE render_report SHALL 為純函式:輸入(分析文字, evidence_list, missing_sources, coverage)→ 輸出 Markdown,不呼叫任何外部服務(可完全離線測試)
2. WHEN 報告引用了不存在的 evidence_id,THE validate_before_export SHALL 列為未通過項目(孤兒引用)
3. WHEN validate_before_export 未通過,THE 匯出流程 SHALL 仍產出交付物但於報告開頭插入品質警示區塊(15 分鐘賽制下不可因驗證失敗而空手)
4. WHEN render_report 顯示證據來源,THE report SHALL 優先渲染新聞原文、FRED 圖表、交易資料頁或區塊瀏覽器等人類可讀連結,API endpoint 僅留在 evidence_list.json(R12.7)
