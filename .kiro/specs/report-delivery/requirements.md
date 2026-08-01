# report-delivery 需求

範圍：`lambda/report.py`、`lambda/export.py`。編號引用主 spec。

## 術語

- **Report_Delivery**：由 `lambda/report.py` 與 `lambda/export.py` 組成的報告渲染、品質驗證及交付物匯出模組。
- **render_report**：遵循既有 C4 Agent → Report 契約的報告渲染函式。
- **validate_before_export**：交付物匯出前執行品質檢查的函式。
- **Export_Flow**：在品質檢查後產出並儲存交付物的流程。
- **Report**：`render_report` 產出的 Markdown 分析報告。
- **Analysis_Dimension**：為回答分析題目而實際完成並用於 Report 推理的分析面向。
- **Cited_Evidence_Count**：Report 透過 `evidence_id` 實際引用的有效 Evidence Record 數量。
- **Canonical_Independent_Source**：將同一資料提供者的 URL、端點或名稱別名正規化後，以資料提供者為單位識別的獨立來源。
- **Canonical_Independent_Source_Count**：Report 實際引用的 Canonical_Independent_Source 數量；同一資料提供者僅計數一次。
- **Source_Category**：價格、技術指標、鏈上、新聞、情緒或總體經濟等證據來源類型，用於匯出驗證門檻。
- **Question_Relevant_Omission**：與分析題目相關，但未取得、未執行或執行失敗的分析面向。
- **Known_Failed_Attempt**：執行紀錄中已嘗試但無法取得資料或執行失敗的分析面向及其狀態。
- **Evidence_Record**：遵循既有 C2 Evidence API 契約的證據紀錄。
- **HTTP_Response**：遵循既有 C5 Handler HTTP 回應契約的回應。

## 承接的主 spec 需求

- **R12 分析報告產出（全部）**：三章節模板保證、`evidence_id` 引用、已知限制、實際分析維度與證據來源附錄、Markdown、三層結構
- **R13 分析內容品質約束（全部）**：禁投資建議語句、跨維度一致或背離訊號、Question_Relevant_Omission、交付前自我檢查、僅供匯出驗證的 Source_Category ≥ 3 門檻
- **R15 交付物匯出與儲存（全部）**：`report.md` / `evidence_list.json` / `execution_log.jsonl`、S3 歸檔、presigned URL、回應含報告原文

## 本模組補充驗收條件

1. THE `render_report` SHALL 維持 `(analysis_text, evidence_list, missing_sources, coverage)` 輸入及 Markdown 輸出的既有 C4 Agent → Report 契約。
2. THE `render_report` SHALL 僅依輸入值產出 Report，並在完全離線環境中對相同輸入產出相同結果。
3. WHEN `render_report` 產出 Report，THE Report SHALL 在附錄列出實際使用的 Analysis_Dimension。
4. WHEN `render_report` 產出 Report，THE Report SHALL 在附錄列出 Cited_Evidence_Count。
5. WHEN `render_report` 產出 Report，THE Report SHALL 在附錄列出 Canonical_Independent_Source_Count。
6. WHEN `render_report` 產出 Report，THE Report SHALL 在附錄按 Analysis_Dimension 列出對應的 `evidence_id` 與 Canonical_Independent_Source 明細。
7. WHEN 執行資料包含 Known_Failed_Attempt，THE Report SHALL 在附錄列出對應的分析面向與失敗或無法取得狀態。
8. WHEN 分析面向未取得、未執行或執行失敗，THE Report SHALL 僅將符合 Question_Relevant_Omission 定義的項目列為缺失項目。
9. THE Report SHALL 排除固定 `x/5` 比率、固定類別分母的百分比、固定類別覆蓋百分比及 Analysis_Dimension 分數。
10. THE `render_report` SHALL 將 `coverage` 解讀為實際 Analysis_Dimension、Cited_Evidence_Count、Canonical_Independent_Source_Count 及各 Analysis_Dimension 證據與來源明細，不解讀為固定資料覆蓋率或評分。
11. THE `render_report` SHALL 將 `missing_sources` 解讀為 Question_Relevant_Omission 與 Known_Failed_Attempt，不列出與分析題目無關的未使用面向。
12. WHEN Evidence_Record 涵蓋少於 3 個 Source_Category，THE `validate_before_export` SHALL 將匯出驗證列為未通過。
13. THE `validate_before_export` SHALL 僅將 Source_Category ≥ 3 門檻用於匯出驗證，不將 Source_Category 門檻轉換為 Report 的固定分母、覆蓋百分比或 Analysis_Dimension 分數。
14. WHEN Report 引用了不存在的 `evidence_id`，THE `validate_before_export` SHALL 將孤兒引用列為未通過項目。
15. WHEN `validate_before_export` 未通過，THE Export_Flow SHALL 仍產出交付物並於 Report 開頭插入品質警示區塊。
16. THE Report_Delivery SHALL 維持既有 Evidence_Record 欄位、C2 Evidence API 行為及語意。
17. THE Report_Delivery SHALL 維持既有 HTTP_Response 欄位、狀態碼及 CORS 行為。
18. WHEN render_report 顯示證據來源，THE report SHALL 優先渲染新聞原文、FRED 圖表、交易資料頁或區塊瀏覽器等人類可讀連結，API endpoint 僅留在 evidence_list.json（R12.10）
