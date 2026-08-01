# report-delivery 實作計畫

## 概覽

以 Python 3.12 將舊固定 `calculate_coverage`／五類覆蓋工作改為題目導向的多維報告、獨立匯出驗證與可追溯交付物。任務只涵蓋程式碼、測試及 repo 內範例輸出。

## 任務

- [x] 1. 完成多維報告核心
  - [x] 1.1 實作決定性的 13 維分類與 canonical provider 正規化
    - 依允許的 capability、結構化 `content_reference`、provider 與工具預設值，以固定優先序選唯一 primary dimension；無法可靠分類時保留 `unclassified`，不得硬歸類。
    - 將同一 provider 的 URL endpoint、hostname／產品別名與結構化 provider 去重，不可解析來源不得虛構。
    - _Requirements: Main R12_

  - [x] 1.2 建立引用衍生的分析摘要、失敗嘗試與相關省略
    - 僅以實際引用 ID 與合法唯一 Evidence Record 的交集產生 Analysis Dimension、Cited Evidence Count、Canonical Independent Source Count 及逐維 evidence/provider 明細。
    - 只保留 `error`／`unavailable`／`timeout` 等已知失敗與明確 Question-Relevant Omission，穩定去重；不得把未使用的 13 維自動列為缺失。
    - 摘要不得產生固定分母、比例、百分比、門檻達成率或 dimension/source score。
    - _Requirements: Main R12, Main R13_

  - [x] 1.3 對齊 C4 報告介面並完成確定性 Markdown 渲染
    - 維持 `render_report(analysis_text, evidence_list, missing_sources, coverage)`，以純離線、相同輸入相同輸出的方式保證市場判斷／關鍵依據／信心說明與附錄。
    - 附錄呈現實際維度、引用證據數、canonical provider 數、逐維明細、失敗嘗試、相關省略及完整 C2 證據表；不得輸出 `x/5`、`x/3`、固定覆蓋百分比或分數。
    - _Requirements: Main R12, Main R13_

- [ ] 2. 完成交付物匯出與品質驗證
  - [x] 2.1 匯出 Evidence Records 為 JSON／CSV，保留 C2 欄位
    - 已從 `lambda/export.py` 與 `tests/test_export.py` 驗證。
    - _Requirements: Main R15_

  - [x] 2.2 依輸入順序匯出逐行可解析的 execution log JSONL
    - 已從 `lambda/export.py` 與 JSONL smoke test 驗證。
    - _Requirements: Main R15_

  - [x] 2.3 隔離 Source Category 匯出門檻並補齊 validator
    - 以獨立 `classify_source_category` 規則檢查唯一 Source Category `>= 3`，並檢查 C2 欄位、孤兒 `evidence_id`、中英文禁語及付費來源唯一依據。
    - `validate_before_export` 只回傳 boolean 與離散 failure reasons；不得把類別門檻、canonical provider 數或任何比例／百分比／分數送入 Report metadata。
    - _Requirements: Main R12, Main R13_

  - [ ] 2.4 在驗證失敗時加入品質警示但仍完成匯出
    - 在最終 `report.md` 開頭插入離散警示原因，仍輸出 `report.md`、`evidence_list.json`、`execution_log.jsonl` 並維持既有 S3 路徑。
    - 維持 C5 body、狀態碼與 CORS，不新增 `validation_warnings` 等回應欄位。
    - _Requirements: Main R13, Main R15_

- [ ] 3. 更新自動化測試
  - [ ]* 3.1 撰寫 Property 1：C4 四參數模板與 Markdown 三章節
    - _Requirements: Main R12_

  - [ ]* 3.2 撰寫 Property 2：完全離線純函式與 byte-for-byte 決定性
    - _Requirements: Main R12_

  - [ ]* 3.3 撰寫 Property 3：13 維分類的決定性、封閉性、唯一性與固定優先序
    - _Requirements: Main R12_

  - [ ]* 3.4 撰寫 Property 4：引用交集、維度與逐維 evidence 明細的摘要忠實性
    - _Requirements: Main R12_

  - [ ]* 3.5 撰寫 Property 5：canonical provider 跨 endpoint／alias 去重
    - _Requirements: Main R12_

  - [ ]* 3.6 撰寫 Property 6：Known Failed Attempt 與 Question-Relevant Omission 精確過濾
    - _Requirements: Main R12, Main R13_

  - [ ]* 3.7 撰寫 Property 7：程式產生的報告 metadata 無固定比例、百分比或分數
    - 保留分析本文中的市場價格變動百分比與技術指標百分位。
    - _Requirements: Main R12, Main R13_

  - [ ]* 3.8 撰寫 Property 8：三來源類別門檻 iff 邊界及 Report 隔離
    - _Requirements: Main R13_

  - [ ]* 3.9 撰寫 Property 9：任一孤兒 evidence 引用使匯出驗證失敗
    - _Requirements: Main R12, Main R13_

  - [ ]* 3.10 撰寫 Property 10：任一禁止投資建議語句使匯出驗證失敗
    - _Requirements: Main R13_

  - [ ]* 3.11 撰寫 Property 11：execution log 每個非空 JSONL 行可解析且順序不變
    - _Requirements: Main R15_

  - [ ]* 3.12 更新 unit／integration／contract tests
    - 涵蓋 13 維代表案例、重複 ID、未引用證據、未知分類、失敗／省略過濾、完整證據表、禁語、孤兒引用、門檻邊界、品質警示、三項 artifacts，以及 C2／C4／C5 契約不變。
    - 移除舊 `calculate_coverage`、固定五類、`4/5`、`80%` 與 dimension score expectations。
    - _Requirements: Main R12, Main R13, Main R15_

- [x] 4. 清理 demo／sample 交付物
  - [x] 4.1 重建 repo 內 `outputs/` 範例並移除舊覆蓋率展示
    - 讓 sample report 顯示實際 13 維子集、引用證據／canonical provider 明細、失敗嘗試與相關省略；移除固定五類、比例、百分比與分數。
    - 保持範例 `report.md`、`evidence_list.json`、`execution_log.jsonl` 互相一致且不包含過期重複 demo artifacts。
    - _Requirements: Main R12, Main R13, Main R15_

- [ ] 5. 最終檢查點
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP.
- Completed items were marked only after verifying the current workspace implementation.
- Property tests use Hypothesis and each property remains a separately executable task.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "2.3"] },
    { "id": 1, "tasks": ["1.2", "2.4"] },
    { "id": 2, "tasks": ["1.3"] },
    { "id": 3, "tasks": ["3.1", "3.8"] },
    { "id": 4, "tasks": ["3.2", "3.9"] },
    { "id": 5, "tasks": ["3.3", "3.10"] },
    { "id": 6, "tasks": ["3.4", "3.11"] },
    { "id": 7, "tasks": ["3.5"] },
    { "id": 8, "tasks": ["3.6"] },
    { "id": 9, "tasks": ["3.7"] },
    { "id": 10, "tasks": ["3.12"] },
    { "id": 11, "tasks": ["4.1"] }
  ]
}
```

## 管線與呈現規劃增補(docs/pipeline-presentation-plan.md 4.1)
- [ ] 12. build_report_data():組裝 C7 JSON(verdict/dimensions/signals/series/coverage/watchlist + 題型專屬區塊)
- [ ] 13. md 模板增補:五維度 emoji 狀態表;comparison 並排表;hypothesis 支持/反對雙欄段
- [ ] 14. 一致性檢查:report_data 與 report.md 的結論/信心/訊號數量一致(單元測試)
- [ ] 15. 降級:build_report_data 失敗時回傳 None 並記 log,不阻斷匯出


- [ ] 16. C7 驗證與輸出:接 core validator、驗證 evidence 外鍵/series/題型條件,成功保存 report_data.json 並附於 C5
- [ ] 17. 三題型與降級測試:golden fixtures、C7/Markdown 一致性、coverage null/59/60 邊界、builder/validator/storage 失敗仍交付原三檔
